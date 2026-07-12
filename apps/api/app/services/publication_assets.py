"""Lazy metadata and cover extraction for local publications.

The library catalog must stay cheap enough to scan tens of thousands of files.
This module enriches only publications the UI actually displays and persists
the result under the application storage directory.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import posixpath
import re
import struct
import threading
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import fitz
from lxml import etree

from .media_library import guess_title


MAX_XML_BYTES = 64 * 1024 * 1024
MAX_COVER_BYTES = 20 * 1024 * 1024
ASSET_CACHE_VERSION = 2

_asset_lock = threading.RLock()

_RASTER_TYPES = {
    ".avif": "image/avif",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _clean_text(value: str | None, *, limit: int = 4000) -> str | None:
    if not value:
        return None
    plain = re.sub(r"<[^>]+>", " ", html.unescape(value))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit] or None


def _local_name(element: etree._Element) -> str:
    if not isinstance(element.tag, str):
        return ""
    return etree.QName(element.tag).localname.lower()


def _elements(root: etree._Element, name: str) -> list[etree._Element]:
    wanted = name.lower()
    return [element for element in root.iter() if _local_name(element) == wanted]


def _first_text(root: etree._Element, name: str) -> str | None:
    for element in _elements(root, name):
        value = _clean_text("".join(element.itertext()))
        if value:
            return value
    return None


def _all_text(root: etree._Element, name: str) -> list[str]:
    values: list[str] = []
    for element in _elements(root, name):
        value = _clean_text("".join(element.itertext()), limit=500)
        if value and value not in values:
            values.append(value)
    return values


def _xml(data: bytes) -> etree._Element:
    parser = etree.XMLParser(
        recover=True,
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    )
    return etree.fromstring(data, parser=parser)


def _safe_zip_read(archive: zipfile.ZipFile, member: str, limit: int) -> bytes:
    normalized = posixpath.normpath(member.replace("\\", "/")).lstrip("/")
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError("Unsafe publication member path")

    names = {name.casefold(): name for name in archive.namelist()}
    actual = names.get(normalized.casefold())
    if not actual:
        raise KeyError(normalized)
    info = archive.getinfo(actual)
    if info.file_size > limit:
        raise ValueError("Publication member exceeds extraction limit")
    return archive.read(actual)


def _resolve_member(base_member: str, href: str) -> str:
    href_path = unquote(urlsplit(href).path)
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(base_member), href_path)
    ).lstrip("/")


def _base_details(path: Path) -> dict[str, Any]:
    title = guess_title(path.name).strip(" '\"")
    author = None
    byline = re.match(r"^(.+?)\s+by\s+(.+)$", title, flags=re.IGNORECASE)
    if byline and len(byline.group(2).split()) >= 2:
        title = byline.group(1).strip(" '\"")
        author = byline.group(2).strip(" '\"") or None
    return {
        "version": ASSET_CACHE_VERSION,
        "title": title or path.name,
        "authors": [author] if author else [],
        "publisher": None,
        "language": None,
        "series": None,
        "series_index": None,
        "description": None,
        "cover_locator": None,
    }


def _epub_details(path: Path) -> dict[str, Any]:
    details = _base_details(path)
    with zipfile.ZipFile(path) as archive:
        container = _xml(
            _safe_zip_read(archive, "META-INF/container.xml", 1024 * 1024)
        )
        rootfiles = _elements(container, "rootfile")
        if not rootfiles:
            return details
        opf_name = rootfiles[0].get("full-path")
        if not opf_name:
            return details
        package = _xml(_safe_zip_read(archive, opf_name, 4 * 1024 * 1024))

        details.update(
            title=_first_text(package, "title") or details["title"],
            authors=_all_text(package, "creator"),
            publisher=_first_text(package, "publisher"),
            language=_first_text(package, "language"),
            description=_first_text(package, "description"),
        )

        manifest: dict[str, dict[str, str]] = {}
        for item in _elements(package, "item"):
            item_id = item.get("id")
            href = item.get("href")
            if item_id and href:
                manifest[item_id] = {
                    "href": href,
                    "media_type": item.get("media-type", ""),
                    "properties": item.get("properties", ""),
                }

        cover_item: dict[str, str] | None = next(
            (
                item
                for item in manifest.values()
                if "cover-image" in item["properties"].split()
            ),
            None,
        )
        if not cover_item:
            for meta in _elements(package, "meta"):
                if meta.get("name", "").lower() == "cover":
                    cover_item = manifest.get(meta.get("content", ""))
                    if cover_item:
                        break
        if not cover_item:
            cover_item = next(
                (
                    item
                    for item_id, item in manifest.items()
                    if item["media_type"].startswith("image/")
                    and "cover" in f"{item_id} {item['href']}".lower()
                ),
                None,
            )

        if cover_item:
            cover_member = _resolve_member(opf_name, cover_item["href"])
            media_type = cover_item["media_type"]
            if media_type in {"application/xhtml+xml", "text/html"}:
                cover_page = _xml(
                    _safe_zip_read(archive, cover_member, 2 * 1024 * 1024)
                )
                image = next(
                    (
                        element
                        for element in cover_page.iter()
                        if _local_name(element) in {"img", "image"}
                    ),
                    None,
                )
                if image is not None:
                    source = image.get("src") or next(
                        (
                            value
                            for key, value in image.attrib.items()
                            if key.endswith("}href") or key == "href"
                        ),
                        None,
                    )
                    if source:
                        cover_member = _resolve_member(cover_member, source)
                        media_type = _RASTER_TYPES.get(
                            Path(urlsplit(source).path).suffix.lower(), ""
                        )

            if media_type in _RASTER_TYPES.values():
                details["cover_locator"] = {
                    "kind": "zip",
                    "member": cover_member,
                    "media_type": media_type,
                }

        for meta in _elements(package, "meta"):
            prop = meta.get("property", "").lower()
            if prop.endswith("belongs-to-collection") and not details["series"]:
                details["series"] = _clean_text("".join(meta.itertext()), limit=500)
            elif prop.endswith("group-position") and not details["series_index"]:
                details["series_index"] = _clean_text(
                    "".join(meta.itertext()), limit=50
                )

    return details


def _natural_name(value: str) -> list[tuple[int, int | str]]:
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
    ]


def _cbz_details(path: Path) -> dict[str, Any]:
    details = _base_details(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        comic_info = next(
            (name for name in names if Path(name).name.casefold() == "comicinfo.xml"),
            None,
        )
        if comic_info:
            root = _xml(_safe_zip_read(archive, comic_info, 2 * 1024 * 1024))
            series = _first_text(root, "series")
            number = _first_text(root, "number")
            details.update(
                title=_first_text(root, "title") or series or details["title"],
                authors=[value for value in [_first_text(root, "writer")] if value],
                publisher=_first_text(root, "publisher"),
                language=_first_text(root, "languageiso"),
                series=series,
                series_index=number,
                description=_first_text(root, "summary"),
            )

        images = sorted(
            (
                name
                for name in names
                if Path(name).suffix.lower() in _RASTER_TYPES
                and "__macosx" not in name.casefold()
            ),
            key=_natural_name,
        )
        if images:
            member = images[0]
            details["cover_locator"] = {
                "kind": "zip",
                "member": member,
                "media_type": _RASTER_TYPES[Path(member).suffix.lower()],
            }
    return details


def _fb2_author(author: etree._Element) -> str | None:
    parts: list[str] = []
    for name in ("first-name", "middle-name", "last-name", "nickname"):
        child = next(
            (item for item in author if _local_name(item) == name),
            None,
        )
        if child is not None:
            value = _clean_text("".join(child.itertext()), limit=200)
            if value:
                parts.append(value)
    return " ".join(parts) or None


def _fb2_details(path: Path) -> dict[str, Any]:
    details = _base_details(path)
    if path.stat().st_size > MAX_XML_BYTES:
        return details
    root = _xml(path.read_bytes())
    title_info = next(iter(_elements(root, "title-info")), root)
    authors = [
        value
        for value in (
            _fb2_author(element) for element in _elements(title_info, "author")
        )
        if value
    ]
    sequence = next(iter(_elements(title_info, "sequence")), None)
    details.update(
        title=_first_text(title_info, "book-title") or details["title"],
        authors=authors,
        publisher=_first_text(root, "publisher"),
        language=_first_text(title_info, "lang"),
        series=sequence.get("name") if sequence is not None else None,
        series_index=sequence.get("number") if sequence is not None else None,
        description=_first_text(title_info, "annotation"),
    )

    coverpage = next(iter(_elements(title_info, "coverpage")), None)
    if coverpage is not None:
        image = next(iter(_elements(coverpage, "image")), None)
        href = None
        if image is not None:
            href = next(
                (
                    value
                    for key, value in image.attrib.items()
                    if key.endswith("}href") or key == "href"
                ),
                None,
            )
        if href:
            binary_id = href.lstrip("#")
            binary = next(
                (
                    element
                    for element in _elements(root, "binary")
                    if element.get("id") == binary_id
                ),
                None,
            )
            media_type = binary.get("content-type", "") if binary is not None else ""
            if media_type in _RASTER_TYPES.values():
                details["cover_locator"] = {
                    "kind": "fb2",
                    "binary_id": binary_id,
                    "media_type": media_type,
                }
    return details


def _mobi_records(path: Path) -> tuple[list[int], bytes]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(78)
        if len(header) < 78:
            raise ValueError("Truncated Palm database")
        count = struct.unpack(">H", header[76:78])[0]
        if count < 1 or count > 100_000:
            raise ValueError("Invalid Palm database record count")
        table = handle.read(count * 8)
        if len(table) != count * 8:
            raise ValueError("Truncated Palm database table")
        offsets = [
            struct.unpack(">I", table[index * 8 : index * 8 + 4])[0]
            for index in range(count)
        ]
        offsets.append(size)
        if offsets != sorted(offsets) or offsets[-2] >= size:
            raise ValueError("Invalid Palm database offsets")
        handle.seek(offsets[0])
        record_zero = handle.read(offsets[1] - offsets[0])
    return offsets, record_zero


def _decode_mobi(value: bytes, encoding: int) -> str | None:
    codec = "utf-8" if encoding == 65001 else "cp1252"
    return _clean_text(value.decode(codec, errors="replace"))


def _mobi_details(path: Path) -> dict[str, Any]:
    details = _base_details(path)
    offsets, record_zero = _mobi_records(path)
    mobi_start = 16
    if record_zero[mobi_start : mobi_start + 4] != b"MOBI":
        return details
    header_length = struct.unpack(">I", record_zero[20:24])[0]
    if header_length < 116 or mobi_start + header_length > len(record_zero):
        return details
    encoding = struct.unpack(">I", record_zero[28:32])[0]
    first_image = struct.unpack(">I", record_zero[mobi_start + 92 : mobi_start + 96])[0]
    exth_start = mobi_start + header_length
    records: dict[int, list[bytes]] = {}
    if record_zero[exth_start : exth_start + 4] == b"EXTH":
        exth_length, count = struct.unpack(">II", record_zero[exth_start + 4 : exth_start + 12])
        end = min(len(record_zero), exth_start + exth_length)
        position = exth_start + 12
        for _ in range(min(count, 10_000)):
            if position + 8 > end:
                break
            record_type, length = struct.unpack(">II", record_zero[position : position + 8])
            if length < 8 or position + length > end:
                break
            records.setdefault(record_type, []).append(
                record_zero[position + 8 : position + length]
            )
            position += length

    def text_record(record_type: int) -> str | None:
        values = records.get(record_type)
        return _decode_mobi(values[0], encoding) if values else None

    authors = [
        value
        for value in (_decode_mobi(raw, encoding) for raw in records.get(100, []))
        if value
    ]
    details.update(
        title=text_record(503) or details["title"],
        authors=authors,
        publisher=text_record(101),
        description=text_record(103),
    )
    cover_offset = records.get(201) or records.get(202)
    if cover_offset and len(cover_offset[0]) >= 4:
        cover_index = first_image + struct.unpack(">I", cover_offset[0][:4])[0]
        if 0 <= cover_index < len(offsets) - 1:
            details["cover_locator"] = {
                "kind": "mobi",
                "record_index": cover_index,
            }
    return details


def _pdf_details(path: Path) -> dict[str, Any]:
    details = _base_details(path)
    with fitz.open(path) as document:
        metadata = document.metadata or {}
        author = _clean_text(metadata.get("author"), limit=500)
        details.update(
            title=_clean_text(metadata.get("title"), limit=500) or details["title"],
            authors=[author] if author else details["authors"],
            publisher=_clean_text(metadata.get("producer"), limit=500),
            description=_clean_text(metadata.get("subject")),
            cover_locator={"kind": "pdf", "page": 0} if document.page_count else None,
        )
    return details


def _extract_details(path: Path) -> dict[str, Any]:
    extension = path.suffix.lower()
    if extension == ".epub":
        return _epub_details(path)
    if extension == ".cbz":
        return _cbz_details(path)
    if extension == ".fb2":
        return _fb2_details(path)
    if extension in {".mobi", ".azw", ".azw3", ".prc"}:
        return _mobi_details(path)
    if extension == ".pdf":
        return _pdf_details(path)
    return _base_details(path)


def _asset_key(path: Path) -> str:
    stat = path.stat()
    identity = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".casefold()
    return hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()


def _asset_dir(path: Path, cache_root: Path) -> Path:
    key = _asset_key(path)
    return cache_root / key[:2] / key


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def get_publication_details(path: Path, cache_root: Path) -> dict[str, Any]:
    """Return cached publication metadata, extracting it on first access."""
    resolved = path.resolve()
    asset_dir = _asset_dir(resolved, cache_root)
    details_file = asset_dir / "details.json"
    with _asset_lock:
        try:
            cached = json.loads(details_file.read_text(encoding="utf-8"))
            if cached.get("version") == ASSET_CACHE_VERSION:
                return cached
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        try:
            details = _extract_details(resolved)
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            struct.error,
            zipfile.BadZipFile,
            etree.XMLSyntaxError,
        ):
            details = _base_details(resolved)
        _write_json(details_file, details)
        return details


def public_publication_details(details: dict[str, Any]) -> dict[str, Any]:
    """Remove internal cover locators from an API-facing details payload."""
    authors = [str(author) for author in details.get("authors", []) if author]
    return {
        "title": details.get("title"),
        "author": ", ".join(authors) or None,
        "authors": authors,
        "publisher": details.get("publisher"),
        "language": details.get("language"),
        "series": details.get("series"),
        "series_index": details.get("series_index"),
        "description": details.get("description"),
        "has_cover": bool(details.get("cover_locator")),
    }


def _detect_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _extract_cover(path: Path, locator: dict[str, Any]) -> tuple[bytes, str] | None:
    kind = locator.get("kind")
    if kind == "zip":
        with zipfile.ZipFile(path) as archive:
            data = _safe_zip_read(archive, locator["member"], MAX_COVER_BYTES)
        media_type = _detect_image_type(data) or locator.get("media_type")
    elif kind == "fb2":
        if path.stat().st_size > MAX_XML_BYTES:
            return None
        root = _xml(path.read_bytes())
        binary = next(
            (
                element
                for element in _elements(root, "binary")
                if element.get("id") == locator.get("binary_id")
            ),
            None,
        )
        if binary is None or not binary.text:
            return None
        data = base64.b64decode(binary.text, validate=False)
        media_type = _detect_image_type(data) or locator.get("media_type")
    elif kind == "mobi":
        offsets, _ = _mobi_records(path)
        index = int(locator["record_index"])
        if index < 0 or index >= len(offsets) - 1:
            return None
        length = offsets[index + 1] - offsets[index]
        if length > MAX_COVER_BYTES:
            return None
        with path.open("rb") as handle:
            handle.seek(offsets[index])
            data = handle.read(length)
        media_type = _detect_image_type(data)
    elif kind == "pdf":
        with fitz.open(path) as document:
            if document.page_count < 1:
                return None
            page = document.load_page(int(locator.get("page", 0)))
            width = max(1.0, page.rect.width)
            height = max(1.0, page.rect.height)
            scale = min(2.0, 420.0 / width, 680.0 / height)
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=False,
                colorspace=fitz.csRGB,
            )
            data = pixmap.tobytes("jpeg", jpg_quality=84)
        media_type = "image/jpeg"
    else:
        return None

    if not data or len(data) > MAX_COVER_BYTES or media_type not in _RASTER_TYPES.values():
        return None
    return data, media_type


def get_publication_cover(
    path: Path,
    cache_root: Path,
) -> tuple[Path, str, str] | None:
    """Return a cached cover path, media type, and stable ETag."""
    resolved = path.resolve()
    asset_dir = _asset_dir(resolved, cache_root)
    cover_file = asset_dir / "cover.bin"
    cover_info_file = asset_dir / "cover.json"
    no_cover_file = asset_dir / "no-cover"

    with _asset_lock:
        if no_cover_file.exists():
            return None
        try:
            cover_info = json.loads(cover_info_file.read_text(encoding="utf-8"))
            media_type = cover_info["media_type"]
            etag = cover_info["etag"]
            if cover_file.exists():
                return cover_file, media_type, etag
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass

        details = get_publication_details(resolved, cache_root)
        locator = details.get("cover_locator")
        try:
            extracted = _extract_cover(resolved, locator) if locator else None
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            struct.error,
            zipfile.BadZipFile,
            etree.XMLSyntaxError,
        ):
            extracted = None
        if not extracted:
            no_cover_file.parent.mkdir(parents=True, exist_ok=True)
            no_cover_file.write_text("", encoding="utf-8")
            return None

        data, media_type = extracted
        etag = hashlib.sha256(data).hexdigest()
        _write_bytes(cover_file, data)
        _write_json(cover_info_file, {"media_type": media_type, "etag": etag})
        return cover_file, media_type, etag

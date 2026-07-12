"""Publication metadata and cover extraction tests."""

from __future__ import annotations

import base64
import struct
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.services.publication_assets import (
    get_publication_cover,
    get_publication_details,
    public_publication_details,
)


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


def write_epub(path: Path) -> None:
    container = """<?xml version="1.0"?>
    <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles><rootfile full-path="OEBPS/book.opf" /></rootfiles>
    </container>"""
    package = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>The Lantern Archive</dc:title>
        <dc:creator>Ada Vale</dc:creator>
        <dc:publisher>Moon House</dc:publisher>
        <dc:language>en</dc:language>
      </metadata>
      <manifest>
        <item id="cover" href="images/cover.png" media-type="image/png"
              properties="cover-image" />
      </manifest>
    </package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/book.opf", package)
        archive.writestr("OEBPS/images/cover.png", TINY_PNG)


def write_mobi(path: Path) -> None:
    def exth_record(record_type: int, payload: bytes) -> bytes:
        return struct.pack(">II", record_type, len(payload) + 8) + payload

    exth_records = b"".join(
        [
            exth_record(503, b"The River Index"),
            exth_record(100, b"Mara Reed"),
            exth_record(201, struct.pack(">I", 0)),
        ]
    )
    exth = b"EXTH" + struct.pack(">II", len(exth_records) + 12, 3) + exth_records
    record_zero = bytearray(16 + 232)
    record_zero[16:20] = b"MOBI"
    struct.pack_into(">I", record_zero, 20, 232)
    struct.pack_into(">I", record_zero, 28, 65001)
    struct.pack_into(">I", record_zero, 16 + 92, 1)
    record_zero.extend(exth)

    cover = b"\xff\xd8\xff\xe0" + b"cover-data" + b"\xff\xd9"
    record_count = 2
    first_offset = 78 + record_count * 8
    second_offset = first_offset + len(record_zero)
    header = bytearray(78)
    struct.pack_into(">H", header, 76, record_count)
    table = (
        struct.pack(">I", first_offset)
        + b"\x00\x00\x00\x01"
        + struct.pack(">I", second_offset)
        + b"\x00\x00\x00\x02"
    )
    path.write_bytes(bytes(header) + table + bytes(record_zero) + cover)


def test_epub_metadata_and_cover_are_persistently_cached(tmp_path: Path):
    publication = tmp_path / "messy-file-name.epub"
    cache = tmp_path / "cache"
    write_epub(publication)

    details = get_publication_details(publication, cache)
    public = public_publication_details(details)
    cover = get_publication_cover(publication, cache)

    assert public["title"] == "The Lantern Archive"
    assert public["author"] == "Ada Vale"
    assert public["publisher"] == "Moon House"
    assert public["has_cover"] is True
    assert cover is not None
    assert cover[0].read_bytes() == TINY_PNG
    assert cover[1] == "image/png"

    with patch(
        "app.services.publication_assets._extract_details",
        side_effect=AssertionError("cache miss"),
    ):
        assert get_publication_details(publication, cache)["title"] == "The Lantern Archive"


def test_mobi_exth_metadata_and_cover_are_extracted(tmp_path: Path):
    publication = tmp_path / "river.azw3"
    write_mobi(publication)

    details = public_publication_details(
        get_publication_details(publication, tmp_path / "cache")
    )
    cover = get_publication_cover(publication, tmp_path / "cache")

    assert details["title"] == "The River Index"
    assert details["author"] == "Mara Reed"
    assert cover is not None
    assert cover[1] == "image/jpeg"


def test_pdf_first_page_becomes_cover(tmp_path: Path):
    publication = tmp_path / "Fallback Title by Fallback Author.pdf"
    document = fitz.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((72, 120), "THE WINTER CATALOG", fontsize=24)
    document.set_metadata({"title": "The Winter Catalog", "author": "Noor Bell"})
    document.save(publication)
    document.close()

    details = public_publication_details(
        get_publication_details(publication, tmp_path / "cache")
    )
    cover = get_publication_cover(publication, tmp_path / "cache")

    assert details["title"] == "The Winter Catalog"
    assert details["author"] == "Noor Bell"
    assert cover is not None
    assert cover[1] == "image/jpeg"
    assert cover[0].read_bytes().startswith(b"\xff\xd8\xff")


def test_filename_byline_is_used_when_embedded_metadata_is_absent(tmp_path: Path):
    publication = tmp_path / "A Cultural Anatomy by Ruth Barcan.txt"
    publication.write_text("sample", encoding="utf-8")

    details = public_publication_details(
        get_publication_details(publication, tmp_path / "cache")
    )

    assert details["title"] == "A Cultural Anatomy"
    assert details["author"] == "Ruth Barcan"
    assert details["has_cover"] is False

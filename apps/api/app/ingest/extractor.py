"""Extract text and structure from supported publication formats."""
from __future__ import annotations
import re
import io
import tempfile
import os
import shutil
from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path

import mobi
from pypdf import PdfReader
from ebooklib import epub
from bs4 import BeautifulSoup
from lxml import etree


@dataclass
class ExtractedSection:
    """A section (chapter, poem, essay) extracted from a book."""
    title: str | None
    section_type: str  # chapter, poem, essay, part, introduction, etc.
    order_index: int
    text: str
    char_start: int  # absolute position in full text
    char_end: int
    page_start: int | None = None  # for PDFs
    page_end: int | None = None


@dataclass
class ExtractedBook:
    """Result of extracting a book."""
    title: str
    author: str | None
    file_type: Literal["pdf", "epub", "txt", "fb2", "mobi", "azw", "azw3", "prc"]
    full_text: str
    sections: list[ExtractedSection]
    metadata: dict = field(default_factory=dict)


# Common chapter heading patterns
CHAPTER_PATTERNS = [
    r"^(Chapter|CHAPTER)\s+(\d+|[IVXLC]+)[\s:.\-]*(.*)$",
    r"^(Part|PART)\s+(\d+|[IVXLC]+)[\s:.\-]*(.*)$",
    r"^(\d+)\.\s+(.+)$",  # "1. Title"
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})[.:\-]+\s*(.+)$",
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})$",
]


def _detect_sections_from_text(text: str, file_type: str) -> list[tuple[int, str | None, str]]:
    """
    Detect section boundaries from plain text using heuristics.
    Returns list of (char_position, title, section_type).
    """
    sections = []
    lines = text.split("\n")
    char_pos = 0

    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) <= 180:
            for pattern in CHAPTER_PATTERNS:
                match = re.match(pattern, stripped)
                if match:
                    # Build title from matched groups
                    groups = [g for g in match.groups() if g]
                    title = " ".join(groups).strip()
                    section_type = "chapter"
                    if "part" in stripped.lower():
                        section_type = "part"
                    sections.append((char_pos, title, section_type))
                    break
        char_pos += len(line) + 1  # +1 for newline

    return sections


def extract_pdf(file_data: bytes, filename: str) -> ExtractedBook:
    """Extract text and structure from a PDF file."""
    reader = PdfReader(io.BytesIO(file_data))

    # Extract metadata
    meta = reader.metadata or {}
    title = meta.get("/Title") or filename.rsplit(".", 1)[0]
    author = meta.get("/Author")

    # Extract text page by page, tracking positions
    full_text_parts = []
    page_char_positions = []  # (page_num, char_start, char_end)
    current_pos = 0

    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        start_pos = current_pos
        full_text_parts.append(page_text)
        current_pos += len(page_text)
        if page_text:
            full_text_parts.append("\n\n")
            current_pos += 2
        page_char_positions.append((page_num + 1, start_pos, current_pos))

    full_text = "".join(full_text_parts)

    # Detect sections
    detected = _detect_sections_from_text(full_text, "pdf")

    # Build sections with page references
    sections = []
    for i, (char_start, sec_title, sec_type) in enumerate(detected):
        # Find end position (start of next section or end of text)
        char_end = detected[i + 1][0] if i + 1 < len(detected) else len(full_text)

        # Find page numbers for this section
        page_start = None
        page_end = None
        for page_num, pstart, pend in page_char_positions:
            if pstart <= char_start < pend and page_start is None:
                page_start = page_num
            if pstart < char_end <= pend:
                page_end = page_num

        sections.append(
            ExtractedSection(
                title=sec_title,
                section_type=sec_type,
                order_index=i,
                text=full_text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                page_start=page_start,
                page_end=page_end,
            )
        )

    # If no sections detected, create one section for the whole book
    if not sections:
        sections.append(
            ExtractedSection(
                title="Full Text",
                section_type="book",
                order_index=0,
                text=full_text,
                char_start=0,
                char_end=len(full_text),
                page_start=1,
                page_end=len(reader.pages),
            )
        )

    return ExtractedBook(
        title=str(title),
        author=str(author) if author else None,
        file_type="pdf",
        full_text=full_text,
        sections=sections,
        metadata={"page_count": len(reader.pages)},
    )


def extract_epub(file_data: bytes, filename: str) -> ExtractedBook:
    """Extract text and structure from an EPUB file."""
    # ebooklib doesn't work well with BytesIO, so use a temp file
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        book = epub.read_epub(tmp_path)
    finally:
        os.unlink(tmp_path)  # Clean up temp file

    # Extract metadata
    title = filename.rsplit(".", 1)[0]
    author = None

    title_meta = book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]

    author_meta = book.get_metadata("DC", "creator")
    if author_meta:
        author = author_meta[0][0]

    # Get TOC for section titles if available
    toc_titles = {}
    def extract_toc(items):
        if items is None:
            return
        # Handle single item (not a list)
        if not isinstance(items, (list, tuple)):
            items = [items]
        for item in items:
            try:
                if isinstance(item, tuple):
                    section, children = item
                    if hasattr(section, 'href') and hasattr(section, 'title'):
                        toc_titles[section.href.split("#")[0]] = section.title
                    extract_toc(children)
                elif hasattr(item, 'href') and hasattr(item, 'title'):
                    toc_titles[item.href.split("#")[0]] = item.title
            except (AttributeError, TypeError):
                continue  # Skip malformed TOC entries

    try:
        extract_toc(book.toc)
    except Exception:
        pass  # TOC extraction is optional, continue without it

    # Extract text from spine items
    full_text_parts = []
    sections = []
    current_pos = 0

    for i, item in enumerate(book.get_items_of_type(9)):  # ITEM_DOCUMENT
        if not item.get_content():
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "head"]):
            tag.decompose()

        # Get text
        text = soup.get_text(separator="\n", strip=True)
        if not text.strip():
            continue

        char_start = current_pos
        full_text_parts.append(text)
        full_text_parts.append("\n\n")
        current_pos += len(text) + 2

        # Try to get section title from TOC or heading
        sec_title = toc_titles.get(item.file_name)
        if not sec_title:
            # Try to find heading in content
            heading = soup.find(["h1", "h2", "h3"])
            if heading:
                sec_title = heading.get_text(strip=True)

        # Determine section type
        sec_type = "chapter"
        if sec_title:
            lower_title = sec_title.lower()
            if "introduction" in lower_title or "preface" in lower_title:
                sec_type = "introduction"
            elif "part" in lower_title:
                sec_type = "part"
            elif "epilogue" in lower_title:
                sec_type = "epilogue"
            elif "poem" in lower_title or "verse" in lower_title:
                sec_type = "poem"

        sections.append(
            ExtractedSection(
                title=sec_title or f"Section {i + 1}",
                section_type=sec_type,
                order_index=len(sections),
                text=text,
                char_start=char_start,
                char_end=current_pos - 2,  # exclude trailing newlines
            )
        )

    full_text = "".join(full_text_parts)

    # If no sections, create one for whole book
    if not sections:
        sections.append(
            ExtractedSection(
                title="Full Text",
                section_type="book",
                order_index=0,
                text=full_text,
                char_start=0,
                char_end=len(full_text),
            )
        )

    return ExtractedBook(
        title=title,
        author=author,
        file_type="epub",
        full_text=full_text,
        sections=sections,
        metadata={"section_count": len(sections)},
    )


def extract_txt(file_data: bytes, filename: str) -> ExtractedBook:
    """Extract text and structure from a plain text file."""
    # Decode the text, trying common encodings
    text = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            text = file_data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        text = file_data.decode("utf-8", errors="replace")

    # Clean up text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    title = filename.rsplit(".", 1)[0]

    # Detect sections using the same heuristics
    detected = _detect_sections_from_text(text, "txt")

    sections = []
    if detected:
        for i, (char_start, sec_title, sec_type) in enumerate(detected):
            char_end = detected[i + 1][0] if i + 1 < len(detected) else len(text)
            sections.append(
                ExtractedSection(
                    title=sec_title,
                    section_type=sec_type,
                    order_index=i,
                    text=text[char_start:char_end],
                    char_start=char_start,
                    char_end=char_end,
                )
            )

    # If no sections detected, split by double newlines or create one section
    if not sections:
        # Try to split on double newlines for natural paragraph breaks
        paragraphs = re.split(r"\n\n\n+", text)
        if len(paragraphs) > 1 and len(paragraphs) <= 50:
            current_pos = 0
            for i, para in enumerate(paragraphs):
                if para.strip():
                    char_start = text.find(para, current_pos)
                    char_end = char_start + len(para)
                    # Use first line as title (truncated)
                    first_line = para.strip().split("\n")[0][:80]
                    sections.append(
                        ExtractedSection(
                            title=f"Section {i + 1}: {first_line}...",
                            section_type="section",
                            order_index=len(sections),
                            text=para,
                            char_start=char_start,
                            char_end=char_end,
                        )
                    )
                    current_pos = char_end
        else:
            # Just create one section for the whole text
            sections.append(
                ExtractedSection(
                    title="Full Text",
                    section_type="book",
                    order_index=0,
                    text=text,
                    char_start=0,
                    char_end=len(text),
                )
            )

    return ExtractedBook(
        title=title,
        author=None,
        file_type="txt",
        full_text=text,
        sections=sections,
        metadata={"char_count": len(text)},
    )


def _xml_local_name(element: etree._Element) -> str:
    if not isinstance(element.tag, str):
        return ""
    return etree.QName(element.tag).localname.lower()


def _xml_elements(root: etree._Element, name: str) -> list[etree._Element]:
    wanted = name.lower()
    return [element for element in root.iter() if _xml_local_name(element) == wanted]


def _xml_text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    text = re.sub(r"\s+", " ", " ".join(element.itertext())).strip()
    return text or None


def _fb2_author(element: etree._Element) -> str | None:
    parts: list[str] = []
    for field_name in ("first-name", "middle-name", "last-name", "nickname"):
        child = next(
            (child for child in element if _xml_local_name(child) == field_name),
            None,
        )
        value = _xml_text(child)
        if value:
            parts.append(value)
    return " ".join(parts) or None


def extract_fb2(file_data: bytes, filename: str) -> ExtractedBook:
    """Extract metadata and top-level reading sections from FictionBook XML."""
    parser = etree.XMLParser(
        recover=True,
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    )
    root = etree.fromstring(file_data, parser=parser)
    title_info = next(iter(_xml_elements(root, "title-info")), None)
    title = (
        _xml_text(next(iter(_xml_elements(title_info, "book-title")), None))
        if title_info is not None
        else None
    ) or filename.rsplit(".", 1)[0]
    authors = (
        [
            author
            for author in (
                _fb2_author(element)
                for element in _xml_elements(title_info, "author")
            )
            if author
        ]
        if title_info is not None
        else []
    )

    sections: list[ExtractedSection] = []
    full_text_parts: list[str] = []
    current_pos = 0
    for body_index, body in enumerate(_xml_elements(root, "body")):
        body_sections = [
            child for child in body if _xml_local_name(child) == "section"
        ] or [body]
        body_name = body.get("name")
        for section in body_sections:
            title_element = next(
                (child for child in section if _xml_local_name(child) == "title"),
                None,
            )
            section_title = _xml_text(title_element)
            lines = [
                value
                for value in (
                    _xml_text(element)
                    for element in section.iter()
                    if _xml_local_name(element)
                    in {"p", "v", "subtitle", "text-author"}
                )
                if value
            ]
            text = "\n\n".join(lines).strip()
            if not text:
                continue
            char_start = current_pos
            full_text_parts.extend([text, "\n\n"])
            current_pos += len(text) + 2
            sections.append(
                ExtractedSection(
                    title=section_title or body_name or f"Section {len(sections) + 1}",
                    section_type="notes" if body_name == "notes" else "chapter",
                    order_index=len(sections),
                    text=text,
                    char_start=char_start,
                    char_end=char_start + len(text),
                )
            )

    full_text = "".join(full_text_parts)
    if not sections or not full_text.strip():
        raise ValueError(f"No readable text found in {filename}")

    language = (
        _xml_text(next(iter(_xml_elements(title_info, "lang")), None))
        if title_info is not None
        else None
    )
    return ExtractedBook(
        title=title,
        author=", ".join(authors) or None,
        file_type="fb2",
        full_text=full_text,
        sections=sections,
        metadata={
            "section_count": len(sections),
            "language": language,
            "source_format": "fb2",
        },
    )


def _unpacked_metadata(directory: Path) -> dict[str, str]:
    for opf_path in directory.rglob("*.opf"):
        try:
            if opf_path.stat().st_size > 4 * 1024 * 1024:
                continue
            parser = etree.XMLParser(
                recover=True,
                resolve_entities=False,
                no_network=True,
                huge_tree=False,
            )
            root = etree.fromstring(opf_path.read_bytes(), parser=parser)
            title = _xml_text(next(iter(_xml_elements(root, "title")), None))
            creator = _xml_text(next(iter(_xml_elements(root, "creator")), None))
            return {
                key: value
                for key, value in {"title": title, "author": creator}.items()
                if value
            }
        except (OSError, ValueError, etree.XMLSyntaxError):
            continue
    return {}


def _extract_unpacked_html(
    html_data: bytes,
    *,
    filename: str,
    file_type: Literal["mobi", "azw", "azw3", "prc"],
    metadata: dict[str, str],
) -> ExtractedBook:
    soup = BeautifulSoup(html_data, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError(f"No readable text found in {filename}")

    detected = _detect_sections_from_text(text, file_type)
    sections: list[ExtractedSection] = []
    for index, (char_start, section_title, section_type) in enumerate(detected):
        char_end = detected[index + 1][0] if index + 1 < len(detected) else len(text)
        sections.append(
            ExtractedSection(
                title=section_title,
                section_type=section_type,
                order_index=index,
                text=text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
            )
        )
    if not sections:
        sections.append(
            ExtractedSection(
                title="Full Text",
                section_type="book",
                order_index=0,
                text=text,
                char_start=0,
                char_end=len(text),
            )
        )

    return ExtractedBook(
        title=metadata.get("title") or filename.rsplit(".", 1)[0],
        author=metadata.get("author"),
        file_type=file_type,
        full_text=text,
        sections=sections,
        metadata={
            "section_count": len(sections),
            "source_format": file_type,
            "unpacked_format": "html",
        },
    )


def extract_mobi_family(file_data: bytes, filename: str) -> ExtractedBook:
    """Unpack a DRM-free Mobipocket/KF8 publication and reuse EPUB/PDF parsing."""
    file_type = Path(filename).suffix.lower().lstrip(".")
    if file_type not in {"mobi", "azw", "azw3", "prc"}:
        raise ValueError(f"Unsupported Kindle-family file: {filename}")

    input_path: str | None = None
    unpacked_dir: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_type}", delete=False
        ) as temporary:
            temporary.write(file_data)
            input_path = temporary.name
        unpacked_dir, output_path = mobi.extract(input_path)
        output = Path(output_path)
        metadata = _unpacked_metadata(Path(unpacked_dir))
        output_type = output.suffix.lower()
        if output_type == ".epub":
            extracted = extract_epub(output.read_bytes(), filename)
            extracted.title = metadata.get("title") or extracted.title
            extracted.author = metadata.get("author") or extracted.author
            extracted.file_type = file_type
            extracted.metadata = {
                **extracted.metadata,
                "source_format": file_type,
                "unpacked_format": "epub",
            }
            return extracted
        if output_type == ".pdf":
            extracted = extract_pdf(output.read_bytes(), filename)
            extracted.title = metadata.get("title") or extracted.title
            extracted.author = metadata.get("author") or extracted.author
            extracted.file_type = file_type
            extracted.metadata = {
                **extracted.metadata,
                "source_format": file_type,
                "unpacked_format": "pdf",
            }
            return extracted
        if output_type in {".html", ".htm"}:
            return _extract_unpacked_html(
                output.read_bytes(),
                filename=filename,
                file_type=file_type,
                metadata=metadata,
            )
        raise ValueError(f"Kindle unpacker returned unsupported output: {output_type}")
    except Exception as error:
        raise ValueError(
            f"Could not unpack {filename}. Only DRM-free MOBI/AZW/AZW3/PRC files "
            "can be prepared for discussion."
        ) from error
    finally:
        if input_path:
            try:
                os.unlink(input_path)
            except OSError:
                pass
        if unpacked_dir:
            shutil.rmtree(unpacked_dir, ignore_errors=True)


def extract_text(file_data: bytes, filename: str) -> ExtractedBook:
    """
    Extract text and structure from a supported publication.

    Args:
        file_data: Raw file bytes
        filename: Original filename (used to detect type and as fallback title)

    Returns:
        ExtractedBook with full text, sections, and metadata
    """
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        return extract_pdf(file_data, filename)
    elif lower_name.endswith(".epub"):
        return extract_epub(file_data, filename)
    elif lower_name.endswith(".txt"):
        return extract_txt(file_data, filename)
    elif lower_name.endswith(".fb2"):
        return extract_fb2(file_data, filename)
    elif lower_name.endswith((".mobi", ".azw", ".azw3", ".prc")):
        return extract_mobi_family(file_data, filename)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

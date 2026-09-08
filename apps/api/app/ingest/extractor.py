"""Extract text and structure from PDF and EPUB files."""
from __future__ import annotations
import re
import io
import tempfile
import os
from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path

from pypdf import PdfReader
from ebooklib import epub
from bs4 import BeautifulSoup


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
    file_type: Literal["pdf", "epub", "txt"]
    full_text: str
    sections: list[ExtractedSection]
    metadata: dict = field(default_factory=dict)


# Common chapter heading patterns
CHAPTER_PATTERNS = [
    r"^(Chapter|CHAPTER)\s+(\d+|[IVXLC]+)[\s:.\-]*(.*)$",
    r"^(Part|PART)\s+(\d+|[IVXLC]+)[\s:.\-]*(.*)$",
    r"^(\d+)\.\s+(.+)$",  # "1. Title"
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})[\s:.\-]+(.+)$",  # Roman numerals
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
        if stripped:
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


def extract_text(file_data: bytes, filename: str) -> ExtractedBook:
    """
    Extract text and structure from a PDF, EPUB, or TXT file.

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
    else:
        raise ValueError(f"Unsupported file type: {filename}")

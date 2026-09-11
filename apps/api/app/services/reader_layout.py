"""Verified typography over an immutable reading edition.

Layout is derived metadata. Recovering it never edits chunks, citations,
conversation, the reading edition hash, or saved page positions.
"""
from bisect import bisect_right
from collections import OrderedDict
import io
import os
from pathlib import Path
import time
from threading import Lock
from typing import Literal
import zipfile

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from ..db.models import Book
from ..settings import settings
from .reader_text import ReadingText, assemble_reading_text

VERSION = 1
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
# Failed recovery costs no more than one parse per five minutes for an unchanged
# source/edition. Successful layout lives with the book, not in this cache.
_failures: OrderedDict[tuple, float] = OrderedDict()
_failures_lock = Lock()


class ReadingMark(BaseModel):
    kind: Literal["emphasis", "strong", "code", "superscript", "subscript", "line_break", "join"]
    char_start: int = Field(ge=0, strict=True)
    char_end: int = Field(ge=1, strict=True)


class ReadingBlock(BaseModel):
    kind: Literal["paragraph", "heading", "quote", "list_item", "preformatted"]
    char_start: int = Field(ge=0, strict=True)
    char_end: int = Field(ge=1, strict=True)
    level: int = Field(default=1, ge=1, le=6)
    list_label: str | None = Field(default=None, max_length=12)
    marks: list[ReadingMark] = Field(default_factory=list)
    continued: bool = False


def build_reading_layout(source_text: str, blocks: list[dict], chunks: list, reading: ReadingText | None = None) -> dict | None:
    """Project exact source coordinates through the overlap assembly map."""
    if not blocks:
        return None
    reading = reading or assemble_reading_text(chunks)
    spans = {span["chunk_id"]: span for span in reading.chunks}
    mappings = []
    for chunk in chunks:
        if not chunk.text:
            continue
        start, end = chunk.char_start, chunk.char_end
        if not 0 <= start < end <= len(source_text):
            return None
        raw = source_text[start:end]
        if raw != chunk.text:
            # Older ingestion stripped whitespace without correcting offsets.
            if raw.strip() != chunk.text:
                return None
            start += len(raw) - len(raw.lstrip())
        span = spans.get(str(chunk.id))
        if span is None or reading.text[span["char_start"]:span["char_end"]] != chunk.text:
            return None
        mappings.append((start, start + len(chunk.text), span["char_start"]))
    if not mappings or mappings != sorted(mappings):
        return None
    starts = [mapping[0] for mapping in mappings]

    def project(position: int):
        index = bisect_right(starts, position) - 1
        if index >= 0:
            start, end, target = mappings[index]
            if start <= position <= end:
                return target + position - start
        return None

    result = []
    for block in blocks:
        start, end = project(block["char_start"]), project(block["char_end"])
        if start is None or end is None or not start < end:
            continue
        if reading.text[start:end] != source_text[block["char_start"]:block["char_end"]]:
            continue
        marks = []
        for mark in block.get("marks", []):
            left, right = project(mark["char_start"]), project(mark["char_end"])
            if (left is not None and right is not None and start <= left < right <= end
                    and reading.text[left:right] == source_text[mark["char_start"]:mark["char_end"]]):
                marks.append({**mark, "char_start": left, "char_end": right})
        result.append({**block, "char_start": start, "char_end": end, "marks": marks})
    if not result:
        return None
    layout = {"version": VERSION, "edition_id": reading.edition_id, "blocks": result}
    return layout if validated_blocks(layout, reading) is not None else None


def cached_blocks(book: Book, reading: ReadingText) -> list[ReadingBlock] | None:
    layout = (book.metadata_json or {}).get("reading_layout")
    return validated_blocks(layout, reading)


def validated_blocks(layout: object, reading: ReadingText) -> list[ReadingBlock] | None:
    if not isinstance(layout, dict) or layout.get("version") != VERSION or layout.get("edition_id") != reading.edition_id:
        return None
    try:
        blocks = TypeAdapter(list[ReadingBlock]).validate_python(layout.get("blocks"))
    except ValidationError:
        return None
    previous = 0
    for block in blocks:
        if not previous <= block.char_start < block.char_end <= len(reading.text):
            return None
        if any(not block.char_start <= mark.char_start < mark.char_end <= block.char_end for mark in block.marks):
            return None
        if any(mark.kind in {"join", "line_break"} and reading.text[mark.char_start:mark.char_end] != "\n" for mark in block.marks):
            return None
        previous = block.char_end
    return blocks


def page_blocks(blocks: list[ReadingBlock], start: int, end: int) -> list[ReadingBlock]:
    result = []
    for block in blocks:
        left, right = max(start, block.char_start), min(end, block.char_end)
        if left >= right:
            continue
        marks = [mark.model_copy(update={"char_start": max(left, mark.char_start), "char_end": min(right, mark.char_end)})
                 for mark in block.marks if mark.char_start < right and mark.char_end > left]
        result.append(block.model_copy(update={"char_start": left, "char_end": right, "marks": marks,
                                               "continued": left > block.char_start,
                                               "list_label": block.list_label if left == block.char_start else None}))
    return result


def _source_path(book: Book) -> Path | None:
    metadata = book.metadata_json or {}
    for key, root in (("stored_path", os.environ.get("STORAGE_DIR", "./storage")), ("source_path", settings.books_dir)):
        value = metadata.get(key)
        if not isinstance(value, str) or not value or not root:
            continue
        try:
            base, path = Path(root).resolve(), Path(value).resolve()
            if path.is_relative_to(base) and path.suffix.lower() == ".epub" and path.is_file():
                return path
        except (OSError, RuntimeError):
            continue
    return None


def book_blocks(db: Session, book: Book, reading: ReadingText, chunks: list) -> list[ReadingBlock]:
    existing = cached_blocks(book, reading)
    if existing is not None:
        return existing
    if book.file_type != "epub":
        return []
    path = _source_path(book)
    if path is None:
        return []
    key = None
    try:
        stat = path.stat()
        if stat.st_size > MAX_SOURCE_BYTES:
            return []
        key = (book.id, reading.edition_id, str(path), stat.st_size, stat.st_mtime_ns)
        with _failures_lock:
            if _failures.get(key, 0) > time.monotonic():
                return []
        with path.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            return []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise ValueError("EPUB exceeds layout recovery limits")
        from ..ingest.extractor import extract_epub
        legacy = (book.metadata_json or {}).get("epub_text_version") != "blocks-v1"
        extracted = extract_epub(data, book.filename, legacy_text=legacy)
        layout = build_reading_layout(extracted.full_text, extracted.blocks, chunks, reading)
        validated = validated_blocks(layout, reading)
        if not validated:
            raise ValueError("The original EPUB no longer matches the saved edition")
        # Preserve metadata written by another tab or a search-index refresh.
        current = db.query(Book).filter(Book.id == book.id).with_for_update().populate_existing().one()
        current.metadata_json = {**(current.metadata_json or {}), "reading_layout": layout}
        db.commit()
        return validated
    except Exception:
        db.rollback()
        if key is not None:
            with _failures_lock:
                _failures[key] = time.monotonic() + 300
                _failures.move_to_end(key)
                while len(_failures) > 32:
                    _failures.popitem(last=False)
        # Formatting recovery must not prevent reading. Never log source paths,
        # original text, or archive exception details.
        return []

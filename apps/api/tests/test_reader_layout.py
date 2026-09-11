"""EPUB typography must preserve source text and existing reading coordinates."""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from ebooklib import epub
import pytest

from app.db.models import Book, BookMemory, Chunk, IngestStatus, Section
from app.ingest.chunker import chunk_text
from app.ingest.epub_text import document_text
from app.ingest.extractor import extract_epub
from app.services import reader_layout
from app.services.reader_text import assemble_reading_text, page_bounds


def epub_bytes(html):
    book = epub.EpubBook()
    book.set_identifier("typography-fixture")
    book.set_title("At the window")
    book.set_language("en")
    chapter = epub.EpubHtml(title="The first morning", file_name="morning.xhtml")
    chapter.content = html
    book.add_item(chapter)
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    output = io.BytesIO()
    epub.write_epub(output, book)
    return output.getvalue()


HTML = '''<h1>The first <em>morning</em></h1>
<p>🕯 She was <em>almost</em> ready. The re<strong>read</strong>ing began.</p>
<p>A second paragraph, with a <a href="https://example.invalid">quiet link</a>.</p>
<blockquote><p>Let the window stay open.</p><p>Let the wind come in.</p></blockquote>
<ol start="3"><li>Listen.</li><li value="7"><p>Wait.</p><p>And wait again.</p></li></ol>
<p>One line.<br/>Another line.<br/>A third.</p>
<pre>  a    b\n    c</pre>
<p>H<sub>2</sub>O and x<sup>2</sup>; <code>hello()</code>.</p>'''


def test_epub_blocks_inline_words_and_inert_marks():
    extracted = extract_epub(epub_bytes(HTML + '<!-- hidden --><script>evil()</script><style>.x{}</style>'), "window.epub")
    assert "The first morning\n\n🕯 She was almost ready. The rereading began.\n\nA second paragraph" in extracted.full_text
    assert "hidden" not in extracted.full_text and "evil()" not in extracted.full_text
    assert [block["kind"] for block in extracted.blocks] == [
        "heading", "paragraph", "paragraph", "quote", "quote", "list_item", "list_item", "list_item", "paragraph", "preformatted", "paragraph"]
    slices = lambda kind: [extracted.full_text[m["char_start"]:m["char_end"]] for b in extracted.blocks for m in b["marks"] if m["kind"] == kind]
    assert slices("emphasis") == ["morning", "almost"]
    assert slices("strong") == ["read"]
    assert slices("line_break") == ["\n", "\n"]
    assert slices("subscript") == ["2"] and slices("superscript") == ["2"]
    assert slices("code") == ["hello()"]
    assert "  a    b\n    c" in extracted.full_text
    assert [b.get("list_label") for b in extracted.blocks if b["kind"] == "list_item"] == ["3.", "7.", None]
    assert "href" not in str(extracted.blocks) and "https:" not in str(extracted.blocks)


@pytest.mark.parametrize("html", [HTML, "<p>re<em>read</em>ing.</p>", "<p>this <em>word</em> matters</p>",
    "<p>a<br/>b</p><p>c</p>", "<p>a<!-- hidden -->b</p>", "<div> a <p>b</p> c </div>", "<pre>  a\n b </pre>"])
def test_legacy_extraction_is_byte_for_byte_compatible(html):
    soup = BeautifulSoup(html, "html.parser")
    text, blocks = document_text(soup, legacy=True)
    assert text == soup.get_text(separator="\n", strip=True)
    assert blocks
    if html == "<p>re<em>read</em>ing.</p>":
        joins = [m for m in blocks[0]["marks"] if m["kind"] == "join"]
        assert len(joins) == 2 and all(text[m["char_start"]:m["char_end"]] == "\n" for m in joins)


@pytest.mark.parametrize("legacy", [False, True])
def test_layout_projects_through_overlaps_and_clips_unicode_pages(legacy):
    extracted = extract_epub(epub_bytes(HTML * 12), "window.epub", legacy_text=legacy)
    raw_chunks = chunk_text(extracted.sections[0].text, section_char_start=0, chunk_size=400, overlap=100, preserve_whitespace=not legacy)
    chunks = [SimpleNamespace(id=str(i), section_id="one", text=c.text, char_start=c.absolute_char_start, char_end=c.absolute_char_end) for i, c in enumerate(raw_chunks)]
    reading = assemble_reading_text(chunks)
    layout = reader_layout.build_reading_layout(extracted.full_text, extracted.blocks, chunks, reading)
    assert layout and len(layout["blocks"]) == len(extracted.blocks)
    for source, target in zip(extracted.blocks, layout["blocks"]):
        assert extracted.full_text[source["char_start"]:source["char_end"]] == reading.text[target["char_start"]:target["char_end"]]
        assert len(source["marks"]) == len(target["marks"])
    blocks = reader_layout.cached_blocks(SimpleNamespace(metadata_json={"reading_layout": layout}), reading)
    rebuilt = ""
    continued = False
    for page in range(1, (len(reading.text) + 199) // 200 + 1):
        start, end = page_bounds(reading.text, page, 200)
        rebuilt += reading.text[start:end]
        for block in reader_layout.page_blocks(blocks, start, end):
            assert start <= block.char_start < block.char_end <= end
            assert all(block.char_start <= m.char_start < m.char_end <= block.char_end for m in block.marks)
            continued |= block.continued
    assert rebuilt == reading.text and continued


@pytest.mark.parametrize("preserve", [False, True])
def test_chunk_offsets_address_exact_content_and_retain_the_tail(preserve):
    text = "  " + "The light moved across the empty room. " * 20 + "\n  End.  "
    chunks = chunk_text(text, section_char_start=17, chunk_size=210, overlap=20, preserve_whitespace=preserve)
    for chunk in chunks:
        assert text[chunk.char_start:chunk.char_end] == chunk.text
        assert chunk.absolute_char_start == 17 + chunk.char_start
    assert chunks[-1].text.rstrip().endswith("End.")
    if preserve:
        assert chunks[0].text.startswith("  ") and chunks[-1].text.endswith("  ")


def saved_legacy_book(db, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    path = tmp_path / "window.epub"
    path.write_bytes(epub_bytes(HTML))
    extracted = extract_epub(path.read_bytes(), path.name, legacy_text=True)
    book = Book(title=extracted.title, filename=path.name, file_type="epub", file_size_bytes=path.stat().st_size,
                ingest_status=IngestStatus.COMPLETED, metadata_json={"stored_path": str(path), "retained": "metadata"})
    db.add(book)
    db.flush()
    section = Section(book_id=book.id, title="The first morning", section_type="chapter", order_index=0,
                      char_start=0, char_end=len(extracted.full_text))
    db.add(section)
    db.flush()
    # Historic trimming stored uncorrected outer whitespace coordinates.
    chunk = Chunk(book_id=book.id, section_id=section.id, order_index=0, text=extracted.full_text.strip(),
                  char_start=0, char_end=len(extracted.full_text))
    db.add(chunk)
    db.commit()
    return book, [chunk], path


def test_old_book_recovers_structure_without_changing_edition_or_memory(mock_db, tmp_path, monkeypatch):
    book, chunks, path = saved_legacy_book(mock_db, tmp_path, monkeypatch)
    reading = assemble_reading_text(chunks)
    chunk_identity = [(c.id, c.text, c.char_start, c.char_end) for c in chunks]
    memory = BookMemory(book_id=book.id, units_completed=[], total_reading_time_min=11)
    mock_db.add(memory)
    mock_db.commit()
    blocks = reader_layout.book_blocks(mock_db, book, reading, chunks)
    assert blocks and blocks[0].kind == "heading"
    assert any(m.kind == "join" for b in blocks for m in b.marks)
    assert assemble_reading_text(chunks).edition_id == reading.edition_id
    assert [(c.id, c.text, c.char_start, c.char_end) for c in chunks] == chunk_identity
    assert memory.total_reading_time_min == 11 and book.metadata_json["retained"] == "metadata"
    # Persisted layout can render even after the original upload is removed.
    path.unlink()
    assert reader_layout.book_blocks(mock_db, book, reading, chunks) == blocks


@pytest.mark.parametrize("failure", ["missing", "changed", "outside", "symlink", "oversize", "expanded", "invalid"])
def test_unrecoverable_original_falls_back_without_mutating_text(mock_db, tmp_path, monkeypatch, failure):
    root = tmp_path / "uploads"
    root.mkdir()
    book, chunks, path = saved_legacy_book(mock_db, root, monkeypatch)
    reading = assemble_reading_text(chunks)
    if failure == "missing":
        path.unlink()
    elif failure == "changed":
        path.write_bytes(epub_bytes("<p>A completely different book.</p>"))
    elif failure in {"outside", "symlink"}:
        outside = tmp_path / "outside.epub"
        path.rename(outside)
        if failure == "outside":
            book.metadata_json = {"stored_path": str(outside)}
        else:
            path.symlink_to(outside)
    elif failure == "oversize":
        monkeypatch.setattr(reader_layout, "MAX_SOURCE_BYTES", 1)
    elif failure == "expanded":
        monkeypatch.setattr(reader_layout, "MAX_EXPANDED_BYTES", 1)
    else:
        path.write_bytes(b"not an archive")
    assert reader_layout.book_blocks(mock_db, book, reading, chunks) == []
    assert "reading_layout" not in book.metadata_json
    assert assemble_reading_text(chunks).text == reading.text


def test_ingestion_persists_readable_layout_before_shelving(mock_db):
    from app.ingest import pipeline
    book = Book(title="Queued", filename="window.epub", file_type="epub", file_size_bytes=100,
                ingest_status=IngestStatus.QUEUED)
    mock_db.add(book)
    mock_db.commit()
    async def embed(texts):
        return [[1.0] + [0.0] * 3071 for _ in texts]
    with patch.object(pipeline, "SessionLocal", return_value=mock_db), patch.object(mock_db, "close"), patch.object(
        pipeline, "get_embeddings_client", return_value=SimpleNamespace(embed=embed)):
        asyncio.run(pipeline.run_ingestion_pipeline(book.id, epub_bytes(HTML), book.filename))
    assert book.ingest_status == IngestStatus.COMPLETED
    assert book.metadata_json["epub_text_version"] == "blocks-v1"
    reading, chunks = pipeline.load_reading(mock_db, book.id)
    assert reader_layout.cached_blocks(book, reading)
    assert "rereading" in reading.text and "  a    b\n    c" in reading.text


@pytest.mark.parametrize("stage", ["load_reading", "build_reading_layout"])
def test_optional_layout_failure_keeps_the_import_readable(mock_db, stage):
    from app.ingest import pipeline
    book = Book(title="Queued", filename="window.epub", file_type="epub", file_size_bytes=100,
                ingest_status=IngestStatus.QUEUED)
    mock_db.add(book)
    mock_db.commit()
    async def embed(texts):
        return [[1.0] + [0.0] * 3071 for _ in texts]
    with patch.object(pipeline, "SessionLocal", return_value=mock_db), patch.object(mock_db, "close"), patch.object(
        pipeline, "get_embeddings_client", return_value=SimpleNamespace(embed=embed)), patch.object(
        pipeline, stage, side_effect=ValueError("invalid formatting")):
        asyncio.run(pipeline.run_ingestion_pipeline(book.id, epub_bytes(HTML), book.filename))
    assert book.ingest_status == IngestStatus.COMPLETED
    reading, chunks = pipeline.load_reading(mock_db, book.id)
    assert "rereading" in reading.text and all(c.embedding is not None for c in chunks)


def test_invalid_rebuild_is_never_committed_and_uses_failure_backoff(mock_db, tmp_path, monkeypatch):
    book, chunks, path = saved_legacy_book(mock_db, tmp_path, monkeypatch)
    reading = assemble_reading_text(chunks)
    bad_layout = {"version": 1, "edition_id": reading.edition_id,
                  "blocks": [{"kind": "paragraph", "char_start": 0, "char_end": len(reading.text) + 1}]}
    with patch.object(reader_layout, "build_reading_layout", return_value=bad_layout) as build:
        assert reader_layout.book_blocks(mock_db, book, reading, chunks) == []
        assert reader_layout.book_blocks(mock_db, book, reading, chunks) == []
        assert build.call_count == 1
    assert "reading_layout" not in book.metadata_json


def test_corrupt_cached_coordinates_are_not_rendered():
    reading = SimpleNamespace(text="abc", edition_id="edition")
    layout = {"version": 1, "edition_id": "edition", "blocks": [{"kind": "heading", "char_start": 0, "char_end": 4}]}
    book = SimpleNamespace(metadata_json={"reading_layout": layout})
    assert reader_layout.cached_blocks(book, reading) is None
    layout["blocks"][0]["char_end"] = 3
    layout["blocks"][0]["marks"] = [{"kind": "strong", "char_start": 0, "char_end": 4}]
    assert reader_layout.cached_blocks(book, reading) is None
    layout["blocks"][0]["marks"] = []
    layout["blocks"][0]["marks"] = [{"kind": "join", "char_start": 0, "char_end": 3}]
    assert reader_layout.cached_blocks(book, reading) is None, "formatting must never hide ordinary prose"
    layout["blocks"][0]["marks"] = []
    layout["edition_id"] = "another-edition"
    assert reader_layout.cached_blocks(book, reading) is None

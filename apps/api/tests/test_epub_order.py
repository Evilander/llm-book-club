"""An EPUB's manifest order must never become its page order."""
import io

from ebooklib import epub

from app.ingest.extractor import extract_epub


def test_epub_uses_spine_order_and_excludes_navigation():
    book = epub.EpubBook()
    book.set_identifier("spine-order-fixture")
    book.set_title("A short journey")
    book.set_language("en")
    first = epub.EpubHtml(title="Opening", file_name="z-opening.xhtml")
    first.content = "<h1>Opening</h1><p>The lamp was lit before dawn.</p>"
    second = epub.EpubHtml(title="Closing", file_name="a-closing.xhtml")
    second.content = "<h1>Closing</h1><p>At night, the compass moved.</p>"
    # Deliberately add the files out of order and include a navigation document.
    for item in [second, epub.EpubNav(), first, epub.EpubNcx()]:
        book.add_item(item)
    book.toc = (first, second)
    book.spine = ["nav", first, second]
    output = io.BytesIO()
    epub.write_epub(output, book)

    extracted = extract_epub(output.getvalue(), "journey.epub")
    assert [section.title for section in extracted.sections] == ["Opening", "Closing"]
    assert extracted.full_text.index("before dawn") < extracted.full_text.index("At night")
    assert extracted.full_text.count("Opening") == 1
    assert extracted.full_text.count("Closing") == 1
    for section in extracted.sections:
        assert extracted.full_text[section.char_start:section.char_end] == section.text

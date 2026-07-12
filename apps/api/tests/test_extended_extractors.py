"""Extraction coverage for discussion-ready FB2 and Kindle-family files."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.ingest.extractor import extract_fb2, extract_mobi_family, extract_txt


def test_fb2_extracts_metadata_and_top_level_sections():
    publication = b"""<?xml version="1.0" encoding="utf-8"?>
    <FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
                 xmlns:l="http://www.w3.org/1999/xlink">
      <description><title-info>
        <book-title>The Glass Archive</book-title>
        <author><first-name>Mara</first-name><last-name>Vale</last-name></author>
        <lang>en</lang>
        <coverpage><image l:href="#cover.jpg" /></coverpage>
      </title-info></description>
      <body>
        <section><title><p>Arrival</p></title><p>The train entered the city.</p></section>
        <section><title><p>Afterlight</p></title><p>The windows held the sunset.</p></section>
      </body>
      <binary id="cover.jpg" content-type="image/jpeg">ZmFrZS1jb3Zlcg==</binary>
    </FictionBook>"""

    extracted = extract_fb2(publication, "fallback.fb2")

    assert extracted.file_type == "fb2"
    assert extracted.title == "The Glass Archive"
    assert extracted.author == "Mara Vale"
    assert [section.title for section in extracted.sections] == ["Arrival", "Afterlight"]
    assert "The train entered the city." in extracted.full_text
    assert "ZmFrZS1jb3Zlcg" not in extracted.full_text


def test_mobi_unpack_html_uses_opf_metadata_and_cleans_tempdir(tmp_path: Path):
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    html_path = unpacked / "book.html"
    html_path.write_text(
        "<html><body><h1>CHAPTER 1 First Light</h1>"
        "<p>I will not be mistaken for a Roman-numeral heading.</p>"
        "<h1>CHAPTER 2 The Door</h1><p>The door opened.</p></body></html>",
        encoding="utf-8",
    )
    (unpacked / "metadata.opf").write_text(
        "<package><metadata><title>The Mobi Archive</title>"
        "<creator>Iris North</creator></metadata></package>",
        encoding="utf-8",
    )

    with patch(
        "app.ingest.extractor.mobi.extract",
        return_value=(str(unpacked), str(html_path)),
    ):
        extracted = extract_mobi_family(b"fake mobi", "fallback.mobi")

    assert extracted.file_type == "mobi"
    assert extracted.title == "The Mobi Archive"
    assert extracted.author == "Iris North"
    assert len(extracted.sections) == 2
    assert not unpacked.exists()


def test_mobi_unpack_failure_explains_drm_constraint():
    with patch(
        "app.ingest.extractor.mobi.extract",
        side_effect=RuntimeError("encrypted"),
    ), pytest.raises(ValueError, match="Only DRM-free"):
        extract_mobi_family(b"encrypted", "locked.azw3")


def test_plain_text_pronoun_is_not_a_roman_numeral_heading():
    extracted = extract_txt(
        b"I will begin with an ordinary sentence.\n\nThe paragraph continues.",
        "memoir.txt",
    )

    assert len(extracted.sections) == 1

"""Exercise upload -> real RQ worker -> reader -> grounded streamed discussion."""
import json
import os
import time
import io
import textwrap

import httpx
import pytest


def document_bytes(kind, prose):
    if kind == "txt":
        return prose.encode()
    if kind == "epub":
        from ebooklib import epub
        book = epub.EpubBook()
        book.set_identifier("integration-fixture")
        book.set_title("The compass")
        book.set_language("en")
        chapter = epub.EpubHtml(title="The garden", file_name="garden.xhtml", lang="en")
        chapter.content = "<html><body>" + "".join(f"<p>{p}</p>" for p in prose.split("\n\n") if p) + "</body></html>"
        book.add_item(chapter)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.toc = (chapter,)
        book.spine = ["nav", chapter]
        buffer = io.BytesIO()
        epub.write_epub(buffer, book)
        return buffer.getvalue()
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    lines = textwrap.wrap(prose, width=85)
    stream.set_data(("BT /F1 11 Tf 40 750 Td 14 TL\n" + "\n".join(f"({line}) Tj T*" for line in lines) + "\nET").encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("kind", ["txt", "epub", "pdf"])
def test_upload_read_discuss_and_recall_across_sessions(kind):
    url = os.environ.get("TEST_APP_URL", "http://127.0.0.1:58000")
    prose = (
        "The cartographer carried an amber compass into the garden. "
        "She trusted its needle even when she could no longer see the path. "
        "A blue thread marked the place where her map had been folded.\n\n"
    ) * 8 + "\n\nUNREAD_ENDING_MARKER. The garden keeper was the cartographer all along."
    with httpx.Client(base_url=url, timeout=30) as client:
        assert client.get("/health").json()["ok"]
        upload = client.post("/v1/ingest", files={"file": (f"the-compass.{kind}", document_bytes(kind, prose), "application/octet-stream")})
        upload.raise_for_status()
        book_id = upload.json()["book_id"]
        deadline = time.monotonic() + 45
        while True:
            book = client.get(f"/v1/books/{book_id}").json()
            assert book["ingest_status"] != "failed", book.get("ingest_error")
            if book["ingest_status"] == "completed":
                break
            assert time.monotonic() < deadline, "The real ingestion worker did not finish."
            time.sleep(0.25)
        page = client.get(f"/v1/books/{book_id}/reader", params={"page": 1, "page_size": 600}).json()
        assert "amber compass" in page["text"]
        sections = list(dict.fromkeys(span["section_id"] for span in page["chunks"]))
        companion = client.post(f"/v1/books/{book_id}/companion", json={"section_ids": sections, "page": 1, "page_size": 600, "edition_id": page["edition_id"]})
        companion.raise_for_status()
        session_id = companion.json()["session_id"]
        early_position = companion.json()["reading_position"]
        assert early_position["edition_id"] == page["edition_id"]
        request = {"session_id": session_id, **early_position}
        notes = client.post(f"/v1/books/{book_id}/reader-notes", json=request)
        notes.raise_for_status()
        note = notes.json()["notes"][0]
        assert note["verified"] and note["quote"] in page["text"]
        assert client.post(f"/v1/books/{book_id}/reader-notes", json=request).json()["cached"]

        def send(session, message, position=None):
            with client.stream("POST", f"/v1/sessions/{session}/message/stream",
                               json={"content": message, "include_close_reader": False, "adaptive": False, "reading_position": position}) as response:
                response.raise_for_status()
                events = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
            assert not [e for e in events if e["type"] in {"error", "agent_error"}], events
            final = next(e for e in events if e["type"] == "message_end")
            assert final["citations"] and all(c["verified"] for c in final["citations"])
            assert events[-1]["type"] == "done"
            assert "".join(e["delta"] for e in events if e["type"] == "message_delta") == final["content"]
            assert all('"analysis"' not in e.get("sentence", "") for e in events)
            sequences = [e["sequence"] for e in events if "sequence" in e]
            assert sequences == sorted(set(sequences))
            return final

        last_page = client.get(f"/v1/books/{book_id}/reader", params={"page": page["total_pages"], "page_size": 600}).json()
        later = client.post(f"/v1/books/{book_id}/companion", json={"section_ids": list(dict.fromkeys(s["section_id"] for s in last_page["chunks"])), "page": last_page["page"], "page_size": 600, "edition_id": last_page["edition_id"]})
        later.raise_for_status()
        send(session_id, "LATER_READER_THOUGHT connects the cartographer with the keeper.", later.json()["reading_position"])
        with httpx.Client(base_url=os.environ.get("TEST_PROVIDER_URL", "http://127.0.0.1:59000"), timeout=10) as provider:
            provider.post("/test/reset").raise_for_status()
            final = send(session_id, "My cobalt-thread observation connects the compass with trust.", early_position)
            captured = provider.get("/test/requests").json()
            assert captured, "The provider must actually receive the earlier-page turn."
            actual_prompts = json.dumps(captured)
            assert "LATER_READER_THOUGHT" not in actual_prompts
            assert "UNREAD_ENDING_MARKER" not in actual_prompts
        history = client.get(f"/v1/sessions/{session_id}/messages", params=early_position).json()["messages"]
        assert any(m["id"] == final["message_id"] and m["content"] == final["content"] for m in history)
        assert not any("LATER_READER_THOUGHT" in m["content"] for m in history)
        citation = final["citations"][0]
        location = client.get(f"/v1/books/{book_id}/reader-location",
                              params={"chunk_id": citation["chunk_id"], "char_start": citation["char_start"], "page_size": 600})
        location.raise_for_status()
        assert location.json()["page"] >= 1
        club = client.post("/v1/sessions/start", json={"book_id": book_id, "section_ids": sections, "mode": "conversation"})
        club.raise_for_status()
        recalled = send(club.json()["session_id"], "How does the compass change the meaning of trust?")
        assert "I remember your cobalt-thread observation." in recalled["content"]

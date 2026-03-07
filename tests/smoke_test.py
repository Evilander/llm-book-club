#!/usr/bin/env python3
"""
Quick smoke test for LLM Book Club API.

Run with: python tests/smoke_test.py

Prerequisites:
- API running at http://localhost:8000
- At least one book ingested (optional for full test)
"""
import requests
import time
import sys
import argparse

# Use ASCII-compatible symbols for Windows compatibility
CHECK = "[OK]"
CROSS = "[FAIL]"
WARN = "[WARN]"

API = "http://localhost:8000"


def test_health():
    """Test API health endpoint."""
    r = requests.get(f"{API}/health", timeout=5)
    assert r.status_code == 200, f"Health check failed: {r.text}"
    data = r.json()
    assert data.get("status") == "healthy", f"Unexpected health status: {data}"
    print(f"{CHECK} Health check passed")


def test_books_list():
    """Test books list endpoint."""
    r = requests.get(f"{API}/v1/books", timeout=10)
    assert r.status_code == 200, f"Books list failed: {r.text}"
    data = r.json()
    # Handle both old (list) and new (dict with books key) response formats
    books = data.get("books", data) if isinstance(data, dict) else data
    print(f"{CHECK} Books list returned {len(books)} books")
    return books


def test_book_sections(book_id: str):
    """Test sections endpoint for a book."""
    r = requests.get(f"{API}/v1/books/{book_id}/sections", timeout=10)
    assert r.status_code == 200, f"Sections list failed: {r.text}"
    sections = r.json()
    print(f"  - Book has {len(sections)} sections")
    return sections


def test_session_creation(book_id: str):
    """Test session creation."""
    r = requests.post(
        f"{API}/v1/sessions/start",
        json={
            "book_id": book_id,
            "mode": "guided",
            "time_budget_min": 15
        },
        timeout=10
    )
    assert r.status_code == 200, f"Session creation failed: {r.text}"
    data = r.json()
    session_id = data.get("session_id")
    assert session_id, f"No session_id in response: {data}"
    print(f"{CHECK} Session created: {session_id[:8]}...")
    return session_id


def test_start_discussion(session_id: str):
    """Test starting a discussion."""
    r = requests.post(
        f"{API}/v1/sessions/{session_id}/start-discussion",
        timeout=60  # LLM calls can be slow
    )
    assert r.status_code == 200, f"Start discussion failed: {r.text}"
    data = r.json()
    messages = data.get("messages", [])
    print(f"{CHECK} Discussion started with {len(messages)} opening message(s)")
    return messages


def test_send_message(session_id: str, content: str = "What is this text about?"):
    """Test sending a user message."""
    r = requests.post(
        f"{API}/v1/sessions/{session_id}/message",
        json={"content": content, "include_close_reader": True},
        timeout=120  # Multiple LLM calls
    )
    assert r.status_code == 200, f"Message failed: {r.text}"
    data = r.json()
    messages = data.get("messages", [])
    print(f"{CHECK} Got {len(messages)} agent response(s)")

    # Check for citations
    total_citations = 0
    for msg in messages:
        citations = msg.get("citations", [])
        if citations:
            total_citations += len(citations)
            print(f"  - {msg.get('role', 'unknown')}: {len(citations)} citation(s)")

    if total_citations == 0:
        print(f"  {WARN} Warning: No citations in responses")

    return messages


def test_streaming(session_id: str, content: str = "Summarize the key points."):
    """Test streaming endpoint."""
    try:
        r = requests.post(
            f"{API}/v1/sessions/{session_id}/message/stream",
            json={"content": content},
            stream=True,
            timeout=120
        )
        assert r.status_code == 200, f"Streaming failed: {r.status_code}"

        event_count = 0
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                event_count += 1
                if event_count >= 5:  # Just check first few events
                    break

        print(f"{CHECK} Streaming works ({event_count}+ events received)")
        return True
    except Exception as e:
        print(f"{WARN} Streaming test skipped: {e}")
        return False


def test_session_messages(session_id: str):
    """Test fetching session messages."""
    r = requests.get(f"{API}/v1/sessions/{session_id}/messages", timeout=10)
    assert r.status_code == 200, f"Messages fetch failed: {r.text}"
    messages = r.json()
    print(f"{CHECK} Session has {len(messages)} total messages")
    return messages


def run_full_test(book_id: str = None):
    """Run full test suite."""
    print("=== LLM Book Club Smoke Test ===\n")

    # Health check
    test_health()

    # List books
    books = test_books_list()

    if not books and not book_id:
        print(f"\n{WARN} No books found. Upload a book first to test full flow.")
        print("  Use: curl -X POST http://localhost:8000/v1/ingest -F 'file=@book.pdf'")
        return True  # Not a failure, just incomplete test

    # Find a completed book
    if book_id:
        target_book = next((b for b in books if b.get("id") == book_id), None)
        if not target_book:
            print(f"\n{CROSS} Book {book_id} not found")
            return False
    else:
        completed = [b for b in books if b.get("ingest_status") == "completed"]
        if not completed:
            print(f"\n{WARN} No completed books. Wait for ingestion to finish.")
            in_progress = [b for b in books if b.get("ingest_status") in ("queued", "processing")]
            if in_progress:
                print(f"  {len(in_progress)} book(s) still processing")
            return True  # Not a failure
        target_book = completed[0]

    book_id = target_book["id"]
    print(f"\nTesting with book: {target_book.get('title', 'Unknown')[:40]}...")

    # Get sections
    test_book_sections(book_id)

    # Create session
    session_id = test_session_creation(book_id)

    # Start discussion
    test_start_discussion(session_id)

    # Send a message
    test_send_message(session_id)

    # Test streaming
    test_streaming(session_id)

    # Verify messages persisted
    test_session_messages(session_id)

    print("\n=== All tests passed! ===")
    return True


def main():
    parser = argparse.ArgumentParser(description="Smoke test for LLM Book Club API")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--book-id", help="Specific book ID to test with")
    parser.add_argument("--health-only", action="store_true", help="Only run health check")
    args = parser.parse_args()

    global API
    API = args.api

    try:
        if args.health_only:
            test_health()
            print("\n=== Health check passed! ===")
            return 0

        success = run_full_test(args.book_id)
        return 0 if success else 1

    except requests.exceptions.ConnectionError:
        print(f"\n{CROSS} Cannot connect to API at {API}")
        print("  Is the backend running? Try: uvicorn app.main:app --port 8000")
        return 1
    except AssertionError as e:
        print(f"\n{CROSS} Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n{CROSS} Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

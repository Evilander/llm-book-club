"""Seed the database with public domain books from Project Gutenberg.

Run this script to pre-ingest classic literature so users can
start a discussion session immediately without uploading anything.

Usage:
    cd apps/api
    python scripts/seed_public_domain.py

The script downloads plain-text versions from Project Gutenberg,
saves them to a temp directory, and triggers ingestion via the API.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

import httpx

# Public domain books from Project Gutenberg (plain text URLs)
SEED_BOOKS = [
    {
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/cache/epub/1342/pg1342.txt",
        "filename": "pride-and-prejudice.txt",
    },
    {
        "title": "Dracula",
        "author": "Bram Stoker",
        "url": "https://www.gutenberg.org/cache/epub/345/pg345.txt",
        "filename": "dracula.txt",
    },
    {
        "title": "The Awakening",
        "author": "Kate Chopin",
        "url": "https://www.gutenberg.org/cache/epub/160/pg160.txt",
        "filename": "the-awakening.txt",
    },
    {
        "title": "Frankenstein",
        "author": "Mary Shelley",
        "url": "https://www.gutenberg.org/cache/epub/84/pg84.txt",
        "filename": "frankenstein.txt",
    },
    {
        "title": "The Picture of Dorian Gray",
        "author": "Oscar Wilde",
        "url": "https://www.gutenberg.org/cache/epub/174/pg174.txt",
        "filename": "dorian-gray.txt",
    },
]

API_BASE = "http://localhost:8000/v1"


async def download_and_ingest(book: dict, tmp_dir: Path) -> bool:
    """Download a book and ingest it via the API."""
    filepath = tmp_dir / book["filename"]

    async with httpx.AsyncClient(timeout=60) as client:
        # Download
        print(f"  Downloading {book['title']}...")
        try:
            resp = await client.get(book["url"])
            resp.raise_for_status()
            filepath.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            print(f"  FAILED to download {book['title']}: {e}")
            return False

        # Ingest via API
        print(f"  Ingesting {book['title']}...")
        try:
            with open(filepath, "rb") as f:
                files = {"file": (book["filename"], f, "text/plain")}
                resp = await client.post(f"{API_BASE}/ingest", files=files)
                resp.raise_for_status()
                data = resp.json()
                print(f"  OK: {book['title']} -> book_id={data.get('book_id', '?')}")
                return True
        except Exception as e:
            print(f"  FAILED to ingest {book['title']}: {e}")
            return False


async def main():
    print("Seeding public domain books from Project Gutenberg...")
    print(f"API: {API_BASE}")
    print()

    # Check API is reachable
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{API_BASE.replace('/v1', '')}/health")
            if resp.status_code != 200:
                resp = await client.get(f"{API_BASE.replace('/v1', '')}/docs")
        except httpx.ConnectError:
            print("ERROR: API is not running. Start it with:")
            print("  cd apps/api && uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        results = await asyncio.gather(
            *[download_and_ingest(book, tmp_dir) for book in SEED_BOOKS]
        )

    succeeded = sum(results)
    failed = len(results) - succeeded
    print()
    print(f"Done: {succeeded} succeeded, {failed} failed")
    print()
    if succeeded > 0:
        print("Users can now start a discussion session immediately")
        print("without uploading anything!")


if __name__ == "__main__":
    asyncio.run(main())

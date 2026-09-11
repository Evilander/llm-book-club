"""Book search preparation, separate from immutable reading positions."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db, Book, IngestStatus
from ..rate_limit import limiter
from ..services.search_index import index_counts
from ..worker import enqueue_index_refresh, index_job_state
from .connections import settings_request

router = APIRouter(tags=["search"])


def _book(db, book_id):
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "Book not found")
    if book.ingest_status != IngestStatus.COMPLETED:
        raise HTTPException(409, "Finish preparing the book before refreshing its search.")
    return book


@router.get("/books/{book_id}/search-index")
def search_index_status(book_id: str, response: Response, db: Session = Depends(get_db)):
    _book(db, book_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        counts = index_counts(db, book_id)
    except ValueError:
        raise HTTPException(503, "Check the book search configuration.") from None
    try:
        state = index_job_state(book_id, counts["space_id"])
    except Exception:
        state = "unavailable"
    return {**counts, "state": "ready" if counts["ready"] else state or "pending"}


@router.post("/books/{book_id}/search-index", dependencies=[Depends(settings_request)])
@limiter.limit("6/minute")
def refresh_search_index(book_id: str, request: Request, db: Session = Depends(get_db)):
    _book(db, book_id)
    try:
        counts = index_counts(db, book_id)
        if counts["ready"]:
            return {"state": "ready"}
        enqueue_index_refresh(book_id, counts["space_id"])
    except Exception:
        raise HTTPException(503, "Search preparation is unavailable. Check that the worker is running and try again.") from None
    return {"state": "queued"}

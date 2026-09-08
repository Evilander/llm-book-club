"""RQ worker configuration and tasks."""
from datetime import timedelta
import time

from redis import Redis
from rq import Queue
from rq.registry import StartedJobRegistry

from .settings import settings

redis_conn = Redis.from_url(settings.redis_url)
ingest_queue = Queue("ingest", connection=redis_conn)
BINDERY_PAUSED_KEY = "bindery:paused"
BINDERY_PAUSE_SLEEP_SEC = 2
BINDERY_DEFER_SECONDS = 30


def is_bindery_paused() -> bool:
    return redis_conn.get(BINDERY_PAUSED_KEY) == b"1"


def set_bindery_paused(paused: bool) -> bool:
    redis_conn.set(BINDERY_PAUSED_KEY, "1" if paused else "0")
    return paused


def get_bindery_status() -> dict[str, int | bool]:
    started = StartedJobRegistry(ingest_queue.name, connection=redis_conn)
    return {
        "paused": is_bindery_paused(),
        "queued": ingest_queue.count,
        "processing": started.count,
    }


def _wait_for_bindery_unpaused() -> None:
    while is_bindery_paused():
        time.sleep(BINDERY_PAUSE_SLEEP_SEC)


def _run_ingestion_when_unpaused(book_id: str, file_data: bytes, filename: str) -> str:
    from .ingest.pipeline import run_ingestion_sync

    _wait_for_bindery_unpaused()
    return run_ingestion_sync(book_id, file_data, filename)


def _run_ingestion_from_path_when_unpaused(book_id: str, file_path: str, filename: str) -> str:
    from .ingest.pipeline import run_ingestion_sync_from_path

    if is_bindery_paused():
        job = ingest_queue.enqueue_in(
            timedelta(seconds=BINDERY_DEFER_SECONDS),
            _run_ingestion_from_path_when_unpaused,
            book_id,
            file_path,
            filename,
            job_timeout="30m",
            result_ttl=86400,
        )
        return f"deferred:{job.id}"

    return run_ingestion_sync_from_path(book_id, file_path, filename)


def enqueue_ingestion(book_id: str, file_data: bytes, filename: str):
    """Enqueue a book ingestion job."""
    job = ingest_queue.enqueue(
        _run_ingestion_when_unpaused,
        book_id,
        file_data,
        filename,
        job_timeout="30m",  # Large books may take time
        result_ttl=86400,  # Keep result for 24 hours
    )
    return job.id


def enqueue_ingestion_from_path(book_id: str, file_path: str, filename: str):
    """Enqueue a book ingestion job that reads bytes from disk inside the worker."""
    job = ingest_queue.enqueue(
        _run_ingestion_from_path_when_unpaused,
        book_id,
        file_path,
        filename,
        job_timeout="30m",
        result_ttl=86400,
    )
    return job.id

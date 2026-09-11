"""RQ worker configuration and tasks."""
from datetime import timedelta
import time

from redis import Redis
from rq import Queue
from rq.registry import StartedJobRegistry

from .settings import settings

redis_conn = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
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


def index_job_id(book_id: str, space_id: str) -> str:
    return f"search-{book_id}-{space_id}"


def index_job_state(book_id: str, space_id: str) -> str | None:
    job = ingest_queue.fetch_job(index_job_id(book_id, space_id))
    return job.get_status().value if job else None


def enqueue_index_refresh(book_id: str, space_id: str) -> str:
    from .services.search_index import run_index_refresh
    job_id = index_job_id(book_id, space_id)
    # A double click or two tabs should not enqueue two model runs.
    with redis_conn.lock(f"enqueue-{job_id}", timeout=10, blocking_timeout=1):
        job = ingest_queue.fetch_job(job_id)
        if job:
            if job.get_status().value in {"queued", "started", "deferred", "scheduled"}:
                return job_id
            job.delete()
        ingest_queue.enqueue(run_index_refresh, book_id, space_id, job_id=job_id, job_timeout="30m", result_ttl=86400)
    return job_id

"""RQ worker configuration and tasks."""
import uuid

from redis import Redis
from rq import Queue

from .settings import settings

redis_conn = Redis.from_url(settings.redis_url)
ingest_queue = Queue("ingest", connection=redis_conn)
catalog_queue = Queue("catalog", connection=redis_conn)


def enqueue_ingestion(book_id: str, file_data: bytes, filename: str):
    """Enqueue a book ingestion job."""
    from .ingest.pipeline import run_ingestion_sync

    job = ingest_queue.enqueue(
        run_ingestion_sync,
        book_id,
        file_data,
        filename,
        job_timeout="30m",  # Large books may take time
        result_ttl=86400,  # Keep result for 24 hours
    )
    return job.id


def enqueue_local_ingestion(book_id: str, file_path: str, filename: str):
    """Queue a mounted local file by path instead of copying it into Redis."""
    from .ingest.pipeline import run_local_ingestion_sync

    job = ingest_queue.enqueue(
        run_local_ingestion_sync,
        book_id,
        file_path,
        filename,
        job_timeout="30m",
        result_ttl=86400,
    )
    return job.id


def enqueue_catalog_scan(catalog_id: str, job_id: str | None = None) -> str:
    """Queue a filesystem catalog refresh outside request latency."""
    from .services.catalog_index import run_catalog_scan

    resolved_job_id = job_id or f"media-catalog-{catalog_id}-{uuid.uuid4().hex}"
    job = catalog_queue.enqueue(
        run_catalog_scan,
        catalog_id,
        job_id=resolved_job_id,
        job_timeout="30m",
        result_ttl=86400,
        failure_ttl=86400,
    )
    return job.id

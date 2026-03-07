"""RQ worker configuration and tasks."""
from redis import Redis
from rq import Queue

from .settings import settings

redis_conn = Redis.from_url(settings.redis_url)
ingest_queue = Queue("ingest", connection=redis_conn)


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

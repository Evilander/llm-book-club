"""Run the RQ worker for processing ingestion jobs."""
from redis import Redis
from rq import Worker, Queue

from app.settings import settings

if __name__ == "__main__":
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [Queue("ingest", connection=redis_conn)]

    print(f"Starting worker, listening on queues: {[q.name for q in queues]}")
    worker = Worker(queues, connection=redis_conn)
    worker.work()

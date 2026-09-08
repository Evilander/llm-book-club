"""Windows-compatible worker for processing ingestion jobs.

RQ's default worker uses os.fork() which doesn't exist on Windows.
This worker uses SimpleWorker which runs in the same process.
"""
from redis import Redis
from rq import Queue, SimpleWorker

from app.settings import settings

if __name__ == "__main__":
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [Queue("ingest", connection=redis_conn)]

    print(f"Windows SimpleWorker started, listening on queues: {[q.name for q in queues]}")
    worker = SimpleWorker(queues, connection=redis_conn)
    worker.work()

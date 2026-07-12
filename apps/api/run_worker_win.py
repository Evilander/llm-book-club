"""Windows-compatible worker for processing ingestion jobs.

RQ's default worker uses os.fork() which doesn't exist on Windows.
This worker uses SimpleWorker which runs in the same process, and a
timer-based death penalty because SIGALRM also doesn't exist on Windows.
"""
from redis import Redis
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.settings import settings


class WindowsSimpleWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty


if __name__ == "__main__":
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [
        Queue("ingest", connection=redis_conn),
        Queue("catalog", connection=redis_conn),
    ]

    print(f"Windows SimpleWorker started, listening on queues: {[q.name for q in queues]}")
    worker = WindowsSimpleWorker(queues, connection=redis_conn)
    worker.work()

"""Run the RQ worker for processing ingestion jobs.

Windows compatibility:
- RQ's default ``Worker`` calls ``os.fork()`` — use ``SimpleWorker``.
- RQ's default death-penalty class uses ``signal.SIGALRM`` (POSIX only) —
  subclass to swap in ``TimerDeathPenalty`` (threading.Timer-based).
"""
import os
import sys

from redis import Redis
from rq import Queue, SimpleWorker, Worker
from rq.timeouts import TimerDeathPenalty

from app.settings import settings


class WindowsSimpleWorker(SimpleWorker):
    """SimpleWorker that uses TimerDeathPenalty instead of SIGALRM."""
    death_penalty_class = TimerDeathPenalty


if __name__ == "__main__":
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [Queue("ingest", connection=redis_conn)]

    is_windows = sys.platform == "win32" or not hasattr(os, "fork")
    worker_cls = WindowsSimpleWorker if is_windows else Worker

    print(
        f"Starting {worker_cls.__name__}"
        f"{' (Windows mode)' if is_windows else ''}, "
        f"listening on queues: {[q.name for q in queues]}",
        flush=True,
    )
    worker = worker_cls(queues, connection=redis_conn)
    worker.work()

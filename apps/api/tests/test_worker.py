"""Worker behavior tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch


def test_path_ingestion_defers_itself_when_bindery_is_paused():
    from app import worker

    class FakeJob:
        id = "deferred-job"

    with patch.object(worker, "is_bindery_paused", return_value=True), patch.object(
        worker.ingest_queue, "enqueue_in", return_value=FakeJob()
    ) as enqueue_in:
        result = worker._run_ingestion_from_path_when_unpaused(
            "book-1",
            r"D:\books\Paused.epub",
            "Paused.epub",
        )

    assert result == "deferred:deferred-job"
    enqueue_in.assert_called_once()
    args, kwargs = enqueue_in.call_args
    assert args[:5] == (
        timedelta(seconds=30),
        worker._run_ingestion_from_path_when_unpaused,
        "book-1",
        r"D:\books\Paused.epub",
        "Paused.epub",
    )
    assert kwargs["job_timeout"] == "30m"
    assert kwargs["result_ttl"] == 86400

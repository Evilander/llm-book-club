from unittest.mock import MagicMock

from app.routers import search_index
from tests.test_library import integration_engine, integration_db, client, populated_book  # noqa: F401


def test_refresh_rejects_cross_site_requests_before_queueing(client, populated_book, monkeypatch):
    enqueue = MagicMock()
    monkeypatch.setattr(search_index, "enqueue_index_refresh", enqueue)
    path = f"/v1/books/{populated_book.id}/search-index"
    assert client.post(path, headers={"Origin": "https://untrusted.example", "X-ReadAgain-Settings": "1"}).status_code == 403
    assert client.post(path, headers={"Origin": "http://localhost:3000"}).status_code == 403
    enqueue.assert_not_called()


def test_refresh_queues_current_model_without_changing_ingest_status(client, populated_book, monkeypatch):
    enqueue = MagicMock()
    monkeypatch.setattr(search_index, "enqueue_index_refresh", enqueue)
    response = client.post(f"/v1/books/{populated_book.id}/search-index", headers={"Origin": "http://localhost:3000", "X-ReadAgain-Settings": "1"})
    assert response.status_code == 200 and response.json()["state"] == "queued"
    assert response.headers["cache-control"] == "no-store"
    enqueue.assert_called_once()
    assert populated_book.ingest_status.value == "completed"


def test_index_status_reports_queue_failure_without_exposing_details(client, populated_book, monkeypatch):
    monkeypatch.setattr(search_index, "index_job_state", MagicMock(side_effect=RuntimeError("PRIVATE_QUEUE_URL")))
    response = client.get(f"/v1/books/{populated_book.id}/search-index")
    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE" not in response.text

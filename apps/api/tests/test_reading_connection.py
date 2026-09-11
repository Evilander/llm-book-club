"""Connection failures stay recoverable without saving unanswered reader turns."""
from unittest.mock import AsyncMock
from types import SimpleNamespace

import httpx
import pytest

from app.db.models import Message, Section
from app.providers.llm.factory import get_llm_client
from app.providers.readiness import local_status
from app.providers.selection import select_provider, selected_provider
from app.settings import settings
from tests.test_library import integration_engine, integration_db, client, populated_book  # noqa: F401

HEADERS = {"Origin": "http://localhost:3000", "X-ReadAgain-Settings": "1"}


@pytest.fixture
def signed_out(monkeypatch, integration_db):
    peer = SimpleNamespace(available=True, account=AsyncMock(return_value={"connected": False}))
    monkeypatch.setattr("app.providers.readiness.get_codex_runtime", lambda: peer)
    select_provider(integration_db, "chatgpt")
    return peer


@pytest.mark.parametrize("endpoint", ["message", "message/stream", "start-discussion", "challenge?claim=A+thought", "summary", "reader-notes"])
def test_signed_out_reading_never_saves_an_unanswered_turn(client, populated_book, integration_db, signed_out, endpoint):
    section = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    opened = client.post(f"/v1/books/{populated_book.id}/companion", json={"section_ids": [section.id], "page": 1}).json()
    session_id = opened["session_id"]
    if endpoint == "reader-notes":
        url = f"/v1/books/{populated_book.id}/reader-notes"
        body = {"session_id": session_id, **opened["reading_position"]}
    else:
        url = f"/v1/sessions/{session_id}/{endpoint}"
        body = {"content": "I wonder why the garden feels familiar.", "reading_position": opened["reading_position"]}
    response = client.post(url, json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "reading_connection_required"
    assert response.headers["cache-control"] == "no-store"
    assert "text/event-stream" not in response.headers["content-type"]
    assert integration_db.query(Message).filter_by(session_id=session_id).count() == 0
    assert client.get(f"/v1/sessions/{session_id}/messages").status_code == 200
    assert client.get(f"/v1/books/{populated_book.id}/reader").status_code == 200


def test_reading_check_can_recover_without_switching_provider(client, signed_out, integration_db):
    assert client.post("/v1/providers/reading-status", json={}).status_code == 403
    response = client.post("/v1/providers/reading-status", json={}, headers=HEADERS)
    assert response.json()["connected"] is False
    assert response.headers["cache-control"] == "no-store"
    signed_out.account.return_value = {"connected": True}
    assert client.post("/v1/providers/reading-status", json={}, headers=HEADERS).json()["connected"] is True
    assert selected_provider(integration_db) == "chatgpt"


def test_edition_conflict_is_distinct_from_missing_connection(client, populated_book, integration_db, signed_out):
    section = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    opened = client.post(f"/v1/books/{populated_book.id}/companion", json={"section_ids": [section.id], "page": 1}).json()
    response = client.post(f"/v1/sessions/{opened['session_id']}/message/stream", json={"content": "A thought", "reading_position": {**opened["reading_position"], "edition_id": "f" * 64}})
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    signed_out.account.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model,listed,expected", [
    ("llama3.2", ["llama3.2:latest"], True),
    ("gpt-oss:20b", ["gpt-oss:20b"], True),
    ("gpt-oss:20b", ["gpt-oss:120b"], False),
    ("fixture", [], False),
    ("default", ["default"], True),
])
async def test_local_readiness_checks_installed_model_without_inference(monkeypatch, model, listed, expected):
    monkeypatch.setattr(settings, "local_llm_base_url", "http://local-model.invalid/v1/")
    monkeypatch.setattr(settings, "local_llm_model", model)
    def respond(request):
        assert str(request.url) == "http://local-model.invalid/v1/models"
        assert request.method == "GET" and not request.content
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": item} for item in listed]})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    status = await local_status()
    assert status.connected is expected
    # Inference uses the same exact model ID as the readiness check.
    assert get_llm_client("local").model == model


@pytest.mark.parametrize("failure", ["offline", "redirect", "malformed", "oversized"])
def test_unavailable_local_model_is_not_connected_or_selectable(monkeypatch, client, integration_db, failure):
    monkeypatch.setattr(settings, "local_llm_base_url", "http://local-model.invalid/v1")
    def respond(request):
        if failure == "offline":
            raise httpx.ConnectError("private host detail", request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.com/private"})
        if failure == "oversized":
            return httpx.Response(200, content=b" " * 512_001)
        return httpx.Response(200, json={"data": None})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    original = selected_provider(integration_db)
    status = client.get("/v1/auth/status").json()
    local = next(provider for provider in status["providers"] if provider["provider"] == "local")
    assert local["connected"] is False
    assert "private" not in local["note"] and "invalid" not in local["note"]
    response = client.post("/v1/providers/active", json={"provider": "local"}, headers=HEADERS)
    assert response.status_code == 409
    assert selected_provider(integration_db) == original

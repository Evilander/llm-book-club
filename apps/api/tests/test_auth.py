"""Integration tests for auth routes and Gemini OAuth mode."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import Base, ProviderCredential, ReadingPrefs, User
from app.providers.llm.gemini import GeminiClient
from app.settings import settings

SETTINGS_HEADERS = {"Origin": "http://localhost:3000", "X-ReadAgain-Settings": "1"}


@pytest.fixture
def chatgpt_peer(monkeypatch):
    peer = MagicMock()
    peer.available = True
    peer.account = AsyncMock(return_value={"connected": True, "plan": "plus"})
    peer.begin_login = AsyncMock(return_value={"login_id": "fixture-login", "state": "pending", "user_code": "TEST-CODE", "verification_url": "https://auth.openai.com/codex/device", "deadline": time.monotonic() + 600})
    peer.login_status = AsyncMock(return_value={"login_id": "fixture-login", "state": "completed", "deadline": time.monotonic() + 600})
    peer.logout = AsyncMock()
    monkeypatch.setattr("app.routers.connections.get_codex_runtime", lambda: peer)
    return peer


@pytest.mark.parametrize("path,body", [
    ("/v1/auth/chatgpt/login", {}),
    ("/v1/auth/chatgpt/login/status", {"login_id": "fixture-login"}),
    ("/v1/auth/chatgpt/login/cancel", {"login_id": "fixture-login"}),
    ("/v1/auth/chatgpt/disconnect", {}),
    ("/v1/providers/active", {"provider": "chatgpt"}),
])
def test_connection_changes_require_first_party_origin_and_header(client, chatgpt_peer, monkeypatch, path, body):
    monkeypatch.setattr(settings, "cors_origins", "*")
    for headers in [{}, {"Origin": "http://localhost:3000"}, {"Origin": "https://example.com", "X-ReadAgain-Settings": "1"}, {"Origin": "null", "X-ReadAgain-Settings": "1"}]:
        assert client.post(path, json=body, headers=headers).status_code == 403
    chatgpt_peer.begin_login.assert_not_awaited()
    chatgpt_peer.logout.assert_not_awaited()


def test_device_code_flow_never_returns_tokens_and_is_not_cached(client, chatgpt_peer):
    response = client.post("/v1/auth/chatgpt/login", json={}, headers=SETTINGS_HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["user_code"] == "TEST-CODE"
    assert "deadline" not in response.json()
    response = client.post("/v1/auth/chatgpt/login/status", json={"login_id": "fixture-login"}, headers=SETTINGS_HEADERS)
    assert response.json()["state"] == "completed" and response.json()["user_code"] is None
    assert "token" not in response.text


def test_selection_persists_and_disconnect_keeps_chatgpt_selected(client, integration_db, chatgpt_peer):
    from app.providers.llm.factory import get_llm_client
    from app.providers.llm.chatgpt import ChatGPTClient
    from app.providers.selection import selected_provider
    response = client.post("/v1/providers/active", json={"provider": "chatgpt"}, headers=SETTINGS_HEADERS)
    assert response.json() == {"active_provider": "chatgpt"}
    integration_db.expire_all()
    assert selected_provider(integration_db) == "chatgpt"
    assert isinstance(get_llm_client(db=integration_db), ChatGPTClient)
    status = client.get("/v1/auth/status").json()
    assert next(item for item in status["providers"] if item["provider"] == "chatgpt")["active"] is True
    assert client.post("/v1/auth/chatgpt/disconnect", json={}, headers=SETTINGS_HEADERS).status_code == 200
    chatgpt_peer.logout.assert_awaited_once()
    assert selected_provider(integration_db) == "chatgpt"


def test_disconnected_provider_cannot_replace_current_selection(client, integration_db, chatgpt_peer):
    from app.providers.selection import selected_provider
    previous = selected_provider(integration_db)
    chatgpt_peer.account.return_value = {"connected": False, "plan": None}
    response = client.post("/v1/providers/active", json={"provider": "chatgpt"}, headers=SETTINGS_HEADERS)
    assert response.status_code == 409
    assert selected_provider(integration_db) == previous


def test_gemini_selection_treats_oauth_case_insensitively(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_auth_mode", "OAuth")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr("app.auth.service.get_current_user", lambda *_: User(id="fixture-user", email="fixture@example.com"))
    monkeypatch.setattr("app.auth.service.get_google_connection", lambda *args, **kwargs: object())
    response = client.post("/v1/providers/active", json={"provider": "gemini"}, headers=SETTINGS_HEADERS)
    assert response.json() == {"active_provider": "gemini"}


@pytest.fixture
def integration_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def integration_db(integration_engine):
    Session = sessionmaker(bind=integration_engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def client(integration_db):
    with patch("app.main.init_db"):
        from app.main import app
        from app.db import get_db
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            try:
                yield integration_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
        app.dependency_overrides.clear()
        limiter.enabled = True


@pytest.fixture(autouse=True)
def auth_settings():
    original_values = {
        "frontend_app_url": settings.frontend_app_url,
        "gemini_auth_mode": settings.gemini_auth_mode,
        "google_oauth_client_id": settings.google_oauth_client_id,
        "google_oauth_client_secret": settings.google_oauth_client_secret,
        "google_oauth_redirect_uri": settings.google_oauth_redirect_uri,
        "google_oauth_project_id": settings.google_oauth_project_id,
    }
    settings.frontend_app_url = "http://localhost:3000"
    settings.gemini_auth_mode = "oauth"
    settings.google_oauth_client_id = "google-client-id"
    settings.google_oauth_client_secret = "google-client-secret"
    settings.google_oauth_redirect_uri = "http://localhost:8000/v1/auth/google/callback"
    settings.google_oauth_project_id = "test-google-project"
    yield
    for key, value in original_values.items():
        setattr(settings, key, value)


def test_auth_status_surfaces_provider_capabilities(client: TestClient):
    response = client.get("/v1/auth/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False

    providers = {item["provider"]: item for item in payload["providers"]}
    assert providers["google"]["oauth_supported"] is True
    assert providers["google"]["oauth_ready"] is True
    assert providers["google"]["connect_path"] == "/v1/auth/google/start"
    assert providers["openai"]["oauth_supported"] is False
    assert providers["anthropic"]["oauth_supported"] is False


def test_reading_prefs_first_get_creates_default(client: TestClient, integration_db):
    response = client.get("/v1/users/me/reading-prefs", headers={"X-Reader-Id": "browser-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "browser-1"
    assert payload["theme"] == "cream-daylight"
    assert payload["font_family"] == "serif"
    assert payload["font_size_px"] == 20
    assert payload["focus_reading"] is False
    assert integration_db.query(ReadingPrefs).filter(ReadingPrefs.user_id == "browser-1").count() == 1


def test_patch_reading_prefs_updates_subset_and_preserves_other_fields(client: TestClient):
    created = client.get("/v1/users/me/reading-prefs", headers={"X-Reader-Id": "browser-2"})
    assert created.status_code == 200

    patched = client.patch(
        "/v1/users/me/reading-prefs",
        headers={"X-Reader-Id": "browser-2"},
        json={"font_size_px": 22, "focus_reading": True},
    )

    assert patched.status_code == 200
    payload = patched.json()
    assert payload["font_size_px"] == 22
    assert payload["focus_reading"] is True
    assert payload["theme"] == "cream-daylight"
    assert payload["line_height"] == 1.75


def test_google_callback_creates_session_and_connection(
    client: TestClient,
    integration_db,
):
    start = client.get("/v1/auth/google/start", follow_redirects=False)
    assert start.status_code == 302
    state = client.cookies.get("llm_book_google_oauth_state")
    verifier = client.cookies.get("llm_book_google_oauth_verifier")
    assert state
    assert verifier

    with patch(
        "app.routers.auth.exchange_google_authorization_code",
        AsyncMock(
            return_value=type(
                "Tokens",
                (),
                {
                    "access_token": "google-access-token",
                    "refresh_token": "google-refresh-token",
                    "expires_in": 3600,
                    "scope": "openid email profile https://www.googleapis.com/auth/cloud-platform",
                    "token_type": "Bearer",
                },
            )()
        ),
    ), patch(
        "app.routers.auth.fetch_google_userinfo",
        AsyncMock(
            return_value={
                "sub": "google-sub-123",
                "email": "reader@example.com",
                "name": "Reader Example",
            }
        ),
    ):
        callback = client.get(
            f"/v1/auth/google/callback?code=test-code&state={state}",
            follow_redirects=False,
        )

    assert callback.status_code == 302
    assert callback.headers["location"] == "http://localhost:3000/?auth=google_connected"
    assert client.cookies.get(settings.app_session_cookie_name)

    status = client.get("/v1/auth/status")
    payload = status.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "reader@example.com"
    google = next(item for item in payload["providers"] if item["provider"] == "google")
    assert google["connected"] is True
    assert google["account_email"] == "reader@example.com"

    assert integration_db.query(User).count() == 1
    connection = integration_db.query(ProviderCredential).first()
    assert connection is not None
    assert connection.provider == "google"
    assert connection.access_token_encrypted is not None
    assert connection.refresh_token_encrypted is not None


def test_google_disconnect_clears_connected_status(client: TestClient):
    start = client.get("/v1/auth/google/start", follow_redirects=False)
    state = client.cookies.get("llm_book_google_oauth_state")
    assert start.status_code == 302
    assert state

    with patch(
        "app.routers.auth.exchange_google_authorization_code",
        AsyncMock(
            return_value=type(
                "Tokens",
                (),
                {
                    "access_token": "google-access-token",
                    "refresh_token": "google-refresh-token",
                    "expires_in": 3600,
                    "scope": "openid email profile https://www.googleapis.com/auth/cloud-platform",
                    "token_type": "Bearer",
                },
            )()
        ),
    ), patch(
        "app.routers.auth.fetch_google_userinfo",
        AsyncMock(
            return_value={
                "sub": "google-sub-456",
                "email": "reader2@example.com",
                "name": "Reader Two",
            }
        ),
    ):
        client.get(
            f"/v1/auth/google/callback?code=test-code&state={state}",
            follow_redirects=False,
        )

    disconnect = client.post("/v1/auth/google/disconnect")
    assert disconnect.status_code == 200
    assert disconnect.json()["status"] == "disconnected"

    status = client.get("/v1/auth/status").json()
    google = next(item for item in status["providers"] if item["provider"] == "google")
    assert status["authenticated"] is True
    assert google["connected"] is False


def test_gemini_client_uses_bearer_auth_in_oauth_mode():
    async def run_test():
        settings.gemini_auth_mode = "oauth"

        request_capture: dict = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
                    "modelVersion": "gemini-test",
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4},
                }

        async def fake_post(self, url, params=None, headers=None, json=None):
            request_capture["url"] = url
            request_capture["params"] = params
            request_capture["headers"] = headers
            request_capture["json"] = json
            return FakeResponse()

        with patch(
            "app.providers.llm.gemini.get_google_api_auth",
            AsyncMock(return_value=type("Auth", (), {"access_token": "oauth-token", "project_id": "proj-123"})()),
        ), patch("httpx.AsyncClient.post", fake_post):
            client = GeminiClient()
            text = await client.complete([])

        assert text == "hello"
        assert request_capture["params"] is None
        assert request_capture["headers"]["Authorization"] == "Bearer oauth-token"
        assert request_capture["headers"]["x-goog-user-project"] == "proj-123"

    asyncio.run(run_test())

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.google import (
    build_google_authorization_url,
    exchange_google_authorization_code,
    fetch_google_userinfo,
    google_oauth_ready,
)
from ..auth.security import build_pkce_challenge, build_pkce_verifier
from ..auth.service import (
    GOOGLE_PROVIDER,
    clear_session_cookie,
    create_auth_session,
    disconnect_google_oauth,
    get_current_user,
    get_google_connection,
    require_current_user,
    revoke_auth_session,
    upsert_google_identity,
)
from ..db import ReadingPrefs, User, get_db
from ..settings import settings

router = APIRouter(tags=["auth"])

GOOGLE_STATE_COOKIE = "llm_book_google_oauth_state"
GOOGLE_VERIFIER_COOKIE = "llm_book_google_oauth_verifier"


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    display_name: str | None = None


class ProviderStatus(BaseModel):
    provider: str
    label: str
    configured_auth_mode: str
    oauth_supported: bool
    oauth_ready: bool
    connected: bool
    account_email: str | None = None
    connect_path: str | None = None
    note: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: AuthenticatedUser | None = None
    providers: list[ProviderStatus]


class ReadingPrefsResponse(BaseModel):
    id: str
    user_id: str
    theme: str
    font_family: str
    font_size_px: int
    line_height: float
    measure_ch: int
    focus_reading: bool
    focus_reading_intensity: int
    created_at: datetime
    updated_at: datetime


class ReadingPrefsUpdate(BaseModel):
    theme: str | None = Field(None, min_length=1, max_length=64)
    font_family: str | None = Field(None, min_length=1, max_length=64)
    font_size_px: int | None = Field(None, ge=12, le=32)
    line_height: float | None = Field(None, ge=1.3, le=2.0)
    measure_ch: int | None = Field(None, ge=40, le=90)
    focus_reading: bool | None = None
    focus_reading_intensity: int | None = Field(None, ge=0, le=100)


def _oauth_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.app_env not in {"dev", "test"},
        "max_age": 600,
        "path": "/",
    }


def _frontend_redirect(path: str) -> str:
    return f"{settings.frontend_app_url.rstrip('/')}{path}"


def _reader_id(value: str) -> str:
    reader_id = value.strip()
    if not reader_id:
        raise HTTPException(422, "X-Reader-Id must not be blank")
    return reader_id


def _get_or_create_reading_prefs(db: Session, user_id: str) -> ReadingPrefs:
    prefs = db.query(ReadingPrefs).filter(ReadingPrefs.user_id == user_id).first()
    if prefs:
        return prefs

    prefs = ReadingPrefs(user_id=user_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


def _serialize_reading_prefs(prefs: ReadingPrefs) -> ReadingPrefsResponse:
    return ReadingPrefsResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        theme=prefs.theme,
        font_family=prefs.font_family,
        font_size_px=prefs.font_size_px,
        line_height=prefs.line_height,
        measure_ch=prefs.measure_ch,
        focus_reading=prefs.focus_reading,
        focus_reading_intensity=prefs.focus_reading_intensity,
        created_at=prefs.created_at,
        updated_at=prefs.updated_at,
    )


@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    google_connection = (
        get_google_connection(db, user_id=current_user.id) if current_user else None
    )

    providers = [
        ProviderStatus(
            provider=GOOGLE_PROVIDER,
            label="Google / Gemini",
            configured_auth_mode=settings.gemini_auth_mode.lower(),
            oauth_supported=True,
            oauth_ready=google_oauth_ready(),
            connected=google_connection is not None,
            account_email=google_connection.email if google_connection else None,
            connect_path="/v1/auth/google/start" if google_oauth_ready() else None,
            note=(
                "Google OAuth is the supported no-API-key path in this app."
                if settings.gemini_auth_mode.lower() == "oauth"
                else "Gemini is currently configured for API-key mode."
            ),
        ),
        ProviderStatus(
            provider="openai",
            label="OpenAI",
            configured_auth_mode=settings.openai_auth_mode.lower(),
            oauth_supported=False,
            oauth_ready=False,
            connected=bool(settings.openai_api_key),
            note="OpenAI API key configured." if settings.openai_api_key else "Add an OpenAI API key to the server configuration.",
        ),
        ProviderStatus(
            provider="anthropic",
            label="Anthropic",
            configured_auth_mode=settings.anthropic_auth_mode.lower(),
            oauth_supported=False,
            oauth_ready=False,
            connected=bool(settings.anthropic_api_key),
            note="Anthropic API key configured." if settings.anthropic_api_key else "Add an Anthropic API key to the server configuration.",
        ),
    ]

    return AuthStatusResponse(
        authenticated=current_user is not None,
        user=(
            AuthenticatedUser(
                id=current_user.id,
                email=current_user.email,
                display_name=current_user.display_name,
            )
            if current_user
            else None
        ),
        providers=providers,
    )


@router.get("/users/me/reading-prefs", response_model=ReadingPrefsResponse)
def get_reading_prefs(
    # Until real auth owns reader identity, the browser supplies an opaque synthetic reader id.
    x_reader_id: str = Header(..., max_length=64),
    db: Session = Depends(get_db),
):
    return _serialize_reading_prefs(_get_or_create_reading_prefs(db, _reader_id(x_reader_id)))


@router.patch("/users/me/reading-prefs", response_model=ReadingPrefsResponse)
def patch_reading_prefs(
    body: ReadingPrefsUpdate,
    x_reader_id: str = Header(..., max_length=64),
    db: Session = Depends(get_db),
):
    prefs = _get_or_create_reading_prefs(db, _reader_id(x_reader_id))
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return _serialize_reading_prefs(prefs)


@router.get("/auth/google/start")
def start_google_oauth():
    if not google_oauth_ready():
        raise HTTPException(503, "Google OAuth is not configured")

    verifier = build_pkce_verifier()
    state = secrets.token_urlsafe(32)
    authorization_url = build_google_authorization_url(
        state=state,
        code_challenge=build_pkce_challenge(verifier),
    )

    response = RedirectResponse(url=authorization_url, status_code=302)
    response.set_cookie(GOOGLE_STATE_COOKIE, state, **_oauth_cookie_kwargs())
    response.set_cookie(GOOGLE_VERIFIER_COOKIE, verifier, **_oauth_cookie_kwargs())
    return response


@router.get("/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    error = request.query_params.get("error")
    if error:
        return RedirectResponse(
            url=_frontend_redirect(f"/?auth_error={error}"),
            status_code=302,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.cookies.get(GOOGLE_STATE_COOKIE)
    verifier = request.cookies.get(GOOGLE_VERIFIER_COOKIE)
    if not code or not state or not expected_state or not verifier:
        raise HTTPException(400, "Google OAuth callback is missing state or verifier")
    if state != expected_state:
        raise HTTPException(400, "Google OAuth state mismatch")

    tokens = await exchange_google_authorization_code(code=code, code_verifier=verifier)
    userinfo = await fetch_google_userinfo(tokens.access_token)
    user, _ = upsert_google_identity(db, userinfo=userinfo, tokens=tokens)

    response = RedirectResponse(
        url=_frontend_redirect("/?auth=google_connected"),
        status_code=302,
    )
    create_auth_session(db, response, user)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/")
    response.delete_cookie(GOOGLE_VERIFIER_COOKIE, path="/")
    return response


@router.post("/auth/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
):
    revoke_auth_session(db, request.cookies.get(settings.app_session_cookie_name))
    response = JSONResponse({"status": "signed_out"})
    clear_session_cookie(response)
    return response


@router.post("/auth/google/disconnect")
def disconnect_google(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    disconnect_google_oauth(db, user_id=current_user.id)
    return {"status": "disconnected"}

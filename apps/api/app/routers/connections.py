"""Settings for the locally hosted, single-owner library connection."""
import time
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..providers.llm.codex_runtime import CodexUnavailable, get_codex_runtime
from ..providers.readiness import ReadingConnection, chatgpt_status, local_status, reading_connection
from ..providers.selection import canonical_provider, select_provider
from ..rate_limit import limiter
from ..settings import settings


def settings_request(request: Request, response: Response):
    """Require a first-party browser request, including for device-code reads.

    A custom header prevents form/image requests; exact Origin validation also
    rejects them when an operator has configured permissive CORS elsewhere.
    This is CSRF protection for local hosting, not multi-user authorization.
    """
    origins = {settings.frontend_app_url.rstrip("/"), *(item.strip().rstrip("/") for item in settings.cors_origins.split(","))}
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    if request.headers.get("x-readagain-settings") != "1" or origin not in origins or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(403, "Open Settings from your library to manage this connection.")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["connections"], dependencies=[Depends(settings_request)])


class LoginResponse(BaseModel):
    login_id: str
    state: Literal["pending", "completed", "failed", "expired", "cancelled"]
    user_code: str | None = None
    verification_url: str | None = None
    expires_in: int = 0


class LoginReference(BaseModel):
    login_id: str = Field(min_length=1, max_length=128)


class ProviderSelection(BaseModel):
    provider: Literal["chatgpt", "openai", "anthropic", "gemini", "grok", "local"]


def login_response(login: dict) -> LoginResponse:
    return LoginResponse(**{key: value for key, value in login.items() if key != "deadline"}, expires_in=max(0, int(login["deadline"] - time.monotonic())))


@router.post("/providers/reading-status", response_model=ReadingConnection)
@limiter.limit("40/minute")
async def reading_status(request: Request, db: Session = Depends(get_db)):
    return await reading_connection(db)


@router.post("/auth/chatgpt/login", response_model=LoginResponse)
@limiter.limit("6/minute")
async def start_chatgpt_login(request: Request):
    try:
        return login_response(await get_codex_runtime().begin_login())
    except CodexUnavailable as error:
        raise HTTPException(503, str(error)) from None


@router.post("/auth/chatgpt/login/status", response_model=LoginResponse)
@limiter.limit("40/minute")
async def chatgpt_login_status(request: Request, body: LoginReference):
    try:
        login = await get_codex_runtime().login_status(body.login_id)
    except CodexUnavailable as error:
        raise HTTPException(503, str(error)) from None
    if login is None:
        raise HTTPException(404, "This sign-in has ended. Start again from Settings.")
    return login_response(login)


@router.post("/auth/chatgpt/login/cancel")
@limiter.limit("12/minute")
async def cancel_chatgpt_login(request: Request, body: LoginReference):
    try:
        await get_codex_runtime().cancel_login(body.login_id)
    except CodexUnavailable as error:
        raise HTTPException(503, str(error)) from None
    return {"status": "cancelled"}


@router.post("/auth/chatgpt/disconnect")
@limiter.limit("6/minute")
async def disconnect_chatgpt(request: Request):
    try:
        await get_codex_runtime().logout()
    except CodexUnavailable as error:
        raise HTTPException(503, str(error)) from None
    # Keep the chosen provider. Requiring reconnection is safer than silently
    # switching subsequent reading turns to a paid API account.
    return {"status": "disconnected"}


@router.post("/providers/active")
@limiter.limit("12/minute")
async def activate_provider(request: Request, body: ProviderSelection, db: Session = Depends(get_db)):
    provider = canonical_provider(body.provider)
    gemini_mode = settings.gemini_auth_mode.lower().strip()
    if provider == "chatgpt":
        status = await chatgpt_status()
        ready = status["connected"]
    elif provider == "local":
        ready = (await local_status()).connected
    else:
        ready = {
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            # OAuth mode has its own server credential validation on use.
            "gemini": bool(settings.gemini_api_key) if gemini_mode != "oauth" else False,
            "grok": bool(settings.grok_api_key),
        }.get(provider, False)
        if provider == "gemini" and gemini_mode == "oauth":
            from ..auth.service import get_current_user, get_google_connection
            user = get_current_user(request, db)
            ready = user is not None and get_google_connection(db, user_id=user.id) is not None
    if not ready:
        raise HTTPException(409, "Connect or configure this provider before selecting it.")
    return {"active_provider": select_provider(db, provider)}

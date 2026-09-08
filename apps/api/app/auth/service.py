from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import AuthSession, ProviderCredential, SessionLocal, User, get_db
from ..settings import settings
from .google import GoogleOAuthTokens, refresh_google_access_token
from .security import decrypt_secret, encrypt_secret, generate_session_token, hash_token


GOOGLE_PROVIDER = "google"


@dataclass
class GoogleAPIAuth:
    access_token: str
    project_id: str


def _session_expiry() -> datetime:
    return datetime.utcnow() + timedelta(hours=settings.app_session_ttl_hours)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.app_session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env not in {"dev", "test"},
        max_age=settings.app_session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.app_session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.app_env not in {"dev", "test"},
        path="/",
    )


def create_auth_session(db: Session, response: Response, user: User) -> str:
    token = generate_session_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_session_expiry(),
        )
    )
    db.commit()
    set_session_cookie(response, token)
    return token


def revoke_auth_session(db: Session, token: str | None) -> None:
    if not token:
        return
    token_hash = hash_token(token)
    db.query(AuthSession).filter(AuthSession.token_hash == token_hash).delete()
    db.commit()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    token = request.cookies.get(settings.app_session_cookie_name)
    if not token:
        return None

    now = datetime.utcnow()
    auth_session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > now,
        )
        .first()
    )
    if not auth_session:
        return None
    return auth_session.user


def require_current_user(
    current_user: User | None = Depends(get_current_user),
) -> User:
    if not current_user:
        raise HTTPException(401, "Sign in required")
    return current_user


def get_google_connection(db: Session, *, user_id: str | None = None) -> ProviderCredential | None:
    query = db.query(ProviderCredential).filter(
        ProviderCredential.provider == GOOGLE_PROVIDER,
        ProviderCredential.status == "connected",
    )
    if user_id:
        query = query.filter(ProviderCredential.user_id == user_id)
    return query.order_by(ProviderCredential.updated_at.desc()).first()


def upsert_google_identity(
    db: Session,
    *,
    userinfo: dict,
    tokens: GoogleOAuthTokens,
) -> tuple[User, ProviderCredential]:
    email = userinfo.get("email")
    sub = userinfo.get("sub")
    if not email or not sub:
        raise HTTPException(400, "Google account payload is missing email or subject")

    user = (
        db.query(User)
        .filter((User.google_sub == sub) | (User.email == email))
        .first()
    )
    if not user:
        user = User(email=email, display_name=userinfo.get("name"), google_sub=sub)
        db.add(user)
        db.flush()
    else:
        user.email = email
        user.display_name = userinfo.get("name") or user.display_name
        user.google_sub = sub

    connection = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.user_id == user.id,
            ProviderCredential.provider == GOOGLE_PROVIDER,
        )
        .first()
    )
    if not connection:
        connection = ProviderCredential(
            user_id=user.id,
            provider=GOOGLE_PROVIDER,
            auth_mode="oauth",
        )
        db.add(connection)

    connection.auth_mode = "oauth"
    connection.status = "connected"
    connection.external_user_id = sub
    connection.email = email
    connection.access_token_encrypted = encrypt_secret(tokens.access_token)
    if tokens.refresh_token:
        connection.refresh_token_encrypted = encrypt_secret(tokens.refresh_token)
    connection.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.expires_in)
    connection.scopes_json = (tokens.scope or "").split() if tokens.scope else None
    connection.meta_json = {"token_type": tokens.token_type}
    connection.is_default = True

    db.commit()
    db.refresh(user)
    db.refresh(connection)
    return user, connection


def disconnect_google_oauth(db: Session, *, user_id: str) -> None:
    connection = get_google_connection(db, user_id=user_id)
    if not connection:
        return
    connection.status = "disconnected"
    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.token_expires_at = None
    connection.meta_json = None
    db.commit()


async def get_google_api_auth() -> GoogleAPIAuth:
    if settings.gemini_auth_mode.lower() != "oauth":
        raise ValueError("Gemini OAuth mode is not enabled")
    if not settings.google_oauth_project_id:
        raise ValueError("GOOGLE_OAUTH_PROJECT_ID is required for Gemini OAuth mode")

    with SessionLocal() as db:
        connection = get_google_connection(db)
        if not connection:
            raise ValueError("Google OAuth connection not configured")

        if (
            connection.access_token_encrypted
            and connection.token_expires_at
            and connection.token_expires_at > datetime.utcnow() + timedelta(minutes=5)
        ):
            return GoogleAPIAuth(
                access_token=decrypt_secret(connection.access_token_encrypted),
                project_id=settings.google_oauth_project_id,
            )

        if not connection.refresh_token_encrypted:
            raise ValueError("Google OAuth refresh token not available")

        refresh_token = decrypt_secret(connection.refresh_token_encrypted)
        connection_id = connection.id

    refreshed = await refresh_google_access_token(refresh_token=refresh_token)

    with SessionLocal() as db:
        connection = (
            db.query(ProviderCredential)
            .filter(ProviderCredential.id == connection_id)
            .first()
        )
        if not connection:
            raise ValueError("Google OAuth connection disappeared during refresh")
        connection.access_token_encrypted = encrypt_secret(refreshed.access_token)
        if refreshed.refresh_token:
            connection.refresh_token_encrypted = encrypt_secret(refreshed.refresh_token)
        connection.token_expires_at = datetime.utcnow() + timedelta(seconds=refreshed.expires_in)
        connection.scopes_json = (refreshed.scope or "").split() if refreshed.scope else connection.scopes_json
        connection.meta_json = {"token_type": refreshed.token_type}
        db.commit()

    return GoogleAPIAuth(
        access_token=refreshed.access_token,
        project_id=settings.google_oauth_project_id,
    )

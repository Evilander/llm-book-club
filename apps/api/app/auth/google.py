from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from ..settings import settings


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass
class GoogleOAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None = None
    token_type: str | None = None


def google_oauth_scopes() -> list[str]:
    return [scope for scope in settings.google_oauth_scopes.split() if scope]


def google_oauth_ready() -> bool:
    return all(
        [
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_redirect_uri,
            settings.google_oauth_project_id,
        ]
    )


def build_google_authorization_url(*, state: str, code_challenge: str) -> str:
    if not google_oauth_ready():
        raise ValueError("Google OAuth is not configured")

    params = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(google_oauth_scopes()),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{params}"


async def exchange_google_authorization_code(
    *,
    code: str,
    code_verifier: str,
) -> GoogleOAuthTokens:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
    return GoogleOAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in", 3600),
        scope=payload.get("scope"),
        token_type=payload.get("token_type"),
    )


async def refresh_google_access_token(*, refresh_token: str) -> GoogleOAuthTokens:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
    return GoogleOAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in", 3600),
        scope=payload.get("scope"),
        token_type=payload.get("token_type"),
    )


async def fetch_google_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()

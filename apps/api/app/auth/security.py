from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet

from ..settings import settings


def _fernet() -> Fernet:
    key_material = hashlib.sha256(settings.auth_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def build_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

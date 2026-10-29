"""Authentication, password hashing, session tokens and authorization guards.

No third-party crypto dependency is required: passwords use PBKDF2-HMAC-SHA256
with a per-user random salt, and session tokens are signed JSON payloads (HMAC).
This keeps the platform runnable offline with only the standard library while
remaining structurally identical to a JWT-based production setup.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .constants import Role
from .db import get_db
from .models import User

log = logging.getLogger("agrosphere.security")

ENVIRONMENT = os.getenv("AGROSPHERE_ENV", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}
MIN_SECRET_LENGTH = 32


def _resolve_secret_key() -> str:
    """Return the token-signing key, refusing to start insecurely in production.

    A predictable signing key lets anyone mint a token for any account, so a
    production deploy with no key configured must fail loudly rather than fall
    back to a shared default. In development we generate a random key once and
    persist it, so tokens survive a reload without shipping a known secret.
    """
    configured = os.getenv("AGROSPHERE_SECRET_KEY", "").strip()
    if configured:
        if IS_PRODUCTION and len(configured) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"AGROSPHERE_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters "
                "in production."
            )
        return configured

    if IS_PRODUCTION:
        raise RuntimeError(
            "AGROSPHERE_SECRET_KEY is required when AGROSPHERE_ENV=production.\n"
            "Generate one with:\n"
            '  python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    key_file = Path(
        os.getenv("AGROSPHERE_SECRET_FILE", Path(__file__).resolve().parents[1] / ".dev-secret")
    )
    if key_file.exists():
        persisted = key_file.read_text(encoding="utf-8").strip()
        if persisted:
            return persisted

    generated = secrets.token_urlsafe(48)
    try:
        key_file.write_text(generated, encoding="utf-8")
        key_file.chmod(0o600)
    except OSError:  # read-only filesystem: keep the key in memory for this process
        pass
    log.warning(
        "Generated a development signing key at %s. "
        "Set AGROSPHERE_SECRET_KEY before deploying.",
        key_file,
    )
    return generated


SECRET_KEY = _resolve_secret_key()
TOKEN_TTL_SECONDS = int(os.getenv("AGROSPHERE_TOKEN_TTL_SECONDS", 60 * 60 * 12))
_PBKDF2_ROUNDS = 240_000

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, encoded = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(digest, base64.b64decode(encoded))
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "email": user.email,
        # Sessions are stamped with the account's credential epoch. Bumping the
        # epoch (password reset, forced logout) makes every previously issued
        # token fail validation, without a server-side session table.
        "ep": user.session_epoch or 0,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_token(token: str) -> dict:
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from exc


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    user = db.get(User, payload["sub"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account inactive")
    # A token minted before the account's last credential change is stale.
    if payload.get("ep", 0) != (user.session_epoch or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        )
    return user


def require_roles(*roles: Role):
    """Dependency factory enforcing server-side role-based access control."""

    allowed = {r.value for r in roles}

    def _guard(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted for this operation",
            )
        return user

    return _guard

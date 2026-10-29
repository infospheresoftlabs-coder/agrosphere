"""Password reset: token issuing, single-use consumption and credential change.

A reset token is generated as 256 bits of entropy and only its SHA-256 is
persisted, so reading the database does not yield anything replayable. Tokens
expire, are single-use, and issuing a new one invalidates the account's previous
unused tokens so a stale email cannot be used later.

Every mutation here also bumps ``User.session_epoch``, which invalidates sessions
minted before the change (see ``security.decode_token``). A password reset must
evict an attacker who already holds a token, otherwise "reset your password"
would not actually lock them out.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import PasswordResetToken, User
from ..security import hash_password

RESET_TTL_MINUTES = 30


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def issue_reset_token(
    db: Session, user: User, *, requested_by: str | None = None
) -> tuple[str, PasswordResetToken]:
    """Invalidate any outstanding tokens and mint a fresh single-use one."""
    now = _now()
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw),
        expires_at=now + dt.timedelta(minutes=RESET_TTL_MINUTES),
        requested_by=requested_by,
    )
    db.add(token)
    db.flush()
    return raw, token


def resolve_reset_token(db: Session, raw: str) -> PasswordResetToken | None:
    """Return the token row if it is still redeemable, else None."""
    token = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(raw))
    ).scalars().first()
    if token is None or token.used_at is not None:
        return None
    if token.expires_at < _now():
        return None
    return token


def set_password(db: Session, user: User, new_password: str) -> None:
    """Change the credential and evict every existing session for the account."""
    user.password_hash = hash_password(new_password)
    user.session_epoch = (user.session_epoch or 0) + 1
    db.flush()


def consume_reset_token(db: Session, token: PasswordResetToken) -> None:
    token.used_at = _now()
    db.flush()

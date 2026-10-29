"""Outbound email for transactional messages such as password resets.

Sending is optional: when SMTP is not configured the message is logged and the
caller is told delivery did not happen, so no code path can claim an email was
sent when it was not. Configure with:

    AGROSPHERE_SMTP_HOST, AGROSPHERE_SMTP_PORT (default 587)
    AGROSPHERE_SMTP_USER, AGROSPHERE_SMTP_PASSWORD
    AGROSPHERE_SMTP_FROM (default no-reply@agrosphere.app)
    AGROSPHERE_SMTP_TLS  (default true; set false for a plaintext relay)
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("agrosphere.mail")


def smtp_configured() -> bool:
    return bool(os.getenv("AGROSPHERE_SMTP_HOST", "").strip())


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def send_email(*, to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns False when SMTP is unconfigured."""
    if not smtp_configured():
        # Not an error: the deployment may rely on in-app delivery or a CLI.
        log.warning("SMTP not configured; email to %s was not sent", to)
        return False

    host = os.getenv("AGROSPHERE_SMTP_HOST", "").strip()
    port = int(os.getenv("AGROSPHERE_SMTP_PORT", "587") or 587)
    user = os.getenv("AGROSPHERE_SMTP_USER", "").strip()
    password = os.getenv("AGROSPHERE_SMTP_PASSWORD", "")
    sender = os.getenv("AGROSPHERE_SMTP_FROM", "no-reply@agrosphere.app").strip()
    use_tls = _bool("AGROSPHERE_SMTP_TLS", True)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # network, auth or relay rejection
        log.error("SMTP delivery to %s failed: %s", to, exc)
        return False


def send_password_reset(*, to: str, full_name: str, reset_url: str, ttl_minutes: int) -> bool:
    body = (
        f"Hello {full_name},\n\n"
        "A password reset was requested for your AgroSphere account.\n"
        f"Open this link to choose a new password (valid for {ttl_minutes} minutes):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this message; your password "
        "will not change.\n\n"
        "— AgroSphere\n"
    )
    return send_email(to=to, subject="Reset your AgroSphere password", body=body)

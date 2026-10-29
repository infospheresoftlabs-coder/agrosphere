"""Outbound SMS and WhatsApp dispatch, and phone-number normalisation.

Delivery is optional and never claimed when it did not happen: with no provider
configured the call reports ``delivered: False`` and a reason, so no code path
can tell a farmer a message was sent when it was not. Configure a Twilio account
to enable real dispatch:

    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    TWILIO_WHATSAPP_FROM   (e.g. whatsapp:+14155238886)
    TWILIO_SMS_FROM        (e.g. +14155550123)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("agrosphere.messaging")

# India is the default home market; a bare 10-digit mobile is a domestic number.
_DEFAULT_COUNTRY_CODE = "91"
_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str | None, *, country_code: str = _DEFAULT_COUNTRY_CODE) -> str | None:
    """Return an E.164 number, or ``None`` when the input cannot be one.

    Accepts ``+91 98765 43210``, ``09876543210`` and ``9876543210`` alike. A bare
    ten-digit number that starts with 6-9 is treated as an Indian mobile; anything
    else must carry an explicit country code.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    has_plus = text.startswith("+")
    digits = _DIGITS.sub("", text)
    if not digits:
        return None
    if has_plus:
        candidate = digits
    elif len(digits) == 10 and digits[0] in "6789":
        candidate = country_code + digits
    elif len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        candidate = country_code + digits[1:]
    else:
        candidate = digits
    # E.164 allows at most 15 digits including the country code.
    if not (8 <= len(candidate) <= 15):
        return None
    return "+" + candidate


def _config() -> dict:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    return {
        "sid": sid,
        "token": token,
        "whatsapp_from": os.getenv("TWILIO_WHATSAPP_FROM", "").strip(),
        "sms_from": os.getenv("TWILIO_SMS_FROM", "").strip(),
    }


def messaging_status() -> dict:
    cfg = _config()
    has_auth = bool(cfg["sid"] and cfg["token"])
    sms = has_auth and bool(cfg["sms_from"])
    whatsapp = has_auth and bool(cfg["whatsapp_from"])
    if not has_auth:
        note = ("No messaging provider is configured; SMS and WhatsApp are recorded "
                "in-app only. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to enable dispatch.")
    elif not (sms or whatsapp):
        note = "Twilio is configured but no sender number is set (TWILIO_SMS_FROM / TWILIO_WHATSAPP_FROM)."
    else:
        channels = ", ".join(c for c, on in (("SMS", sms), ("WhatsApp", whatsapp)) if on)
        note = f"Live dispatch enabled for {channels}."
    return {
        "provider": "twilio" if has_auth else "none",
        "sms": sms,
        "whatsapp": whatsapp,
        "note": note,
    }


def _post_twilio(cfg: dict, *, from_number: str, to: str, body: str) -> tuple[bool, str]:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg['sid']}/Messages.json"
    data = urllib.parse.urlencode({"From": from_number, "To": to, "Body": body}).encode()
    auth = base64.b64encode(f"{cfg['sid']}:{cfg['token']}".encode()).decode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode() or "{}")
        return True, payload.get("sid", "sent")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        log.error("Twilio dispatch to %s failed: %s %s", to, exc.code, detail)
        return False, f"provider rejected the message ({exc.code})"
    except Exception as exc:  # network or encoding failure
        log.error("Twilio dispatch to %s failed: %s", to, exc)
        return False, f"dispatch failed: {exc}"


def dispatch(to: str | None, body: str, *, channel: str = "whatsapp") -> dict:
    """Send ``body`` to ``to`` over ``channel`` (``whatsapp`` or ``sms``).

    Returns a result dict that states plainly whether the message was delivered
    by a provider, so the caller can record honest delivery evidence.
    """
    channel = (channel or "whatsapp").strip().lower()
    if channel not in {"whatsapp", "sms"}:
        channel = "whatsapp"
    number = normalize_phone(to)
    if not number:
        return {"delivered": False, "channel": channel, "provider": "none",
                "reason": "No valid phone number is stored for this account."}

    cfg = _config()
    if channel == "whatsapp":
        from_number = cfg["whatsapp_from"]
        if not (cfg["sid"] and cfg["token"] and from_number):
            return {"delivered": False, "channel": channel, "provider": "none",
                    "reason": "WhatsApp dispatch is not configured on the server."}
        if not from_number.startswith("whatsapp:"):
            from_number = "whatsapp:" + from_number
        dest = number if number.startswith("whatsapp:") else "whatsapp:" + number
    else:
        from_number = cfg["sms_from"]
        if not (cfg["sid"] and cfg["token"] and from_number):
            return {"delivered": False, "channel": channel, "provider": "none",
                    "reason": "SMS dispatch is not configured on the server."}
        dest = number

    ok, evidence = _post_twilio(cfg, from_number=from_number, to=dest, body=body)
    return {"delivered": ok, "channel": channel, "provider": "twilio",
            "to": number, "evidence": evidence,
            "reason": None if ok else evidence}

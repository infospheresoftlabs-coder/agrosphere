"""Cross-cutting services: audit trail, notifications, workflow engine, payments."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import ROLE_LABELS, STATE_OWNER, TRANSITIONS, CaseState, Role
from ..models import (
    AuditEvent,
    Case,
    IdempotencyRecord,
    Invoice,
    Notification,
    Transaction,
    User,
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Audit trail (tamper-evident hash chain)
# --------------------------------------------------------------------------- #
def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    # Flush pending events first: the session disables autoflush, so without this
    # a second audit event in the same transaction would chain off a stale head.
    db.flush()
    prev = db.execute(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1)).scalars().first()
    prev_hash = prev.hash if prev else "0" * 64
    # Naive UTC so the value round-trips identically through the database and the
    # hash can be re-derived during verification.
    stamp = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    payload = {
        "actor": actor.id if actor else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "detail": detail or {},
        "prev": prev_hash,
        "ts": stamp.isoformat(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    event = AuditEvent(
        actor_id=actor.id if actor else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail or {},
        prev_hash=prev_hash,
        hash=digest,
        created_at=stamp,
    )
    db.add(event)
    return event


def verify_audit_chain(db: Session) -> dict:
    events = (
        db.execute(select(AuditEvent).order_by(AuditEvent.created_at.asc())).scalars().all()
    )
    prev = "0" * 64
    for ev in events:
        payload = {
            "actor": ev.actor_id,
            "action": ev.action,
            "entity": ev.entity,
            "entity_id": ev.entity_id,
            "detail": ev.detail or {},
            "prev": prev,
            "ts": ev.created_at.isoformat() if ev.created_at else "",
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        if ev.prev_hash != prev or ev.hash != digest:
            return {"valid": False, "broken_at": ev.id}
        prev = ev.hash
    return {"valid": True, "events": len(events)}


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
def notify(
    db: Session,
    *,
    user_id: str,
    title: str,
    body: str,
    category: str = "system",
    delivered: bool = False,
    delivery_evidence: str | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        title=title,
        body=body,
        category=category,
        delivered=delivered,
        delivery_evidence=delivery_evidence,
    )
    db.add(n)
    return n


# --------------------------------------------------------------------------- #
# Workflow engine
# --------------------------------------------------------------------------- #
def transition_case(
    db: Session,
    case: Case,
    to_state: CaseState,
    actor: User,
    reason: str | None = None,
    *,
    allow_admin: bool = True,
) -> Case:
    """Validate and apply a state transition with role enforcement."""
    from_state = CaseState(case.state)
    allowed = TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal transition {from_state.value} -> {to_state.value}",
        )

    owner = STATE_OWNER.get(to_state)
    if actor.role != owner.value and not (allow_admin and actor.role == Role.SUPER_ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Only {ROLE_LABELS.get(owner, owner)} may move a case to "
                f"'{to_state.value}'"
            ),
        )

    case.state = to_state.value
    record_audit(
        db,
        actor=actor,
        action="case.transition",
        entity="case",
        entity_id=case.id,
        detail={"from": from_state.value, "to": to_state.value, "reason": reason},
    )
    return case


# --------------------------------------------------------------------------- #
# Idempotency for sensitive operations
# --------------------------------------------------------------------------- #
def idempotent(db: Session, key: str | None, endpoint: str) -> dict | None:
    if not key:
        return None
    existing = db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.key == key)
    ).scalars().first()
    if existing and existing.response is not None:
        return existing.response
    return None


def store_idempotent(db: Session, key: str | None, endpoint: str, response: dict) -> None:
    if not key:
        return
    existing = db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.key == key)
    ).scalars().first()
    if existing:
        existing.response = response
        existing.endpoint = endpoint
    else:
        db.add(IdempotencyRecord(key=key, endpoint=endpoint, response=response))


# --------------------------------------------------------------------------- #
# Payments (provider-independent; Razorpay-shaped sandbox)
# --------------------------------------------------------------------------- #
SANDBOX_WEBHOOK_SECRET = "agrosphere_sandbox_secret"


def create_invoice(db: Session, case: Case, amount: float, tax_pct: float = 18.0) -> Invoice:
    tax = round(amount * tax_pct / 100.0, 2)
    inv = Invoice(
        case_id=case.id,
        number="INV-" + secrets.token_hex(4).upper(),
        amount=round(amount, 2),
        tax=tax,
        total=round(amount + tax, 2),
        status="pending",
    )
    db.add(inv)
    return inv


def sign_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(SANDBOX_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def verify_webhook(payload: dict, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(payload), signature)


def record_payment(
    db: Session,
    *,
    invoice: Invoice,
    kind: str,
    amount: float,
    idempotency_key: str | None,
    signature_verified: bool,
    detail: dict | None = None,
) -> Transaction:
    tx = Transaction(
        invoice_id=invoice.id,
        kind=kind,
        amount=amount,
        status="succeeded",
        idempotency_key=idempotency_key,
        signature_verified=signature_verified,
        detail=detail or {},
    )
    db.add(tx)
    if kind == "payment":
        invoice.status = "paid"
        invoice.payment_ref = "pay_" + secrets.token_hex(6)
    elif kind == "refund":
        invoice.status = "refunded"
    return tx

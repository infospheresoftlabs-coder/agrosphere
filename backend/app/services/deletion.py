"""Cascading, FK-safe deletion of operational records.

Farms, cases, media, drones, grievances and notifications are referenced by
child rows through foreign keys that PostgreSQL enforces, so removing a parent
means removing its whole subtree in the right order. Each function here resolves
the subtree, deletes children before parents, re-seals the audit chain when it
has de-identified an actor, and records the deletion itself so the trail explains
what happened. None of them commits: the caller owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Analysis,
    Case,
    CostEstimate,
    DroneDevice,
    Farm,
    Field,
    Grievance,
    Invoice,
    Job,
    LiveSession,
    LocationPing,
    MediaAsset,
    Notification,
    Review,
    Transaction,
    TreatmentPlan,
    User,
)
from .core import record_audit


@dataclass
class DeletionResult:
    """A record of what a delete removed, for the audit trail and the response."""

    entity: str
    id: str
    label: str
    removed: dict[str, int]

    @property
    def removed_total(self) -> int:
        return sum(self.removed.values())

    def as_detail(self) -> dict:
        return {"label": self.label, "removed": self.removed,
                "removed_total": self.removed_total}


def _ids(db: Session, model, column, values) -> list[str]:
    if values is None or (isinstance(values, (list, tuple, set)) and not values):
        return []
    return list(db.execute(select(model.id).where(column.in_(values))).scalars().all())


def _delete_ids(db: Session, model, ids: list[str]) -> int:
    if not ids:
        return 0
    db.execute(delete(model).where(model.id.in_(ids)))
    return len(ids)


def delete_case(db: Session, case: Case, *, actor: User | None = None) -> DeletionResult:
    """Delete a crop-health case and every child row that hangs off it."""
    removed: dict[str, int] = {}
    plan_ids = _ids(db, TreatmentPlan, TreatmentPlan.case_id, [case.id])
    invoice_ids = _ids(db, Invoice, Invoice.case_id, [case.id])
    job_ids = _ids(db, Job, Job.case_id, [case.id])
    removed["transactions"] = _delete_ids(
        db, Transaction, _ids(db, Transaction, Transaction.invoice_id, invoice_ids))
    removed["cost_estimates"] = _delete_ids(
        db, CostEstimate, _ids(db, CostEstimate, CostEstimate.plan_id, plan_ids))
    removed["reviews"] = _delete_ids(db, Review, _ids(db, Review, Review.case_id, [case.id]))
    removed["analyses"] = _delete_ids(db, Analysis, _ids(db, Analysis, Analysis.case_id, [case.id]))
    removed["jobs"] = _delete_ids(db, Job, job_ids)
    removed["invoices"] = _delete_ids(db, Invoice, invoice_ids)
    removed["treatment_plans"] = _delete_ids(db, TreatmentPlan, plan_ids)
    removed["live_sessions"] = _delete_ids(
        db, LiveSession, _ids(db, LiveSession, LiveSession.case_id, [case.id]))
    removed["cases"] = _delete_ids(db, Case, [case.id])
    result = DeletionResult("case", case.id, case.reference, removed)
    _record(db, actor, "case.deleted", "case", case.id, result)
    return result


def delete_field(db: Session, field: Field, *, actor: User | None = None) -> DeletionResult:
    """Delete a field, its media and every case recorded against it."""
    removed: dict[str, int] = {}
    case_ids = _ids(db, Case, Case.field_id, [field.id])
    removed["media_assets"] = _delete_ids(
        db, MediaAsset, _ids(db, MediaAsset, MediaAsset.field_id, [field.id]))
    removed["location_pings"] = _delete_ids(
        db, LocationPing, _ids(db, LocationPing, LocationPing.field_id, [field.id]))
    removed["live_sessions"] = _delete_ids(
        db, LiveSession, _ids(db, LiveSession, LiveSession.field_id, [field.id]))
    for cid in case_ids:
        case = db.get(Case, cid)
        if case:
            child = delete_case(db, case, actor=actor)
            for k, v in child.removed.items():
                removed[k] = removed.get(k, 0) + v
    removed["fields"] = _delete_ids(db, Field, [field.id])
    result = DeletionResult("field", field.id, field.name, removed)
    _record(db, actor, "field.deleted", "field", field.id, result)
    return result


def delete_farm(db: Session, farm: Farm, *, actor: User | None = None) -> DeletionResult:
    """Delete a farm with its fields, cases, media and downstream records."""
    removed: dict[str, int] = {}
    field_ids = _ids(db, Field, Field.farm_id, [farm.id])
    removed["location_pings"] = _delete_ids(
        db, LocationPing, _ids(db, LocationPing, LocationPing.farm_id, [farm.id]))
    removed["live_sessions"] = _delete_ids(
        db, LiveSession, _ids(db, LiveSession, LiveSession.farm_id, [farm.id]))
    for fid in field_ids:
        field = db.get(Field, fid)
        if field:
            child = delete_field(db, field, actor=actor)
            for k, v in child.removed.items():
                removed[k] = removed.get(k, 0) + v
    removed["farms"] = _delete_ids(db, Farm, [farm.id])
    result = DeletionResult("farm", farm.id, farm.name, removed)
    _record(db, actor, "farm.deleted", "farm", farm.id, result)
    return result


def delete_media(db: Session, asset: MediaAsset, *, actor: User | None = None) -> DeletionResult:
    result = DeletionResult("media", asset.id, asset.filename, {"media_assets": _delete_ids(db, MediaAsset, [asset.id])})
    _record(db, actor, "media.deleted", "media", asset.id, result)
    return result


def delete_drone(db: Session, device: DroneDevice, *, actor: User | None = None) -> DeletionResult:
    removed: dict[str, int] = {}
    # A job may reference the device; keep the job but clear the device slot.
    job_ids = _ids(db, Job, Job.device_id, [device.id])
    if job_ids:
        db.execute(
            Job.__table__.update().where(Job.id.in_(job_ids)).values(device_id=None)
        )
    removed["drone_devices"] = _delete_ids(db, DroneDevice, [device.id])
    result = DeletionResult("drone", device.id, f"{device.model} ({device.serial})", removed)
    _record(db, actor, "drone.deleted", "drone", device.id, result)
    return result


def delete_grievance(db: Session, grievance: Grievance, *, actor: User | None = None) -> DeletionResult:
    result = DeletionResult("grievance", grievance.id, grievance.ticket,
                            {"grievances": _delete_ids(db, Grievance, [grievance.id])})
    _record(db, actor, "grievance.deleted", "grievance", grievance.id, result)
    return result


def delete_notification(db: Session, notification: Notification, *, actor: User | None = None) -> DeletionResult:
    result = DeletionResult("notification", notification.id, notification.title,
                            {"notifications": _delete_ids(db, Notification, [notification.id])})
    _record(db, actor, "notification.deleted", "notification", notification.id, result)
    return result


# Order matters: children before parents across the whole schema.
_PURGE_ORDER: tuple[tuple[str, type], ...] = (
    ("transactions", Transaction),
    ("cost_estimates", CostEstimate),
    ("reviews", Review),
    ("analyses", Analysis),
    ("jobs", Job),
    ("invoices", Invoice),
    ("treatment_plans", TreatmentPlan),
    ("media_assets", MediaAsset),
    ("cases", Case),
    ("location_pings", LocationPing),
    ("live_sessions", LiveSession),
    ("fields", Field),
    ("farms", Farm),
    ("drone_devices", DroneDevice),
    ("grievances", Grievance),
    ("notifications", Notification),
)


def purge_operational_data(db: Session, *, actor: User | None = None) -> DeletionResult:
    """Delete all app-captured operational data, keeping accounts and knowledge.

    User accounts, the verified knowledge base, products and feature flags are
    preserved so the platform stays usable and its reference data is not lost;
    every record captured *about* a farm, field, crop-health case, mission,
    payment, notification or support ticket is removed.
    """
    removed: dict[str, int] = {}
    for name, model in _PURGE_ORDER:
        count = db.execute(delete(model)).rowcount or 0
        if count:
            removed[name] = int(count)
    # Accounts and their audit events survive a purge, so no actor id changes and
    # the hash chain is left intact.
    result = DeletionResult("all", "*", "All operational data", removed)
    _record(db, actor, "data.purged", "system", None, result)
    return result


def _record(db: Session, actor: User | None, action: str, entity: str,
            entity_id: str | None, result: DeletionResult) -> None:
    record_audit(db, actor=actor, action=action, entity=entity, entity_id=entity_id,
                 detail=result.as_detail())

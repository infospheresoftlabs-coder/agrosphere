"""Account lifecycle: FK-safe deletion of users and the data they own.

Fifteen foreign keys reference ``users.id``, so a plain ``DELETE`` fails on any
database that enforces them (PostgreSQL does; SQLite does not by default, which
is why a naive delete can look fine locally and fail in production). Deleting an
account therefore has to decide, per reference, whether the row is *owned* by the
user and should be removed with them, or merely *mentions* the user and should
be reassigned or de-identified so the record survives.

Owned rows (deleted):
    farms, fields, cases and their analyses/reviews/plans/costs/jobs/invoices,
    transactions, media assets, notifications, grievances, drone devices.

Mentioned rows (reassigned to the acting administrator, or de-identified):
    case.agronomist_id / manager_id, farm.manager_id, plan.agronomist_id,
    review.agronomist_id, cost_estimate.manager_id, job.operator_id,
    grievance.owner_id, audit_event.actor_id.

De-identifying an audit event changes the value the hash chain commits to, so the
chain is re-sealed afterwards; the deletion itself is recorded as a new event.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import (
    Analysis,
    AuditEvent,
    Case,
    CostEstimate,
    DroneDevice,
    Farm,
    Field,
    Grievance,
    Invoice,
    Job,
    MediaAsset,
    Notification,
    Review,
    Transaction,
    TreatmentPlan,
    User,
)
from .core import record_audit, reseal_audit_chain


@dataclass
class DeletionPlan:
    """What a deletion would touch, resolved before anything is written."""

    user_id: str
    email: str
    role: str
    owned: dict[str, list[str]] = field(default_factory=dict)
    reassigned: dict[str, int] = field(default_factory=dict)
    deidentified: dict[str, int] = field(default_factory=dict)
    # References that are NOT NULL in the schema: they cannot be cleared, so
    # deleting the user who holds them requires an explicit replacement account.
    requires_actor: list[str] = field(default_factory=list)

    @property
    def owned_total(self) -> int:
        return sum(len(ids) for ids in self.owned.values())

    def describe(self, has_replacement: bool = False) -> str:
        lines = [
            f"user      : {self.email} ({self.role})",
            f"id        : {self.user_id}",
            f"owned rows: {self.owned_total}",
        ]
        for table, ids in sorted(self.owned.items()):
            lines.append(f"    - {table}: {len(ids)}")
        if self.reassigned:
            target = "reassign to replacement account:" if has_replacement else "reassign  :"
            lines.append(target)
            for table, n in sorted(self.reassigned.items()):
                lines.append(f"    - {table}: {n}")
        if self.deidentified:
            lines.append("de-identify:")
            for table, n in sorted(self.deidentified.items()):
                lines.append(f"    - {table}: {n}")
        if self.requires_actor and not has_replacement:
            lines.append("NOT NULL, needs --reassign-to:")
            for label in sorted(self.requires_actor):
                lines.append(f"    ! {label}")
        return "\n".join(lines)


# References to a user that outlive them. The trailing key names the ``owned``
# bucket holding rows of the same table that are deleted with the user, so those
# references are excluded from the reassignment footprint. Nullability is read
# from the column: a NOT NULL reference cannot be set to NULL, so it must be
# handed to a replacement account rather than cleared.
REASSIGN_REFS: tuple[tuple[str, type, object, str], ...] = (
    ("case.agronomist_id", Case, Case.agronomist_id, "cases"),
    ("case.manager_id", Case, Case.manager_id, "cases"),
    ("farm.manager_id", Farm, Farm.manager_id, "farms"),
    ("plan.agronomist_id", TreatmentPlan, TreatmentPlan.agronomist_id, "treatment_plans"),
    ("review.agronomist_id", Review, Review.agronomist_id, "reviews"),
    ("cost_estimate.manager_id", CostEstimate, CostEstimate.manager_id, "cost_estimates"),
    ("job.operator_id", Job, Job.operator_id, "jobs"),
    ("grievance.owner_id", Grievance, Grievance.owner_id, "grievances"),
    ("media_asset.uploaded_by", MediaAsset, MediaAsset.uploaded_by, "media_assets"),
)


def _ids(db: Session, model, column, value) -> list[str]:
    return list(db.execute(select(model.id).where(column == value)).scalars().all())


def _surviving_ids(db: Session, model, column, user_id: str, owned: list[str]) -> list[str]:
    """Ids of rows referencing ``user_id`` that are NOT themselves being deleted."""
    stmt = select(model.id).where(column == user_id)
    if owned:
        stmt = stmt.where(model.id.notin_(owned))
    return list(db.execute(stmt).scalars().all())


def plan_deletion(db: Session, user: User) -> DeletionPlan:
    """Resolve every row a deletion would affect, without writing anything."""
    plan = DeletionPlan(user_id=user.id, email=user.email, role=user.role)

    case_ids = _ids(db, Case, Case.farmer_id, user.id)
    farm_ids = _ids(db, Farm, Farm.owner_id, user.id)
    field_ids = list(
        db.execute(select(Field.id).where(Field.farm_id.in_(farm_ids))).scalars().all()
    ) if farm_ids else []
    # Cases can also hang off fields the user owns without naming them as farmer.
    if field_ids:
        case_ids = sorted(
            set(case_ids)
            | set(db.execute(select(Case.id).where(Case.field_id.in_(field_ids))).scalars().all())
        )
    plan_ids = list(
        db.execute(select(TreatmentPlan.id).where(TreatmentPlan.case_id.in_(case_ids))).scalars().all()
    ) if case_ids else []
    invoice_ids = list(
        db.execute(select(Invoice.id).where(Invoice.case_id.in_(case_ids))).scalars().all()
    ) if case_ids else []

    owned: dict[str, list[str]] = {}
    if farm_ids:
        owned["farms"] = farm_ids
    if field_ids:
        owned["fields"] = field_ids
    if case_ids:
        owned["cases"] = case_ids
    if plan_ids:
        owned["treatment_plans"] = plan_ids
    if invoice_ids:
        owned["invoices"] = invoice_ids

    def _children(name: str, model, column, parents: list[str]) -> None:
        if not parents:
            return
        ids = list(db.execute(select(model.id).where(column.in_(parents))).scalars().all())
        if ids:
            owned[name] = ids

    _children("analyses", Analysis, Analysis.case_id, case_ids)
    _children("reviews", Review, Review.case_id, case_ids)
    _children("jobs", Job, Job.case_id, case_ids)
    _children("cost_estimates", CostEstimate, CostEstimate.plan_id, plan_ids)
    _children("transactions", Transaction, Transaction.invoice_id, invoice_ids)
    _children("media_assets", MediaAsset, MediaAsset.field_id, field_ids)

    for name, model, column in (
        ("notifications", Notification, Notification.user_id),
        ("grievances", Grievance, Grievance.user_id),
        ("drone_devices", DroneDevice, DroneDevice.operator_id),
    ):
        ids = _ids(db, model, column, user.id)
        if ids:
            owned[name] = ids
    plan.owned = owned

    # References that outlive the user: count only rows that survive the deletion,
    # and note which cannot be cleared because the column is NOT NULL.
    for label, model, column, owned_key in REASSIGN_REFS:
        ids = _surviving_ids(db, model, column, user.id, plan.owned.get(owned_key, []))
        if ids:
            plan.reassigned[label] = len(ids)
            if not column.nullable:
                plan.requires_actor.append(label)
    n_audit = len(_ids(db, AuditEvent, AuditEvent.actor_id, user.id))
    if n_audit:
        plan.deidentified["audit_event.actor_id"] = n_audit
    return plan


def delete_user(db: Session, user: User, *, actor: User | None = None) -> DeletionPlan:
    """Delete a user and everything they own, FK-safe and audit-recorded.

    Runs in the caller's transaction: commit is the caller's decision.
    """
    plan = plan_deletion(db, user)
    if plan.requires_actor and actor is None:
        raise ValueError(
            "these references are NOT NULL and need a replacement account "
            f"(--reassign-to): {', '.join(sorted(plan.requires_actor))}"
        )

    # De-identify rather than reassign the audit trail: reassigning a deleted
    # account's events to a living administrator would be a lie in the record.
    db.execute(
        update(AuditEvent).where(AuditEvent.actor_id == user.id).values(actor_id=None)
    )

    # Hand surviving references to the replacement account, or clear them when
    # the column allows NULL. Rows being deleted with the user are skipped.
    keeper = actor.id if actor else None
    for label, model, column, owned_key in REASSIGN_REFS:
        if label not in plan.reassigned:
            continue
        stmt = update(model).where(column == user.id)
        owned = plan.owned.get(owned_key)
        if owned:
            stmt = stmt.where(model.id.notin_(owned))
        db.execute(stmt.values({column.key: keeper}))

    # Owned rows, children before parents.
    order = [
        ("transactions", Transaction),
        ("cost_estimates", CostEstimate),
        ("reviews", Review),
        ("analyses", Analysis),
        ("jobs", Job),
        ("invoices", Invoice),
        ("treatment_plans", TreatmentPlan),
        ("media_assets", MediaAsset),
        ("cases", Case),
        ("fields", Field),
        ("farms", Farm),
        ("notifications", Notification),
        ("grievances", Grievance),
        ("drone_devices", DroneDevice),
    ]
    for name, model in order:
        ids = plan.owned.get(name)
        if ids:
            db.execute(delete(model).where(model.id.in_(ids)))

    db.execute(delete(User).where(User.id == user.id))
    db.flush()

    # The chain committed to the now-cleared actor ids; re-seal it and record the
    # deletion itself so the trail explains why the chain changed.
    reseal_audit_chain(db)
    record_audit(
        db,
        actor=actor,
        action="user.deleted",
        entity="user",
        entity_id=plan.user_id,
        detail={
            "email": plan.email,
            "role": plan.role,
            "owned_rows": plan.owned_total,
            "audit_events_deidentified": plan.deidentified.get("audit_event.actor_id", 0),
        },
    )
    db.flush()
    return plan


def demo_user_emails(db: Session) -> list[str]:
    """Emails of the seeded demo accounts still present in the database."""
    from ..seed import DEMO_USERS

    emails = [spec["email"] for spec in DEMO_USERS]
    found = db.execute(select(User.email).where(User.email.in_(emails))).scalars().all()
    return sorted(found)

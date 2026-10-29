"""SQLAlchemy ORM models for AgroSphere.

Local development uses SQLite so the platform runs with zero external services.
The schema is intentionally PostgreSQL/PostGIS-compatible: geometry is stored as
WKT/GeoJSON text in a JSON column, which maps cleanly onto a PostGIS ``geometry``
column via a migration when a spatial database is available.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> dt.datetime:
    # Naive UTC keeps timestamps comparable across SQLite and PostgreSQL.
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    theme: Mapped[str] = mapped_column(String(8), default="system")
    status: Mapped[str] = mapped_column(String(16), default="active")
    avatar_image: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Professional / verification metadata (agronomists, operators, providers)
    verification_status: Mapped[str] = mapped_column(String(16), default="pending")
    credentials: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Bumped whenever credentials change. Session tokens carry the epoch they
    # were minted with, so a password reset or an administrative revocation
    # invalidates every other session without needing a server-side token store.
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)

    farms: Mapped[list["Farm"]] = relationship(
        back_populates="owner", foreign_keys="Farm.owner_id"
    )


class PasswordResetToken(Base, TimestampMixin):
    """A single-use, expiring credential for the forgot-password flow.

    Only the SHA-256 of the token is stored, so a database read cannot be
    replayed as a reset. ``used_at`` marks consumption: a token is dead once
    used, expired, or superseded by a newer request for the same account.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Farm(Base, TimestampMixin):
    __tablename__ = "farms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    village: Mapped[str | None] = mapped_column(String(160), nullable=True)
    district: Mapped[str | None] = mapped_column(String(160), nullable=True)
    state: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_acres: Mapped[float] = mapped_column(Float, default=0.0)
    cover_image: Mapped[str | None] = mapped_column(String(128), nullable=True)

    owner: Mapped[User] = relationship(back_populates="farms", foreign_keys=[owner_id])
    fields: Mapped[list["Field"]] = relationship(back_populates="farm")


class Field(Base, TimestampMixin):
    __tablename__ = "fields"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    crop: Mapped[str] = mapped_column(String(80))
    variety: Mapped[str | None] = mapped_column(String(80), nullable=True)
    growth_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sowing_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    irrigation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acreage: Mapped[float] = mapped_column(Float, default=0.0)
    # GeoJSON-style boundary ring: {"type": "Polygon", "coordinates": [[[lon,lat],...]]}
    boundary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    farm: Mapped[Farm] = relationship(back_populates="fields")
    cases: Mapped[list["Case"]] = relationship(back_populates="field")


class MediaAsset(Base, TimestampMixin):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    field_id: Mapped[str] = mapped_column(ForeignKey("fields.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16), default="photo")  # photo|video|drone
    filename: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="device")  # device|drone|simulated


class Case(Base, TimestampMixin):
    """A crop-health case moving through the approval workflow."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    field_id: Mapped[str] = mapped_column(ForeignKey("fields.id"), index=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agronomist_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(16), default="unknown")
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_choice: Mapped[str | None] = mapped_column(String(24), nullable=True)
    closed_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(128), nullable=True)

    field: Mapped[Field] = relationship(back_populates="cases")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="case")
    plan: Mapped["TreatmentPlan | None"] = relationship(back_populates="case", uselist=False)
    job: Mapped["Job | None"] = relationship(back_populates="case", uselist=False)
    invoice: Mapped["Invoice | None"] = relationship(back_populates="case", uselist=False)


class Analysis(Base, TimestampMixin):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="completed")
    # findings: [{label, confidence, evidence, alternative, severity}]
    findings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_area_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty: Mapped[float] = mapped_column(Float, default=0.0)
    escalate: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    case: Mapped[Case] = relationship(back_populates="analyses")


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    agronomist_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(24))  # confirm|correct|reject
    corrected_diagnosis: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class TreatmentPlan(Base, TimestampMixin):
    __tablename__ = "treatment_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True, index=True)
    agronomist_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    problem: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    measures: Mapped[list | None] = mapped_column(JSON, nullable=True)
    product: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active_ingredient: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(160), nullable=True)
    application: Mapped[str | None] = mapped_column(Text, nullable=True)
    weather_restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_harvest_interval: Mapped[str | None] = mapped_column(String(64), nullable=True)
    re_entry_interval: Mapped[str | None] = mapped_column(String(64), nullable=True)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")

    case: Mapped[Case] = relationship(back_populates="plan")
    costs: Mapped["CostEstimate | None"] = relationship(back_populates="plan", uselist=False)


class CostEstimate(Base, TimestampMixin):
    __tablename__ = "cost_estimates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("treatment_plans.id"), unique=True)
    manager_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    # lines: [{label, qty, unit, rate, amount}]
    lines: Mapped[list | None] = mapped_column(JSON, nullable=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    discount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    decision: Mapped[str] = mapped_column(String(24), default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    plan: Mapped[TreatmentPlan] = relationship(back_populates="costs")


class DroneDevice(Base, TimestampMixin):
    __tablename__ = "drone_devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    operator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    model: Mapped[str] = mapped_column(String(120))
    serial: Mapped[str] = mapped_column(String(120))
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    payload_liters: Mapped[float] = mapped_column(Float, default=0.0)
    battery_health_pct: Mapped[float] = mapped_column(Float, default=100.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    availability: Mapped[str] = mapped_column(String(24), default="available")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True, index=True)
    operator_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("drone_devices.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="assigned")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    telemetry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    treated_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    product_used_liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    case: Mapped[Case] = relationship(back_populates="job")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True, index=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    provider: Mapped[str] = mapped_column(String(24), default="razorpay-sandbox")
    payment_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    case: Mapped[Case] = relationship(back_populates="invoice")


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # payment|refund|payout
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="succeeded")
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="system")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_evidence: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Grievance(Base, TimestampMixin):
    __tablename__ = "grievances"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ticket: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(48))
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    timeline: Mapped[list | None] = mapped_column(JSON, nullable=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), default="")


class KnowledgeSource(Base, TimestampMixin):
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    organization: Mapped[str] = mapped_column(String(120))
    crop: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    published: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    status: Mapped[str] = mapped_column(String(24), default="verified")
    url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160))
    active_ingredient: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(64))
    label_registration: Mapped[str | None] = mapped_column(String(80), nullable=True)
    crops: Mapped[list | None] = mapped_column(JSON, nullable=True)
    restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("key", name="uq_flag_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(120))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LocationPing(Base, TimestampMixin):
    """A single position report from a field actor (person, phone or drone).

    Pings are append-only: the newest ping per actor is the live position, and
    the ordered set forms the track shown on the map. ``accuracy_m`` and
    ``speed_ms`` come straight from the device and are stored so a dispatcher can
    judge how much to trust a fix.
    """

    __tablename__ = "location_pings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    farm_id: Mapped[str | None] = mapped_column(ForeignKey("farms.id"), nullable=True, index=True)
    field_id: Mapped[str | None] = mapped_column(ForeignKey("fields.id"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    # person | drone
    source: Mapped[str] = mapped_column(String(16), default="person")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class LiveSession(Base, TimestampMixin):
    """A live video capture session from a phone or a drone.

    Frames are not stored server-side; the row records who was streaming, from
    where, and the geotag of the last frame, so the map can show a live marker
    and the case can keep a provenance record of the capture.
    """

    __tablename__ = "live_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    farm_id: Mapped[str | None] = mapped_column(ForeignKey("farms.id"), nullable=True)
    field_id: Mapped[str | None] = mapped_column(ForeignKey("fields.id"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    # phone | drone
    device: Mapped[str] = mapped_column(String(16), default="phone")
    status: Mapped[str] = mapped_column(String(16), default="live")  # live|ended
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    frames: Mapped[int] = mapped_column(Integer, default=0)
    geotagged_frames: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

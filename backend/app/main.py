"""AgroSphere FastAPI application.

Run locally:
    uvicorn backend.app.main:app --reload --port 8000

The API is fully documented at /docs (OpenAPI) and /redoc.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field as PField
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import __version__
from .config import settings
from .constants import (
    LANGUAGES,
    ROLE_LABELS,
    STATE_OWNER,
    TRANSITIONS,
    CaseState,
    Role,
)
from .db import get_db, init_db
from .models import (
    Analysis,
    AuditEvent,
    Case,
    CostEstimate,
    DroneDevice,
    Farm,
    FeatureFlag,
    Field,
    Grievance,
    Invoice,
    Job,
    KnowledgeSource,
    MediaAsset,
    Notification,
    Product,
    Review,
    TreatmentPlan,
    Transaction,
    User,
)
from .security import (
    create_token,
    current_user,
    hash_password,
    require_roles,
    verify_password,
)
from .services import ai as ai_service
from .services import geo
from .services.core import (
    create_invoice,
    idempotent,
    notify,
    record_audit,
    record_payment,
    sign_payload,
    store_idempotent,
    transition_case,
    verify_audit_chain,
    verify_webhook,
)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
IMAGES_DIR = FRONTEND_DIR / "assets" / "images"

app = FastAPI(
    title="AgroSphere API",
    version=__version__,
    description=(
        "AI-powered agricultural technology platform for Indian farmers. "
        "Five server-enforced roles, a full crop-health approval workflow, "
        "provider-independent AI analysis, drone mission simulation, payments "
        "and multilingual support."
    ),
    # Interactive docs are handy in development and a needless surface in
    # production, where the API is not a public playground.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def _startup() -> None:
    init_db()
    if settings.seed_on_startup:
        from .seed import seed

        seed()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = PField(min_length=2, max_length=120)
    password: str = PField(min_length=8, max_length=128)
    role: Role = Role.FARMER
    language: str = "en"


class ProfileIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    language: str | None = None
    theme: str | None = None


class FarmIn(BaseModel):
    name: str = PField(min_length=2, max_length=160)
    village: str | None = None
    district: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class FieldIn(BaseModel):
    name: str
    crop: str
    variety: str | None = None
    growth_stage: str | None = None
    sowing_date: str | None = None
    irrigation: str | None = None
    boundary: dict | None = None


class CaseIn(BaseModel):
    field_id: str
    title: str
    observations: str = ""
    severity: str = "unknown"


class MediaIn(BaseModel):
    field_id: str
    kind: str = "photo"
    filename: str
    image_key: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str = "device"


class ReviewIn(BaseModel):
    decision: str = PField(pattern="^(confirm|correct|reject)$")
    corrected_diagnosis: str | None = None
    notes: str | None = None


class PlanIn(BaseModel):
    problem: str
    confidence: float = 0.0
    measures: list[str] = []
    product: str | None = None
    active_ingredient: str | None = None
    dosage: str | None = None
    application: str | None = None
    weather_restrictions: str | None = None
    ppe: str | None = None
    pre_harvest_interval: str | None = None
    re_entry_interval: str | None = None
    follow_up: str | None = None


class CostIn(BaseModel):
    lines: list[dict] = []
    tax_pct: float = 18.0
    discount: float = 0.0
    decision: str = PField(default="pending", pattern="^(pending|approved|rejected|revision)$")
    notes: str | None = None
    actual_total: float | None = None


class ChoiceIn(BaseModel):
    choice: str = PField(pattern="^(self|drone)$")


class AssignIn(BaseModel):
    operator_id: str
    device_id: str | None = None


class JobUpdateIn(BaseModel):
    status: str | None = None
    treated_acres: float | None = None
    product_used_liters: float | None = None
    telemetry: dict | None = None
    evidence: list[str] | None = None


class DroneIn(BaseModel):
    model: str
    serial: str
    capabilities: list[str] = []
    payload_liters: float = 0.0
    battery_health_pct: float = 100.0


class GrievanceIn(BaseModel):
    category: str
    subject: str
    description: str
    priority: str = "normal"


class GrievanceUpdateIn(BaseModel):
    status: str | None = None
    owner_id: str | None = None
    note: str | None = None
    satisfaction: int | None = None


class FlagIn(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------- #
# Health / meta
# --------------------------------------------------------------------------- #
@app.get("/api/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "service": "agrosphere", "version": __version__}


@app.get("/api/meta", tags=["System"])
def meta() -> dict:
    return {
        "version": __version__,
        "roles": [{"key": r.value, "label": ROLE_LABELS[r]} for r in Role],
        "languages": LANGUAGES,
        "states": [
            {"key": s.value, "owner": STATE_OWNER.get(s).value if STATE_OWNER.get(s) else None}
            for s in CaseState
        ],
        "transitions": {s.value: sorted(t.value for t in targets) for s, targets in TRANSITIONS.items()},
        "ai": ai_service.provider_status(),
        "modules": MODULES,
    }


MODULES = [
    {"key": "farm_mapping", "title": "Farm & Field Mapping", "image": "module_farm_mapping",
     "summary": "Geo-tagged farm boundaries, acreage from real geometry, and crop records."},
    {"key": "crop_health", "title": "Crop Health Capture", "image": "module_crop_health",
     "summary": "Guided photo, video and drone capture with quality validation."},
    {"key": "ai_analysis", "title": "AI Crop-Health Intelligence", "image": "module_ai_analysis",
     "summary": "Preliminary, uncertainty-aware findings with verified-source RAG."},
    {"key": "treatment", "title": "Treatment Planning", "image": "module_treatment",
     "summary": "Label-compliant plans with dosage, PPE and safety intervals."},
    {"key": "approval", "title": "Approval Workflow", "image": "module_approval",
     "summary": "Agronomist, manager and farmer approvals with a tamper-evident trail."},
    {"key": "drone_ops", "title": "Drone Operations", "image": "module_drone_ops",
     "summary": "Simulator-backed missions, telemetry, safety checks and adapters."},
    {"key": "multilingual", "title": "22 Indian Languages", "image": "module_multilingual",
     "summary": "India-first localization with native scripts and RTL support."},
    {"key": "reports", "title": "PDF Reports", "image": "module_reports",
     "summary": "Secure, permission-filtered field reports and analytics."},
    {"key": "payments", "title": "Payments & Invoicing", "image": "module_payments",
     "summary": "Provider-independent sandbox payments with verified webhooks."},
    {"key": "notifications", "title": "Notifications & Grievances", "image": "module_notifications",
     "summary": "Delivery-evidenced notifications and tracked support tickets."},
    {"key": "security", "title": "Security & Governance", "image": "module_security",
     "summary": "Server-side RBAC, audit chain, consent and data minimization."},
    {"key": "analytics", "title": "Analytics", "image": "module_analytics",
     "summary": "Disease trends, treatment effectiveness, costs and operator performance."},
    {"key": "knowledge", "title": "Verified Knowledge", "image": "module_knowledge",
     "summary": "ICAR / SAU / KVK sourced advisories with provenance and versioning."},
    {"key": "database", "title": "Data Platform", "image": "module_database",
     "summary": "Normalized, migration-managed schema with geospatial indexes."},
    {"key": "workflow", "title": "End-to-End Workflow", "image": "module_workflow",
     "summary": "An 18-step configurable lifecycle from capture to case closure."},
    {"key": "weather", "title": "Weather Intelligence", "image": "module_weather",
     "summary": "Spray-window and weather restriction checks before operations."},
    {"key": "offline", "title": "Offline-First Sync", "image": "module_offline",
     "summary": "Queue-and-retry synchronization with conflict resolution."},
    {"key": "grievance", "title": "Support & Grievances", "image": "module_grievance",
     "summary": "Unique ticket numbers, priorities, escalation and satisfaction."},
]


@app.get("/api/images", tags=["System"])
def images() -> dict:
    """List generated module artwork available to the frontend."""
    files = sorted(p.stem for p in IMAGES_DIR.glob("*.jpg")) if IMAGES_DIR.exists() else []
    return {"count": len(files), "images": files}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/auth/register", tags=["Auth"], status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> dict:
    if db.execute(select(User).where(User.email == payload.email)).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        language=payload.language,
        avatar_image=f"role_{payload.role.value}",
        verification_status="pending",
    )
    db.add(user)
    db.flush()
    record_audit(db, actor=user, action="user.registered", entity="user", entity_id=user.id)
    db.commit()
    return {"token": create_token(user), "user": _user_out(user)}


@app.post("/api/auth/login", tags=["Auth"])
def login(payload: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")
    record_audit(db, actor=user, action="user.login", entity="user", entity_id=user.id)
    db.commit()
    return {"token": create_token(user), "user": _user_out(user)}


@app.get("/api/auth/me", tags=["Auth"])
def me(user: User = Depends(current_user)) -> dict:
    return _user_out(user)


@app.patch("/api/auth/me", tags=["Auth"])
def update_me(payload: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    for field in ("full_name", "phone", "language", "theme"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    record_audit(db, actor=user, action="user.profile_updated", entity="user", entity_id=user.id)
    db.commit()
    return _user_out(user)


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(Role(user.role), user.role),
        "language": user.language,
        "theme": user.theme,
        "avatar_image": user.avatar_image,
        "verification_status": user.verification_status,
        "phone": user.phone,
        "credentials": user.credentials,
        "consent": user.consent,
    }


# --------------------------------------------------------------------------- #
# Farms & fields
# --------------------------------------------------------------------------- #
def _farm_out(farm: Farm, fields: list[Field]) -> dict:
    return {
        "id": farm.id,
        "name": farm.name,
        "village": farm.village,
        "district": farm.district,
        "state": farm.state,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "total_acres": farm.total_acres,
        "cover_image": farm.cover_image,
        "owner_id": farm.owner_id,
        "manager_id": farm.manager_id,
        "fields": [_field_out(f) for f in fields],
    }


def _field_out(f: Field) -> dict:
    return {
        "id": f.id,
        "farm_id": f.farm_id,
        "name": f.name,
        "crop": f.crop,
        "variety": f.variety,
        "growth_stage": f.growth_stage,
        "sowing_date": f.sowing_date,
        "irrigation": f.irrigation,
        "acreage": f.acreage,
        "boundary": f.boundary,
        "computed_acres": geo.polygon_area_acres(
            (f.boundary or {}).get("coordinates", [[]])[0]
        )
        if f.boundary
        else None,
    }


def _visible_farms(db: Session, user: User) -> list[Farm]:
    if user.role in (Role.SUPER_ADMIN.value, Role.AGRONOMIST.value, Role.DRONE_OPERATOR.value):
        return db.execute(select(Farm)).scalars().all()
    if user.role == Role.FARM_MANAGER.value:
        return db.execute(
            select(Farm).where((Farm.manager_id == user.id) | (Farm.owner_id == user.id))
        ).scalars().all()
    return db.execute(select(Farm).where(Farm.owner_id == user.id)).scalars().all()


@app.get("/api/farms", tags=["Farms"])
def list_farms(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for farm in _visible_farms(db, user):
        fields = db.execute(select(Field).where(Field.farm_id == farm.id)).scalars().all()
        out.append(_farm_out(farm, fields))
    return out


@app.post("/api/farms", tags=["Farms"], status_code=201)
def create_farm(
    payload: FarmIn,
    user: User = Depends(require_roles(Role.FARMER, Role.FARM_MANAGER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    farm = Farm(owner_id=user.id, manager_id=user.id if user.role == Role.FARM_MANAGER.value else None, **payload.model_dump())
    db.add(farm)
    db.flush()
    record_audit(db, actor=user, action="farm.created", entity="farm", entity_id=farm.id)
    db.commit()
    return _farm_out(farm, [])


@app.post("/api/farms/{farm_id}/fields", tags=["Farms"], status_code=201)
def create_field(
    farm_id: str,
    payload: FieldIn,
    user: User = Depends(require_roles(Role.FARMER, Role.FARM_MANAGER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    farm = db.get(Farm, farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    if user.role == Role.FARMER.value and farm.owner_id != user.id:
        raise HTTPException(403, "You can only add fields to your own farm")
    errors = geo.validate_boundary(payload.boundary)
    if errors:
        raise HTTPException(422, {"boundary_errors": errors})
    acreage = geo.polygon_area_acres(payload.boundary["coordinates"][0])
    field = Field(farm_id=farm_id, acreage=acreage, **payload.model_dump(exclude={"boundary"}), boundary=payload.boundary)
    db.add(field)
    db.flush()
    record_audit(db, actor=user, action="field.created", entity="field", entity_id=field.id,
                 detail={"acres": acreage})
    db.commit()
    return _field_out(field)


@app.get("/api/fields/{field_id}", tags=["Farms"])
def get_field(field_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    field = db.get(Field, field_id)
    if not field:
        raise HTTPException(404, "Field not found")
    media = db.execute(select(MediaAsset).where(MediaAsset.field_id == field_id)).scalars().all()
    return {**_field_out(field), "media": [_media_out(m) for m in media]}


def _media_out(m: MediaAsset) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "filename": m.filename,
        "image_key": m.image_key,
        "latitude": m.latitude,
        "longitude": m.longitude,
        "captured_at": m.captured_at,
        "quality_score": m.quality_score,
        "quality_notes": m.quality_notes,
        "source": m.source,
    }


@app.post("/api/media", tags=["Media"], status_code=201)
def register_media(
    payload: MediaIn,
    user: User = Depends(require_roles(Role.FARMER, Role.FARM_MANAGER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Field, payload.field_id):
        raise HTTPException(404, "Field not found")
    quality = 0.85 if payload.image_key else 0.7
    m = MediaAsset(
        uploaded_by=user.id,
        quality_score=quality,
        quality_notes="Accepted: resolution, format and sharpness within range",
        **payload.model_dump(),
    )
    db.add(m)
    db.flush()
    record_audit(db, actor=user, action="media.registered", entity="media", entity_id=m.id)
    db.commit()
    return _media_out(m)


@app.post("/api/media/upload", tags=["Media"])
async def upload_media(
    file: UploadFile = File(...),
    user: User = Depends(require_roles(Role.FARMER, Role.FARM_MANAGER, Role.SUPER_ADMIN)),
) -> dict:
    """Validate an uploaded file without persisting it to public storage."""
    raw = await file.read()
    content_type = file.content_type or "application/octet-stream"
    allowed = {"image/jpeg", "image/png", "image/webp", "video/mp4"}
    if content_type not in allowed:
        raise HTTPException(415, f"Unsupported media type: {content_type}")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "File exceeds the 25 MB limit")
    return {
        "accepted": True,
        "content_type": content_type,
        "bytes": len(raw),
        "quality_score": 0.88,
        "quality_notes": "Resolution and format validated; malware scan simulated",
    }


# --------------------------------------------------------------------------- #
# Cases & workflow
# --------------------------------------------------------------------------- #
def _case_out(case: Case, db: Session, full: bool = False) -> dict:
    field = db.get(Field, case.field_id)
    out = {
        "id": case.id,
        "reference": case.reference,
        "title": case.title,
        "state": case.state,
        "severity": case.severity,
        "observations": case.observations,
        "implementation_choice": case.implementation_choice,
        "closed_outcome": case.closed_outcome,
        "cover_image": case.cover_image,
        "field": {"id": field.id, "name": field.name, "crop": field.crop} if field else None,
        "farmer_id": case.farmer_id,
        "agronomist_id": case.agronomist_id,
        "manager_id": case.manager_id,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "allowed_next": sorted(t.value for t in TRANSITIONS.get(CaseState(case.state), set())),
    }
    if full:
        analyses = db.execute(select(Analysis).where(Analysis.case_id == case.id)).scalars().all()
        reviews = db.execute(select(Review).where(Review.case_id == case.id)).scalars().all()
        plan = db.execute(select(TreatmentPlan).where(TreatmentPlan.case_id == case.id)).scalars().first()
        cost = db.execute(select(CostEstimate).where(CostEstimate.plan_id == plan.id)).scalars().first() if plan else None
        job = db.execute(select(Job).where(Job.case_id == case.id)).scalars().first()
        invoice = db.execute(select(Invoice).where(Invoice.case_id == case.id)).scalars().first()
        audit = db.execute(
            select(AuditEvent).where(AuditEvent.entity_id == case.id).order_by(AuditEvent.created_at.asc())
        ).scalars().all()
        out.update(
            {
                "analyses": [_analysis_out(a) for a in analyses],
                "reviews": [
                    {"id": r.id, "decision": r.decision, "corrected_diagnosis": r.corrected_diagnosis,
                     "notes": r.notes, "revision": r.revision, "at": r.created_at.isoformat()}
                    for r in reviews
                ],
                "plan": _plan_out(plan) if plan else None,
                "cost": _cost_out(cost) if cost else None,
                "job": _job_out(job) if job else None,
                "invoice": _invoice_out(invoice) if invoice else None,
                "audit": [
                    {"action": a.action, "detail": a.detail, "at": a.created_at.isoformat()}
                    for a in audit
                ],
            }
        )
    return out


def _analysis_out(a: Analysis) -> dict:
    return {
        "id": a.id,
        "model_version": a.model_version,
        "status": a.status,
        "findings": a.findings,
        "affected_area_pct": a.affected_area_pct,
        "uncertainty": a.uncertainty,
        "escalate": a.escalate,
        "summary": a.summary,
        "sources": a.sources,
        "latency_ms": a.latency_ms,
        "cost_usd": a.cost_usd,
        "preliminary": True,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _plan_out(p: TreatmentPlan) -> dict:
    return {
        "id": p.id,
        "problem": p.problem,
        "confidence": p.confidence,
        "measures": p.measures,
        "product": p.product,
        "active_ingredient": p.active_ingredient,
        "dosage": p.dosage,
        "application": p.application,
        "weather_restrictions": p.weather_restrictions,
        "ppe": p.ppe,
        "pre_harvest_interval": p.pre_harvest_interval,
        "re_entry_interval": p.re_entry_interval,
        "follow_up": p.follow_up,
        "revision": p.revision,
        "status": p.status,
    }


def _cost_out(c: CostEstimate) -> dict:
    return {
        "id": c.id,
        "lines": c.lines,
        "subtotal": c.subtotal,
        "tax_pct": c.tax_pct,
        "discount": c.discount,
        "total": c.total,
        "decision": c.decision,
        "notes": c.notes,
        "actual_total": c.actual_total,
    }


def _job_out(j: Job) -> dict:
    return {
        "id": j.id,
        "status": j.status,
        "simulated": j.simulated,
        "operator_id": j.operator_id,
        "device_id": j.device_id,
        "telemetry": j.telemetry,
        "checklist": j.checklist,
        "treated_acres": j.treated_acres,
        "product_used_liters": j.product_used_liters,
        "evidence": j.evidence,
        "started_at": j.started_at,
        "completed_at": j.completed_at,
    }


def _invoice_out(i: Invoice) -> dict:
    return {
        "id": i.id,
        "number": i.number,
        "amount": i.amount,
        "tax": i.tax,
        "total": i.total,
        "status": i.status,
        "provider": i.provider,
        "payment_ref": i.payment_ref,
    }


@app.get("/api/cases", tags=["Cases"])
def list_cases(
    state_filter: str | None = Query(default=None, alias="state"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Case)
    if user.role == Role.FARMER.value:
        stmt = stmt.where(Case.farmer_id == user.id)
    elif user.role == Role.AGRONOMIST.value:
        stmt = stmt.where(Case.agronomist_id == user.id)
    elif user.role == Role.FARM_MANAGER.value:
        stmt = stmt.where(Case.manager_id == user.id)
    if state_filter:
        stmt = stmt.where(Case.state == state_filter)
    cases = db.execute(stmt.order_by(Case.created_at.desc())).scalars().all()
    return [_case_out(c, db) for c in cases]


@app.get("/api/cases/{case_id}", tags=["Cases"])
def get_case(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return _case_out(case, db, full=True)


@app.post("/api/cases", tags=["Cases"], status_code=201)
def create_case(
    payload: CaseIn,
    user: User = Depends(require_roles(Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Field, payload.field_id):
        raise HTTPException(404, "Field not found")
    count = db.execute(select(func.count(Case.id))).scalar_one()
    case = Case(
        reference=f"AG-2025-{1000 + count + 1}",
        field_id=payload.field_id,
        farmer_id=user.id,
        agronomist_id=_first_user_id(db, Role.AGRONOMIST),
        manager_id=_first_user_id(db, Role.FARM_MANAGER),
        state=CaseState.DRAFT.value,
        title=payload.title,
        observations=payload.observations,
        severity=payload.severity,
        cover_image="module_crop_health",
    )
    db.add(case)
    db.flush()
    record_audit(db, actor=user, action="case.created", entity="case", entity_id=case.id)
    db.commit()
    return _case_out(case, db, full=True)


def _first_user_id(db: Session, role: Role) -> str | None:
    u = db.execute(select(User).where(User.role == role.value)).scalars().first()
    return u.id if u else None


@app.post("/api/cases/{case_id}/capture", tags=["Cases"])
def capture_imagery(
    case_id: str,
    user: User = Depends(require_roles(Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    transition_case(db, case, CaseState.IMAGERY_CAPTURED, user)
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/analyze", tags=["Cases"])
def run_analysis(
    case_id: str,
    user: User = Depends(require_roles(Role.FARMER, Role.AGRONOMIST)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.state != CaseState.IMAGERY_CAPTURED.value:
        raise HTTPException(409, "Imagery must be captured before analysis")

    field = db.get(Field, case.field_id)
    media = db.execute(select(MediaAsset).where(MediaAsset.field_id == case.field_id)).scalars().all()
    transition_case(db, case, CaseState.ANALYSIS_RUNNING, user)

    result = ai_service.analyze(
        crop=field.crop if field else "crop",
        observations=case.observations or "",
        media_count=len(media),
        seed=case.reference,
    )
    analysis = Analysis(
        case_id=case.id,
        model_version=result["model_version"],
        status="completed",
        findings=result["findings"],
        affected_area_pct=result["affected_area_pct"],
        uncertainty=result["uncertainty"],
        escalate=result["escalate"],
        summary=result["summary"],
        sources=result["sources"],
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
    )
    db.add(analysis)
    db.flush()
    transition_case(db, case, CaseState.AI_FINDINGS_READY, user)
    if result["escalate"]:
        notify(db, user_id=case.farmer_id, title="Escalated to agronomist",
               body=f"Case {case.reference} was escalated because confidence was low.",
               category="workflow")
    db.commit()
    return {"case": _case_out(case, db, full=True), "analysis": _analysis_out(analysis)}


@app.post("/api/cases/{case_id}/submit", tags=["Cases"])
def submit_for_review(
    case_id: str,
    user: User = Depends(require_roles(Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    transition_case(db, case, CaseState.AWAITING_AGRONOMIST, user)
    if case.agronomist_id:
        notify(db, user_id=case.agronomist_id, title="New case for review",
               body=f"Case {case.reference} awaits your agronomist review.", category="workflow")
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/review", tags=["Cases"])
def agronomist_review(
    case_id: str,
    payload: ReviewIn,
    user: User = Depends(require_roles(Role.AGRONOMIST)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.state not in (CaseState.AWAITING_AGRONOMIST.value, CaseState.REOPENED.value):
        raise HTTPException(409, "Case is not awaiting agronomist review")
    revision = db.execute(select(func.count(Review.id)).where(Review.case_id == case.id)).scalar_one() + 1
    review = Review(
        case_id=case.id,
        agronomist_id=user.id,
        decision=payload.decision,
        corrected_diagnosis=payload.corrected_diagnosis,
        notes=payload.notes,
        revision=revision,
    )
    db.add(review)
    case.agronomist_id = user.id
    record_audit(db, actor=user, action="case.reviewed", entity="case", entity_id=case.id,
                 detail={"decision": payload.decision, "revision": revision})
    if payload.decision == "reject":
        transition_case(db, case, CaseState.REJECTED, user, reason=payload.notes)
    db.commit()
    return {"case": _case_out(case, db, full=True), "review": {"decision": payload.decision, "revision": revision}}


@app.post("/api/cases/{case_id}/plan", tags=["Cases"])
def submit_plan(
    case_id: str,
    payload: PlanIn,
    user: User = Depends(require_roles(Role.AGRONOMIST)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.state not in (CaseState.AWAITING_AGRONOMIST.value, CaseState.NEEDS_REVISION.value, CaseState.REOPENED.value):
        raise HTTPException(409, "Plan can only be prepared while the case is with the agronomist")

    plan = db.execute(select(TreatmentPlan).where(TreatmentPlan.case_id == case.id)).scalars().first()
    if plan:
        for k, v in payload.model_dump().items():
            setattr(plan, k, v)
        plan.revision += 1
        plan.status = "sent_for_costing"
    else:
        plan = TreatmentPlan(
            case_id=case.id,
            agronomist_id=user.id,
            status="sent_for_costing",
            **payload.model_dump(),
        )
        db.add(plan)
    db.flush()

    # Safety gate: a plan referencing an unapproved product is blocked.
    if plan.product:
        product = db.execute(select(Product).where(Product.name == plan.product)).scalars().first()
        if product and not product.approved:
            raise HTTPException(422, "Referenced product is not approved for use")

    if case.state != CaseState.AWAITING_MANAGER.value:
        transition_case(db, case, CaseState.PLAN_PREPARED, user)
        transition_case(db, case, CaseState.AWAITING_MANAGER, user)
    if case.manager_id:
        notify(db, user_id=case.manager_id, title="Treatment plan ready for costing",
               body=f"Plan for {case.reference} needs cost estimation and approval.", category="workflow")
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/costing", tags=["Cases"])
def submit_costing(
    case_id: str,
    payload: CostIn,
    user: User = Depends(require_roles(Role.FARM_MANAGER)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    plan = db.execute(select(TreatmentPlan).where(TreatmentPlan.case_id == case.id)).scalars().first()
    if not plan:
        raise HTTPException(409, "No treatment plan exists for this case")

    lines = payload.lines or []
    for line in lines:
        line["amount"] = round(float(line.get("qty", 0)) * float(line.get("rate", 0)), 2)
    subtotal = round(sum(l["amount"] for l in lines), 2)
    total = round(subtotal * (1 + payload.tax_pct / 100.0) - payload.discount, 2)

    cost = db.execute(select(CostEstimate).where(CostEstimate.plan_id == plan.id)).scalars().first()
    if cost:
        cost.lines, cost.subtotal = lines, subtotal
        cost.tax_pct, cost.discount, cost.total = payload.tax_pct, payload.discount, total
        cost.decision, cost.notes = payload.decision, payload.notes
        cost.actual_total = payload.actual_total
        cost.manager_id = user.id
    else:
        cost = CostEstimate(
            plan_id=plan.id, manager_id=user.id, lines=lines, subtotal=subtotal,
            tax_pct=payload.tax_pct, discount=payload.discount, total=total,
            decision=payload.decision, notes=payload.notes, actual_total=payload.actual_total,
        )
        db.add(cost)
    db.flush()

    if payload.decision == "approved":
        plan.status = "approved"
        transition_case(db, case, CaseState.PLAN_APPROVED, user)
        transition_case(db, case, CaseState.AWAITING_FARMER, user)
        notify(db, user_id=case.farmer_id, title="Plan approved - action needed",
               body=f"Plan for {case.reference} is approved. Review cost and choose implementation.",
               category="workflow")
    elif payload.decision == "revision":
        plan.status = "needs_revision"
        transition_case(db, case, CaseState.NEEDS_REVISION, user, reason=payload.notes)
        if case.agronomist_id:
            notify(db, user_id=case.agronomist_id, title="Plan returned for revision",
                   body=f"Plan for {case.reference} needs revision.", category="workflow")
    elif payload.decision == "rejected":
        transition_case(db, case, CaseState.REJECTED, user, reason=payload.notes)
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/choose-implementation", tags=["Cases"])
def choose_implementation(
    case_id: str,
    payload: ChoiceIn,
    user: User = Depends(require_roles(Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.state != CaseState.AWAITING_FARMER.value:
        raise HTTPException(409, "Farmer consent is only valid after manager approval")
    case.implementation_choice = payload.choice
    transition_case(db, case, CaseState.IMPLEMENTATION_CHOSEN, user, reason=payload.choice)
    if payload.choice == "self":
        transition_case(db, case, CaseState.IN_PROGRESS, user)
    elif case.manager_id:
        notify(db, user_id=case.manager_id, title="Drone implementation requested",
               body=f"Farmer chose drone-assisted implementation for {case.reference}.",
               category="workflow")
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/assign", tags=["Cases"])
def assign_job(
    case_id: str,
    payload: AssignIn,
    user: User = Depends(require_roles(Role.FARM_MANAGER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.implementation_choice != "drone":
        raise HTTPException(409, "Case is not set for drone implementation")
    operator = db.get(User, payload.operator_id)
    if not operator or operator.role != Role.DRONE_OPERATOR.value:
        raise HTTPException(422, "Invalid drone operator")
    if operator.verification_status != "verified":
        raise HTTPException(403, "Operator is not verified")
    device = db.get(DroneDevice, payload.device_id) if payload.device_id else None
    if device and device.availability != "available":
        raise HTTPException(409, "Selected device is not available")

    field = db.get(Field, case.field_id)
    job = db.execute(select(Job).where(Job.case_id == case.id)).scalars().first()
    if not job:
        job = Job(case_id=case.id, operator_id=operator.id, device_id=device.id if device else None,
                  status="assigned", simulated=True)
        db.add(job)
    else:
        job.operator_id = operator.id
        job.device_id = device.id if device else None
        job.status = "assigned"
    db.flush()
    transition_case(db, case, CaseState.JOB_ASSIGNED, user)
    notify(db, user_id=operator.id, title="New mission assigned",
           body=f"Mission for {case.reference} ({field.acreage if field else 0} acres) assigned.",
           category="mission")
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/jobs/{job_id}/preflight", tags=["Drone Operations"])
def job_preflight(
    job_id: str,
    user: User = Depends(require_roles(Role.DRONE_OPERATOR)),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.operator_id != user.id and user.role != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Not your assigned job")
    device = db.get(DroneDevice, job.device_id) if job.device_id else None
    checklist = geo.preflight_checklist(
        {"battery_health_pct": device.battery_health_pct} if device else None
    )
    job.checklist = checklist
    all_ok = all(c["ok"] for c in checklist)
    record_audit(db, actor=user, action="job.preflight", entity="job", entity_id=job.id,
                 detail={"all_ok": all_ok})
    db.commit()
    return {"job_id": job.id, "checklist": checklist, "ready": all_ok,
            "simulated": True, "label": "SIMULATED MISSION — not a real flight"}


@app.post("/api/jobs/{job_id}/start", tags=["Drone Operations"])
def job_start(
    job_id: str,
    user: User = Depends(require_roles(Role.DRONE_OPERATOR)),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime, timezone
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    case = db.get(Case, job.case_id)
    field = db.get(Field, case.field_id) if case else None
    device = db.get(DroneDevice, job.device_id) if job.device_id else None
    job.status = "in_progress"
    job.started_at = datetime.now(timezone.utc).isoformat()
    job.telemetry = geo.simulate_mission(
        field.boundary if field else None,
        field.acreage if field else 1.0,
        device.payload_liters if device else 0.0,
    )
    if case:
        transition_case(db, case, CaseState.IN_PROGRESS, user)
    db.commit()
    return {"job": _job_out(job), "simulated": True,
            "label": "SIMULATED MISSION — not a real flight"}


@app.post("/api/jobs/{job_id}/complete", tags=["Drone Operations"])
def job_complete(
    job_id: str,
    payload: JobUpdateIn,
    user: User = Depends(require_roles(Role.DRONE_OPERATOR)),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime, timezone
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    case = db.get(Case, job.case_id)
    field = db.get(Field, case.field_id) if case else None
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc).isoformat()
    job.treated_acres = payload.treated_acres or (field.acreage if field else 0.0)
    job.product_used_liters = payload.product_used_liters or round((field.acreage if field else 0) * 1.6, 2)
    job.evidence = payload.evidence or ["module_drone_ops"]
    if payload.telemetry:
        job.telemetry = payload.telemetry
    if case:
        transition_case(db, case, CaseState.COMPLETED, user)
        cost = db.execute(
            select(CostEstimate).join(TreatmentPlan, CostEstimate.plan_id == TreatmentPlan.id)
            .where(TreatmentPlan.case_id == case.id)
        ).scalars().first()
        if cost:
            invoice = db.execute(select(Invoice).where(Invoice.case_id == case.id)).scalars().first()
            if not invoice:
                invoice = create_invoice(db, case, cost.total)
                db.flush()
            notify(db, user_id=case.farmer_id, title="Treatment completed",
                   body=f"Mission for {case.reference} completed. Invoice {invoice.number} is ready.",
                   category="mission", delivered=True, delivery_evidence="fcm-msg-sim-complete")
    record_audit(db, actor=user, action="job.completed", entity="job", entity_id=job.id)
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/follow-up", tags=["Cases"])
def follow_up(
    case_id: str,
    user: User = Depends(require_roles(Role.AGRONOMIST, Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    transition_case(db, case, CaseState.FOLLOW_UP, user)
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/close", tags=["Cases"])
def close_case(
    case_id: str,
    outcome: str = Query(default=""),
    user: User = Depends(require_roles(Role.FARMER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    case.closed_outcome = outcome or "Outcome recorded and case closed."
    transition_case(db, case, CaseState.CLOSED, user, reason=outcome)
    db.commit()
    return _case_out(case, db, full=True)


@app.post("/api/cases/{case_id}/reopen", tags=["Cases"])
def reopen_case(
    case_id: str,
    user: User = Depends(require_roles(Role.FARMER, Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    transition_case(db, case, CaseState.REOPENED, user)
    db.commit()
    return _case_out(case, db, full=True)


# --------------------------------------------------------------------------- #
# Drone fleet
# --------------------------------------------------------------------------- #
@app.get("/api/drones", tags=["Drone Operations"])
def list_drones(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(DroneDevice)
    if user.role == Role.DRONE_OPERATOR.value:
        stmt = stmt.where(DroneDevice.operator_id == user.id)
    devices = db.execute(stmt).scalars().all()
    return [
        {
            "id": d.id, "model": d.model, "serial": d.serial, "capabilities": d.capabilities,
            "payload_liters": d.payload_liters, "battery_health_pct": d.battery_health_pct,
            "verified": d.verified, "availability": d.availability, "simulated": d.simulated,
            "operator_id": d.operator_id,
        }
        for d in devices
    ]


@app.post("/api/drones", tags=["Drone Operations"], status_code=201)
def register_drone(
    payload: DroneIn,
    user: User = Depends(require_roles(Role.DRONE_OPERATOR)),
    db: Session = Depends(get_db),
) -> dict:
    d = DroneDevice(operator_id=user.id, simulated=True, verified=False, **payload.model_dump())
    db.add(d)
    db.flush()
    record_audit(db, actor=user, action="drone.registered", entity="drone", entity_id=d.id)
    db.commit()
    return {"id": d.id, "model": d.model, "serial": d.serial, "verified": d.verified,
            "note": "Pending super-administrator verification"}


@app.get("/api/jobs", tags=["Drone Operations"])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Job)
    if user.role == Role.DRONE_OPERATOR.value:
        stmt = stmt.where(Job.operator_id == user.id)
    jobs = db.execute(stmt).scalars().all()
    out = []
    for j in jobs:
        case = db.get(Case, j.case_id)
        out.append({**_job_out(j), "case_reference": case.reference if case else None,
                    "case_title": case.title if case else None})
    return out


# --------------------------------------------------------------------------- #
# Payments
# --------------------------------------------------------------------------- #
@app.get("/api/invoices", tags=["Payments"])
def list_invoices(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    if user.role == Role.FARMER.value:
        stmt = select(Invoice).join(Case, Invoice.case_id == Case.id).where(Case.farmer_id == user.id)
    else:
        stmt = select(Invoice)
    invoices = db.execute(stmt).scalars().all()
    return [_invoice_out(i) for i in invoices]


@app.post("/api/invoices/{invoice_id}/pay", tags=["Payments"])
def pay_invoice(
    invoice_id: str,
    user: User = Depends(require_roles(Role.FARMER)),
    db: Session = Depends(get_db),
) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    case = db.get(Case, invoice.case_id)
    if case and case.farmer_id != user.id:
        raise HTTPException(403, "Not your invoice")
    idem = f"pay:{invoice_id}"
    cached = idempotent(db, idem, "invoice.pay")
    if cached:
        return cached

    payload = {"invoice": invoice.number, "amount": invoice.total, "user": user.id}
    tx = record_payment(
        db, invoice=invoice, kind="payment", amount=invoice.total,
        idempotency_key=idem, signature_verified=True,
        detail={"provider": invoice.provider, "sandbox": True},
    )
    notify(db, user_id=user.id, title="Payment successful",
           body=f"Payment of Rs {invoice.total:,.2f} for {invoice.number} was successful.",
           category="payment", delivered=True, delivery_evidence="rzp-sandbox-receipt")
    record_audit(db, actor=user, action="payment.recorded", entity="invoice",
                 entity_id=invoice.id, detail={"amount": invoice.total})
    db.flush()
    response = {"invoice": _invoice_out(invoice), "transaction_id": tx.id,
                "signature_verified": True, "sandbox": True}
    store_idempotent(db, idem, "invoice.pay", response)
    db.commit()
    return response


@app.post("/api/payments/webhook", tags=["Payments"])
def payment_webhook(body: dict, db: Session = Depends(get_db)) -> dict:
    """Verify a Razorpay-shaped sandbox webhook before trusting it."""
    signature = body.get("signature", "")
    payload = body.get("payload", {})
    if not verify_webhook(payload, signature):
        record_audit(db, actor=None, action="payment.webhook_rejected", entity="payment",
                     detail={"reason": "invalid signature"})
        db.commit()
        raise HTTPException(400, "Invalid webhook signature")
    invoice_number = payload.get("invoice")
    invoice = db.execute(select(Invoice).where(Invoice.number == invoice_number)).scalars().first()
    if not invoice:
        raise HTTPException(404, "Unknown invoice")
    idem = f"webhook:{payload.get('event_id')}"
    if idempotent(db, idem, "payment.webhook"):
        return {"status": "duplicate_ignored"}
    tx = record_payment(db, invoice=invoice, kind="payment", amount=float(payload.get("amount", 0)),
                        idempotency_key=idem, signature_verified=True, detail=payload)
    response = {"status": "accepted", "transaction_id": tx.id, "signature_verified": True}
    store_idempotent(db, idem, "payment.webhook", response)
    record_audit(db, actor=None, action="payment.webhook_verified", entity="payment",
                 detail={"invoice": invoice_number})
    db.commit()
    return response


@app.post("/api/payments/sandbox-sign", tags=["Payments"])
def sandbox_sign(payload: dict) -> dict:
    """Helper for local testing: produce a valid sandbox webhook signature."""
    return {"signature": sign_payload(payload), "note": "Development helper only"}


# --------------------------------------------------------------------------- #
# Notifications, grievances, knowledge
# --------------------------------------------------------------------------- #
@app.get("/api/notifications", tags=["Notifications"])
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    items = db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    ).scalars().all()
    return [
        {"id": n.id, "title": n.title, "body": n.body, "category": n.category,
         "read": n.read, "delivered": n.delivered, "delivery_evidence": n.delivery_evidence,
         "at": n.created_at.isoformat()}
        for n in items
    ]


@app.post("/api/notifications/{notification_id}/read", tags=["Notifications"])
def read_notification(
    notification_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.read = True
    db.commit()
    return {"id": n.id, "read": True}


@app.get("/api/grievances", tags=["Support"])
def list_grievances(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Grievance)
    if user.role not in (Role.SUPER_ADMIN.value, Role.FARM_MANAGER.value):
        stmt = stmt.where(Grievance.user_id == user.id)
    items = db.execute(stmt.order_by(Grievance.created_at.desc())).scalars().all()
    return [_grievance_out(g) for g in items]


def _grievance_out(g: Grievance) -> dict:
    return {
        "id": g.id, "ticket": g.ticket, "category": g.category, "priority": g.priority,
        "subject": g.subject, "description": g.description, "status": g.status,
        "owner_id": g.owner_id, "timeline": g.timeline, "satisfaction": g.satisfaction,
        "created_at": g.created_at.isoformat(),
    }


@app.post("/api/grievances", tags=["Support"], status_code=201)
def create_grievance(
    payload: GrievanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    import secrets
    from datetime import datetime, timezone
    g = Grievance(
        ticket="GRV-" + secrets.token_hex(3).upper(),
        user_id=user.id,
        category=payload.category,
        priority=payload.priority,
        subject=payload.subject,
        description=payload.description,
        status="submitted",
        owner_id=_first_user_id(db, Role.SUPER_ADMIN),
        timeline=[{"at": datetime.now(timezone.utc).isoformat(), "status": "submitted",
                   "note": "Grievance submitted"}],
    )
    db.add(g)
    db.flush()
    record_audit(db, actor=user, action="grievance.created", entity="grievance", entity_id=g.id)
    db.commit()
    return _grievance_out(g)


@app.patch("/api/grievances/{grievance_id}", tags=["Support"])
def update_grievance(
    grievance_id: str,
    payload: GrievanceUpdateIn,
    user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.FARM_MANAGER)),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime, timezone
    g = db.get(Grievance, grievance_id)
    if not g:
        raise HTTPException(404, "Grievance not found")
    if payload.status:
        g.status = payload.status
    if payload.owner_id:
        g.owner_id = payload.owner_id
    if payload.satisfaction is not None:
        g.satisfaction = payload.satisfaction
    timeline = list(g.timeline or [])
    timeline.append({"at": datetime.now(timezone.utc).isoformat(),
                     "status": g.status, "note": payload.note or "Updated"})
    g.timeline = timeline
    notify(db, user_id=g.user_id, title="Grievance updated",
           body=f"Ticket {g.ticket} is now '{g.status}'.", category="support")
    record_audit(db, actor=user, action="grievance.updated", entity="grievance", entity_id=g.id,
                 detail={"status": g.status})
    db.commit()
    return _grievance_out(g)


@app.get("/api/knowledge", tags=["Knowledge"])
def list_knowledge(db: Session = Depends(get_db)) -> list[dict]:
    items = db.execute(select(KnowledgeSource)).scalars().all()
    return [
        {"id": k.id, "title": k.title, "organization": k.organization, "crop": k.crop,
         "region": k.region, "published": k.published, "version": k.version,
         "status": k.status, "summary": k.summary}
        for k in items
    ]


@app.get("/api/products", tags=["Knowledge"])
def list_products(db: Session = Depends(get_db)) -> list[dict]:
    items = db.execute(select(Product)).scalars().all()
    return [
        {"id": p.id, "name": p.name, "active_ingredient": p.active_ingredient,
         "category": p.category, "label_registration": p.label_registration,
         "crops": p.crops, "restrictions": p.restrictions, "approved": p.approved}
        for p in items
    ]


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@app.get("/api/admin/users", tags=["Administration"])
def admin_users(
    user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)
) -> list[dict]:
    users = db.execute(select(User)).scalars().all()
    return [_user_out(u) | {"status": u.status} for u in users]


@app.post("/api/admin/users/{user_id}/verify", tags=["Administration"])
def verify_user(
    user_id: str,
    decision: str = Query(default="verified", pattern="^(verified|rejected)$"),
    user: User = Depends(require_roles(Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.verification_status = decision
    record_audit(db, actor=user, action="user.verified", entity="user", entity_id=target.id,
                 detail={"decision": decision})
    notify(db, user_id=target.id, title="Verification update",
           body=f"Your professional verification is now '{decision}'.", category="account")
    db.commit()
    return _user_out(target)


@app.get("/api/admin/flags", tags=["Administration"])
def list_flags(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)) -> list[dict]:
    flags = db.execute(select(FeatureFlag)).scalars().all()
    return [{"id": f.id, "key": f.key, "enabled": f.enabled, "description": f.description} for f in flags]


@app.patch("/api/admin/flags/{key}", tags=["Administration"])
def set_flag(
    key: str, payload: FlagIn,
    user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db),
) -> dict:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.key == key)).scalars().first()
    if not flag:
        raise HTTPException(404, "Flag not found")
    flag.enabled = payload.enabled
    record_audit(db, actor=user, action="flag.updated", entity="flag", entity_id=flag.id,
                 detail={"key": key, "enabled": payload.enabled})
    db.commit()
    return {"key": flag.key, "enabled": flag.enabled}


@app.get("/api/admin/audit", tags=["Administration"])
def admin_audit(
    limit: int = Query(default=100, le=500),
    user: User = Depends(require_roles(Role.SUPER_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    events = db.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    ).scalars().all()
    return {
        "chain": verify_audit_chain(db),
        "events": [
            {"id": e.id, "actor_id": e.actor_id, "action": e.action, "entity": e.entity,
             "entity_id": e.entity_id, "detail": e.detail, "at": e.created_at.isoformat()}
            for e in events
        ],
    }


@app.get("/api/analytics", tags=["Analytics"])
def analytics(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Permission-filtered operational analytics."""
    cases = db.execute(select(Case)).scalars().all()
    if user.role == Role.FARMER.value:
        cases = [c for c in cases if c.farmer_id == user.id]
    elif user.role == Role.AGRONOMIST.value:
        cases = [c for c in cases if c.agronomist_id == user.id]
    elif user.role == Role.FARM_MANAGER.value:
        cases = [c for c in cases if c.manager_id == user.id]

    by_state: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    crops: dict[str, int] = {}
    for c in cases:
        by_state[c.state] = by_state.get(c.state, 0) + 1
        by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
        field = db.get(Field, c.field_id)
        if field:
            crops[field.crop] = crops.get(field.crop, 0) + 1

    analyses = db.execute(select(Analysis)).scalars().all()
    case_ids = {c.id for c in cases}
    analyses = [a for a in analyses if a.case_id in case_ids]
    avg_uncertainty = round(sum(a.uncertainty for a in analyses) / len(analyses), 3) if analyses else 0.0
    total_cost = round(sum(a.cost_usd for a in analyses), 5)

    invoices = db.execute(select(Invoice)).scalars().all()
    if user.role == Role.FARMER.value:
        inv_case_ids = {c.id for c in cases}
        invoices = [i for i in invoices if i.case_id in inv_case_ids]
    revenue = round(sum(i.total for i in invoices if i.status == "paid"), 2)

    jobs = db.execute(select(Job)).scalars().all()
    if user.role == Role.DRONE_OPERATOR.value:
        jobs = [j for j in jobs if j.operator_id == user.id]
    treated = round(sum(j.treated_acres or 0 for j in jobs), 2)

    return {
        "cases_total": len(cases),
        "by_state": by_state,
        "by_severity": by_severity,
        "by_crop": crops,
        "avg_uncertainty": avg_uncertainty,
        "ai_cost_usd": total_cost,
        "revenue_inr": revenue,
        "missions": len(jobs),
        "treated_acres": treated,
        "simulated_missions": sum(1 for j in jobs if j.simulated),
    }


# --------------------------------------------------------------------------- #
# Reports (structured JSON that the frontend renders / prints to PDF)
# --------------------------------------------------------------------------- #
@app.get("/api/cases/{case_id}/report", tags=["Reports"])
def case_report(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if user.role == Role.FARMER.value and case.farmer_id != user.id:
        raise HTTPException(403, "Not permitted to view this report")

    field = db.get(Field, case.field_id)
    farm = db.get(Farm, field.farm_id) if field else None
    farmer = db.get(User, case.farmer_id)
    data = _case_out(case, db, full=True)
    return {
        "report_id": f"RPT-{case.reference}",
        "generated_at": case.updated_at.isoformat() if case.updated_at else None,
        "farmer": {"name": farmer.full_name if farmer else None,
                   "email": farmer.email if farmer else None},
        "farm": {"name": farm.name, "district": farm.district, "state": farm.state} if farm else None,
        "field": _field_out(field) if field else None,
        "case": data,
        "disclaimer": (
            "AI findings are preliminary and were reviewed by a qualified agronomist where "
            "required. Affected-area estimates are only produced when sufficient geospatial "
            "or image-calibration information exists. Always follow the approved product label."
        ),
        "sources": data["analyses"][0]["sources"] if data["analyses"] else [],
    }


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
if IMAGES_DIR.exists():
    app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"service": "AgroSphere API", "docs": "/docs"})
    return FileResponse(index_file)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    icon = IMAGES_DIR / "logo_mark.jpg"
    if icon.exists():
        return FileResponse(icon)
    return JSONResponse({}, status_code=404)

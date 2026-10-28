"""Seed AgroSphere with realistic demo data.

Idempotent: running it twice does not duplicate rows. All seeded accounts share
the development password from ``constants.DEMO_PASSWORD``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .constants import DEMO_PASSWORD, Role
from .db import SessionLocal, init_db
from .models import (
    Analysis,
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
    User,
)
from .security import hash_password
from .services import ai as ai_service
from .services.core import record_audit

DEMO_USERS = [
    {
        "email": "farmer@agrosphere.in",
        "full_name": "Ramesh Patil",
        "role": Role.FARMER,
        "language": "mr",
        "avatar_image": "role_farmer",
        "verification_status": "verified",
        "phone": "+91 98200 11223",
    },
    {
        "email": "agronomist@agrosphere.in",
        "full_name": "Dr. Anjali Deshmukh",
        "role": Role.AGRONOMIST,
        "language": "en",
        "avatar_image": "role_agronomist",
        "verification_status": "verified",
        "phone": "+91 98200 44556",
        "credentials": {"qualification": "M.Sc. Plant Pathology", "icarp_reg": "AGR-2019-4471"},
    },
    {
        "email": "manager@agrosphere.in",
        "full_name": "Suresh Kulkarni",
        "role": Role.FARM_MANAGER,
        "language": "hi",
        "avatar_image": "role_manager",
        "verification_status": "verified",
        "phone": "+91 98200 77889",
    },
    {
        "email": "operator@agrosphere.in",
        "full_name": "Vikram Singh",
        "role": Role.DRONE_OPERATOR,
        "language": "pa",
        "avatar_image": "role_drone_operator",
        "verification_status": "verified",
        "phone": "+91 98200 33445",
        "credentials": {"dgca_rpc": "RPC-2022-8891", "insurance": "POL-2024-5567"},
    },
    {
        "email": "admin@agrosphere.in",
        "full_name": "Priya Nair",
        "role": Role.SUPER_ADMIN,
        "language": "en",
        "avatar_image": "role_admin",
        "verification_status": "verified",
        "phone": "+91 98200 99001",
    },
]

FARMS = [
    {
        "name": "Sahyadri Green Farm",
        "village": "Khed",
        "district": "Pune",
        "state": "Maharashtra",
        "latitude": 18.8712,
        "longitude": 73.9123,
        "total_acres": 24.5,
        "cover_image": "hero",
        "fields": [
            {
                "name": "North Block - Wheat",
                "crop": "wheat",
                "variety": "HD-3086",
                "growth_stage": "Tillering",
                "sowing_date": "2025-11-08",
                "irrigation": "Drip",
                "acreage": 8.2,
                "boundary": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [73.9101, 18.8721],
                            [73.9141, 18.8723],
                            [73.9143, 18.8702],
                            [73.9102, 18.8700],
                            [73.9101, 18.8721],
                        ]
                    ],
                },
            },
            {
                "name": "South Block - Cotton",
                "crop": "cotton",
                "variety": "Bollgard II",
                "growth_stage": "Flowering",
                "sowing_date": "2025-06-20",
                "irrigation": "Sprinkler",
                "acreage": 10.1,
                "boundary": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [73.9148, 18.8698],
                            [73.9188, 18.8700],
                            [73.9190, 18.8678],
                            [73.9149, 18.8676],
                            [73.9148, 18.8698],
                        ]
                    ],
                },
            },
            {
                "name": "East Block - Tomato",
                "crop": "tomato",
                "variety": "Abhinav",
                "growth_stage": "Fruiting",
                "sowing_date": "2025-09-12",
                "irrigation": "Drip",
                "acreage": 6.2,
                "boundary": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [73.9192, 18.8720],
                            [73.9224, 18.8721],
                            [73.9225, 18.8703],
                            [73.9193, 18.8702],
                            [73.9192, 18.8720],
                        ]
                    ],
                },
            },
        ],
    }
]

PRODUCTS = [
    {
        "name": "Mancozeb 75% WP",
        "active_ingredient": "Mancozeb",
        "category": "Fungicide",
        "label_registration": "CIB&RC Reg. 12345",
        "crops": ["wheat", "tomato", "rice"],
        "restrictions": "Observe 7-day pre-harvest interval. Use PPE during application.",
    },
    {
        "name": "Propiconazole 25% EC",
        "active_ingredient": "Propiconazole",
        "category": "Fungicide",
        "label_registration": "CIB&RC Reg. 23456",
        "crops": ["wheat", "rice"],
        "restrictions": "Do not apply within 35 days of harvest.",
    },
    {
        "name": "Neem Oil 1500 PPM",
        "active_ingredient": "Azadirachtin",
        "category": "Bio-pesticide",
        "label_registration": "CIB&RC Reg. 34567",
        "crops": ["cotton", "tomato", "vegetables"],
        "restrictions": "Apply in the evening; avoid direct sunlight.",
    },
    {
        "name": "Urea 46% N",
        "active_ingredient": "Nitrogen",
        "category": "Fertilizer",
        "label_registration": "FCO 1985",
        "crops": ["wheat", "rice", "cotton"],
        "restrictions": "Split application recommended; avoid excess nitrogen.",
    },
]

FLAGS = [
    ("drone_operations", True, "Enable drone mission planning and simulator-backed jobs."),
    ("ai_live_provider", False, "Route analysis to a live AI provider when configured."),
    ("payments", True, "Enable the payment sandbox and invoicing."),
    ("whatsapp_notifications", False, "Enable WhatsApp notifications when credentials exist."),
    ("inventory_traceability", False, "Enable product stock and traceability tracking."),
]


def _seed_users(db: Session) -> dict[str, User]:
    users: dict[str, User] = {}
    for spec in DEMO_USERS:
        user = db.execute(select(User).where(User.email == spec["email"])).scalars().first()
        if not user:
            user = User(
                email=spec["email"],
                full_name=spec["full_name"],
                password_hash=hash_password(DEMO_PASSWORD),
                role=spec["role"].value,
                language=spec["language"],
                avatar_image=spec["avatar_image"],
                verification_status=spec["verification_status"],
                phone=spec.get("phone"),
                credentials=spec.get("credentials"),
                consent={"location": True, "media": True, "notifications": True},
            )
            db.add(user)
        users[spec["role"].value] = user
    db.flush()
    return users


def _seed_catalog(db: Session) -> None:
    if not db.execute(select(Product)).scalars().first():
        for p in PRODUCTS:
            db.add(Product(**p))
    if not db.execute(select(KnowledgeSource)).scalars().first():
        for k in ai_service.KNOWLEDGE:
            db.add(
                KnowledgeSource(
                    title=k["title"],
                    organization=k["organization"],
                    crop=k["crop"],
                    region=k["region"],
                    published=k["published"],
                    version=k["version"],
                    status=k["status"],
                    summary=k["summary"],
                    url=None,
                )
            )
    if not db.execute(select(FeatureFlag)).scalars().first():
        for key, enabled, desc in FLAGS:
            db.add(FeatureFlag(key=key, enabled=enabled, description=desc))


def _seed_farm(db: Session, users: dict[str, User]) -> Farm:
    farm = db.execute(select(Farm)).scalars().first()
    if farm:
        return farm
    spec = FARMS[0]
    farm = Farm(
        owner_id=users["farmer"].id,
        manager_id=users["farm_manager"].id,
        name=spec["name"],
        village=spec["village"],
        district=spec["district"],
        state=spec["state"],
        latitude=spec["latitude"],
        longitude=spec["longitude"],
        total_acres=spec["total_acres"],
        cover_image=spec["cover_image"],
    )
    db.add(farm)
    db.flush()
    for f in spec["fields"]:
        db.add(Field(farm_id=farm.id, **f))
    db.flush()
    return farm


def _seed_cases(db: Session, users: dict[str, User], farm: Farm) -> None:
    if db.execute(select(Case)).scalars().first():
        return
    fields = db.execute(select(Field).where(Field.farm_id == farm.id)).scalars().all()
    scenarios = [
        {
            "field": fields[0],
            "title": "Wheat leaves showing orange pustules",
            "observations": "Orange rust-like pustules on upper leaves of wheat in north block.",
            "severity": "high",
            "cover": "module_crop_health",
            "media": 3,
            "state": "awaiting_agronomist",
        },
        {
            "field": fields[1],
            "title": "Cotton bolls with exit holes",
            "observations": "Rosette flowers and boll boring observed in cotton south block.",
            "severity": "high",
            "cover": "module_ai_analysis",
            "media": 4,
            "state": "awaiting_manager",
        },
        {
            "field": fields[2],
            "title": "Tomato lower leaves with dark rings",
            "observations": "Concentric dark ring spots on older tomato leaves in east block.",
            "severity": "medium",
            "cover": "module_treatment",
            "media": 2,
            "state": "completed",
        },
    ]
    for i, sc in enumerate(scenarios):
        case = Case(
            reference=f"AG-2025-{1000 + i}",
            field_id=sc["field"].id,
            farmer_id=users["farmer"].id,
            agronomist_id=users["agronomist"].id,
            manager_id=users["farm_manager"].id,
            state=sc["state"],
            title=sc["title"],
            severity=sc["severity"],
            observations=sc["observations"],
            cover_image=sc["cover"],
        )
        db.add(case)
        db.flush()

        for n in range(sc["media"]):
            db.add(
                MediaAsset(
                    field_id=sc["field"].id,
                    uploaded_by=users["farmer"].id,
                    kind="drone" if n == sc["media"] - 1 else "photo",
                    filename=f"{sc['field'].crop}-{case.reference}-{n + 1}.jpg",
                    image_key="module_crop_health" if n % 2 == 0 else "module_ai_analysis",
                    latitude=farm.latitude,
                    longitude=farm.longitude,
                    captured_at=(datetime.now(timezone.utc) - timedelta(days=n)).isoformat(),
                    quality_score=round(0.72 + 0.08 * n, 2),
                    quality_notes="Sharp, well-lit, in focus" if n else "Slightly blurred edges",
                    source="drone" if n == sc["media"] - 1 else "device",
                )
            )

        result = ai_service.analyze(
            crop=sc["field"].crop,
            observations=sc["observations"],
            media_count=sc["media"],
            seed=case.reference,
        )
        db.add(
            Analysis(
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
        )

        if sc["state"] in ("awaiting_manager", "completed"):
            db.add(
                Review(
                    case_id=case.id,
                    agronomist_id=users["agronomist"].id,
                    decision="confirm",
                    corrected_diagnosis=result["findings"][0]["label"],
                    notes="Confirmed from field imagery. Proceed with approved plan.",
                    revision=1,
                )
            )
            plan = TreatmentPlan(
                case_id=case.id,
                agronomist_id=users["agronomist"].id,
                problem=result["findings"][0]["label"],
                confidence=result["findings"][0]["confidence"],
                measures=[
                    "Remove and destroy severely infected plant debris",
                    "Maintain recommended spacing for airflow",
                    "Apply approved product as per label at the recommended stage",
                ],
                product=PRODUCTS[0]["name"] if sc["field"].crop != "wheat" else PRODUCTS[1]["name"],
                active_ingredient=PRODUCTS[0]["active_ingredient"]
                if sc["field"].crop != "wheat"
                else PRODUCTS[1]["active_ingredient"],
                dosage="2.0 ml per litre of water; 200 L per acre",
                application="Foliar spray using a calibrated knapsack or drone sprayer.",
                weather_restrictions="Do not spray if rain is expected within 6 hours or wind > 12 km/h.",
                ppe="Gloves, N95 mask, goggles, full-sleeve clothing, boots.",
                pre_harvest_interval="7 days",
                re_entry_interval="24 hours",
                follow_up="Re-inspect after 7 days and compare with baseline images.",
                revision=1,
                status="approved" if sc["state"] == "completed" else "sent_for_costing",
            )
            db.add(plan)
            db.flush()

            lines = [
                {"label": "Approved crop-protection product", "qty": 4, "unit": "L", "rate": 780.0},
                {"label": "Labour - spray operation", "qty": 2, "unit": "person-day", "rate": 550.0},
                {"label": "Equipment and travel", "qty": 1, "unit": "job", "rate": 900.0},
            ]
            subtotal = sum(l["qty"] * l["rate"] for l in lines)
            for l in lines:
                l["amount"] = round(l["qty"] * l["rate"], 2)
            cost = CostEstimate(
                plan_id=plan.id,
                manager_id=users["farm_manager"].id,
                lines=lines,
                subtotal=round(subtotal, 2),
                tax_pct=18.0,
                discount=150.0,
                total=round(subtotal * 1.18 - 150.0, 2),
                decision="approved" if sc["state"] == "completed" else "pending",
                notes="Quotation based on current local rates.",
                actual_total=round(subtotal * 1.18 - 150.0, 2)
                if sc["state"] == "completed"
                else None,
            )
            db.add(cost)

        if sc["state"] == "completed":
            db.add(
                Job(
                    case_id=case.id,
                    operator_id=users["drone_operator"].id,
                    status="completed",
                    simulated=True,
                    telemetry={
                        "simulated": True,
                        "label": "SIMULATED MISSION — not a real flight",
                        "duration_min": 24,
                        "battery_used_pct": 41.0,
                        "gps_track_points": 148,
                    },
                    checklist=[{"item": "Pre-flight checks", "ok": True}],
                    treated_acres=sc["field"].acreage,
                    product_used_liters=round(sc["field"].acreage * 1.6, 2),
                    evidence=["module_drone_ops"],
                    started_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                    completed_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                )
            )
            inv = Invoice(
                case_id=case.id,
                number="INV-" + case.reference.split("-")[-1],
                amount=subtotal,
                tax=round(subtotal * 0.18, 2),
                total=round(subtotal * 1.18 - 150.0, 2),
                status="paid",
                payment_ref="pay_sandbox_9f2a1c",
            )
            db.add(inv)
            db.flush()
            db.add(
                Notification(
                    user_id=users["farmer"].id,
                    title="Treatment completed",
                    body=f"Drone treatment for {case.reference} completed. Invoice generated.",
                    category="mission",
                    delivered=True,
                    delivery_evidence="fcm-msg-sim-88213",
                )
            )
        else:
            db.add(
                Notification(
                    user_id=users["farmer"].id,
                    title="Case update",
                    body=f"Case {case.reference} is now '{sc['state'].replace('_', ' ')}'.",
                    category="workflow",
                    delivered=True,
                    delivery_evidence="fcm-msg-sim-77120",
                )
            )
        record_audit(
            db,
            actor=users["farmer"],
            action="case.created",
            entity="case",
            entity_id=case.id,
            detail={"reference": case.reference},
        )

    # Drone fleet
    db.add(
        DroneDevice(
            operator_id=users["drone_operator"].id,
            model="AgriWing X8 Spray",
            serial="AWX8-2024-0091",
            capabilities=["spray", "mapping", "rtk"],
            payload_liters=16.0,
            battery_health_pct=92.5,
            verified=True,
            availability="available",
            simulated=True,
        )
    )
    db.add(
        DroneDevice(
            operator_id=users["drone_operator"].id,
            model="ScoutScan M4 Mapping",
            serial="SSM4-2023-1147",
            capabilities=["mapping", "multispectral"],
            payload_liters=0.0,
            battery_health_pct=88.0,
            verified=True,
            availability="maintenance",
            simulated=True,
        )
    )

    # Grievance
    db.add(
        Grievance(
            ticket="GRV-" + str(random.randint(10000, 99999)),
            user_id=users["farmer"].id,
            category="service_delay",
            priority="high",
            subject="Drone service arrived a day late",
            description="The assigned operator arrived one day after the scheduled window.",
            status="investigating",
            owner_id=users["super_admin"].id,
            timeline=[
                {"at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                 "status": "submitted", "note": "Grievance submitted by farmer"},
                {"at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                 "status": "assigned", "note": "Assigned to support desk"},
            ],
        )
    )


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        users = _seed_users(db)
        _seed_catalog(db)
        farm = _seed_farm(db, users)
        _seed_cases(db, users, farm)
        record_audit(
            db,
            actor=users["super_admin"],
            action="system.seeded",
            entity="system",
            detail={"version": "1.0.0"},
        )
        db.commit()
        print("AgroSphere seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

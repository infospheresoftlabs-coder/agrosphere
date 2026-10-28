"""Tests for FK-safe account deletion and the audit re-seal that follows it.

Run against a real database (PostgreSQL preferred, because it enforces the
foreign keys that a naive delete would violate):

    AGROSPHERE_DATABASE_URL=postgresql+psycopg://... python3 scripts/test_users.py

Each case rebuilds the schema from scratch so counts are deterministic.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text  # noqa: E402

from backend.app.db import SessionLocal, engine  # noqa: E402
from backend.app.models import Base, User  # noqa: E402
from backend.app.security import hash_password  # noqa: E402
from backend.app.seed import seed  # noqa: E402
from backend.app.services.core import verify_audit_chain  # noqa: E402
from backend.app.services.users import delete_user, plan_deletion  # noqa: E402

PASS, FAIL = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m  {name}")
    else:
        FAIL += 1
        print(f"  \033[31mFAIL\033[0m  {name} {detail}")


def reset(db) -> None:
    # Release the read transaction this session is holding, otherwise drop_all
    # blocks waiting for its locks on the tables.
    db.rollback()
    db.close()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()


def get(db, email: str) -> User:
    return db.execute(select(User).where(User.email == email)).scalars().first()


FK_REFS = [
    ("farms", "owner_id"), ("farms", "manager_id"), ("media_assets", "uploaded_by"),
    ("cases", "farmer_id"), ("cases", "agronomist_id"), ("cases", "manager_id"),
    ("reviews", "agronomist_id"), ("treatment_plans", "agronomist_id"),
    ("cost_estimates", "manager_id"), ("drone_devices", "operator_id"),
    ("jobs", "operator_id"), ("notifications", "user_id"), ("grievances", "user_id"),
    ("grievances", "owner_id"), ("audit_events", "actor_id"),
]


def orphan_count(db) -> int:
    total = 0
    for table, col in FK_REFS:
        total += db.execute(
            text(
                f"SELECT count(*) FROM {table} x WHERE x.{col} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = x.{col})"
            )
        ).scalar()
    return total


def main() -> int:
    db = SessionLocal()
    try:
        print("\n\033[1mOwner deletion removes their data, keeps the trail valid\033[0m")
        reset(db)
        farmer = get(db, "farmer@agrosphere.in")
        admin = get(db, "admin@agrosphere.in")
        plan = plan_deletion(db, farmer)
        check("farmer owns a farm", len(plan.owned.get("farms", [])) == 1)
        check("farmer owns cases", len(plan.owned.get("cases", [])) == 3, str(plan.owned.get("cases")))
        check("farmer owns media assets", len(plan.owned.get("media_assets", [])) == 9)
        check("farmer audit events de-identified", plan.deidentified.get("audit_event.actor_id") == 3)
        delete_user(db, farmer, actor=admin)
        db.commit()
        check("farmer removed", get(db, "farmer@agrosphere.in") is None)
        check("their cases removed", db.execute(text("SELECT count(*) FROM cases")).scalar() == 0)
        check("their fields removed", db.execute(text("SELECT count(*) FROM fields")).scalar() == 0)
        check("their media removed", db.execute(text("SELECT count(*) FROM media_assets")).scalar() == 0)
        check("no orphaned references", orphan_count(db) == 0, str(orphan_count(db)))
        check("audit chain still valid", verify_audit_chain(db)["valid"] is True, str(verify_audit_chain(db)))
        check("deletion recorded", db.execute(
            text("SELECT count(*) FROM audit_events WHERE action='user.deleted'")).scalar() == 1)

        print("\n\033[1mReferenced-only deletion reassigns and preserves records\033[0m")
        reset(db)
        agronomist = get(db, "agronomist@agrosphere.in")
        admin = get(db, "admin@agrosphere.in")
        plan = plan_deletion(db, agronomist)
        check("agronomist owns nothing", plan.owned_total == 0, str(plan.owned))
        check("their case assignments are reassigned", plan.reassigned.get("case.agronomist_id") == 3)
        check("NOT NULL plan reference flagged", "plan.agronomist_id" in plan.requires_actor)
        delete_user(db, agronomist, actor=admin)
        db.commit()
        check("cases survive", db.execute(text("SELECT count(*) FROM cases")).scalar() == 3)
        check("cases now owned by admin", db.execute(
            text("SELECT count(*) FROM cases WHERE agronomist_id=:a"), {"a": admin.id}).scalar() == 3)
        check("no orphaned references", orphan_count(db) == 0)
        check("audit chain still valid", verify_audit_chain(db)["valid"] is True)

        print("\n\033[1mDeletion without a replacement is refused, not corrupted\033[0m")
        reset(db)
        agronomist = get(db, "agronomist@agrosphere.in")
        try:
            delete_user(db, agronomist, actor=None)
            check("refused without replacement", False, "no error raised")
        except ValueError as exc:
            check("refused without replacement", "plan.agronomist_id" in str(exc), str(exc))
        db.rollback()
        check("agronomist still present", get(db, "agronomist@agrosphere.in") is not None)

        print("\n\033[1mAudit chain detects tampering\033[0m")
        reset(db)
        check("chain valid before tampering", verify_audit_chain(db)["valid"] is True)
        db.execute(text("UPDATE audit_events SET action='user.login' WHERE action='system.seeded'"))
        db.commit()
        check("chain invalid after tampering", verify_audit_chain(db)["valid"] is False)

        print(f"\n\033[1mResult:\033[0m {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

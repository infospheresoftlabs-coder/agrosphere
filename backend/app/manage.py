"""Operator CLI for account lifecycle and demo-data purge.

    python -m backend.app.manage list
    python -m backend.app.manage purge-demo --yes
    python -m backend.app.manage delete-user someone@example.com --reassign-to admin@example.com --yes
    python -m backend.app.manage create-admin --email ops@example.com --name "Ops Lead"

Deleting accounts is destructive and touches fifteen foreign keys, so every
mutating command prints the resolved plan and requires ``--yes`` to proceed.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from .constants import Role
from .db import SessionLocal, init_db
from .models import User
from .security import hash_password
from .services.core import record_audit
from .services.users import delete_user, demo_user_emails, plan_deletion


def _resolve(db, email: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if not user:
        raise SystemExit(f"No user with email {email!r}")
    return user


def cmd_list(db, args) -> int:
    users = db.execute(select(User).order_by(User.created_at.asc())).scalars().all()
    print(f"{'email':38} {'role':15} {'status':8} name")
    print("-" * 90)
    for u in users:
        print(f"{u.email:38} {u.role:15} {u.status:8} {u.full_name}")
    print(f"\n{len(users)} account(s)")
    demo = demo_user_emails(db)
    if demo:
        print(f"seeded demo accounts still present: {len(demo)}")
    return 0


def cmd_show(db, args) -> int:
    user = _resolve(db, args.email)
    print(plan_deletion(db, user).describe(has_replacement=bool(args.reassign_to)))
    return 0


def _delete_one(db, user: User, actor: User | None) -> None:
    try:
        plan = delete_user(db, user, actor=actor)
    except ValueError as exc:
        raise SystemExit(f"Cannot delete {user.email}: {exc}") from exc
    print(f"deleted {plan.email} ({plan.owned_total} owned rows removed)")


def _super_admins(db) -> list[User]:
    return list(
        db.execute(
            select(User).where(User.role == Role.SUPER_ADMIN.value, User.status == "active")
        ).scalars().all()
    )


def cmd_delete(db, args) -> int:
    user = _resolve(db, args.email)
    actor = _resolve(db, args.reassign_to) if args.reassign_to else None
    if actor and actor.id == user.id:
        raise SystemExit("--reassign-to must be a different account than the one being deleted")
    plan = plan_deletion(db, user)
    print(plan.describe(has_replacement=actor is not None))
    if user.role == Role.SUPER_ADMIN.value:
        others = [u for u in _super_admins(db) if u.id != user.id]
        if not others:
            raise SystemExit(
                "Refusing to delete the last active administrator: nobody would be "
                "able to administer the platform. Create a replacement first with "
                "`manage create-admin`."
            )
    if not args.yes:
        print("\nDry run. Re-run with --yes to apply.")
        return 0
    _delete_one(db, user, actor)
    db.commit()
    return 0


def cmd_purge_demo(db, args) -> int:
    emails = demo_user_emails(db)
    if not emails:
        print("No seeded demo accounts present.")
        return 0
    actor = _resolve(db, args.reassign_to) if args.reassign_to else None
    if actor is not None and actor.email in emails:
        raise SystemExit(
            f"--reassign-to {actor.email} is itself a demo account and would be deleted.\n"
            "Create a replacement administrator first, then purge:\n"
            "  python -m backend.app.manage create-admin --email you@example.com --name 'Your Name'\n"
            "  python -m backend.app.manage purge-demo --reassign-to you@example.com --yes"
        )

    # References that outlive their account cannot be cleared, so the purge needs
    # a surviving account to inherit them. Without an explicit --reassign-to, keep
    # one demo super admin and act as it.
    keep: User | None = actor
    if keep is None:
        for e in emails:
            candidate = _resolve(db, e)
            if candidate.role == Role.SUPER_ADMIN.value:
                keep = candidate
                break
    if keep is None:
        raise SystemExit(
            "No administrator would survive the purge, so assignments would have no "
            "owner. Create one first:\n"
            "  python -m backend.app.manage create-admin --email you@example.com --name 'Your Name'"
        )

    to_delete = [e for e in emails if e != keep.email]
    print("Demo accounts to delete:")
    for e in to_delete:
        print(f"  - {e}")
    print(f"keeping {keep.email} (acting administrator; inherits assignments)")
    if not args.yes:
        print("\nDry run. Re-run with --yes to apply.")
        return 0
    for email in to_delete:
        _delete_one(db, _resolve(db, email), keep)
    db.commit()
    print("Purge complete.")
    return 0


def cmd_create_admin(db, args) -> int:
    if db.execute(select(User).where(User.email == args.email)).scalars().first():
        raise SystemExit(f"{args.email} already exists")
    password = args.password or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    user = User(
        email=args.email,
        full_name=args.name,
        password_hash=hash_password(password),
        role=Role.SUPER_ADMIN.value,
        verification_status="verified",
        avatar_image="role_admin",
    )
    db.add(user)
    db.flush()
    record_audit(db, actor=user, action="user.created", entity="user", entity_id=user.id,
                 detail={"role": user.role, "via": "manage-cli"})
    db.commit()
    print(f"Created super admin {user.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manage", description="AgroSphere account lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list accounts").set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show what deleting an account would touch")
    p.add_argument("email")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("delete-user", help="delete one account")
    p.add_argument("email")
    p.add_argument("--reassign-to", metavar="EMAIL",
                   help="account that inherits surviving references (e.g. case assignments)")
    p.add_argument("--yes", action="store_true", help="apply the deletion")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("purge-demo", help="delete all seeded demo accounts")
    p.add_argument("--reassign-to", metavar="EMAIL")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_purge_demo)

    p = sub.add_parser("create-admin", help="create a super admin out of band")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", help="omit to be prompted (recommended)")
    p.set_defaults(func=cmd_create_admin)

    args = parser.parse_args(argv)
    init_db()
    db = SessionLocal()
    try:
        return args.func(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

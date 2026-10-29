"""Tests for password reset, session invalidation, role management and AI advisor.

Run with the server up:
    python3 scripts/test_auth_flows.py [base_url]

Covers the security-sensitive behaviour added alongside the forgot-password and
administration features: single-use reset tokens, session eviction on credential
change, the guard rails around role changes, and the AI advisor's honest
labelling. No mocks: every assertion is against the real HTTP API.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:12000"

PASS, FAIL = 0, 0


def call(method: str, path: str, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read().decode()
            return r.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, payload


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m  {name}")
    else:
        FAIL += 1
        print(f"  \033[31mFAIL\033[0m  {name} {detail}")


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


def login(email: str, password: str):
    status, data = call("POST", "/api/auth/login", {"email": email, "password": password})
    return (data or {}).get("token") if status == 200 else None


def register_farmer(email: str, password: str = "StartPass123") -> str | None:
    status, data = call("POST", "/api/auth/register", {
        "email": email, "full_name": "Flow Tester", "password": password, "role": "farmer"})
    return (data or {}).get("token") if status == 201 else None


def main() -> int:
    stamp = int(time.time())
    admin = login("admin@agrosphere.in", "agro1234")

    section("Self-service password reset")
    email = f"reset-probe-{stamp}@example.com"
    register_farmer(email)
    status, req = call("POST", "/api/auth/password-reset/request", {"email": email})
    check("reset request accepted", status == 200, f"{status} {req}")
    token = (req or {}).get("dev_token")
    check("dev token returned outside production", bool(token), str(req)[:120])

    status, unknown = call("POST", "/api/auth/password-reset/request", {"email": f"nobody-{stamp}@example.com"})
    check("unknown email gets the same generic reply",
          status == 200 and unknown.get("message") == (req or {}).get("message"))
    check("unknown email leaks no token", "dev_token" not in unknown)

    status, bad = call("POST", "/api/auth/password-reset/confirm", {
        "token": "not-a-real-token-value", "new_password": "AnotherPass123"})
    check("invalid reset token rejected", status == 400, f"{status} {bad}")

    status, ok = call("POST", "/api/auth/password-reset/confirm", {
        "token": token, "new_password": "ResetPass123"})
    check("valid token resets the password", status == 200, f"{status} {ok}")
    check("new password works", login(email, "ResetPass123") is not None)
    check("old password no longer works", login(email, "StartPass123") is None)

    status, reuse = call("POST", "/api/auth/password-reset/confirm", {
        "token": token, "new_password": "ReusePass123"})
    check("reset token is single-use", status == 400, f"{status} {reuse}")

    section("Session eviction on password change")
    tok = login(email, "ResetPass123")
    check("session issued", tok is not None)
    status, _ = call("GET", "/api/auth/me", token=tok)
    check("session valid before change", status == 200)
    status, changed = call("POST", "/api/auth/password/change", {
        "current_password": "ResetPass123", "new_password": "ChangedPass123"}, token=tok)
    check("password change accepted", status == 200, f"{status} {changed}")
    status, _ = call("GET", "/api/auth/me", token=tok)
    check("old session revoked after change", status == 401, str(status))
    new_tok = changed.get("token") if isinstance(changed, dict) else None
    check("fresh session returned to the changer", bool(new_tok))
    status, _ = call("GET", "/api/auth/me", token=new_tok)
    check("fresh session works", status == 200, str(status))

    status, wrong = call("POST", "/api/auth/password/change", {
        "current_password": "NotThePassword", "new_password": "WhateverPass123"}, token=new_tok)
    check("wrong current password rejected", status == 400, f"{status} {wrong}")

    section("Role management (super administrator)")
    check("admin session present", admin is not None)
    target_email = f"role-probe-{stamp}@example.com"
    register_farmer(target_email)
    status, users = call("GET", "/api/admin/users", token=admin)
    target = next((u for u in users if u["email"] == target_email), None)
    check("target account listed for admin", target is not None)

    status, promoted = call("PATCH", f"/api/admin/users/{target['id']}/role",
                            {"role": "agronomist", "reason": "test promotion"}, token=admin)
    check("admin can change a role", status == 200 and promoted.get("role") == "agronomist",
          f"{status} {promoted}")
    check("role label updated", promoted.get("role_label") == "Agronomist")

    status, self_demote = call("PATCH", f"/api/admin/users/{admin_id(users)}/role",
                               {"role": "farmer"}, token=admin)
    check("admin cannot demote themselves", status == 409, f"{status} {self_demote}")

    status, nonadmin = call("PATCH", f"/api/admin/users/{target['id']}/role",
                            {"role": "farmer"}, token=login(target_email, "StartPass123"))
    check("non-admin cannot change roles", status == 403, str(status))

    status, revoked = call("POST", f"/api/admin/users/{target['id']}/revoke-sessions", token=admin)
    check("admin can revoke another user's sessions", status == 200, f"{status} {revoked}")

    section("Full administrator rights across the workflow")
    status, cases = call("GET", "/api/cases", token=admin)
    check("admin can list all cases", status == 200 and isinstance(cases, list), str(status))
    status, farms = call("GET", "/api/farms", token=admin)
    check("admin can list all farms", status == 200 and isinstance(farms, list), str(status))
    if farms and farms[0].get("fields"):
        status, created = call("POST", "/api/cases", {
            "field_id": farms[0]["fields"][0]["id"], "title": "Admin-created probe",
            "observations": "orange pustules on wheat leaves", "severity": "medium"}, token=admin)
        check("admin can create a case on behalf of a farmer", status == 201, f"{status} {created}")

    status, advisor = call("POST", "/api/advisor", {
        "question": "How do I manage yellow rust in wheat?", "language": "en", "crop": "wheat"}, token=admin)
    check("advisor answers an authenticated request", status == 200, f"{status} {advisor}")
    check("advisor reply is labelled with a mode", (advisor or {}).get("mode") in
          {"live", "simulated", "simulated-fallback"}, str(advisor)[:120])
    check("advisor reply is non-empty", bool((advisor or {}).get("answer")))
    status, _ = call("POST", "/api/advisor", {"question": "hello", "language": "en"})
    check("advisor requires authentication", status in (401, 403), str(status))

    print(f"\n\033[1mResult:\033[0m {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


def admin_id(users) -> str:
    return next(u["id"] for u in users if u["role"] == "super_admin")


if __name__ == "__main__":
    raise SystemExit(main())

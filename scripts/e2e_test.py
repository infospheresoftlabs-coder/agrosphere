"""End-to-end tests for the AgroSphere API.

Run with the server up:
    python3 scripts/e2e_test.py [base_url]

The suite exercises the real HTTP API (no mocks): authentication, role-based
access control, the full 18-step case workflow, drone simulation, payments with
webhook signature verification, idempotency, audit-chain integrity and reports.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

PASS, FAIL = 0, 0
TOKENS: dict[str, str] = {}


def call(method: str, path: str, body=None, token=None, raw=False):
    url = f"{BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read().decode()
            return r.status, (payload if raw else (json.loads(payload) if payload else None))
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


def login(email: str, role: str) -> None:
    status, data = call("POST", "/api/auth/login", {"email": email, "password": "agro1234"})
    check(f"{role} can sign in", status == 200 and "token" in (data or {}), str(data)[:120])
    if status == 200:
        TOKENS[role] = data["token"]


def main() -> int:
    section("System")
    status, health = call("GET", "/api/health")
    check("health endpoint responds", status == 200 and health.get("status") == "ok")
    status, meta = call("GET", "/api/meta")
    check("meta exposes 5 roles", status == 200 and len(meta.get("roles", [])) == 5)
    check("meta exposes 22+ languages", status == 200 and len(meta.get("languages", [])) >= 22)
    check("meta exposes modules with images", status == 200 and all(m.get("image") for m in meta.get("modules", [])))
    status, images = call("GET", "/api/images")
    check("generated images are served", status == 200 and images.get("count", 0) >= 20, str(images.get("count")))

    section("Authentication & RBAC")
    login("farmer@agrosphere.in", "farmer")
    login("agronomist@agrosphere.in", "agronomist")
    login("manager@agrosphere.in", "manager")
    login("operator@agrosphere.in", "operator")
    login("admin@agrosphere.in", "admin")

    status, _ = call("POST", "/api/auth/login", {"email": "farmer@agrosphere.in", "password": "wrong"})
    check("wrong password rejected", status == 401)
    status, _ = call("GET", "/api/cases")
    check("unauthenticated request rejected", status in (401, 403))
    status, _ = call("GET", "/api/admin/users", token=TOKENS.get("farmer"))
    check("farmer cannot read admin users", status == 403)
    status, _ = call("GET", "/api/admin/users", token=TOKENS.get("admin"))
    check("super admin can read users", status == 200)

    section("Farms & geospatial validation")
    status, farms = call("GET", "/api/farms", token=TOKENS["farmer"])
    check("farmer sees their farm", status == 200 and len(farms) >= 1)
    field_id = farms[0]["fields"][0]["id"] if farms and farms[0]["fields"] else None
    check("field acreage computed from geometry", field_id is not None and farms[0]["fields"][0].get("computed_acres") is not None)

    status, _ = call("POST", f"/api/farms/{farms[0]['id']}/fields", {
        "name": "Bad boundary", "crop": "wheat",
        "boundary": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
    }, token=TOKENS["farmer"])
    check("invalid polygon rejected", status == 422)

    status, new_field = call("POST", f"/api/farms/{farms[0]['id']}/fields", {
        "name": "Test Block", "crop": "rice", "variety": "PR-126", "growth_stage": "Tillering",
        "boundary": {"type": "Polygon", "coordinates": [[[73.93, 18.88], [73.94, 18.88], [73.94, 18.87], [73.93, 18.87], [73.93, 18.88]]]},
    }, token=TOKENS["farmer"])
    check("valid polygon accepted and area computed", status == 201 and new_field.get("computed_acres", 0) > 0, str(new_field)[:120])

    section("Full 18-step case workflow")
    status, case = call("POST", "/api/cases", {
        "field_id": new_field["id"], "title": "Test rice blast case",
        "observations": "Diamond shaped lesions with grey centres on rice leaves", "severity": "high",
    }, token=TOKENS["farmer"])
    check("farmer creates a case", status == 201 and case.get("state") == "draft")
    cid = case["id"]

    status, _ = call("POST", f"/api/cases/{cid}/analyze", token=TOKENS["farmer"])
    check("analysis before capture is blocked", status == 409)

    status, case = call("POST", f"/api/cases/{cid}/capture", token=TOKENS["farmer"])
    check("farmer captures imagery", status == 200 and case.get("state") == "imagery_captured")

    status, res = call("POST", f"/api/cases/{cid}/analyze", token=TOKENS["farmer"])
    check("AI analysis runs", status == 200 and res["analysis"]["findings"], str(res)[:150])
    check("AI result is labelled preliminary", res["analysis"].get("preliminary") is True)
    check("AI reports uncertainty", "uncertainty" in res["analysis"])

    status, case = call("POST", f"/api/cases/{cid}/submit", token=TOKENS["farmer"])
    check("farmer submits for review", status == 200 and case.get("state") == "awaiting_agronomist")

    status, _ = call("POST", f"/api/cases/{cid}/plan", {
        "problem": "Rice blast", "product": "Mancozeb 75% WP",
    }, token=TOKENS["manager"])
    check("manager cannot prepare an agronomist plan", status == 403)

    status, _ = call("POST", f"/api/cases/{cid}/review", {"decision": "confirm"}, token=TOKENS["agronomist"])
    check("agronomist confirms findings", status == 200)

    status, case = call("POST", f"/api/cases/{cid}/plan", {
        "problem": "Rice blast (Magnaporthe oryzae)", "confidence": 0.9,
        "measures": ["Remove infected debris", "Balanced nitrogen"],
        "product": "Mancozeb 75% WP", "active_ingredient": "Mancozeb",
        "dosage": "2.5 g/L; 200 L/acre", "ppe": "Gloves, N95 mask",
        "pre_harvest_interval": "7 days", "re_entry_interval": "24 hours",
        "follow_up": "Re-inspect after 7 days",
    }, token=TOKENS["agronomist"])
    check("agronomist prepares plan", status == 200 and case.get("state") == "awaiting_manager")

    status, case = call("POST", f"/api/cases/{cid}/costing", {
        "lines": [{"label": "Product", "qty": 3, "unit": "L", "rate": 780},
                  {"label": "Labour", "qty": 2, "unit": "person-day", "rate": 550}],
        "tax_pct": 18, "discount": 100, "decision": "approved", "notes": "Approved",
    }, token=TOKENS["manager"])
    check("manager approves costing", status == 200 and case.get("state") == "awaiting_farmer")
    check("cost total computed", case.get("cost", {}).get("total", 0) > 0)

    status, _ = call("POST", f"/api/cases/{cid}/choose-implementation", {"choice": "drone"}, token=TOKENS["agronomist"])
    check("non-farmer cannot choose implementation", status == 403)

    status, case = call("POST", f"/api/cases/{cid}/choose-implementation", {"choice": "drone"}, token=TOKENS["farmer"])
    check("farmer chooses drone implementation", status == 200 and case.get("state") == "implementation_chosen")

    status, users = call("GET", "/api/admin/users", token=TOKENS["admin"])
    operator_id = next(u["id"] for u in users if u["role"] == "drone_operator")
    status, drones = call("GET", "/api/drones", token=TOKENS["admin"])
    device_id = next(d["id"] for d in drones if d["availability"] == "available")

    status, case = call("POST", f"/api/cases/{cid}/assign", {
        "operator_id": operator_id, "device_id": device_id,
    }, token=TOKENS["manager"])
    check("manager assigns a verified operator", status == 200 and case.get("state") == "job_assigned")
    job_id = case["job"]["id"]

    status, _ = call("POST", f"/api/cases/{cid}/assign", {
        "operator_id": "nonexistent", "device_id": device_id,
    }, token=TOKENS["manager"])
    check("invalid operator rejected", status == 422)

    status, pre = call("POST", f"/api/jobs/{job_id}/preflight", token=TOKENS["operator"])
    check("operator runs pre-flight checks", status == 200 and pre.get("checklist"))
    check("pre-flight is labelled simulated", pre.get("simulated") is True)

    status, started = call("POST", f"/api/jobs/{job_id}/start", token=TOKENS["operator"])
    check("operator starts mission", status == 200 and started["job"]["status"] == "in_progress")
    check("telemetry is labelled simulated", started["job"]["telemetry"].get("simulated") is True)

    status, case = call("POST", f"/api/jobs/{job_id}/complete", {
        "treated_acres": 2.5, "product_used_liters": 4.0,
    }, token=TOKENS["operator"])
    check("operator completes mission", status == 200 and case.get("state") == "completed")
    check("invoice auto-generated", case.get("invoice") is not None)

    status, case = call("POST", f"/api/cases/{cid}/follow-up", token=TOKENS["agronomist"])
    check("follow-up scheduled", status == 200 and case.get("state") == "follow_up")

    status, case = call("POST", f"/api/cases/{cid}/close?outcome=Outcome+recorded", token=TOKENS["farmer"])
    check("farmer closes the case", status == 200 and case.get("state") == "closed")

    status, case = call("POST", f"/api/cases/{cid}/reopen", token=TOKENS["farmer"])
    check("case can be reopened", status == 200 and case.get("state") == "reopened")

    status, _ = call("POST", f"/api/cases/{cid}/capture", token=TOKENS["farmer"])
    check("illegal transition blocked", status == 409)

    section("Payments, webhooks & idempotency")
    status, invoices = call("GET", "/api/invoices", token=TOKENS["farmer"])
    check("farmer sees their invoices", status == 200 and len(invoices) >= 1)
    unpaid = next((i for i in invoices if i["status"] != "paid"), None)
    if unpaid:
        status, pay = call("POST", f"/api/invoices/{unpaid['id']}/pay", token=TOKENS["farmer"])
        check("farmer pays invoice (sandbox)", status == 200 and pay.get("signature_verified") is True)
        status, pay2 = call("POST", f"/api/invoices/{unpaid['id']}/pay", token=TOKENS["farmer"])
        check("repeat payment is idempotent", status == 200 and pay2.get("invoice", {}).get("status") == "paid")

    status, signed = call("POST", "/api/payments/sandbox-sign", {"invoice": "NOPE", "amount": 100, "event_id": "evt_test"})
    check("sandbox signing helper works", status == 200 and signed.get("signature"))
    status, bad = call("POST", "/api/payments/webhook", {"payload": {"invoice": "NOPE"}, "signature": "deadbeef"})
    check("webhook with bad signature rejected", status == 400)

    section("Reports, notifications, grievances, audit")
    status, report = call("GET", f"/api/cases/{cid}/report", token=TOKENS["farmer"])
    check("report generated for owner", status == 200 and report.get("report_id"))
    check("report carries a disclaimer", "preliminary" in report.get("disclaimer", "").lower())

    status, notifs = call("GET", "/api/notifications", token=TOKENS["farmer"])
    check("notifications delivered with evidence", status == 200 and any(n.get("delivery_evidence") for n in notifs))

    status, grv = call("POST", "/api/grievances", {
        "category": "payment", "subject": "Test ticket", "description": "Testing grievance flow", "priority": "high",
    }, token=TOKENS["farmer"])
    check("grievance created with ticket number", status == 201 and grv.get("ticket"))
    status, grv2 = call("PATCH", f"/api/grievances/{grv['id']}", {"status": "resolved", "note": "Fixed"}, token=TOKENS["admin"])
    check("admin resolves grievance", status == 200 and grv2.get("status") == "resolved")

    status, audit = call("GET", "/api/admin/audit", token=TOKENS["admin"])
    check("audit chain verified", status == 200 and audit.get("chain", {}).get("valid") is True)
    check("audit recorded the workflow", status == 200 and any(e["action"] == "case.transition" for e in audit.get("events", [])))

    status, analytics = call("GET", "/api/analytics", token=TOKENS["admin"])
    check("analytics returns aggregates", status == 200 and "by_state" in analytics)

    status, knowledge = call("GET", "/api/knowledge")
    check("verified knowledge sources exposed", status == 200 and len(knowledge) >= 5)
    check("knowledge has provenance", all(k.get("organization") for k in knowledge))

    print(f"\n\033[1mResult:\033[0m {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())

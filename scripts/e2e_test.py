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
            payload = r.read()
            if raw:
                # Binary payloads (PDF reports) must not be force-decoded.
                try:
                    return r.status, payload.decode()
                except UnicodeDecodeError:
                    return r.status, payload
            text = payload.decode()
            return r.status, (json.loads(text) if text else None)
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

    section("Registration privilege boundaries")
    status, meta = call("GET", "/api/meta")
    signup_roles = {r["key"] for r in (meta or {}).get("signup_roles", [])}
    check("signup roles advertised", signup_roles == {"farmer", "agronomist", "farm_manager", "drone_operator"},
          str(signup_roles))
    check("super_admin not self-service", "super_admin" not in signup_roles)

    status, esc = call("POST", "/api/auth/register", {
        "email": "escalate-probe@example.com", "full_name": "Escalation Probe",
        "password": "ProbePass123", "role": "super_admin",
    })
    check("self-registering as super_admin rejected", status == 403, f"{status} {esc}")

    # Unique address per run so the suite is idempotent against a persistent DB.
    import time as _time

    probe_email = f"selfservice-probe-{int(_time.time())}@example.com"
    status, ok = call("POST", "/api/auth/register", {
        "email": probe_email, "full_name": "Self Service",
        "password": "ProbePass123", "role": "farmer",
    })
    check("self-registering as farmer allowed", status == 201, f"{status} {ok}")
    if status == 201:
        check("new farmer gets farmer role", ok.get("user", {}).get("role") == "farmer")
        status, forbidden = call("GET", "/api/admin/users", token=ok.get("token"))
        check("new farmer cannot reach admin users", status == 403, str(status))

    section("Weather intelligence")
    status, farms = call("GET", "/api/farms", token=TOKENS["admin"])
    check("farms listed for weather lookup", status == 200 and len(farms) > 0)
    farm_id = farms[0]["id"] if farms else None
    status, wx = call("GET", f"/api/weather?farm_id={farm_id}&days=5", token=TOKENS["admin"])
    check("weather forecast returned", status == 200 and "current" in (wx or {}), str(status))
    if status == 200:
        check("weather includes spray windows", "spray_windows" in wx and "thresholds" in wx["spray_windows"])
        check("weather includes disease pressure", wx["disease_pressure"]["band"] in {"low", "moderate", "high", "unknown"})
        check("weather gives crop-health guidance", len(wx["guidance"]["crop_health"]) >= 1)
        check("weather gives treatment guidance", len(wx["guidance"]["treatment"]) >= 1)
        check("weather states a disclaimer", bool(wx.get("disclaimer")))
        check("hourly hours carry a spray verdict", all("spray_ok" in h for h in wx["hourly"][:6]))
    status, wxn = call("GET", "/api/weather", token=TOKENS["admin"])
    check("weather without a location is rejected", status == 422, str(status))

    section("Geospatial: search, reverse and directions")
    status, search = call("POST", "/api/geo/search", {"text": "Pune Maharashtra", "limit": 3}, token=TOKENS["admin"])
    check("place search returns results", status == 200 and len(search.get("results", [])) >= 1, str(status))
    if search.get("results"):
        r0 = search["results"][0]
        check("place result carries coordinates", r0.get("latitude") is not None and r0.get("longitude") is not None)
    status, rev = call("GET", "/api/geo/reverse?lat=18.5204&lon=73.8567", token=TOKENS["admin"])
    check("reverse geocode resolves an address", status == 200 and bool(rev.get("formatted")), str(status))
    status, direc = call("GET", f"/api/geo/directions/{farm_id}?from_lat=18.5204&from_lon=73.8567&mode=drive",
                         token=TOKENS["admin"])
    check("directions to a farm returned", status == 200 and "straight_line_km" in (direc or {}), str(status))
    if status == 200:
        check("directions include an origin and destination",
              bool(direc.get("origin")) and bool(direc.get("destination")))
        check("directions include a route or an explained fallback",
              bool(direc.get("route")) or bool(direc.get("route_error")))
    import time as _t
    _s, outsider = call("POST", "/api/auth/register", {
        "email": f"geo-outsider-{int(_t.time())}@example.com", "full_name": "Geo Outsider",
        "password": "ProbePass123", "role": "farmer"})
    outsider_token = (outsider or {}).get("token")
    status, forbidden = call("GET", f"/api/geo/directions/{farm_id}?from_lat=18.5&from_lon=73.8",
                             token=outsider_token)
    check("directions enforce farm access", status in (403, 404), str(status))

    section("Live location tracking")
    status, ping = call("POST", "/api/tracking/ping",
                        {"latitude": 18.8712, "longitude": 73.9123, "source": "person", "accuracy_m": 10},
                        token=TOKENS["admin"])
    check("location ping accepted", status == 201, f"{status} {ping}")
    status, live = call("GET", "/api/tracking/live?max_age_min=60", token=TOKENS["admin"])
    check("live actors returned", status == 200 and live.get("count", 0) >= 1, str(status))
    if status == 200 and live.get("actors"):
        check("live actor has a track and a latest fix",
              "latest" in live["actors"][0] and "track" in live["actors"][0])
    status, bad = call("POST", "/api/tracking/ping", {"latitude": 999, "longitude": 0}, token=TOKENS["admin"])
    check("out-of-range latitude rejected", status == 422, str(status))

    section("Live capture sessions")
    status, sess = call("POST", "/api/live-sessions", {"device": "drone", "notes": "e2e sweep"},
                        token=TOKENS["admin"])
    check("live session started", status == 201 and sess.get("status") == "live", f"{status} {sess}")
    if status == 201:
        status, upd = call("PATCH", f"/api/live-sessions/{sess['id']}",
                           {"latitude": 18.87, "longitude": 73.91, "frames": 4, "geotagged_frames": 3},
                           token=TOKENS["admin"])
        check("live session accepts frames and geotags",
              status == 200 and upd.get("frames") == 4 and upd.get("geotagged_frames") == 3)
        status, ended = call("POST", f"/api/live-sessions/{sess['id']}/end", {}, token=TOKENS["admin"])
        check("live session can be ended", status == 200 and ended.get("status") == "ended")

    section("Real-time AI vision analysis")
    # A 1x1 PNG is enough to prove the frame path and the response contract.
    import base64 as _b64
    tiny = ("data:image/png;base64," + _b64.b64encode(_b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")).decode())
    status, frame = call("POST", "/api/ai/analyze-frame",
                         {"image": tiny, "crop": "wheat", "observations": "orange pustules"},
                         token=TOKENS["admin"])
    check("frame analysis returned", status == 200 and "analysis" in (frame or {}), str(status))
    if status == 200:
        a = frame["analysis"]
        check("frame analysis yields findings", len(a.get("findings", [])) >= 1)
        check("frame analysis is labelled preliminary", a.get("preliminary") is True)
        check("frame analysis reports a mode", a.get("mode") in {"live", "simulated", "simulated-fallback"})
        check("frame analysis states uncertainty", 0 <= a.get("uncertainty", -1) <= 1)
    status, rejected = call("POST", "/api/ai/analyze-frame", {"image": "not-a-data-url"}, token=TOKENS["admin"])
    check("non data-URL frame rejected", status == 422, str(status))

    section("AI treatment drafting")
    status, draft = call("POST", "/api/ai/treatment-draft",
                         {"problem": "Wheat leaf rust", "crop": "wheat", "severity": "high"},
                         token=TOKENS["agronomist"])
    check("treatment draft returned", status == 200 and "measures" in (draft or {}), f"{status} {draft}")
    if status == 200:
        check("draft includes safety fields",
              bool(draft.get("ppe")) and bool(draft.get("pre_harvest_interval"))
              and bool(draft.get("re_entry_interval")))
        check("draft is marked as drafted", draft.get("drafted") is True)
    status, denied = call("POST", "/api/ai/treatment-draft",
                          {"problem": "Wheat leaf rust"}, token=TOKENS.get("farmer"))
    check("treatment drafting restricted to agronomist roles", status == 403, str(status))

    section("PDF reports")
    status, cases = call("GET", "/api/cases", token=TOKENS["admin"])
    if cases:
        cid = cases[0]["id"]
        status, pdf = call("GET", f"/api/cases/{cid}/report/pdf", token=TOKENS["admin"], raw=True)
        head = pdf[:4].decode('latin-1') if isinstance(pdf, (bytes, bytearray)) else str(pdf)[:4]
        check("PDF report generated", status == 200 and head == "%PDF", f"{status} {head!r}")
        check("PDF report is non-trivial in size", len(pdf) > 5000, str(len(pdf)))
        status, jsonrep = call("GET", f"/api/cases/{cid}/report", token=TOKENS["admin"])
        check("JSON report still available alongside PDF", status == 200 and "report_id" in jsonrep)

    print(f"\n\033[1mResult:\033[0m {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())

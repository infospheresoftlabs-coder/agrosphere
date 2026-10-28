"""Domain constants for AgroSphere: roles, workflow states, languages, crops."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    FARMER = "farmer"
    AGRONOMIST = "agronomist"
    FARM_MANAGER = "farm_manager"
    DRONE_OPERATOR = "drone_operator"
    SUPER_ADMIN = "super_admin"


ROLE_LABELS = {
    Role.FARMER: "Farmer",
    Role.AGRONOMIST: "Agronomist",
    Role.FARM_MANAGER: "Farm Manager",
    Role.DRONE_OPERATOR: "Drone Operator",
    Role.SUPER_ADMIN: "Super Administrator",
}


class CaseState(str, Enum):
    """Configurable lifecycle state machine for a crop-health case."""

    DRAFT = "draft"
    IMAGERY_CAPTURED = "imagery_captured"
    ANALYSIS_RUNNING = "analysis_running"
    AI_FINDINGS_READY = "ai_findings_ready"
    AWAITING_AGRONOMIST = "awaiting_agronomist"
    PLAN_PREPARED = "plan_prepared"
    AWAITING_MANAGER = "awaiting_manager"
    PLAN_APPROVED = "plan_approved"
    AWAITING_FARMER = "awaiting_farmer"
    IMPLEMENTATION_CHOSEN = "implementation_chosen"
    JOB_ASSIGNED = "job_assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"
    REOPENED = "reopened"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


# Allowed transitions: state -> set of states reachable from it.
TRANSITIONS: dict[CaseState, set[CaseState]] = {
    CaseState.DRAFT: {CaseState.IMAGERY_CAPTURED, CaseState.REJECTED},
    CaseState.IMAGERY_CAPTURED: {CaseState.ANALYSIS_RUNNING, CaseState.REJECTED},
    CaseState.ANALYSIS_RUNNING: {CaseState.AI_FINDINGS_READY, CaseState.REJECTED},
    CaseState.AI_FINDINGS_READY: {CaseState.AWAITING_AGRONOMIST, CaseState.REJECTED},
    CaseState.AWAITING_AGRONOMIST: {
        CaseState.PLAN_PREPARED,
        CaseState.NEEDS_REVISION,
        CaseState.REJECTED,
    },
    CaseState.NEEDS_REVISION: {CaseState.PLAN_PREPARED, CaseState.REJECTED},
    CaseState.PLAN_PREPARED: {CaseState.AWAITING_MANAGER},
    CaseState.AWAITING_MANAGER: {
        CaseState.PLAN_APPROVED,
        CaseState.NEEDS_REVISION,
        CaseState.REJECTED,
    },
    CaseState.PLAN_APPROVED: {CaseState.AWAITING_FARMER},
    CaseState.AWAITING_FARMER: {
        CaseState.IMPLEMENTATION_CHOSEN,
        CaseState.NEEDS_REVISION,
        CaseState.REJECTED,
    },
    CaseState.IMPLEMENTATION_CHOSEN: {CaseState.JOB_ASSIGNED, CaseState.IN_PROGRESS},
    CaseState.JOB_ASSIGNED: {CaseState.IN_PROGRESS, CaseState.REJECTED},
    CaseState.IN_PROGRESS: {CaseState.COMPLETED},
    CaseState.COMPLETED: {CaseState.FOLLOW_UP, CaseState.CLOSED},
    CaseState.FOLLOW_UP: {CaseState.CLOSED, CaseState.REOPENED},
    CaseState.REOPENED: {CaseState.AWAITING_AGRONOMIST},
    CaseState.CLOSED: {CaseState.REOPENED},
    CaseState.REJECTED: set(),
}

# Which role owns the action that moves a case *into* a given state.
STATE_OWNER: dict[CaseState, Role] = {
    CaseState.IMAGERY_CAPTURED: Role.FARMER,
    CaseState.ANALYSIS_RUNNING: Role.FARMER,
    CaseState.AI_FINDINGS_READY: Role.FARMER,
    CaseState.AWAITING_AGRONOMIST: Role.FARMER,
    CaseState.PLAN_PREPARED: Role.AGRONOMIST,
    CaseState.AWAITING_MANAGER: Role.AGRONOMIST,
    CaseState.PLAN_APPROVED: Role.FARM_MANAGER,
    CaseState.AWAITING_FARMER: Role.FARM_MANAGER,
    CaseState.IMPLEMENTATION_CHOSEN: Role.FARMER,
    CaseState.JOB_ASSIGNED: Role.FARM_MANAGER,
    CaseState.IN_PROGRESS: Role.DRONE_OPERATOR,
    CaseState.COMPLETED: Role.DRONE_OPERATOR,
    CaseState.FOLLOW_UP: Role.AGRONOMIST,
    CaseState.CLOSED: Role.FARMER,
    CaseState.REOPENED: Role.FARMER,
    CaseState.NEEDS_REVISION: Role.AGRONOMIST,
    CaseState.REJECTED: Role.SUPER_ADMIN,
}


# 22 Scheduled Indian Languages + English.
LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English", "dir": "ltr"},
    {"code": "as", "name": "Assamese", "native": "অসমীয়া", "dir": "ltr"},
    {"code": "bn", "name": "Bengali", "native": "বাংলা", "dir": "ltr"},
    {"code": "brx", "name": "Bodo", "native": "बड़ो", "dir": "ltr"},
    {"code": "doi", "name": "Dogri", "native": "डोगरी", "dir": "ltr"},
    {"code": "gu", "name": "Gujarati", "native": "ગુજરાતી", "dir": "ltr"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
    {"code": "kn", "name": "Kannada", "native": "ಕನ್ನಡ", "dir": "ltr"},
    {"code": "ks", "name": "Kashmiri", "native": "کٲشُر", "dir": "rtl"},
    {"code": "kok", "name": "Konkani", "native": "कोंकणी", "dir": "ltr"},
    {"code": "mai", "name": "Maithili", "native": "मैथिली", "dir": "ltr"},
    {"code": "ml", "name": "Malayalam", "native": "മലയാളം", "dir": "ltr"},
    {"code": "mni", "name": "Manipuri (Meitei)", "native": "ꯃꯤꯇꯩ ꯂꯣꯟ", "dir": "ltr"},
    {"code": "mr", "name": "Marathi", "native": "मराठी", "dir": "ltr"},
    {"code": "ne", "name": "Nepali", "native": "नेपाली", "dir": "ltr"},
    {"code": "or", "name": "Odia", "native": "ଓଡ଼ିଆ", "dir": "ltr"},
    {"code": "pa", "name": "Punjabi", "native": "ਪੰਜਾਬੀ", "dir": "ltr"},
    {"code": "sa", "name": "Sanskrit", "native": "संस्कृतम्", "dir": "ltr"},
    {"code": "sat", "name": "Santali", "native": "ᱥᱟᱱᱛᱟᱲᱤ", "dir": "ltr"},
    {"code": "sd", "name": "Sindhi", "native": "سنڌي", "dir": "rtl"},
    {"code": "ta", "name": "Tamil", "native": "தமிழ்", "dir": "ltr"},
    {"code": "te", "name": "Telugu", "native": "తెలుగు", "dir": "ltr"},
    {"code": "ur", "name": "Urdu", "native": "اردو", "dir": "rtl"},
]


# Demo credentials for the seeded accounts (development only).
DEMO_PASSWORD = "agro1234"

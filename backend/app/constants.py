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

# Roles an anonymous visitor may claim when creating their own account.
# Privileged roles are deliberately excluded: self-registration must never mint
# an administrator. Super admin accounts are created out of band (see
# ``python -m backend.app.manage create-admin``) and other privileged roles are
# granted by an administrator.
SELF_SERVICE_ROLES = (Role.FARMER, Role.AGRONOMIST, Role.FARM_MANAGER, Role.DRONE_OPERATOR)


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

# Which roles may perform the action that moves a case *into* a given state.
#
# A state lists every role that legitimately performs that step, so each role can
# carry its part of the workflow to completion. Where a step is shared — a farm
# manager may run the same capture or analysis a farmer would, an agronomist may
# confirm their own plan while the farm manager also approves it — both roles are
# named, rather than forcing a hand-off to a single role. The super administrator
# is always permitted (see ``transition_case``).
STATE_OWNERS: dict[CaseState, set[Role]] = {
    CaseState.IMAGERY_CAPTURED: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.ANALYSIS_RUNNING: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.AI_FINDINGS_READY: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.AWAITING_AGRONOMIST: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.PLAN_PREPARED: {Role.AGRONOMIST},
    CaseState.AWAITING_MANAGER: {Role.AGRONOMIST},
    CaseState.PLAN_APPROVED: {Role.FARM_MANAGER},
    CaseState.AWAITING_FARMER: {Role.FARM_MANAGER},
    CaseState.IMPLEMENTATION_CHOSEN: {Role.FARMER, Role.FARM_MANAGER},
    CaseState.JOB_ASSIGNED: {Role.FARM_MANAGER},
    CaseState.IN_PROGRESS: {Role.DRONE_OPERATOR, Role.FARMER, Role.FARM_MANAGER},
    CaseState.COMPLETED: {Role.DRONE_OPERATOR, Role.FARMER, Role.FARM_MANAGER},
    CaseState.FOLLOW_UP: {Role.AGRONOMIST, Role.FARMER, Role.FARM_MANAGER},
    CaseState.CLOSED: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.REOPENED: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST, Role.DRONE_OPERATOR},
    CaseState.NEEDS_REVISION: {Role.AGRONOMIST},
    CaseState.REJECTED: {Role.FARMER, Role.FARM_MANAGER, Role.AGRONOMIST},
}

# The single role shown as the "owner" of a state in the interface, for the
# primary actor of that step. Kept for the /api/meta contract.
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


def state_roles(state: CaseState) -> set[Role]:
    """Roles permitted to move a case into ``state`` (super admin aside)."""
    return STATE_OWNERS.get(state, {Role.SUPER_ADMIN})


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

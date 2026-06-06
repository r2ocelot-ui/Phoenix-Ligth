"""Rank ladder, permission resolution and progression rules.

Each rank carries a default permission set. A user's *effective* permissions are
(rank defaults ∪ per-user extra) − per-user denied; owners hold the wildcard.

Progression is mostly informational: it reports whether a user meets the
points/tenure bar for the next rank. Actual promotion is an admin action unless
auto-promote is enabled (and even then only up to a configured ceiling), so
newcomers stay limited until they've shown activity — exactly the "novato vs
experto" behaviour requested.
"""
from datetime import datetime, timezone

# --- Granular permissions ---------------------------------------------------
P_CABINET_READ = "cabinet:read"
P_CABINET_CONTROL = "cabinet:control"
P_ALARM_ACK = "alarm:ack"
P_CABINET_MANAGE = "cabinet:manage"
P_AUDIT_READ = "audit:read"
P_USER_VIEW = "user:view"
P_USER_MANAGE = "user:manage"
WILDCARD = "*"

ALL_PERMISSIONS = [
    P_CABINET_READ,
    P_CABINET_CONTROL,
    P_ALARM_ACK,
    P_CABINET_MANAGE,
    P_AUDIT_READ,
    P_USER_VIEW,
    P_USER_MANAGE,
]

# --- Rank ladder (ordered low -> high) --------------------------------------
RANK_ORDER = ["novato", "operador", "tecnico", "supervisor", "admin", "owner"]

RANKS: dict[str, dict] = {
    "novato": {"level": 0, "label": "Novato", "permissions": {P_CABINET_READ}},
    "operador": {
        "level": 1,
        "label": "Operador",
        "permissions": {P_CABINET_READ, P_CABINET_CONTROL},
    },
    "tecnico": {
        "level": 2,
        "label": "Técnico",
        "permissions": {P_CABINET_READ, P_CABINET_CONTROL, P_ALARM_ACK, P_CABINET_MANAGE},
    },
    "supervisor": {
        "level": 3,
        "label": "Supervisor",
        "permissions": {
            P_CABINET_READ,
            P_CABINET_CONTROL,
            P_ALARM_ACK,
            P_CABINET_MANAGE,
            P_AUDIT_READ,
            P_USER_VIEW,
        },
    },
    "admin": {
        "level": 4,
        "label": "Admin",
        "permissions": {
            P_CABINET_READ,
            P_CABINET_CONTROL,
            P_ALARM_ACK,
            P_CABINET_MANAGE,
            P_AUDIT_READ,
            P_USER_VIEW,
            P_USER_MANAGE,
        },
    },
    "owner": {"level": 5, "label": "Owner", "permissions": {WILDCARD}},
}

# Points / tenure (days) required to be eligible for each target rank.
# admin and owner are intentionally absent: manual assignment only.
PROGRESSION: dict[str, dict] = {
    "operador": {"min_points": 10, "min_days": 0},
    "tecnico": {"min_points": 50, "min_days": 3},
    "supervisor": {"min_points": 200, "min_days": 14},
}

DEFAULT_RANK = "novato"
BOOTSTRAP_RANK = "owner"  # the very first registered user


def rank_level(rank: str) -> int:
    return RANKS.get(rank, RANKS[DEFAULT_RANK])["level"]


def next_rank(rank: str) -> str | None:
    try:
        idx = RANK_ORDER.index(rank)
    except ValueError:
        return None
    return RANK_ORDER[idx + 1] if idx + 1 < len(RANK_ORDER) else None


def rank_permissions(rank: str) -> set[str]:
    return set(RANKS.get(rank, RANKS[DEFAULT_RANK])["permissions"])


def effective_permissions(user) -> set[str]:
    perms = rank_permissions(user.rank)
    if WILDCARD in perms:
        return {WILDCARD}
    perms |= set(user.extra_permissions or [])
    perms -= set(user.denied_permissions or [])
    return perms


def has_permission(user, permission: str) -> bool:
    perms = effective_permissions(user)
    return WILDCARD in perms or permission in perms


def _tenure_days(user) -> int:
    created = getattr(user, "created_at", None)
    if created is None:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).days


def promotion_eligibility(user) -> dict:
    target = next_rank(user.rank)
    if target is None or target not in PROGRESSION:
        return {
            "next_rank": target,
            "eligible": False,
            "reason": "Top rank or manual assignment only.",
        }
    rule = PROGRESSION[target]
    days = _tenure_days(user)
    eligible = user.activity_points >= rule["min_points"] and days >= rule["min_days"]
    return {
        "next_rank": target,
        "eligible": eligible,
        "have_points": user.activity_points,
        "need_points": rule["min_points"],
        "have_days": days,
        "need_days": rule["min_days"],
    }


def maybe_auto_promote(user, *, enabled: bool, max_rank: str) -> bool:
    """Promote the user one step if enabled and eligible, capped at max_rank.

    Returns True if a promotion happened (the caller is responsible for
    persisting the change).
    """
    if not enabled:
        return False
    info = promotion_eligibility(user)
    target = info.get("next_rank")
    if not target or not info.get("eligible"):
        return False
    if rank_level(target) > rank_level(max_rank):
        return False
    user.rank = target
    return True

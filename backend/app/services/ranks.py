"""Rank ladder, permission resolution and progression rules.

Each rank carries a default permission set. A user's *effective* permissions are
(rank defaults ∪ per-user extra) − per-user denied; owners hold the wildcard.

The ``RANKS`` dict is a live, mutable view of what's in the ``roles`` table —
``reload_ranks(db)`` rebuilds it after edits, and a startup hook hydrates it
once the database is up. Code outside the editor consumes ``RANKS`` exactly
as before, so the rest of the app didn't have to change.

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
P_ROLE_MANAGE = "role:manage"
WILDCARD = "*"

# Catalogue surfaced to the panel — each permission carries a short label so
# the role editor's checklist reads in Spanish, not in API jargon.
PERMISSION_CATALOG: list[dict] = [
    {"id": P_CABINET_READ, "label": "Ver cuadros",
     "description": "Listar cuadros, ver mapa, telemetría y alarmas."},
    {"id": P_CABINET_CONTROL, "label": "Operar cuadros",
     "description": "Encender, apagar y regular (dimming) los cuadros."},
    {"id": P_ALARM_ACK, "label": "Reconocer alarmas",
     "description": "Marcar alarmas como reconocidas / cerradas."},
    {"id": P_CABINET_MANAGE, "label": "Gestionar cuadros",
     "description": "Crear, editar y borrar cuadros, circuitos y puntos de luz."},
    {"id": P_AUDIT_READ, "label": "Ver auditoría",
     "description": "Acceso al registro de auditoría general."},
    {"id": P_USER_VIEW, "label": "Ver usuarios",
     "description": "Listar usuarios y ver sus detalles."},
    {"id": P_USER_MANAGE, "label": "Gestionar usuarios",
     "description": "Crear, desactivar, cambiar rango/contraseña y permisos de usuario."},
    {"id": P_ROLE_MANAGE, "label": "Gestionar rangos",
     "description": "Editar los permisos por defecto de cada rango y crear rangos custom."},
]

ALL_PERMISSIONS = [p["id"] for p in PERMISSION_CATALOG]

# --- Built-in rank ladder (low -> high) -------------------------------------
# 7-tier ladder inspired by Hydra's role separation: a clear divide between
# "operates the software" (owner / project admin) and "operates a city's
# lights" (engineer / supervisor / technician / operator / viewer).
# These are *defaults* — used to seed the ``roles`` table the first time
# Phoenix boots; after that, every read goes through the live ``RANKS`` dict
# (which the editor in /api/v1/roles keeps fresh).
BUILTIN_RANK_ORDER = [
    "visualizador", "operador", "tecnico", "supervisor",
    "ingeniero", "admin_proyecto", "owner",
]

DEFAULT_RANKS: dict[str, dict] = {
    "visualizador": {
        "level": 0, "label": "Visualizador",
        "description": "Solo lectura. Ve cuadros, alarmas y mapa, pero no opera.",
        "permissions": {P_CABINET_READ},
    },
    "operador": {
        "level": 1, "label": "Operador",
        "description": "Sala de control: encender, apagar y regular (dimming) cuadros.",
        "permissions": {P_CABINET_READ, P_CABINET_CONTROL},
    },
    "tecnico": {
        "level": 2, "label": "Técnico",
        "description": "Operario de campo: opera cuadros y reconoce alarmas.",
        "permissions": {P_CABINET_READ, P_CABINET_CONTROL, P_ALARM_ACK},
    },
    "supervisor": {
        "level": 3, "label": "Supervisor",
        "description": "Jefe de turno: operación, alarmas, ver usuarios y auditoría.",
        "permissions": {
            P_CABINET_READ, P_CABINET_CONTROL, P_ALARM_ACK,
            P_AUDIT_READ, P_USER_VIEW,
        },
    },
    "ingeniero": {
        "level": 4, "label": "Ingeniero",
        "description": "Responsable técnico: topología, configuración de cuadros y analítica.",
        "permissions": {
            P_CABINET_READ, P_CABINET_CONTROL, P_ALARM_ACK, P_CABINET_MANAGE,
            P_AUDIT_READ, P_USER_VIEW,
        },
    },
    "admin_proyecto": {
        "level": 5, "label": "Director",
        "description": "Director territorial: administra una ciudad/instalación entera (usuarios, roles, configuración del proyecto).",
        "permissions": {
            P_CABINET_READ, P_CABINET_CONTROL, P_ALARM_ACK, P_CABINET_MANAGE,
            P_AUDIT_READ, P_USER_VIEW, P_USER_MANAGE, P_ROLE_MANAGE,
        },
    },
    "owner": {
        "level": 6, "label": "Phoenix",
        "description": "Dueño del software Phoenix. Acceso total, multi-proyecto.",
        "permissions": {WILDCARD},
    },
}

# Live view of the catalogue — populated from BD by reload_ranks() and used
# as a fallback (defaults) the very first time the cache is empty.
RANKS: dict[str, dict] = {rid: dict(r, permissions=set(r["permissions"]))
                          for rid, r in DEFAULT_RANKS.items()}
RANK_ORDER: list[str] = list(BUILTIN_RANK_ORDER)


def reload_ranks(db) -> None:
    """Refresh ``RANKS`` / ``RANK_ORDER`` from the ``roles`` table.

    Called once at startup and after any role edit. Falls back to the built-in
    defaults if the table is empty (typical during very-first-boot before the
    seeder has run, or in tests that don't bother seeding).
    """
    from app.models.role import Role
    rows = db.query(Role).order_by(Role.level).all()
    if not rows:
        return
    new_ranks: dict[str, dict] = {}
    for r in rows:
        perms = set(r.permissions or [])
        if r.is_owner:
            perms.add(WILDCARD)
        new_ranks[r.id] = {
            "level": r.level,
            "label": r.label,
            "description": r.description or "",
            "permissions": perms,
        }
    RANKS.clear()
    RANKS.update(new_ranks)
    RANK_ORDER.clear()
    RANK_ORDER.extend(sorted(RANKS.keys(), key=lambda rid: RANKS[rid]["level"]))


# Aliases for renamed ranks, so older databases keep working after upgrade.
# Read-only mapping consumed by the migration step in init_db().
LEGACY_ALIASES: dict[str, str] = {
    "novato": "visualizador",
    "admin": "admin_proyecto",
}

# Points / tenure (days) required to be eligible for each target rank.
# admin_proyecto and owner are intentionally absent: manual assignment only.
PROGRESSION: dict[str, dict] = {
    "operador": {"min_points": 10, "min_days": 0},
    "tecnico": {"min_points": 50, "min_days": 3},
    "supervisor": {"min_points": 200, "min_days": 14},
    "ingeniero": {"min_points": 500, "min_days": 30},
}

DEFAULT_RANK = "visualizador"
BOOTSTRAP_RANK = "owner"  # the very first registered user


def canonicalize(rank: str) -> str:
    """Return the current canonical id for a rank, mapping legacy aliases."""
    return LEGACY_ALIASES.get(rank, rank)


def rank_level(rank: str) -> int:
    rank = canonicalize(rank)
    if rank in RANKS:
        return RANKS[rank]["level"]
    return RANKS.get(DEFAULT_RANK, {"level": 0})["level"]


def next_rank(rank: str) -> str | None:
    rank = canonicalize(rank)
    try:
        idx = RANK_ORDER.index(rank)
    except ValueError:
        return None
    return RANK_ORDER[idx + 1] if idx + 1 < len(RANK_ORDER) else None


def rank_permissions(rank: str) -> set[str]:
    rank = canonicalize(rank)
    if rank in RANKS:
        return set(RANKS[rank]["permissions"])
    return set(RANKS.get(DEFAULT_RANK, {"permissions": set()})["permissions"])


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

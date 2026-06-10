from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Quick-unlock credentials (hashed like the password). Optional, per user.
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pattern_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 2FA TOTP (Google Authenticator). Secret stored base32; only enforced
    # once totp_enabled is True (set after the user confirms a first code).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Claves de recuperación 2FA: lista JSON de hashes (se consumen al usarse).
    # Permiten entrar si el usuario pierde el móvil con el autenticador.
    totp_recovery: Mapped[list] = mapped_column(JSON, default=list)
    # Brute-force guard: consecutive failures and an auto-expiring lockout.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rank: Mapped[str] = mapped_column(String(32), default="visualizador")
    # Multi-tenant scaffolding (see docs/DECISIONS.md §3.1). NULL = global,
    # which is the default until proper tenant scoping is wired up.
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-user permission overrides on top of the rank defaults.
    extra_permissions: Mapped[list] = mapped_column(JSON, default=list)
    denied_permissions: Mapped[list] = mapped_column(JSON, default=list)
    activity_points: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Ficha del trabajador. Campos opcionales (la mayoría empleados los rellenan).
    # Pack laboral (empleados Phoenix):
    full_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    job_title: Mapped[str] = mapped_column(String(80), default="")
    department: Mapped[str] = mapped_column(String(80), default="")
    site: Mapped[str] = mapped_column(String(80), default="")  # sede física
    # Turno base: "mañana", "tarde" (cubre también la noche operativa) u
    # "oficina" (sin turno fijo). Las horas concretas las marca el convenio.
    shift: Mapped[str] = mapped_column(String(32), default="")
    # Guardia: fecha hasta la que está localizable fuera de horario. Eje
    # independiente del turno — alguien de mañana puede estar de guardia
    # esa semana. NULL o fecha pasada = no está de guardia.
    on_call_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Pack contractual:
    employee_id: Mapped[str] = mapped_column(String(40), default="")  # internos
    national_id: Mapped[str] = mapped_column(String(20), default="")  # DNI/NIF externos
    company: Mapped[str] = mapped_column(String(120), default="")     # empresa externos
    # Auditoría visible en la ficha:
    last_login_ip: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(String(512), default="")  # solo la ve admin

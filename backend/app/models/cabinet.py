from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Cabinet(Base):
    """Registry of lighting cabinets: identity + location metadata.

    Live telemetry is kept in-memory by the MQTT bus; this table holds the
    durable description (name, zone, coordinates) used by the map and reports.
    """

    __tablename__ = "cabinets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    number: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(9), default="#f97316")
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Project / city scope. NULL = "global" (visible only to owners or to
    # users without a project assigned). See services/tenancy.py.
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Modo de regulación del alumbrado (ver services/dimming_controller.py):
    #   "manual"   → el operario fija el nivel; el programador no lo toca.
    #   "schedule" → programa horario fijo (+ lux). Determinista.
    #   "ai"       → motor adaptativo: sol + tarifa + lux + perfil de calle.
    dimming_mode: Mapped[str] = mapped_column(String(16), default="schedule")
    # Perfil de uso de la vía (suelo de seguridad del modo IA):
    #   "arterial"    → vía principal: mantener alto.
    #   "residential" → calle residencial tranquila: bajar agresivo.
    #   "crossing"    → paso de peatones / glorieta: nunca por debajo de X.
    street_profile: Mapped[str] = mapped_column(String(16), default="residential")
    # Modo de regulación ANTES de entrar en emergencia. NULL = el cuadro no está
    # en emergencia. Cuando se activa /emergency/all-on se guarda aquí el modo
    # previo (si aún no había uno) para poder restaurarlo con /emergency/clear.
    pre_emergency_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

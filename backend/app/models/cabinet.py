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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

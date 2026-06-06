from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LightPoint(Base):
    """A single lighting point (farola/luminaria).

    Belongs to a cabinet (CM) and a circuit, and sits on one phase (L1/L2/L3).
    Carries its own coordinates so it can be drawn as a point on the map.
    """

    __tablename__ = "light_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cabinet_code: Mapped[str] = mapped_column(String(32), index=True)
    circuit_id: Mapped[int] = mapped_column(Integer, index=True)
    number: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(120), default="")
    phase: Mapped[str] = mapped_column(String(8), default="L1")  # L1/L2/L3
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_w: Mapped[float] = mapped_column(Float, default=100.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

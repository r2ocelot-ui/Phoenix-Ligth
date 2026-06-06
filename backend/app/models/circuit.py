from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Circuit(Base):
    """A feeder circuit (salida) of a control cabinet (CM).

    A cabinet has several circuits; each lighting point belongs to one circuit
    and one phase. `color` is used to identify the circuit on the map.
    """

    __tablename__ = "circuits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cabinet_code: Mapped[str] = mapped_column(String(32), index=True)
    number: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), default="")
    color: Mapped[str] = mapped_column(String(9), default="#38bdf8")
    phase: Mapped[str] = mapped_column(String(8), default="III")  # L1/L2/L3/III
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

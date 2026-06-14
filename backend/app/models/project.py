"""Project / city model — multi-tenant scaffolding.

The schema includes it so users, cabinets and audit entries can later be
scoped to a specific project without a schema migration. The API does NOT
filter by project_id yet: that switch flips when a second tenant arrives.
See docs/DECISIONS.md §3.1.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Topes de dimming por tramo tarifario (configurables por proyecto/contrato).
    # NULL = usa el default global de settings (tariff_cap_*/tariff_floor_level).
    # Así, una ciudad con un contrato 3.0TD agresivo puede recortar más en punta
    # sin afectar al resto.
    tariff_cap_punta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_cap_llano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_cap_valle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_floor_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

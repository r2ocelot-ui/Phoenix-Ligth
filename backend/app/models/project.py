"""Project / city model — multi-tenant scaffolding.

The schema includes it so users, cabinets and audit entries can later be
scoped to a specific project without a schema migration. The API does NOT
filter by project_id yet: that switch flips when a second tenant arrives.
See docs/DECISIONS.md §3.1.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Región / comunidad para AGRUPAR ciudades (Comunidad Valenciana, Murcia…).
    # Es solo organización + asignación en bloque: por debajo el aislamiento
    # sigue siendo por ``project_id`` (N:N), así que no toca el núcleo multi-tenant.
    region: Mapped[str] = mapped_column(String(64), default="")
    # Topes de dimming por tramo tarifario (configurables por proyecto/contrato).
    # NULL = usa el default global de settings (tariff_cap_*/tariff_floor_level).
    # Así, una ciudad con un contrato 3.0TD agresivo puede recortar más en punta
    # sin afectar al resto.
    tariff_cap_punta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_cap_llano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_cap_valle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tariff_floor_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ¿Aplicar recorte de dimming por tarifa en este proyecto? NULL = usa el
    # global (settings.tariff_enabled). False = nunca recorta por precio (p.ej.
    # una avenida noble que se quiere a tope siempre). True = sí recorta.
    tariff_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

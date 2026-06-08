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

    # --- Identificación (RF Light GEO §1) ---
    inventory_code: Mapped[str] = mapped_column(String(64), default="")
    technology: Mapped[str] = mapped_column(String(40), default="")   # LED, VSAP, HM, Halog, Otro
    manufacturer: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(80), default="")

    # --- Óptica (RF Light GEO §2) ---
    photometric: Mapped[str] = mapped_column(String(80), default="")
    regulation: Mapped[str] = mapped_column(String(40), default="")   # 1-10V, DALI, autónoma, ninguna
    serial_number: Mapped[str] = mapped_column(String(80), default="")
    color_temp_k: Mapped[str] = mapped_column(String(16), default="")  # "3000K", "4000K"
    network_id: Mapped[str] = mapped_column(String(64), default="")    # nodo RF/LoRa/DALI

    # --- Ubicación administrativa (§3, autorrellenable por geocoding) ---
    province: Mapped[str] = mapped_column(String(80), default="")
    locality: Mapped[str] = mapped_column(String(80), default="")
    postal_code: Mapped[str] = mapped_column(String(10), default="")
    street: Mapped[str] = mapped_column(String(160), default="")
    street_number: Mapped[str] = mapped_column(String(16), default="")
    notes: Mapped[str] = mapped_column(String(512), default="")

    # --- Montaje (§4) ---
    support_type: Mapped[str] = mapped_column(String(40), default="")  # poste, columna, brazo, etc.
    layout_type: Mapped[str] = mapped_column(String(40), default="")   # unilateral, bilateral, tresbolillo
    construction_type: Mapped[str] = mapped_column(String(60), default="")
    light_source_type: Mapped[str] = mapped_column(String(40), default="")

    # --- Desmontaje (§5): datos de la antigua luminaria sustituida ---
    old_manufacturer: Mapped[str] = mapped_column(String(80), default="")
    old_model: Mapped[str] = mapped_column(String(80), default="")
    old_power_w: Mapped[float] = mapped_column(Float, default=0.0)
    old_light_source_type: Mapped[str] = mapped_column(String(40), default="")
    old_notes: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

from pydantic import BaseModel, ConfigDict, Field


class CircuitCreate(BaseModel):
    cabinet_code: str
    number: int = 1
    name: str = ""
    color: str = "#38bdf8"
    phase: str = "III"
    expected_power_w: float = Field(0.0, ge=0)


class CircuitUpdate(BaseModel):
    number: int | None = None
    name: str | None = None
    color: str | None = None
    phase: str | None = None
    expected_power_w: float | None = Field(default=None, ge=0)
    # Reasignar el circuito a otro CM (fusión de cuadros tras retrofit LED).
    # Al cambiarlo, las luminarias del circuito se mueven con él.
    cabinet_code: str | None = None


class CircuitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_code: str
    number: int
    name: str
    color: str
    phase: str
    expected_power_w: float = 0.0


class LightPointCreate(BaseModel):
    cabinet_code: str
    circuit_id: int
    number: int = 1
    label: str = ""
    phase: str = "L1"
    latitude: float | None = None
    longitude: float | None = None
    power_w: float = Field(100.0, ge=0)
    # Identificación
    inventory_code: str = ""
    technology: str = ""
    manufacturer: str = ""
    model: str = ""
    # Óptica
    photometric: str = ""
    regulation: str = ""
    serial_number: str = ""
    color_temp_k: str = ""
    network_id: str = ""
    # Ubicación administrativa
    province: str = ""
    locality: str = ""
    postal_code: str = ""
    street: str = ""
    street_number: str = ""
    notes: str = ""
    # Montaje
    support_type: str = ""
    layout_type: str = ""
    construction_type: str = ""
    light_source_type: str = ""
    # Desmontaje (luminaria antigua sustituida)
    old_manufacturer: str = ""
    old_model: str = ""
    old_power_w: float = Field(0.0, ge=0)
    old_light_source_type: str = ""
    old_notes: str = ""


class LightPointUpdate(BaseModel):
    # Todo opcional; sólo se actualiza lo que llega.
    circuit_id: int | None = None
    number: int | None = None
    label: str | None = None
    phase: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    power_w: float | None = None
    inventory_code: str | None = None
    technology: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    photometric: str | None = None
    regulation: str | None = None
    serial_number: str | None = None
    color_temp_k: str | None = None
    network_id: str | None = None
    province: str | None = None
    locality: str | None = None
    postal_code: str | None = None
    street: str | None = None
    street_number: str | None = None
    notes: str | None = None
    support_type: str | None = None
    layout_type: str | None = None
    construction_type: str | None = None
    light_source_type: str | None = None
    old_manufacturer: str | None = None
    old_model: str | None = None
    old_power_w: float | None = None
    old_light_source_type: str | None = None
    old_notes: str | None = None


class LightPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_code: str
    circuit_id: int
    number: int
    label: str
    phase: str
    latitude: float | None
    longitude: float | None
    power_w: float
    inventory_code: str = ""
    technology: str = ""
    manufacturer: str = ""
    model: str = ""
    photometric: str = ""
    regulation: str = ""
    serial_number: str = ""
    color_temp_k: str = ""
    network_id: str = ""
    province: str = ""
    locality: str = ""
    postal_code: str = ""
    street: str = ""
    street_number: str = ""
    notes: str = ""
    support_type: str = ""
    layout_type: str = ""
    construction_type: str = ""
    light_source_type: str = ""
    old_manufacturer: str = ""
    old_model: str = ""
    old_power_w: float = 0.0
    old_light_source_type: str = ""
    old_notes: str = ""


class LightCatalog(BaseModel):
    """Valores conocidos para los selectores con autocompletado de la ficha
    de luminaria (datalist en frontend). Se construye con la unión de los
    valores ya usados en la BD + un conjunto de defaults razonables."""
    technologies: list[str]
    manufacturers: list[str]
    models: list[str]
    regulations: list[str]
    color_temps: list[str]
    support_types: list[str]
    layout_types: list[str]
    light_source_types: list[str]

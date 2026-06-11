"""Tarifa eléctrica por tramos → dimming consciente del coste (offline).

La idea: el alumbrado **no se apaga** porque la luz esté cara (seguridad
primero), pero en horas punta se puede **reducir un poco** el dimming para
ahorrar, siempre por encima de un mínimo de seguridad (`floor`).

Tramos por defecto: tarifa española **2.0TD** (3 periodos), en hora civil
LOCAL. Es configurable para encajar con el contrato real (2.0TD/3.0TD).
Sin dependencias externas: funciona en redes OT aisladas.

- P1 **Punta** (caro): 10–14 h y 18–22 h en días laborables.
- P2 **Llano**: 8–10, 14–18 y 22–24 h laborables.
- P3 **Valle** (barato): 0–8 h laborables + **todo** el fin de semana.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

# Mapa hora→periodo para un día laborable (índice = hora 0–23).
WORKDAY_PERIODS: tuple[str, ...] = (
    "P3", "P3", "P3", "P3", "P3", "P3", "P3", "P3",  # 00–07 valle
    "P2", "P2",                                       # 08–09 llano
    "P1", "P1", "P1", "P1",                           # 10–13 punta
    "P2", "P2", "P2", "P2",                           # 14–17 llano
    "P1", "P1", "P1", "P1",                           # 18–21 punta
    "P2", "P2",                                       # 22–23 llano
)
# Fin de semana (y festivos, si se amplía): todo valle.
WEEKEND_PERIODS: tuple[str, ...] = tuple("P3" for _ in range(24))

PERIOD_LABELS: dict[str, str] = {"P1": "Punta", "P2": "Llano", "P3": "Valle"}

# Topes por defecto (se pueden sobreescribir por settings/contrato). En valle
# no se limita; en punta se recorta para ahorrar. Nunca baja del `floor` que
# pasa el llamador (mínimo de seguridad del alumbrado).
LEVEL_CAP: dict[str, int] = {"P1": 75, "P2": 90, "P3": 100}


def level_cap(period: str) -> int:
    """Tope de dimming del periodo, leído de settings (configurable por
    contrato); cae a los valores por defecto si el periodo es desconocido."""
    caps = {
        "P1": settings.tariff_cap_punta,
        "P2": settings.tariff_cap_llano,
        "P3": settings.tariff_cap_valle,
    }
    return caps.get(period, LEVEL_CAP.get(period, 100))


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.tariff_timezone)


def now_local() -> datetime:
    """Hora actual en la zona del despliegue (NO la del servidor, que suele
    ir en UTC). Es la que manda para decidir el tramo de tarifa."""
    return datetime.now(_tz())


def _to_local(when: datetime) -> datetime:
    """Lleva ``when`` a la zona de tarifa. Si trae tzinfo se convierte; si es
    naive se asume que ya viene en hora local del despliegue."""
    return when.astimezone(_tz()) if when.tzinfo is not None else when


def current_period(when: datetime) -> str:
    """Periodo tarifario (P1/P2/P3) para ese instante, en hora civil LOCAL.

    Convierte ``when`` a la zona del despliegue (`tariff_timezone`) antes de
    mirar día/hora, así un datetime en UTC da el tramo correcto."""
    when = _to_local(when)
    table = WEEKEND_PERIODS if when.weekday() >= 5 else WORKDAY_PERIODS
    return table[when.hour]


def cost_aware_level(base_level: int, when: datetime, *, floor: int) -> int:
    """Ajusta un nivel de dimming base según la tarifa, con red de seguridad.

    - Si la luz va apagada (``base_level <= 0``) se queda apagada: la tarifa
      nunca enciende el alumbrado.
    - Si va encendida, se recorta al tope del periodo pero **nunca por
      debajo de ``floor``** (mínimo de seguridad vial).
    """
    if base_level <= 0:
        return 0
    cap = level_cap(current_period(when))
    return max(min(base_level, cap), floor)

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

# Tope de dimming permitido por periodo (consciente del coste). En valle no
# se limita; en punta se recorta para ahorrar. Nunca baja del `floor` que
# pasa el llamador (mínimo de seguridad del alumbrado).
LEVEL_CAP: dict[str, int] = {"P1": 75, "P2": 90, "P3": 100}


def current_period(when: datetime) -> str:
    """Periodo tarifario (P1/P2/P3) para ese instante en hora LOCAL.

    Usa ``when.weekday()`` (0=lunes … 6=domingo) y ``when.hour``. El
    servidor debe correr en la zona horaria del despliegue, o se pasa un
    ``when`` ya en hora local."""
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
    cap = LEVEL_CAP.get(current_period(when), 100)
    return max(min(base_level, cap), floor)

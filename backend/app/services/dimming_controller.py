"""Dimming profile resolver.

Given a time-of-day and an optional ambient lux reading, returns the dimming
level (0-100) that should be applied to a cabinet. Profiles are intentionally
simple: a list of (start_hour, end_hour, level) tuples evaluated in order.

``resolve_level_cost_aware`` añade una capa opcional de tarifa eléctrica:
recorta el nivel en horas caras pero nunca por debajo de un mínimo de
seguridad. Ver services/tariff.py.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.services import sun, tariff


DEFAULT_PROFILE: list[tuple[time, time, int]] = [
    (time(0, 0), time(6, 0), 30),
    (time(6, 0), time(7, 30), 70),
    (time(7, 30), time(18, 0), 0),
    (time(18, 0), time(22, 0), 100),
    (time(22, 0), time(23, 59, 59), 50),
]

LUX_THRESHOLD_ON = 30.0
LUX_THRESHOLD_OFF = 80.0


def resolve_level(now: time, ambient_lux: float | None = None) -> int:
    if ambient_lux is not None and ambient_lux > LUX_THRESHOLD_OFF:
        return 0

    for start, end, level in DEFAULT_PROFILE:
        if start <= now <= end:
            if ambient_lux is not None and ambient_lux < LUX_THRESHOLD_ON:
                return max(level, 50)
            return level
    return 0


def resolve_level_cost_aware(
    now: time, when: datetime, ambient_lux: float | None = None, *, floor: int
) -> int:
    """Como ``resolve_level`` pero aplicando el tope por tarifa eléctrica.

    ``when`` es el datetime (hora local) que decide el tramo tarifario.
    El alumbrado apagado sigue apagado; encendido, se recorta en horas
    caras pero nunca por debajo de ``floor`` (mínimo de seguridad)."""
    base = resolve_level(now, ambient_lux)
    return tariff.cost_aware_level(base, when, floor=floor)


# Nivel al que se enciende si astronómicamente es de noche pero el perfil
# horario (de horas fijas) cree que es de día y devuelve 0.
NIGHT_DEFAULT_LEVEL = 100


def resolve_auto_level(
    when: datetime, latitude: float, longitude: float, *, floor: int,
    use_tariff: bool = True,
) -> int:
    """Nivel de dimming decidido por el SOL (`sun.py`), SIN fotocélula.

    - De día (astronómico) → 0 (apagado).
    - De noche → nivel del perfil horario; si el perfil cree que es de día
      (devuelve 0) pero astronómicamente es de noche, enciende a
      ``NIGHT_DEFAULT_LEVEL``. Después aplica el tope de tarifa y nunca baja
      del mínimo de seguridad ``floor``.

    ``when`` debe llevar tzinfo (usa ``tariff.now_local()``). El sol manda
    sobre el reloj: más fiable que horas fijas y sin hardware que se ensucie.
    """
    if when.tzinfo is None:
        raise ValueError("`when` debe llevar tzinfo (usa tariff.now_local())")
    if not sun.is_dark(when, latitude, longitude):
        return 0
    local = when.astimezone(ZoneInfo(settings.tariff_timezone))
    base = resolve_level(local.time())
    if base <= 0:
        base = NIGHT_DEFAULT_LEVEL
    if use_tariff:
        return tariff.cost_aware_level(base, when, floor=floor)
    return max(base, floor)

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
    now: time, when: datetime, ambient_lux: float | None = None, *,
    floor: int, caps: dict[str, int] | None = None,
) -> int:
    """Como ``resolve_level`` pero aplicando el tope por tarifa eléctrica.

    ``when`` es el datetime (hora local) que decide el tramo tarifario.
    El alumbrado apagado sigue apagado; encendido, se recorta en horas
    caras pero nunca por debajo de ``floor`` (mínimo de seguridad).

    ``caps`` permite usar topes por proyecto/contrato (P1/P2/P3)."""
    base = resolve_level(now, ambient_lux)
    return tariff.cost_aware_level(base, when, floor=floor, caps=caps)


# Nivel al que se enciende si astronómicamente es de noche pero el perfil
# horario (de horas fijas) cree que es de día y devuelve 0.
NIGHT_DEFAULT_LEVEL = 100


def resolve_auto_level(
    when: datetime, latitude: float, longitude: float, *, floor: int,
    use_tariff: bool = True, caps: dict[str, int] | None = None,
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
        return tariff.cost_aware_level(base, when, floor=floor, caps=caps)
    return max(base, floor)


# ---- Modo IA: dimming adaptativo por reglas (offline) --------------------
# Suelo de seguridad por perfil de vía: nivel mínimo que NUNCA se baja de
# noche (visibilidad y seguridad vial).
STREET_FLOOR: dict[str, int] = {"arterial": 60, "residential": 20, "crossing": 50}
# Nivel base nocturno por perfil (punto de partida en horario de tarde-noche).
STREET_NIGHT_BASE: dict[str, int] = {"arterial": 100, "residential": 70, "crossing": 90}
# Ventana de "noche profunda" (hora civil local): tráfico/peatones mínimos.
DEEP_NIGHT_START = time(0, 0)
DEEP_NIGHT_END = time(5, 30)


def _street_params(street_profile: str) -> tuple[int, int]:
    """Devuelve (suelo, base_nocturna) del perfil; cae a residencial si es
    desconocido."""
    floor = STREET_FLOOR.get(street_profile, STREET_FLOOR["residential"])
    night_base = STREET_NIGHT_BASE.get(street_profile, STREET_NIGHT_BASE["residential"])
    return floor, night_base


def resolve_ai_level(
    when: datetime, latitude: float, longitude: float, *,
    street_profile: str = "residential", ambient_lux: float | None = None,
    floor: int | None = None, use_tariff: bool = True,
    caps: dict[str, int] | None = None,
) -> int:
    """Dimming **adaptativo por reglas** (modo "IA"), 100 % offline y auditable.

    Combina, en este orden:
      1. **Sol** (`sun.py`): de día astronómico → 0 (apagado). El sol manda.
      2. **Perfil de vía**: base nocturna y suelo de seguridad según sea
         arteria / residencial / paso de peatones.
      3. **Noche profunda** (0:00–5:30 local): franja de menor uso → se baja
         hacia el suelo del perfil para ahorrar.
      4. **Lux ambiente** (si hay sensor): si está realmente oscuro
         (nublado/niebla) sube para mantener visibilidad.
      5. **Tarifa** (`tariff.py`): recorta en horas caras, nunca por debajo del
         suelo de seguridad.

    Interfaz estable: el día de mañana se puede sustituir el cuerpo por un
    modelo ML sin tocar a quien lo llama. ``when`` debe llevar tzinfo.
    """
    if when.tzinfo is None:
        raise ValueError("`when` debe llevar tzinfo (usa tariff.now_local())")
    profile_floor, night_base = _street_params(street_profile)
    eff_floor = max(profile_floor, floor or 0)

    # 1) El sol manda: de día, apagado.
    if not sun.is_dark(when, latitude, longitude):
        return 0

    # 2/3) Base por perfil, rebajada en noche profunda (hora civil local).
    local = when.astimezone(ZoneInfo(settings.tariff_timezone))
    if DEEP_NIGHT_START <= local.time() < DEEP_NIGHT_END:
        level = max(profile_floor, round(night_base * 0.6))
    else:
        level = night_base

    # 4) Lux: si el sensor ve oscuro de verdad, garantizamos la base nocturna.
    if ambient_lux is not None and ambient_lux < LUX_THRESHOLD_ON:
        level = max(level, night_base)

    # 5) Tarifa: recorte por coste con suelo de seguridad (topes por proyecto si vienen).
    if use_tariff:
        level = tariff.cost_aware_level(level, when, floor=eff_floor, caps=caps)

    return max(min(level, 100), eff_floor)

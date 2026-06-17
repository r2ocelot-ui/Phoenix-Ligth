"""Zona horaria de DISPLAY del despliegue (reloj y tiempos del panel).

Separada a propósito de ``tariff_timezone``: el reloj muestra la hora civil
LOCAL (Canarias va 1 h por detrás de la península), pero los tramos de la
tarifa eléctrica española se definen por ley en hora PENINSULAR. Por eso no
se comparten.

``settings.display_timezone`` puede ser:
- una zona IANA concreta ("Europe/Madrid", "Atlantic/Canary"…), o
- "auto" (por defecto): se DEDUCE de la ubicación real de los cuadros con
  ``timezonefinder`` (mapas de husos horarios, offline) → funciona en
  cualquier país (Madrid→Europe/Madrid, Las Palmas→Atlantic/Canary,
  CDMX→America/Mexico_City…). Si la librería no está, cae a una heurística
  por longitud válida para España (Canarias vs península).

Se resuelve UNA vez al arrancar (``set_display_tz`` desde el lifespan).
"""
from app.core.config import settings

_DEFAULT = "Europe/Madrid"
_CANARY = "Atlantic/Canary"
_effective_display: str | None = None


def resolve_from_longitude(longitude: float | None) -> str:
    """Fallback España (sin timezonefinder): Canarias (lon < -10°) →
    Atlantic/Canary; resto → Europe/Madrid."""
    if longitude is not None and longitude < -10:
        return _CANARY
    return _DEFAULT


def tz_from_coords(latitude: float | None, longitude: float | None) -> str:
    """Zona horaria IANA REAL para unas coordenadas, vía ``timezonefinder``
    (offline, mundial). Si la librería no está disponible, cae a la heurística
    por longitud (España)."""
    if latitude is None or longitude is None:
        return _DEFAULT
    try:
        from timezonefinder import TimezoneFinder
        tz = TimezoneFinder().timezone_at(lat=latitude, lng=longitude)
        if tz:
            return tz
    except Exception:  # noqa: BLE001 — sin timezonefinder: fallback
        pass
    return resolve_from_longitude(longitude)


def set_display_tz(value: str) -> None:
    global _effective_display
    _effective_display = value


def display_tz() -> str:
    """Zona horaria efectiva para mostrar al usuario (reloj, tiempos)."""
    if _effective_display:
        return _effective_display
    v = settings.display_timezone
    return _DEFAULT if (not v or v == "auto") else v

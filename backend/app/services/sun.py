"""Salida/puesta del sol astronómicas — cálculo offline (algoritmo NOAA).

Útil para:
- Sanity-check de la fotocélula del CM: si el sensor lux marca "noche" al
  mediodía astronómico, la fotocélula está sucia/tapada/rota.
- Fallback seguro: si el sensor lux no llega o falla, el control de
  alumbrado puede caer al ciclo astronómico y mantener la operativa.

NO sustituye al sensor lux real (no ve nubes, eclipses ni sombras). La
estrategia siempre es: fotocélula primero, astronómico como red de
seguridad.

Sin dependencias externas (stdlib pura) — funciona en redes OT aisladas.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone


def _julian_day(d: date) -> float:
    """Día juliano a las 00:00 UTC."""
    y, m = d.year, d.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d.day + b - 1524.5


def _sun_event(d: date, lat: float, lon: float, rising: bool) -> datetime | None:
    """Devuelve el evento (sunrise/sunset) en UTC para esa fecha y posición.

    Implementación de la "sunrise equation" (algoritmo simplificado de
    Jean Meeus / Wikipedia). Precisión ±1 min para latitudes operativas;
    suficiente para alumbrado, no para astronomía fina.

    Convención de longitud: ``lon`` positivo al ESTE (estándar moderno).
    Internamente se convierte a ``lw`` (oeste positivo) para encajar con
    la fórmula publicada.

    Devuelve ``None`` si en esa fecha y latitud no hay evento (sol de
    medianoche o noche polar). En la franja operativa de España no debería
    pasar nunca.
    """
    # Ángulo cenital oficial: 90°50' (refracción atmosférica + radio solar).
    zenith = math.radians(90.0 + 50.0 / 60.0)

    lw = -lon  # convención del algoritmo: oeste positivo
    jd = _julian_day(d)

    # Aproximación del día solar n (entero más cercano al mediodía solar).
    n = round(jd - 2451545.0 - 0.0009 + lw / 360.0)
    # Tiempo solar medio.
    j_star = n + 0.0009 + lw / 360.0
    # Anomalía media (grados → radianes).
    m_deg = (357.5291 + 0.98560028 * j_star) % 360.0
    m = math.radians(m_deg)
    # Ecuación del centro.
    c_deg = (1.9148 * math.sin(m) + 0.0200 * math.sin(2 * m)
             + 0.0003 * math.sin(3 * m))
    # Longitud eclíptica del sol.
    lam_deg = (m_deg + c_deg + 180.0 + 102.9372) % 360.0
    lam = math.radians(lam_deg)
    # Tránsito solar (mediodía solar local) en JD.
    j_transit = (2451545.0 + j_star
                 + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam))
    # Declinación del sol.
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))

    lat_rad = math.radians(lat)
    cos_h = ((math.cos(zenith) - math.sin(lat_rad) * math.sin(decl))
             / (math.cos(lat_rad) * math.cos(decl)))
    if cos_h > 1 or cos_h < -1:
        return None  # noche/día polares: no hay evento.
    h_deg = math.degrees(math.acos(cos_h))

    # Sunrise = transit - h, sunset = transit + h.
    j_event = j_transit + (-h_deg if rising else h_deg) / 360.0
    secs = (j_event - 2440587.5) * 86400.0
    return datetime.fromtimestamp(secs, tz=timezone.utc)


def sunrise_utc(d: date, lat: float, lon: float) -> datetime | None:
    return _sun_event(d, lat, lon, rising=True)


def sunset_utc(d: date, lat: float, lon: float) -> datetime | None:
    return _sun_event(d, lat, lon, rising=False)


def is_dark(at: datetime, lat: float, lon: float, *, margin_minutes: int = 15) -> bool:
    """¿Es de noche astronómica (con margen) en ese instante y posición?

    Útil para decidir si el alumbrado debería estar encendido en ausencia
    de lectura fiable del sensor lux. El ``margin_minutes`` añade un
    colchón de seguridad: enciende antes del ocaso y apaga después del
    alba, para que no haya ventanas de "oscuro y sin luz".
    """
    if at.tzinfo is None:
        raise ValueError("`at` debe llevar tzinfo")
    at_utc = at.astimezone(timezone.utc)
    d = at_utc.date()
    sr = sunrise_utc(d, lat, lon)
    ss = sunset_utc(d, lat, lon)
    if sr is None or ss is None:
        return True  # noche polar / sin sol: asumimos oscuro (failsafe)
    margin = timedelta(minutes=margin_minutes)
    # Antes del alba + margen, o después del ocaso − margen.
    return at_utc < (sr + margin) or at_utc > (ss - margin)

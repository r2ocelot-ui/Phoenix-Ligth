"""Precio de la luz en TIEMPO REAL (opcional, offline-graceful).

Proveedor de precio **enchufable**. Por defecto está OFF: mandan los tramos
fijos de ``tariff.py`` (100 % offline). Si ``settings.price_source`` activa un
proveedor, se consulta una API externa para el precio horario real:

- ``"ree"`` → API pública de Red Eléctrica de España (PVPC, sin clave).

Diseño deliberadamente genérico (no se ata el núcleo a un país): añadir otro
mercado europeo es escribir otro ``_fetch_*``. **Cualquier fallo** (sin
internet, formato distinto, timeout, API caída) devuelve ``None`` y el sistema
cae limpio a los tramos fijos. Lo offline siempre gana.

La curva del día se cachea en memoria para no machacar la API.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from app.core.config import settings
from app.services import tariff

log = logging.getLogger("phoenix.price")

# Cache en memoria: {fecha_iso: {"fetched": datetime, "values": [(dt_tz, eur_mwh)]}}
_cache: dict[str, dict] = {}


def enabled() -> bool:
    """¿Hay un proveedor de precio real activo?"""
    return (settings.price_source or "off").strip().lower() != "off"


def _fetch_ree(day) -> list[tuple[datetime, float]] | None:
    """Descarga la curva horaria del día de la API pública de REE. Devuelve
    lista de ``(datetime_con_tz, €/MWh)`` o ``None`` si algo falla.

    Parser TOLERANTE a propósito: si la forma del JSON cambia un poco, no
    revienta — devuelve lo que pueda o ``None`` (y se usa el fallback)."""
    params = {
        "start_date": day.strftime("%Y-%m-%dT00:00"),
        "end_date": day.strftime("%Y-%m-%dT23:59"),
        "time_trunc": "hour",
    }
    try:
        r = httpx.get(settings.price_api_url, params=params,
                      timeout=settings.price_timeout_s,
                      headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Precio en tiempo real no disponible (%s): %s",
                    settings.price_source, exc)
        return None
    return _parse_ree(data)


def _parse_ree(data: dict) -> list[tuple[datetime, float]] | None:
    """Extrae [(datetime, €/MWh)] del JSON de apidatos.ree.es. Prefiere la
    serie PVPC; si no, la primera con valores."""
    included = (data or {}).get("included") or []
    series = None
    for it in included:
        title = ((it or {}).get("attributes", {}) or {}).get("title", "") or ""
        if "pvpc" in title.lower():
            series = it
            break
    if series is None and included:
        series = included[0]
    if not series:
        return None
    values = (series.get("attributes", {}) or {}).get("values") or []
    out: list[tuple[datetime, float]] = []
    for v in values:
        try:
            out.append((datetime.fromisoformat(v["datetime"]), float(v["value"])))
        except Exception:  # noqa: BLE001
            continue  # un punto malformado no tira toda la curva
    return out or None


def _day_curve(day) -> list[tuple[datetime, float]] | None:
    """Curva horaria del día, con caché. None si el proveedor no da datos."""
    key = day.isoformat()
    now = datetime.now()
    ent = _cache.get(key)
    if ent and (now - ent["fetched"]) < timedelta(minutes=settings.price_cache_minutes):
        return ent["values"]
    source = (settings.price_source or "off").strip().lower()
    values = _fetch_ree(day) if source == "ree" else None
    if values is not None:
        _cache[key] = {"fetched": now, "values": values}
    return values


def current_price(when: datetime | None = None) -> dict | None:
    """Precio de la luz para ``when`` (o ahora). Devuelve un dict con
    ``price_eur_kwh`` / ``eur_mwh`` / ``at`` / ``source``, o ``None`` si el
    proveedor está apagado o no hay dato (→ el llamador usa los tramos fijos)."""
    if not enabled():
        return None
    when = when or tariff.now_local()
    local = tariff._to_local(when)
    curve = _day_curve(local.date())
    if not curve:
        return None
    eur_mwh = None
    for dt, val in curve:
        if dt.hour == local.hour and dt.date() == local.date():
            eur_mwh = val
            break
    if eur_mwh is None:
        return None
    return {
        "source": settings.price_source,
        "at": local.isoformat(),
        "eur_mwh": round(eur_mwh, 2),
        "price_eur_kwh": round(eur_mwh / 1000.0, 5),  # REE da €/MWh
    }

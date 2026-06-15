"""Proveedor de precio en tiempo real (offline-graceful).

No tocamos la red: mockeamos httpx. Verificamos: off→None, parseo del JSON de
REE, selección de la hora correcta, y fallback limpio ante errores."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services import price
from app.services import tariff

MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    price._cache.clear()
    monkeypatch.setattr(tariff.settings, "tariff_timezone", "Europe/Madrid")
    yield
    price._cache.clear()


def _ree_json(day="2026-06-15"):
    # Forma simplificada del JSON de apidatos.ree.es (€/MWh por hora).
    return {"included": [{
        "type": "PVPC", "attributes": {"title": "PVPC (€/MWh)", "values": [
            {"value": 80.0, "datetime": f"{day}T00:00:00.000+02:00"},
            {"value": 200.0, "datetime": f"{day}T20:00:00.000+02:00"},
        ]}}]}


def test_off_returns_none(monkeypatch):
    monkeypatch.setattr(price.settings, "price_source", "off")
    assert price.enabled() is False
    assert price.current_price(datetime(2026, 6, 15, 20, tzinfo=MADRID)) is None


def test_ree_parses_and_picks_hour(monkeypatch):
    monkeypatch.setattr(price.settings, "price_source", "ree")
    monkeypatch.setattr(price, "_fetch_ree", lambda day: price._parse_ree(_ree_json()))
    p = price.current_price(datetime(2026, 6, 15, 20, tzinfo=MADRID))
    assert p is not None
    assert p["eur_mwh"] == 200.0
    assert p["price_eur_kwh"] == 0.2  # 200 €/MWh = 0.20 €/kWh
    # Otra hora (valle).
    p0 = price.current_price(datetime(2026, 6, 15, 0, 30, tzinfo=MADRID))
    assert p0["price_eur_kwh"] == 0.08


def test_parse_tolerates_garbage():
    # Un punto malformado no tira la curva; sin serie válida → None.
    data = {"included": [{"attributes": {"title": "PVPC", "values": [
        {"value": "x", "datetime": "mal"}, {"value": 50.0, "datetime": "2026-06-15T01:00:00+02:00"},
    ]}}]}
    curve = price._parse_ree(data)
    assert curve and len(curve) == 1 and curve[0][1] == 50.0
    assert price._parse_ree({"included": []}) is None


def test_fetch_error_falls_back_to_none(monkeypatch):
    monkeypatch.setattr(price.settings, "price_source", "ree")
    def boom(*a, **k):
        raise RuntimeError("sin internet")
    monkeypatch.setattr(price.httpx, "get", boom)
    # _fetch_ree captura la excepción → None → current_price None (usa tramos).
    assert price.current_price(datetime(2026, 6, 15, 20, tzinfo=MADRID)) is None

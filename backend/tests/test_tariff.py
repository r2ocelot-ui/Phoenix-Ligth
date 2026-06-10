"""Tarifa por tramos + dimming consciente de coste (funciones puras)."""
from datetime import datetime, time

from app.services import dimming_controller as dc
from app.services import tariff

# 2026-06-08 es lunes; 2026-06-13 es sábado (hoy del proyecto: 2026-06-10, X).
MONDAY = datetime(2026, 6, 8)
SATURDAY = datetime(2026, 6, 13)


def test_workday_periods():
    assert tariff.current_period(MONDAY.replace(hour=3)) == "P3"   # valle
    assert tariff.current_period(MONDAY.replace(hour=9)) == "P2"   # llano
    assert tariff.current_period(MONDAY.replace(hour=12)) == "P1"  # punta mañana
    assert tariff.current_period(MONDAY.replace(hour=20)) == "P1"  # punta tarde
    assert tariff.current_period(MONDAY.replace(hour=23)) == "P2"  # llano noche


def test_weekend_is_all_valle():
    for h in (3, 12, 20):
        assert tariff.current_period(SATURDAY.replace(hour=h)) == "P3"


def test_cost_aware_caps_in_punta_but_respects_floor():
    punta = MONDAY.replace(hour=12)
    assert tariff.cost_aware_level(100, punta, floor=40) == 75   # recortado al tope
    assert tariff.cost_aware_level(60, punta, floor=40) == 60    # por debajo del tope, intacto
    assert tariff.cost_aware_level(20, punta, floor=40) == 40    # nunca bajo el floor de seguridad
    assert tariff.cost_aware_level(0, punta, floor=40) == 0      # apagado sigue apagado


def test_valle_has_no_cap():
    valle = MONDAY.replace(hour=3)
    assert tariff.cost_aware_level(100, valle, floor=40) == 100


def test_dimming_wrapper_applies_tariff():
    # 20:00 el perfil base da 100 (18-22h), tarifa punta lo recorta a 75.
    lvl = dc.resolve_level_cost_aware(time(20, 0), MONDAY.replace(hour=20), None, floor=40)
    assert lvl == 75
    # 03:00 el perfil base da 30 (0-6h) y en valle no se toca → 40 (floor) ?
    # No: 30 < floor 40 → sube al floor de seguridad.
    lvl_night = dc.resolve_level_cost_aware(time(3, 0), MONDAY.replace(hour=3), None, floor=40)
    assert lvl_night == 40

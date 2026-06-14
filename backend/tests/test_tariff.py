"""Tarifa por tramos + dimming consciente de coste (funciones puras)."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from app.services import dimming_controller as dc
from app.services import tariff

MADRID = ZoneInfo("Europe/Madrid")
MADRID_LAT, MADRID_LON = 40.4168, -3.7038

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


def test_utc_datetime_converted_to_local(monkeypatch):
    """El bug V1.R1.P1: un datetime en UTC debe dar el tramo de la hora
    LOCAL, no la del servidor. 21:25 UTC en verano = 23:25 en Madrid →
    Llano (P2). Sin la conversión saldría Punta (P1, hora 21)."""
    monkeypatch.setattr(tariff.settings, "tariff_timezone", "Europe/Madrid")
    utc_2125 = datetime(2026, 6, 8, 21, 25, tzinfo=timezone.utc)  # lunes
    assert tariff.current_period(utc_2125) == "P2"
    # Comprobación de control: la misma hora interpretada como naive/local
    # (hora 21) sí cae en Punta — demuestra que la conversión cambia el tramo.
    assert tariff.current_period(datetime(2026, 6, 8, 21, 25)) == "P1"


def test_dimming_wrapper_applies_tariff():
    # 20:00 el perfil base da 100 (18-22h), tarifa punta lo recorta a 75.
    lvl = dc.resolve_level_cost_aware(time(20, 0), MONDAY.replace(hour=20), None, floor=40)
    assert lvl == 75
    # 03:00 el perfil base da 30 (0-6h) y en valle no se toca → 40 (floor) ?
    # No: 30 < floor 40 → sube al floor de seguridad.
    lvl_night = dc.resolve_level_cost_aware(time(3, 0), MONDAY.replace(hour=3), None, floor=40)
    assert lvl_night == 40


# --- #2 · Encendido automático astronómico (sin fotocélula) ---------------
def test_auto_level_off_during_day():
    noon = datetime(2026, 6, 21, 13, 0, tzinfo=MADRID)  # mediodía de verano
    assert dc.resolve_auto_level(noon, MADRID_LAT, MADRID_LON, floor=40) == 0


def test_auto_level_on_at_night():
    night = datetime(2026, 1, 15, 22, 0, tzinfo=MADRID)  # noche de invierno
    assert dc.resolve_auto_level(night, MADRID_LAT, MADRID_LON, floor=40) > 0


def test_auto_level_night_fallback_when_profile_zero():
    # 07:35 a mediados de enero en Madrid: antes del alba (~08:35) → es de
    # noche, pero el perfil horario (7:30-18:00) marca 0. Debe encender al
    # nivel nocturno por defecto (valle → sin tope de tarifa).
    pre_dawn = datetime(2026, 1, 15, 7, 35, tzinfo=MADRID)
    assert dc.resolve_auto_level(pre_dawn, MADRID_LAT, MADRID_LON, floor=40) == dc.NIGHT_DEFAULT_LEVEL


def test_auto_level_requires_tzaware():
    import pytest
    with pytest.raises(ValueError):
        dc.resolve_auto_level(datetime(2026, 1, 15, 22, 0), MADRID_LAT, MADRID_LON, floor=40)


def test_level_cap_is_configurable(monkeypatch):
    """Los topes por periodo se pueden ajustar al contrato real vía settings."""
    monkeypatch.setattr(tariff.settings, "tariff_cap_punta", 60)
    punta = datetime(2026, 6, 8, 12, tzinfo=MADRID)  # lunes mediodía → P1
    assert tariff.level_cap("P1") == 60
    # base 100 en punta ahora se recorta a 60 (no a 75).
    assert tariff.cost_aware_level(100, punta, floor=40) == 60


# --- Modo IA · dimming adaptativo por reglas (offline) --------------------
def test_ai_off_during_day():
    """El sol manda: de día astronómico, apagado en cualquier perfil."""
    noon = datetime(2026, 6, 21, 13, 0, tzinfo=MADRID)
    for profile in ("arterial", "residential", "crossing"):
        assert dc.resolve_ai_level(noon, MADRID_LAT, MADRID_LON,
                                   street_profile=profile) == 0


def test_ai_requires_tzaware():
    import pytest
    with pytest.raises(ValueError):
        dc.resolve_ai_level(datetime(2026, 1, 15, 22, 0), MADRID_LAT, MADRID_LON)


def test_ai_evening_uses_profile_base():
    """A primera hora de la noche (no profunda) sale la base del perfil, con
    el tope de tarifa del tramo. 20:00 invierno = noche, punta (P1, tope 75)."""
    evening = datetime(2026, 1, 15, 20, 0, tzinfo=MADRID)
    # arterial base 100 → recortado a 75 por punta.
    assert dc.resolve_ai_level(evening, MADRID_LAT, MADRID_LON,
                               street_profile="arterial") == 75
    # residential base 70 → por debajo del tope, intacto.
    assert dc.resolve_ai_level(evening, MADRID_LAT, MADRID_LON,
                               street_profile="residential") == 70


def test_ai_deep_night_lowers_residential():
    """En noche profunda (03:00, valle sin tope) la residencial baja respecto a
    su base nocturna (70 → 42), pero por encima de su suelo (20)."""
    deep = datetime(2026, 1, 15, 3, 0, tzinfo=MADRID)
    lvl = dc.resolve_ai_level(deep, MADRID_LAT, MADRID_LON, street_profile="residential")
    assert lvl == 42  # round(70 * 0.6)
    assert lvl >= dc.STREET_FLOOR["residential"]


def test_ai_crossing_never_below_safety_floor():
    """Un paso de peatones nunca baja de su suelo de seguridad (50), ni en
    noche profunda ni con tarifa cara."""
    deep = datetime(2026, 1, 15, 3, 0, tzinfo=MADRID)
    lvl = dc.resolve_ai_level(deep, MADRID_LAT, MADRID_LON, street_profile="crossing")
    assert lvl >= dc.STREET_FLOOR["crossing"] == 50


def test_cost_aware_uses_project_caps():
    """Topes por proyecto: una ciudad con un contrato más agresivo recorta a 60
    en punta sin afectar a otra que usa los globales (75)."""
    punta = MONDAY.replace(hour=12)
    caps = {"P1": 60, "P2": 90, "P3": 100}
    assert tariff.cost_aware_level(100, punta, floor=40, caps=caps) == 60
    # Sin caps, sigue al global (75 por defecto).
    assert tariff.cost_aware_level(100, punta, floor=40) == 75


def test_cost_aware_caps_partial():
    """Solo se sustituye el tramo que viene en caps; los demás caen al global."""
    valle = MONDAY.replace(hour=3)  # P3
    caps_p1 = {"P1": 50}  # solo cambia punta
    assert tariff.cost_aware_level(100, valle, floor=40, caps=caps_p1) == 100


def test_ai_respects_project_caps():
    """Modo IA con topes propios del proyecto: arteria a 100 en punta cae a 60
    (en vez de a 75 con los globales)."""
    evening = datetime(2026, 1, 15, 20, 0, tzinfo=MADRID)
    caps = {"P1": 60, "P2": 90, "P3": 100}
    assert dc.resolve_ai_level(evening, MADRID_LAT, MADRID_LON,
                               street_profile="arterial", caps=caps) == 60


def test_ai_low_lux_boosts_to_night_base():
    """Si el sensor ve oscuro de verdad (nublado) en noche profunda, sube a la
    base nocturna del perfil para mantener visibilidad."""
    deep = datetime(2026, 1, 15, 3, 0, tzinfo=MADRID)
    dark = dc.resolve_ai_level(deep, MADRID_LAT, MADRID_LON,
                               street_profile="residential", ambient_lux=5.0)
    assert dark == dc.STREET_NIGHT_BASE["residential"]  # 70, no el 42 de noche profunda

from datetime import time

from app.services import dimming_controller as dc


def test_daytime_is_off():
    assert dc.resolve_level(time(12, 0)) == 0


def test_evening_is_full():
    assert dc.resolve_level(time(20, 0)) == 100


def test_bright_ambient_forces_off():
    assert dc.resolve_level(time(20, 0), ambient_lux=200.0) == 0


def test_dark_ambient_raises_night_floor():
    # Night profile is 30%, but a dark ambient reading bumps the floor to 50%.
    assert dc.resolve_level(time(2, 0), ambient_lux=5.0) == 50

from app.schemas.alarm import AlarmType
from app.schemas.measurement import Measurement
from app.services import alarm_engine


def _m(**overrides) -> Measurement:
    base = dict(
        cabinet_id="CAB-001",
        voltage_v=230.0,
        current_a=2.8,
        active_power_w=600.0,
        power_factor=0.95,
        lamp_circuit="L1",
    )
    base.update(overrides)
    # timestamp intentionally omitted: verifies the server-side default factory.
    return Measurement(**base)


def _types(alarms) -> set[AlarmType]:
    return {a.type for a in alarms}


def test_normal_operation_raises_no_alarm():
    assert alarm_engine.evaluate(_m()) == []


def test_lamp_out_when_energised_with_zero_current():
    alarms = alarm_engine.evaluate(_m(current_a=0.0, active_power_w=0.0, power_factor=0.0))
    assert AlarmType.LAMP_OUT in _types(alarms)


def test_no_lamp_out_when_commanded_off():
    # Zero current is expected when the circuit is commanded off (dim 0 / relay off).
    alarms = alarm_engine.evaluate(
        _m(current_a=0.0, active_power_w=0.0, power_factor=0.0), expected_on=False
    )
    assert AlarmType.LAMP_OUT not in _types(alarms)


def test_overvoltage():
    assert AlarmType.OVERVOLTAGE in _types(alarm_engine.evaluate(_m(voltage_v=255.0)))


def test_undervoltage():
    assert AlarmType.UNDERVOLTAGE in _types(alarm_engine.evaluate(_m(voltage_v=200.0)))


def test_line_failure_on_voltage_collapse():
    alarms = alarm_engine.evaluate(
        _m(voltage_v=0.0, current_a=0.0, active_power_w=0.0, power_factor=0.0)
    )
    assert AlarmType.LINE_FAILURE in _types(alarms)


def test_ambient_lux_is_accepted_and_optional():
    assert _m(ambient_lux=15.2).ambient_lux == 15.2
    assert _m().ambient_lux is None

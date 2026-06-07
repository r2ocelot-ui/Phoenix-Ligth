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


# --- Matriz §6.6: desviación de consumo ------------------------------------
# expected_power_w = 1000 → nominal del cuadro.
def test_circuit_load_drop_when_consumption_below_half():
    # Carga al 35 %: 350 W de 1000 esperados.
    alarms = alarm_engine.evaluate(
        _m(active_power_w=350.0, current_a=1.6), expected_power_w=1000.0,
    )
    assert AlarmType.CIRCUIT_LOAD_DROP in _types(alarms)
    assert AlarmType.CIRCUIT_OVERLOAD not in _types(alarms)


def test_circuit_overload_when_consumption_above_threshold():
    # 155 % del nominal.
    alarms = alarm_engine.evaluate(
        _m(active_power_w=1550.0, current_a=7.0), expected_power_w=1000.0,
    )
    assert AlarmType.CIRCUIT_OVERLOAD in _types(alarms)


def test_load_drop_silent_when_no_nominal_configured():
    # Sin nominal (0 W) no se evalúa: evita falsos positivos en circuitos
    # legacy todavía sin configurar.
    alarms = alarm_engine.evaluate(_m(active_power_w=50.0), expected_power_w=0.0)
    assert AlarmType.CIRCUIT_LOAD_DROP not in _types(alarms)
    assert AlarmType.CIRCUIT_OVERLOAD not in _types(alarms)


def test_load_drop_silent_when_off():
    # Si está ordenado apagado, una caída de carga no aplica.
    alarms = alarm_engine.evaluate(
        _m(active_power_w=80.0, current_a=0.5),
        expected_on=False, expected_power_w=1000.0,
    )
    assert AlarmType.CIRCUIT_LOAD_DROP not in _types(alarms)


def test_contactor_stuck_when_off_but_consuming():
    # Cuadro ordenado OFF pero el analizador sigue midiendo consumo: el
    # contactor no abrió. Crítica máxima.
    alarms = alarm_engine.evaluate(
        _m(active_power_w=400.0, current_a=1.8),
        expected_on=False, expected_power_w=1000.0,
    )
    assert AlarmType.CONTACTOR_STUCK in _types(alarms)


def test_contactor_stuck_ignores_residual_noise():
    # Pequeño consumo residual cuando está OFF (cargas auxiliares de
    # iluminación interior del cuadro, etc.) no debe disparar STUCK.
    alarms = alarm_engine.evaluate(
        _m(active_power_w=5.0, current_a=0.05),
        expected_on=False, expected_power_w=1000.0,
    )
    assert AlarmType.CONTACTOR_STUCK not in _types(alarms)


def test_door_open_temp_intrusion_pass_through():
    # Sanity: las alarmas físicas siguen disparándose.
    m = _m(door_open=True, cabinet_temp_c=65.0, intrusion=True)
    types = _types(alarm_engine.evaluate(m))
    assert AlarmType.DOOR_OPEN in types
    assert AlarmType.CABINET_OVERTEMP in types
    assert AlarmType.INTRUSION in types

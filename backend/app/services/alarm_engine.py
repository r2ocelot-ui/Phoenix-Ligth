"""Rule-based alarm engine.

Evaluates each incoming Measurement against thresholds and emits Alarm objects.
Stateless by design — callers persist or publish the resulting alarms.

Metering is assumed to be upstream of the contactor (cabinet head), so line
voltage is present even when the lamps are commanded off. `expected_on` tells
the engine whether the circuit is *supposed* to be drawing current right now
(relay on AND dim level > 0); when it is not, zero current is normal and must
not raise a LAMP_OUT alarm.
"""
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.alarm import Alarm, AlarmSeverity, AlarmType
from app.schemas.measurement import Measurement


def evaluate(measurement: Measurement, expected_on: bool = True) -> list[Alarm]:
    alarms: list[Alarm] = []
    now = datetime.now(timezone.utc)

    if (
        expected_on
        and measurement.voltage_v > 50
        and measurement.current_a < settings.alarm_zero_current_threshold_a
    ):
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.LAMP_OUT,
                severity=AlarmSeverity.CRITICAL,
                message=(
                    f"Zero current with line energised on {measurement.lamp_circuit}: "
                    f"likely blown lamp or driver failure."
                ),
                timestamp=now,
                value=measurement.current_a,
            )
        )

    if measurement.voltage_v < 50:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.LINE_FAILURE,
                severity=AlarmSeverity.CRITICAL,
                message=f"Line voltage collapsed on {measurement.lamp_circuit}.",
                timestamp=now,
                value=measurement.voltage_v,
            )
        )

    if measurement.voltage_v > settings.alarm_overvoltage_threshold_v:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.OVERVOLTAGE,
                severity=AlarmSeverity.WARNING,
                message=f"Overvoltage detected ({measurement.voltage_v:.1f} V).",
                timestamp=now,
                value=measurement.voltage_v,
            )
        )

    if 50 < measurement.voltage_v < settings.alarm_undervoltage_threshold_v:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.UNDERVOLTAGE,
                severity=AlarmSeverity.WARNING,
                message=f"Undervoltage detected ({measurement.voltage_v:.1f} V).",
                timestamp=now,
                value=measurement.voltage_v,
            )
        )

    if measurement.current_a > settings.alarm_overcurrent_threshold_a:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.OVERCURRENT,
                severity=AlarmSeverity.CRITICAL,
                message=f"Overcurrent: {measurement.current_a:.2f} A.",
                timestamp=now, value=measurement.current_a,
            )
        )

    # --- Infraestructura del cuadro ----------------------------------------
    if measurement.cabinet_temp_c is not None and (
        measurement.cabinet_temp_c > settings.alarm_cabinet_temp_c
    ):
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.CABINET_OVERTEMP,
                severity=AlarmSeverity.WARNING,
                message=f"Temperatura interior elevada ({measurement.cabinet_temp_c:.1f} °C).",
                timestamp=now, value=measurement.cabinet_temp_c,
            )
        )
    if measurement.door_open is True:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.DOOR_OPEN,
                severity=AlarmSeverity.WARNING,
                message="Puerta del cuadro abierta.",
                timestamp=now,
            )
        )
    if measurement.intrusion is True:
        alarms.append(
            Alarm(
                cabinet_id=measurement.cabinet_id,
                type=AlarmType.INTRUSION,
                severity=AlarmSeverity.CRITICAL,
                message="¡Intento de intrusión detectado!",
                timestamp=now,
            )
        )

    return alarms

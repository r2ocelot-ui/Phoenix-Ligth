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


def evaluate(
    measurement: Measurement,
    expected_on: bool = True,
    expected_power_w: float = 0.0,
) -> list[Alarm]:
    """Run the rule-based alarm engine against a single telemetry sample.

    ``expected_on`` mirrors the commanded relay state (True when the cabinet
    is supposed to be drawing current). ``expected_power_w`` is the nominal
    total of all the circuits in the cabinet — passed by the bus so this
    function stays free of database access. When 0 the consumption-deviation
    checks are skipped, so circuits without a configured nominal stay quiet.
    """
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

    # --- Desviación de consumo (matriz §6.6) -------------------------------
    # Solo se evalúa cuando hay un nominal configurado y la línea está
    # energizada (sin tensión todo es 0 W, y eso ya lo cubre LINE_FAILURE).
    if expected_power_w > 0 and measurement.voltage_v > 50:
        if expected_on:
            # El cuadro está ordenado encendido: comparamos consumo real vs
            # nominal. Sólo si ya hay algo de consumo (>0): LAMP_OUT cubre
            # el caso "todo a cero".
            if measurement.active_power_w > 0:
                ratio = measurement.active_power_w / expected_power_w
                if ratio < settings.alarm_load_drop_ratio:
                    pct = (1 - ratio) * 100
                    alarms.append(
                        Alarm(
                            cabinet_id=measurement.cabinet_id,
                            type=AlarmType.CIRCUIT_LOAD_DROP,
                            severity=AlarmSeverity.WARNING,
                            message=(
                                f"Carga caída: {measurement.active_power_w:.0f} W "
                                f"sobre un nominal de {expected_power_w:.0f} W "
                                f"(~{pct:.0f}% por debajo). Posibles luminarias fundidas."
                            ),
                            timestamp=now,
                            value=measurement.active_power_w,
                        )
                    )
                elif ratio > settings.alarm_overload_ratio:
                    pct = (ratio - 1) * 100
                    alarms.append(
                        Alarm(
                            cabinet_id=measurement.cabinet_id,
                            type=AlarmType.CIRCUIT_OVERLOAD,
                            severity=AlarmSeverity.CRITICAL,
                            message=(
                                f"Sobrecarga: {measurement.active_power_w:.0f} W "
                                f"sobre un nominal de {expected_power_w:.0f} W "
                                f"(~{pct:.0f}% por encima). Posible fuga, derivación o cortocircuito parcial."
                            ),
                            timestamp=now,
                            value=measurement.active_power_w,
                        )
                    )
        else:
            # El cuadro está ordenado apagado, pero se mide consumo: el
            # contactor no abrió (contactos soldados, bobina pegada, ...).
            if measurement.active_power_w > settings.alarm_contactor_stuck_min_w:
                alarms.append(
                    Alarm(
                        cabinet_id=measurement.cabinet_id,
                        type=AlarmType.CONTACTOR_STUCK,
                        severity=AlarmSeverity.CRITICAL,
                        message=(
                            f"Contactor pegado: ordenado OFF pero sigue consumiendo "
                            f"{measurement.active_power_w:.0f} W. Riesgo de no poder "
                            f"apagar el circuito de forma remota."
                        ),
                        timestamp=now,
                        value=measurement.active_power_w,
                    )
                )

    return alarms

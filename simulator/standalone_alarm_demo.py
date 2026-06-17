"""Standalone alarm demo — no broker required.

Demonstrates the core requirement of the brief: when current drops to 0 while
the line is energised, the system emits a `LAMP_OUT` alert. This script wires
the simulator straight into the alarm engine so it runs with zero infra.

Run with: `python simulator/standalone_alarm_demo.py`
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.schemas.measurement import Measurement  # noqa: E402
from app.services import alarm_engine  # noqa: E402


def main() -> None:
    samples = [
        {"voltage_v": 230.1, "current_a": 2.85, "active_power_w": 622.5, "power_factor": 0.95},
        {"voltage_v": 229.7, "current_a": 2.83, "active_power_w": 617.2, "power_factor": 0.95},
        {"voltage_v": 230.4, "current_a": 0.00, "active_power_w": 0.0,   "power_factor": 0.00},
        {"voltage_v": 255.0, "current_a": 2.85, "active_power_w": 689.0, "power_factor": 0.95},
    ]

    for i, s in enumerate(samples, 1):
        m = Measurement(
            cabinet_id="CAB-001",
            timestamp=datetime.now(timezone.utc),
            lamp_circuit="L1",
            **s,
        )
        alarms = alarm_engine.evaluate(m)
        print(f"\n--- Sample {i}: V={m.voltage_v}V I={m.current_a}A ---")
        if not alarms:
            print("  OK — no alarm")
        for a in alarms:
            print(f"  [{a.severity.value}] {a.type.value}: {a.message}")


if __name__ == "__main__":
    main()

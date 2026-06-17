"""Cabinet telemetry simulator.

Publishes synthetic measurements to the MQTT broker so the backend pipeline can
be exercised end-to-end. After N normal samples it simulates a blown lamp by
dropping the current to zero while keeping the line energised — this triggers
the LAMP_OUT alarm in the alarm engine.

Usage:
    python simulator/cabinet_simulator.py --cabinet-id CAB-001 --fail-after 5
"""
import argparse
import asyncio
import json
import random
from datetime import datetime, timezone

import aiomqtt


async def run(cabinet_id: str, host: str, port: int, fail_after: int, interval: float) -> None:
    async with aiomqtt.Client(hostname=host, port=port) as client:
        topic = f"phoenix/cabinets/{cabinet_id}/telemetry"
        print(f"[sim] Publishing to {topic}")

        for i in range(fail_after + 5):
            blown = i >= fail_after
            voltage = round(random.uniform(228.0, 232.0), 2)
            current = 0.0 if blown else round(random.uniform(2.5, 3.2), 3)
            power = round(voltage * current * 0.95, 2)

            payload = {
                "cabinet_id": cabinet_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "voltage_v": voltage,
                "current_a": current,
                "active_power_w": power,
                "power_factor": 0.95 if not blown else 0.0,
                "lamp_circuit": "L1",
            }

            await client.publish(topic, json.dumps(payload), qos=1)
            tag = "FAULT" if blown else "OK"
            print(f"[sim {tag}] V={voltage}V  I={current}A  P={power}W")
            await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cabinet-id", default="CAB-001")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--fail-after", type=int, default=5, help="Samples before simulating blown lamp")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    asyncio.run(run(args.cabinet_id, args.host, args.port, args.fail_after, args.interval))


if __name__ == "__main__":
    main()

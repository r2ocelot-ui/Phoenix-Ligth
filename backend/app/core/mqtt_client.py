"""Async MQTT client wrapper.

Responsibilities:
- Subscribe to telemetry topics and feed the alarm engine (via `ingest`).
- Subscribe to the status topic (LWT) and raise/clear COMMUNICATION_LOSS.
- Track the *commanded* state of each cabinet (relay + dim) so the alarm engine
  can tell an intentional "off" apart from a blown lamp.
- Keep the latest telemetry per cabinet and expose a `snapshot()` for the API/UI.
- Maintain stateful alarms (raised once, cleared when resolved).
- Run a dimming scheduler and (optionally) a demo telemetry generator.
- Expose publish() for the REST control API.
"""
import asyncio
import json
import logging
import random
from datetime import datetime, timezone

import aiomqtt

from app.core.config import settings
from app.schemas.alarm import Alarm, AlarmSeverity, AlarmType
from app.schemas.measurement import Measurement
from app.services import alarm_engine, dimming_controller

log = logging.getLogger("phoenix.mqtt")

_DEMO_CABINETS = ["CAB-001", "CAB-002", "CAB-003", "CAB-004"]


class MQTTBus:
    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._tasks: list[asyncio.Task] = []
        # cabinet_id -> {alarm_type: alarm_payload}
        self.active_alarms: dict[str, dict[str, dict]] = {}
        # cabinet_id -> {"relay": "on"|"off", "dim": 0-100}
        self.cabinet_state: dict[str, dict] = {}
        # cabinet_id -> last telemetry dict / last ambient lux
        self.last_telemetry: dict[str, dict] = {}
        self.last_lux: dict[str, float] = {}
        self._known_cabinets: set[str] = set()

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._run()),
            asyncio.create_task(self._dimming_loop()),
        ]
        if settings.demo_mode:
            self._tasks.append(asyncio.create_task(self._demo_loop()))
            log.info("Demo mode ON — injecting synthetic telemetry")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()

    async def publish(self, topic: str, payload: dict) -> None:
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        await self._client.publish(topic, json.dumps(payload), qos=1)

    def record_command(
        self, cabinet_id: str, *, relay: str | None = None, dim: int | None = None
    ) -> None:
        state = self.cabinet_state.setdefault(cabinet_id, {"relay": "on", "dim": 100})
        if relay is not None:
            state["relay"] = relay
        if dim is not None:
            state["dim"] = dim

    def _is_expected_on(self, cabinet_id: str) -> bool:
        state = self.cabinet_state.get(cabinet_id)
        if state is None:
            return True
        return state.get("relay", "on") == "on" and state.get("dim", 100) > 0

    # ----- Snapshot for the API / web panel ---------------------------------
    def snapshot(self) -> list[dict]:
        out = []
        for cid in sorted(self._known_cabinets):
            alarms = list(self.active_alarms.get(cid, {}).values())
            online = AlarmType.COMMUNICATION_LOSS.value not in self.active_alarms.get(cid, {})
            severities = [a.get("severity") for a in alarms]
            if "CRITICAL" in severities:
                status = "critical"
            elif "WARNING" in severities:
                status = "warning"
            else:
                status = "ok"
            out.append(
                {
                    "cabinet_id": cid,
                    "online": online,
                    "status": status,
                    "telemetry": self.last_telemetry.get(cid),
                    "state": self.cabinet_state.get(cid, {"relay": "on", "dim": 100}),
                    "alarms": alarms,
                }
            )
        return out

    # ----- Core ingest (shared by MQTT and demo) ----------------------------
    async def ingest(self, measurement: Measurement) -> None:
        cid = measurement.cabinet_id
        self._known_cabinets.add(cid)
        self.last_telemetry[cid] = measurement.model_dump(mode="json")
        if measurement.ambient_lux is not None:
            self.last_lux[cid] = measurement.ambient_lux

        expected_on = self._is_expected_on(cid)
        current = alarm_engine.evaluate(measurement, expected_on=expected_on)
        await self._reconcile_alarms(cid, current)

    # ----- MQTT loop --------------------------------------------------------
    async def _run(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_host,
                    port=settings.mqtt_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                ) as client:
                    self._client = client
                    await client.subscribe(settings.mqtt_topic_telemetry, qos=1)
                    await client.subscribe(settings.mqtt_topic_status, qos=1)
                    log.info(
                        "Subscribed to %s and %s",
                        settings.mqtt_topic_telemetry,
                        settings.mqtt_topic_status,
                    )
                    async for message in client.messages:
                        await self._dispatch(message)
            except aiomqtt.MqttError as exc:
                log.warning("MQTT disconnected: %s — retrying in 5s", exc)
                self._client = None
                await asyncio.sleep(5)

    async def _dispatch(self, message: aiomqtt.Message) -> None:
        topic = str(message.topic)
        if topic.endswith("/telemetry"):
            await self._handle_telemetry(message)
        elif topic.endswith("/status"):
            await self._handle_status(message)

    async def _handle_telemetry(self, message: aiomqtt.Message) -> None:
        try:
            payload = json.loads(message.payload)
            measurement = Measurement(**payload)
        except Exception as exc:  # noqa: BLE001
            log.error("Bad telemetry payload on %s: %s", message.topic, exc)
            return
        await self.ingest(measurement)

    async def _handle_status(self, message: aiomqtt.Message) -> None:
        try:
            payload = json.loads(message.payload) if message.payload else {}
        except json.JSONDecodeError:
            return

        cabinet_id = str(message.topic).split("/")[-2]
        self._known_cabinets.add(cabinet_id)
        online = payload.get("online", True)

        active = self.active_alarms.setdefault(cabinet_id, {})
        atype = AlarmType.COMMUNICATION_LOSS.value

        if not online and atype not in active:
            alarm = Alarm(
                cabinet_id=cabinet_id,
                type=AlarmType.COMMUNICATION_LOSS,
                severity=AlarmSeverity.CRITICAL,
                message="Cabinet went offline (MQTT Last Will).",
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json")
            active[atype] = alarm
            log.warning("ALARM RAISED COMMUNICATION_LOSS on %s", cabinet_id)
            await self.publish(settings.mqtt_topic_alarms, alarm)
        elif online and atype in active:
            cleared = dict(active.pop(atype))
            cleared["cleared"] = True
            log.info("ALARM CLEARED COMMUNICATION_LOSS on %s", cabinet_id)
            await self.publish(settings.mqtt_topic_alarms, cleared)

    async def _reconcile_alarms(self, cabinet_id: str, current_alarms: list) -> None:
        current_by_type = {a.type.value: a for a in current_alarms}
        active = self.active_alarms.setdefault(cabinet_id, {})

        for atype, alarm in current_by_type.items():
            if atype not in active:
                payload = alarm.model_dump(mode="json")
                active[atype] = payload
                log.warning("ALARM RAISED %s — %s", atype, alarm.message)
                await self._safe_publish(settings.mqtt_topic_alarms, payload)

        managed_elsewhere = {AlarmType.COMMUNICATION_LOSS.value}
        for atype in list(active.keys()):
            if atype not in current_by_type and atype not in managed_elsewhere:
                cleared = dict(active.pop(atype))
                cleared["cleared"] = True
                log.info("ALARM CLEARED %s on %s", atype, cabinet_id)
                await self._safe_publish(settings.mqtt_topic_alarms, cleared)

    async def _safe_publish(self, topic: str, payload: dict) -> None:
        try:
            await self.publish(topic, payload)
        except RuntimeError:
            pass  # broker not connected (e.g. demo mode); alarm is still tracked

    async def _dimming_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.dimming_interval_s)
            now = datetime.now().time()
            for cabinet_id in list(self._known_cabinets):
                lux = self.last_lux.get(cabinet_id)
                level = dimming_controller.resolve_level(now, ambient_lux=lux)
                self.record_command(cabinet_id, dim=level)
                await self._safe_publish(
                    f"phoenix/cabinets/{cabinet_id}/cmd/dim", {"level": level}
                )

    async def _demo_loop(self) -> None:
        """Inject synthetic telemetry so the panel is alive without a broker."""
        tick = 0
        while True:
            await asyncio.sleep(settings.demo_interval_s)
            tick += 1
            for cid in _DEMO_CABINETS:
                blown = cid == "CAB-003" and (tick % 14) in (6, 7, 8)
                over = cid == "CAB-004" and (tick % 22) == 0
                voltage = 255.6 if over else round(random.uniform(228.0, 232.0), 1)
                current = 0.0 if blown else round(random.uniform(2.4, 3.3), 2)
                measurement = Measurement(
                    cabinet_id=cid,
                    voltage_v=voltage,
                    current_a=current,
                    active_power_w=round(voltage * current * 0.95, 1),
                    power_factor=0.0 if blown else 0.95,
                    lamp_circuit="L1",
                    ambient_lux=round(random.uniform(0.0, 55.0), 1),
                )
                await self.ingest(measurement)


bus = MQTTBus()

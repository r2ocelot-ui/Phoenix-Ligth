"""Async MQTT client wrapper.

Responsibilities:
- Subscribe to telemetry topics and feed the alarm engine.
- Track the *commanded* state of each cabinet (relay + dim) so the alarm engine
  can tell an intentional "off" apart from a blown lamp.
- Maintain stateful alarms (raised once, cleared when the condition resolves)
  instead of re-emitting on every telemetry sample.
- Run a dimming scheduler that resolves the time-based profile and pushes
  `cmd/dim` to every known cabinet.
- Expose publish() for the REST control API.
"""
import asyncio
import json
import logging
from datetime import datetime

import aiomqtt

from app.core.config import settings
from app.schemas.measurement import Measurement
from app.services import alarm_engine, dimming_controller

log = logging.getLogger("phoenix.mqtt")


class MQTTBus:
    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._tasks: list[asyncio.Task] = []
        # cabinet_id -> {alarm_type: alarm_payload}
        self.active_alarms: dict[str, dict[str, dict]] = {}
        # cabinet_id -> {"relay": "on"|"off", "dim": 0-100}
        self.cabinet_state: dict[str, dict] = {}
        self._known_cabinets: set[str] = set()

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._run()),
            asyncio.create_task(self._dimming_loop()),
        ]

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
        """Remember the last command sent to a cabinet (used by the alarm engine)."""
        state = self.cabinet_state.setdefault(cabinet_id, {"relay": "on", "dim": 100})
        if relay is not None:
            state["relay"] = relay
        if dim is not None:
            state["dim"] = dim

    def _is_expected_on(self, cabinet_id: str) -> bool:
        state = self.cabinet_state.get(cabinet_id)
        if state is None:
            return True  # assume energised until we have commanded otherwise
        return state.get("relay", "on") == "on" and state.get("dim", 100) > 0

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
                    log.info("Subscribed to %s", settings.mqtt_topic_telemetry)
                    async for message in client.messages:
                        await self._handle(message)
            except aiomqtt.MqttError as exc:
                log.warning("MQTT disconnected: %s — retrying in 5s", exc)
                self._client = None
                await asyncio.sleep(5)

    async def _handle(self, message: aiomqtt.Message) -> None:
        try:
            payload = json.loads(message.payload)
            measurement = Measurement(**payload)
        except Exception as exc:  # noqa: BLE001 - malformed payloads should not kill loop
            log.error("Bad telemetry payload on %s: %s", message.topic, exc)
            return

        self._known_cabinets.add(measurement.cabinet_id)
        expected_on = self._is_expected_on(measurement.cabinet_id)
        current = alarm_engine.evaluate(measurement, expected_on=expected_on)
        await self._reconcile_alarms(measurement.cabinet_id, current)

    async def _reconcile_alarms(self, cabinet_id: str, current_alarms: list) -> None:
        """Diff freshly-evaluated alarms against the active set: raise new ones,
        clear resolved ones, and publish each transition exactly once."""
        current_by_type = {a.type.value: a for a in current_alarms}
        active = self.active_alarms.setdefault(cabinet_id, {})

        for atype, alarm in current_by_type.items():
            if atype not in active:
                payload = alarm.model_dump(mode="json")
                active[atype] = payload
                log.warning("ALARM RAISED %s — %s", atype, alarm.message)
                await self.publish(settings.mqtt_topic_alarms, payload)

        for atype in list(active.keys()):
            if atype not in current_by_type:
                cleared = dict(active.pop(atype))
                cleared["cleared"] = True
                log.info("ALARM CLEARED %s on %s", atype, cabinet_id)
                await self.publish(settings.mqtt_topic_alarms, cleared)

    async def _dimming_loop(self) -> None:
        """Resolve the time-based dimming profile and push it to every cabinet.

        Uses server local time; a production build would resolve each cabinet's
        own timezone and optionally feed an ambient lux reading from telemetry.
        """
        while True:
            await asyncio.sleep(settings.dimming_interval_s)
            now = datetime.now().time()
            for cabinet_id in list(self._known_cabinets):
                level = dimming_controller.resolve_level(now)
                self.record_command(cabinet_id, dim=level)
                try:
                    await self.publish(
                        f"phoenix/cabinets/{cabinet_id}/cmd/dim", {"level": level}
                    )
                except RuntimeError:
                    pass  # broker not connected yet; retry next tick


bus = MQTTBus()

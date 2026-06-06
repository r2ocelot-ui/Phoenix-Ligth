"""Async MQTT client wrapper.

Subscribes to telemetry topics, feeds the ingest service, and exposes a
publish() helper used by the REST API to send commands back to the edge.
"""
import asyncio
import json
import logging

import aiomqtt

from app.core.config import settings
from app.schemas.measurement import Measurement
from app.services import alarm_engine

log = logging.getLogger("phoenix.mqtt")


class MQTTBus:
    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task | None = None
        self.active_alarms: dict[str, list[dict]] = {}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def publish(self, topic: str, payload: dict) -> None:
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        await self._client.publish(topic, json.dumps(payload), qos=1)

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
                await asyncio.sleep(5)

    async def _handle(self, message: aiomqtt.Message) -> None:
        try:
            payload = json.loads(message.payload)
            measurement = Measurement(**payload)
        except Exception as exc:  # noqa: BLE001 - malformed payloads should not kill loop
            log.error("Bad telemetry payload on %s: %s", message.topic, exc)
            return

        alarms = alarm_engine.evaluate(measurement)
        for alarm in alarms:
            log.warning("ALARM %s — %s", alarm.type, alarm.message)
            self.active_alarms.setdefault(alarm.cabinet_id, []).append(
                alarm.model_dump(mode="json")
            )
            await self.publish(settings.mqtt_topic_alarms, alarm.model_dump(mode="json"))


bus = MQTTBus()

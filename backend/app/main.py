"""Phoenix-Light backend entry point.

Bootstraps the MQTT bus, exposes the FastAPI app and mounts the v1 routers.
Run with: `uvicorn app.main:app --reload`.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import alarms, control
from app.core.config import settings
from app.core.mqtt_client import bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bus.start()
    yield
    await bus.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(alarms.router, prefix=settings.api_v1_prefix)
app.include_router(control.router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}

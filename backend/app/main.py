"""Phoenix-Light backend entry point.

Bootstraps the MQTT bus, exposes the FastAPI app and mounts the v1 routers.
Run with: `uvicorn app.main:app --reload`.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import alarms, audit, auth, cabinets, control, realtime, topology, users
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.mqtt_client import bus
from app.services.seed import seed_demo_admin, seed_demo_cabinets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.demo_mode:
        with SessionLocal() as db:
            seed_demo_admin(db, settings.demo_admin_username, settings.demo_admin_password)
            seed_demo_cabinets(db)
    await bus.start()
    yield
    await bus.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# Open CORS by default so integrator dashboards (ETRA/SICE Smart City portals)
# can call the API from a browser. Tighten via PHOENIX_CORS_ORIGINS in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(audit.router, prefix=settings.api_v1_prefix)
app.include_router(cabinets.router, prefix=settings.api_v1_prefix)
app.include_router(topology.router, prefix=settings.api_v1_prefix)
app.include_router(alarms.router, prefix=settings.api_v1_prefix)
app.include_router(control.router, prefix=settings.api_v1_prefix)
app.include_router(control.emergency_router, prefix=settings.api_v1_prefix)
app.include_router(realtime.router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


# Serve the Phoenix Light web panel (single-page app) if present.
_frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if _frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_frontend_dir), html=True), name="ui")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

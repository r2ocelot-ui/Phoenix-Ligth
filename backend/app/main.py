"""Phoenix-Light backend entry point.

Bootstraps the MQTT bus, exposes the FastAPI app and mounts the v1 routers.
Run with: `uvicorn app.main:app --reload`.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.v1 import alarms, audit, auth, cabinets, control, devices, projects, realtime, roles, security, tariff, topology, users
from app.core.config import settings
from app.core.database import SessionLocal, get_db, init_db
from app.core.mqtt_client import bus
from app.services import ip_guard, role_store
from app.services.seed import seed_demo_admin, seed_demo_cabinets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


DEFAULT_JWT_SECRET = "dev-secret-change-me"


def _check_production_safety() -> None:
    """Aborta el arranque si quedan defaults inseguros con el modo demo
    apagado. La idea es no estrenar producción con el secreto de ejemplo
    olvidado en ``.env``: una omisión muda que se ha cargado a más de un
    despliegue. Se ejecuta en cada lifespan; con ``demo_mode=true`` (la
    forma por defecto de la demo) no hace nada."""
    if settings.demo_mode:
        return
    problems: list[str] = []
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        problems.append(
            "PHOENIX_JWT_SECRET sigue en el valor por defecto. "
            "Genera una clave aleatoria larga y exporta PHOENIX_JWT_SECRET."
        )
    if not settings.lockout_enabled:
        problems.append(
            "PHOENIX_LOCKOUT_ENABLED=false con demo apagado: el anti-fuerza"
            "-bruta está desactivado. Actívalo (true) antes de producción."
        )
    if problems:
        raise RuntimeError("Configuración insegura para producción:\n - " + "\n - ".join(problems))


@asynccontextmanager
async def lifespan(_: FastAPI):
    _check_production_safety()
    init_db()
    with SessionLocal() as db:
        # Seed the editable role catalogue on first boot, then hydrate the
        # in-memory RANKS view from the table. Runs in every mode (not just
        # demo) so the editor has something to show out of the box.
        role_store.seed_default_roles(db)
        if settings.demo_mode:
            seed_demo_admin(db, settings.demo_admin_username, settings.demo_admin_password)
            seed_demo_cabinets(db)
    await bus.start()
    yield
    await bus.stop()


# Health and the static UI are exempt so a banned admin can still reach the
# panel when the ban lapses.
_IP_GUARD_EXEMPT_PREFIXES = ("/health", "/ui/")


async def ip_guard_dependency(
    request: Request, db: Session = Depends(get_db),
) -> None:
    """Per-HTTP-router gate: blocks any request from an IP on the banlist (or
    any IP that isn't whitelisted while siege mode is on). Applied at router
    level (not global) so WebSocket routes — which don't get a Request — keep
    working. WS endpoints check the IP guard manually if they need to."""
    if request.url.path.startswith(_IP_GUARD_EXEMPT_PREFIXES):
        return
    ip = ip_guard.client_ip(request)
    try:
        blocked, reason = ip_guard.check_blocked(db, ip)
    except OperationalError:
        # First boot before init_db() finished — fail open.
        return
    if blocked:
        raise HTTPException(status_code=403, detail=f"Acceso bloqueado: {reason}")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
_HTTP_GUARD = [Depends(ip_guard_dependency)]

# Open CORS by default so integrator dashboards (ETRA/SICE Smart City portals)
# can call the API from a browser. Tighten via PHOENIX_CORS_ORIGINS in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(users.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(roles.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(projects.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(audit.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(security.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(cabinets.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(topology.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(devices.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(alarms.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(control.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(control.emergency_router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
app.include_router(tariff.router, prefix=settings.api_v1_prefix, dependencies=_HTTP_GUARD)
# realtime carries WebSocket endpoints — they don't get a Request, so the
# guard is skipped for them. WS connections still go through auth.
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

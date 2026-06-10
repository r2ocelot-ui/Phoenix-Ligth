"""WebSocket endpoint that pushes live cabinet snapshots to the web panel.

Auth is via a `token` query parameter (the JWT). On connect the client gets the
current snapshot, then a fresh one whenever the bus state changes. Snapshots
carry live fields only; the panel merges them onto the metadata it already
fetched over REST.

R2 hardening: además de validar la firma del token, cargamos el usuario,
comprobamos que sigue activo y que tiene ``cabinet:read``, y filtramos el
snapshot al proyecto del usuario — antes un token válido de un usuario
desactivado o sin permisos seguía abriendo el WS, y owners y no-owners
veían el mismo snapshot global.
"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.core.security import TokenError, decode_access_token
from app.models.user import User
from app.services import ranks, tenancy

router = APIRouter(tags=["realtime"])


def _filtered(snapshot: list[dict], visible_codes: set[str] | None) -> list[dict]:
    """Recorta el snapshot a los cuadros que el usuario tiene permitido ver.
    ``None`` = sin filtro (owner)."""
    if visible_codes is None:
        return snapshot
    return [c for c in snapshot if c.get("cabinet_id") in visible_codes]


@router.websocket("/ws")
async def live_updates(
    websocket: WebSocket,
    token: str = "",
    db: Session = Depends(get_db),
) -> None:
    try:
        payload = decode_access_token(token)
    except TokenError:
        await websocket.close(code=4401)
        return

    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if user is None or not user.is_active:
        await websocket.close(code=4401)
        return
    if not ranks.has_permission(user, ranks.P_CABINET_READ):
        await websocket.close(code=4403)
        return

    # Resolvemos el scope una vez al conectar; si el usuario es reasignado
    # de proyecto mientras está conectado, se aplica al reconectar (igual
    # que el JWT, que también se refresca al hacer login de nuevo).
    visible = tenancy.cabinet_codes_in_scope(db, user, None)

    await websocket.accept()
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "snapshot", "cabinets": _filtered(bus.snapshot(), visible)})
        while True:
            snapshot = await queue.get()
            await websocket.send_json({"type": "snapshot", "cabinets": _filtered(snapshot, visible)})
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)

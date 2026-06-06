"""WebSocket endpoint that pushes live cabinet snapshots to the web panel.

Auth is via a `token` query parameter (the JWT). On connect the client gets the
current snapshot, then a fresh one whenever the bus state changes. Snapshots
carry live fields only; the panel merges them onto the metadata it already
fetched over REST.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.mqtt_client import bus
from app.core.security import TokenError, decode_access_token

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def live_updates(websocket: WebSocket, token: str = "") -> None:
    try:
        decode_access_token(token)
    except TokenError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "snapshot", "cabinets": bus.snapshot()})
        while True:
            snapshot = await queue.get()
            await websocket.send_json({"type": "snapshot", "cabinets": snapshot})
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)

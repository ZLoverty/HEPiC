import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/sensors")
async def sensor_stream(websocket: WebSocket, request: Request):
    """Stream real-time sensor + Klipper state as JSON at ~10 Hz."""
    await websocket.accept()
    broadcaster = request.app.state.app_state.broadcaster
    q = broadcaster.subscribe()
    try:
        while True:
            payload = await asyncio.wait_for(q.get(), timeout=5.0)
            await websocket.send_text(payload)
    except (WebSocketDisconnect, asyncio.TimeoutError, asyncio.CancelledError):
        pass
    finally:
        broadcaster.unsubscribe(q)

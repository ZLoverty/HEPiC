import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from HEPiC.database.material_database import get_material_database
from HEPiC.quality_check.gcode import build_quality_check_gcode

router = APIRouter()


def _db():
    return get_material_database()


class QCStartRequest(BaseModel):
    family: str
    pi_code: str


@router.post("/start")
async def start_quality_check(body: QCStartRequest, request: Request):
    """Generate QC gcode for the given material and send it to Klipper."""
    material = _db().get_material(body.pi_code, family=body.family)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    gcode = build_quality_check_gcode(material)
    await request.app.state.app_state.klipper.send_gcode(gcode)
    return {"ok": True, "gcode": gcode}


@router.websocket("/stream")
async def qc_status_stream(websocket: WebSocket, request: Request):
    """Stream M118 gcode responses (STATUS, START/STOP_QUALITY_CHECK, etc.)."""
    await websocket.accept()
    klipper = request.app.state.app_state.klipper
    q = klipper.subscribe_responses()
    try:
        while True:
            text = await asyncio.wait_for(q.get(), timeout=30.0)
            await websocket.send_text(json.dumps({"response": text}))
    except (WebSocketDisconnect, asyncio.TimeoutError, asyncio.CancelledError):
        pass
    finally:
        klipper.unsubscribe_responses(q)

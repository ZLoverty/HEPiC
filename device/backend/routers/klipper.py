import math

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


def _state(request: Request):
    return request.app.state.app_state


def _clean(v: object) -> object:
    return None if (isinstance(v, float) and not math.isfinite(v)) else v


class TemperatureRequest(BaseModel):
    temperature: float


class GcodeRequest(BaseModel):
    script: str


@router.get("/status")
async def get_status(request: Request):
    k = _state(request).klipper
    return {
        "hotend_temperature": _clean(k.hotend_temperature),
        "target_temperature": _clean(k.target_hotend_temperature),
        "feedrate_mms": k.active_feedrate_mms,
        "progress": k.progress,
        "klippy_state": k.klippy_state,
    }


@router.post("/temperature")
async def set_temperature(body: TemperatureRequest, request: Request):
    await _state(request).klipper.set_temperature(body.temperature)
    return {"ok": True}


@router.post("/gcode")
async def send_gcode(body: GcodeRequest, request: Request):
    await _state(request).klipper.send_gcode(body.script)
    return {"ok": True}


@router.post("/emergency_stop")
async def emergency_stop(request: Request):
    await _state(request).klipper.emergency_stop()
    return {"ok": True}


@router.post("/restart")
async def restart_firmware(request: Request):
    await _state(request).klipper.restart_firmware()
    return {"ok": True}

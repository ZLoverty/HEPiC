"""Fan-out broadcaster: pushes sensor snapshots to all subscribed WebSocket queues."""

import asyncio
import json
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from HEPiC.communications.tcp_client import TCPClient
    from .workers.klipper import DeviceKlipperWorker


def _clean(v: object) -> object:
    """Replace non-finite floats with None for JSON serialization."""
    return None if (isinstance(v, float) and not math.isfinite(v)) else v


def _clean_dict(d: dict) -> dict:
    return {k: _clean(v) for k, v in d.items()}


class SensorBroadcaster:
    def __init__(
        self,
        tcp_client: "TCPClient",
        klipper: "DeviceKlipperWorker",
        interval: float = 0.1,
    ):
        self._tcp = tcp_client
        self._klipper = klipper
        self._interval = interval
        self._queues: set[asyncio.Queue] = set()
        self._running = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._queues.discard(q)

    async def run(self):
        self._running = True
        while self._running:
            snapshot = {
                **_clean_dict(self._tcp.latest_sensor_data),
                "hotend_temperature": _clean(self._klipper.hotend_temperature),
                "target_temperature": _clean(self._klipper.target_hotend_temperature),
                "feedrate_mms": _clean(self._klipper.active_feedrate_mms),
            }
            payload = json.dumps(snapshot)
            dead: set[asyncio.Queue] = set()
            for q in list(self._queues):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass  # slow consumer — drop frame rather than block
                except Exception:
                    dead.add(q)
            self._queues -= dead
            await asyncio.sleep(self._interval)

    def stop(self):
        self._running = False

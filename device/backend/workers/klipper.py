"""Asyncio-native Moonraker client — no Qt/qasync dependency."""

import asyncio
import json
import logging
import math

import websockets

logger = logging.getLogger(__name__)

_nan = math.nan


class DeviceKlipperWorker:
    def __init__(self, host: str, port: int = 7125, query_delay: float = 0.5):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}/websocket"

        # public state polled by broadcaster / routers
        self.hotend_temperature: float = _nan
        self.target_hotend_temperature: float = _nan
        self.active_feedrate_mms: float = 0.0
        self.progress: float = 0.0
        # "ready" | "shutdown" | "error" | "disconnected" | "unknown"
        # Tracked so the UI can offer a FIRMWARE_RESTART affordance the
        # instant Klipper enters shutdown (e.g. after an emergency stop),
        # no matter which page is on screen.
        self.klippy_state: str = "unknown"

        self._running = True
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._response_queues: list[asyncio.Queue] = []
        self._id = 0

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    async def send_gcode(self, gcode: str):
        await self._enqueue({
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {"script": gcode},
            "id": self._next_id(),
        })

    async def set_temperature(self, temperature: float):
        await self.send_gcode(
            f"SET_HEATER_TEMPERATURE HEATER=extruder TARGET={temperature:.0f}"
        )

    async def emergency_stop(self):
        await self._enqueue({
            "jsonrpc": "2.0",
            "method": "printer.emergency_stop",
            "id": self._next_id(),
        })

    async def restart_firmware(self):
        await self.send_gcode("FIRMWARE_RESTART")

    def subscribe_responses(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._response_queues.append(q)
        return q

    def unsubscribe_responses(self, q: asyncio.Queue):
        try:
            self._response_queues.remove(q)
        except ValueError:
            pass

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _enqueue(self, msg: dict):
        try:
            self._send_queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Klipper send queue full, dropping message")

    def _subscribe_msg(self) -> dict:
        return {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {"objects": {
                "extruder": None,
                "motion_report": None,
                "print_stats": None,
                "webhooks": None,
            }},
            "id": self._next_id(),
        }

    async def run(self):
        while self._running:
            try:
                async with websockets.connect(self.uri, open_timeout=2.0) as ws:
                    logger.info("Connected to Moonraker at %s", self.uri)
                    await ws.send(json.dumps(self._subscribe_msg()))
                    send_task = asyncio.create_task(self._send_loop(ws))
                    try:
                        await self._listen(ws)
                    finally:
                        send_task.cancel()
                        try:
                            await send_task
                        except asyncio.CancelledError:
                            pass
            except Exception as e:
                logger.warning("Moonraker connection error: %s", e)
                self.hotend_temperature = _nan
                self.target_hotend_temperature = _nan
                self.klippy_state = "disconnected"
            if self._running:
                await asyncio.sleep(3)

    async def _listen(self, ws):
        async for raw in ws:
            try:
                self._handle(json.loads(raw))
            except Exception as e:
                logger.debug("Message error: %s", e)

    async def _send_loop(self, ws):
        while True:
            msg = await self._send_queue.get()
            await ws.send(json.dumps(msg))

    def _handle(self, msg: dict):
        method = msg.get("method")

        if method == "notify_status_update":
            status = (msg.get("params") or [{}])[0]
            self._apply_status(status)

        if "result" in msg and isinstance(msg["result"], dict):
            self._apply_status(msg["result"].get("status", {}))

        # Klippy state notifications fire independently of the subscribed
        # status stream, so they're the most reliable signal that the
        # firmware just entered (or left) shutdown.
        if method == "notify_klippy_ready":
            self.klippy_state = "ready"
            # Klippy just (re)started (e.g. after FIRMWARE_RESTART). The
            # Moonraker websocket itself never dropped, so run()'s reconnect
            # path never re-fires — without this, our object subscription
            # stays registered against the dead pre-restart Klippy instance
            # and status updates (temperature, feedrate, ...) never resume.
            try:
                self._send_queue.put_nowait(self._subscribe_msg())
            except asyncio.QueueFull:
                logger.warning("Klipper send queue full, dropping re-subscribe")
        elif method == "notify_klippy_shutdown":
            self.klippy_state = "shutdown"
        elif method == "notify_klippy_disconnected":
            self.klippy_state = "disconnected"

        if method == "notify_gcode_response":
            params = msg.get("params") or []
            if params:
                text = params[0] if isinstance(params[0], str) else str(params[0])
                for q in list(self._response_queues):
                    try:
                        q.put_nowait(text)
                    except asyncio.QueueFull:
                        pass

    def _apply_status(self, status: dict):
        extruder = status.get("extruder", {})
        if "temperature" in extruder:
            self.hotend_temperature = float(extruder["temperature"])
        if "target" in extruder:
            self.target_hotend_temperature = float(extruder["target"])
        motion_report = status.get("motion_report", {})
        if "live_extruder_velocity" in motion_report:
            self.active_feedrate_mms = float(motion_report["live_extruder_velocity"])
        print_stats = status.get("print_stats", {})
        if "progress" in print_stats:
            self.progress = float(print_stats["progress"])
        webhooks = status.get("webhooks", {})
        if "state" in webhooks:
            self.klippy_state = webhooks["state"]

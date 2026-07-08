"""Mock workers for local development without physical hardware."""

import asyncio
import logging
import math
import time

logger = logging.getLogger(__name__)


class MockTCPClient:
    """Simulates the Pi sensor TCP stream with synthetic data."""

    def __init__(self):
        self.latest_sensor_data: dict[str, float] = {
            "extrusion_force_N": 0.0,
            "measured_feedrate_mms": 0.0,
        }
        self._running = False

    async def run(self):
        self._running = True
        logger.info("[MOCK] TCPClient running — generating synthetic sensor data")
        t0 = time.monotonic()
        while self._running:
            t = time.monotonic() - t0
            self.latest_sensor_data = {
                "extrusion_force_N": 2.5 + 1.5 * math.sin(t * 0.3),
                "measured_feedrate_mms": 5.0 + 0.5 * math.sin(t * 0.7 + 1.0),
            }
            await asyncio.sleep(0.05)

    def stop(self):
        self._running = False

    # stubs expected by AppState teardown
    def get_zeroable_sensor_names(self):
        return []


class MockKlipperWorker:
    """Simulates Moonraker/Klipper with slowly-changing state."""

    def __init__(self):
        self.hotend_temperature: float = 25.0
        self.target_hotend_temperature: float = 0.0
        self.active_feedrate_mms: float = 0.0
        self.progress: float = 0.0
        self.klippy_state: str = "ready"
        self._running = False

    async def run(self):
        self._running = True
        logger.info("[MOCK] KlipperWorker running — simulating printer state")
        t0 = time.monotonic()
        while self._running:
            t = time.monotonic() - t0
            # temperature creeps toward target
            diff = self.target_hotend_temperature - self.hotend_temperature
            self.hotend_temperature += diff * 0.02
            # small ambient noise
            self.hotend_temperature += 0.05 * math.sin(t * 2.1)
            self.active_feedrate_mms = 5.0 + math.sin(t * 0.4)
            await asyncio.sleep(0.1)

    def stop(self):
        self._running = False

    async def send_gcode(self, gcode: str):
        logger.info("[MOCK] G-code: %s", gcode)

    async def set_temperature(self, temperature: float):
        logger.info("[MOCK] Set temperature: %s °C", temperature)
        self.target_hotend_temperature = temperature

    async def emergency_stop(self):
        logger.warning("[MOCK] Emergency stop!")
        self.target_hotend_temperature = 0.0
        self.klippy_state = "shutdown"

    async def restart_firmware(self):
        logger.info("[MOCK] Firmware restart")
        self.klippy_state = "ready"

    def subscribe_responses(self) -> asyncio.Queue:
        return asyncio.Queue()

    def unsubscribe_responses(self, q: asyncio.Queue):
        pass

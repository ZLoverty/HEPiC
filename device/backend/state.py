import asyncio
import logging

from HEPiC.communications.tcp_client import TCPClient

from .broadcast import SensorBroadcaster
from .config import Config
from .workers.klipper import DeviceKlipperWorker

logger = logging.getLogger(__name__)


class AppState:
    """Holds long-lived worker instances shared across all request handlers."""

    def __init__(self, config: Config):
        self.config = config
        self.tcp_client = TCPClient(config.hepic_host, config.hepic_tcp_port)
        self.klipper = DeviceKlipperWorker(config.klipper_host, config.klipper_port)
        self.broadcaster = SensorBroadcaster(
            self.tcp_client,
            self.klipper,
            interval=config.sensor_broadcast_interval,
        )
        self._tasks: list[asyncio.Task] = []

    async def __aenter__(self):
        self._tasks = [
            asyncio.create_task(self.tcp_client.run(), name="tcp_client"),
            asyncio.create_task(self.klipper.run(), name="klipper"),
            asyncio.create_task(self.broadcaster.run(), name="broadcaster"),
        ]
        logger.info("AppState started: tcp=%s:%d  klipper=%s:%d",
                    self.config.hepic_host, self.config.hepic_tcp_port,
                    self.config.klipper_host, self.config.klipper_port)
        return self

    async def __aexit__(self, *_):
        self.tcp_client.stop()
        self.klipper.stop()
        self.broadcaster.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("AppState stopped.")

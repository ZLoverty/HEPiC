import asyncio
import logging
import os

from .broadcast import SensorBroadcaster
from .config import Config

logger = logging.getLogger(__name__)


def _build_workers(config: Config):
    if os.getenv("HEPIC_MOCK"):
        from .mock import MockTCPClient, MockKlipperWorker
        logger.info("HEPIC_MOCK enabled — using mock hardware workers")
        return MockTCPClient(), MockKlipperWorker()
    from HEPiC.communications.tcp_client import TCPClient
    from .workers.klipper import DeviceKlipperWorker
    return TCPClient(config.hepic_host, config.hepic_tcp_port), DeviceKlipperWorker(config.klipper_host, config.klipper_port)


class AppState:
    """Holds long-lived worker instances shared across all request handlers."""

    def __init__(self, config: Config):
        self.config = config
        self.tcp_client, self.klipper = _build_workers(config)
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

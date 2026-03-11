from collections import deque
from dataclasses import dataclass
import asyncio
import json
import logging
import random
import sys
import time

import numpy as np

try:
    from PySide6.QtCore import QObject, Signal, Slot
except ImportError:
    class QObject:
        pass

    class Signal:
        def __init__(self, *_args, **_kwargs):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def emit(self, *args, **kwargs):
            for callback in list(self._callbacks):
                callback(*args, **kwargs)

    def Slot(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator


@dataclass
class SensorData:
    name: str
    can_zero: bool = False
    raw_value: float = np.nan
    offset: float = 0.0
    value: float = np.nan

    def update(self, raw_value):
        self.raw_value = float(raw_value)
        self.value = self.raw_value - self.offset

    def zero(self) -> bool:
        if not self.can_zero:
            print(f"Sensor {self.name} is not zeroable.")
            return False
        if np.isnan(self.raw_value):
            return False
        self.offset = self.raw_value
        self.value = 0.0
        return True


class TCPClient(QObject):
    connection_status = Signal(str)
    connected = Signal(int)
    extrusion_force_signal = Signal(float)
    meter_count_signal = Signal(float)
    sensor_config_received = Signal(list)

    def __init__(
        self,
        host: str,
        port: int,
        rotary_encoder_steps_total: int = 1000,
        rotary_encoder_wheel_diameter: float = 28.6,
        meter_count_cache_size: int = 100,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = True

        self.queue: asyncio.Queue = asyncio.Queue()

        # Backward-compatible public states used by UI.
        self.extrusion_force = np.nan
        self.extrusion_force_offset = 0.0
        self.extrusion_force_raw = np.nan
        self.meter_count_raw = np.nan
        self.meter_count_offset = 0.0
        self.meter_count = np.nan

        self.steps_total = rotary_encoder_steps_total
        self.wheel_diameter = rotary_encoder_wheel_diameter

        self.cache_size = meter_count_cache_size
        self.meter_count_cache = deque(maxlen=self.cache_size)
        self.time_cache = deque(maxlen=self.cache_size)
        self.filament_velocity = 0.0

        self.latest_sensor_data: dict[str, float] = {}
        self.sensor_columns: list[str] = []
        self.sensor_data_map: dict[str, SensorData] = {}

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.sensor_config: dict | None = None

        self.logger = logging.getLogger(__name__)

    async def run(self):
        while self.is_running:
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=2.0
                )
                self.logger.info(f"HEPiC server connected: {self.host}:{self.port}")

                await self.request_sensor_config()
                self.receive_task = asyncio.create_task(self.receive_data())
                self.process_task = asyncio.create_task(self.process_data())
                _done, pending = await asyncio.wait(
                    [self.receive_task, self.process_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                self.logger.warning("Connection interrupted, cleaning tasks...")
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            except Exception as e:
                self.logger.error(f"TCP client error: {e}")
            finally:
                self.logger.info("Closing HEPiC server connection...")
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                    self.writer = None
                self.reader = None

            if self.is_running:
                self.connection_status.emit("hepic_server disconnected, reconnecting in 3s...")
                await asyncio.sleep(1)
                self.connection_status.emit("hepic_server disconnected, reconnecting in 2s...")
                await asyncio.sleep(1)
                self.connection_status.emit("hepic_server disconnected, reconnecting in 1s...")
                await asyncio.sleep(1)

    async def send_data(self, message: str):
        if not self.is_running or not self.writer:
            self.logger.info("Connection not established; cannot send message.")
            return

        try:
            data_to_send = (message + "\n").encode("utf-8")
            self.writer.write(data_to_send)
            await self.writer.drain()
            self.logger.info(f"Sent -> {message}")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            self.is_running = False

    async def send_json(self, message: dict):
        if not self.is_running or not self.writer:
            self.logger.info("Connection not established; cannot send json.")
            return

        try:
            data_to_send = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
            self.writer.write(data_to_send)
            await self.writer.drain()
        except Exception as e:
            self.logger.error(f"Error sending json: {e}")
            self.is_running = False

    async def request_sensor_config(self):
        await self.send_json({"message_type": "get_sensor_config"})
        self.logger.info("Requested sensor_config from server.")

    def _normalize_message(self, message: object) -> dict:
        if isinstance(message, dict) and "message_type" in message:
            return {
                "message_type": message.get("message_type"),
                "payload": message.get("payload"),
            }
        if isinstance(message, dict):
            return {"message_type": "sensor_data", "payload": message}
        return {"message_type": "unknown", "payload": message}

    def _extract_sensor_columns(self, sensor_config_payload: dict) -> list[str]:
        columns: list[str] = []
        for item in sensor_config_payload.get("sensors", []):
            if not isinstance(item, dict):
                continue
            sensor_name = item.get("name") or item.get("id")
            if sensor_name:
                columns.append(str(sensor_name))

        deduped: list[str] = []
        seen: set[str] = set()
        for col in columns:
            if col in seen:
                continue
            seen.add(col)
            deduped.append(col)
        return deduped

    def _is_zeroable_sensor(self, sensor_name: str) -> bool:
        if self.sensor_config is not None:
            for item in self.sensor_config.get("sensors", []):
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if name == sensor_name:
                    return bool(item.get("zeroable", False))
        else:
            self.logger.info(f"Sensor config not received yet, cannot determine if {sensor_name} is zeroable.")
            return False

    def _ensure_sensor(self, sensor_name: str):
        if sensor_name not in self.sensor_data_map:
            self.sensor_data_map[sensor_name] = SensorData(
                name=sensor_name,
                can_zero=self._is_zeroable_sensor(sensor_name),
            )
            return

        sensor = self.sensor_data_map[sensor_name]
        if not sensor.can_zero:
            sensor.can_zero = self._is_zeroable_sensor(sensor_name)

    def _filter_payload_by_sensor_columns(self, payload: dict) -> dict:
        if not self.sensor_columns:
            return payload
        return {k: payload[k] for k in self.sensor_columns if k in payload}

    async def receive_data(self):
        try:
            while self.is_running:
                if self.reader is None:
                    break
                data = await self.reader.readline()
                if not data:
                    raise ConnectionResetError("Socket closed by server")

                message_str = data.decode("utf-8").strip()
                if not message_str:
                    continue
                message_dict = json.loads(message_str)
                await self.queue.put(self._normalize_message(message_dict))
        except (ConnectionResetError, ConnectionAbortedError):
            self.logger.error("Connection reset/aborted.")
            self.connection_status.emit("Connection lost")
        except Exception as e:
            self.logger.error(f"Receive error: {e}")

    async def process_data(self):
        try:
            while self.is_running:
                try:
                    message = await self.queue.get()
                    self.logger.debug(f"Processing message: {message}")

                    message_type = message.get("message_type")
                    payload = message.get("payload")

                    if message_type == "sensor_config" and isinstance(payload, dict):
                        self.logger.info("Received sensor_config from server.")
                        self.sensor_columns = self._extract_sensor_columns(payload)
                        self.sensor_config = payload
                        for sensor_name in self.sensor_columns:
                            self._ensure_sensor(sensor_name)
                        
                        self.sensor_config_received.emit(self.sensor_columns)
                        

                    if message_type == "sensor_data" and isinstance(payload, dict):
                        filtered_payload = self._filter_payload_by_sensor_columns(payload)
                        processed_payload: dict[str, float] = {}

                        for sensor_name, raw_value in filtered_payload.items():
                            try:
                                self._ensure_sensor(sensor_name)
                                sensor = self.sensor_data_map[sensor_name]
                                sensor.update(raw_value)
                                processed_payload[sensor_name] = sensor.value
                            except Exception as e:
                                self.logger.error(f"Invalid sensor value ignored ({sensor_name}): {e}")

                        if "meter_count_mm" in processed_payload:
                            self.meter_count = processed_payload["meter_count_mm"]
                            self.compute_filament_velocity()
                        processed_payload["measured_feedrate_mms"] = self.filament_velocity

                        self.latest_sensor_data = processed_payload

                    self.queue.task_done()
                except Exception as e:
                    self.logger.error(f"Error in process_data: {e}")
        except asyncio.CancelledError:
            self.logger.debug("Process data task cancelled.")


    def zero_sensor(self, sensor_name: str):
        sensor = self.sensor_data_map.get(sensor_name)
        if not sensor:
            self.logger.warning(f"Cannot set zero offset for {sensor_name}: sensor not found.")
            return
        if not sensor.zero():
            self.logger.warning(f"Cannot set zero offset for {sensor_name}: no data or not zeroable.")
            return

        self.logger.info(f"{sensor.name} offset set to {sensor.offset}")

    def get_zeroable_sensor_names(self) -> list[str]:
        return [name for name, sensor in self.sensor_data_map.items() if sensor.can_zero]

    def compute_filament_velocity(self):
        if np.isnan(self.meter_count):
            self.filament_velocity = np.nan
            return

        self.meter_count_cache.append(self.meter_count)
        self.time_cache.append(time.time())

        if len(self.meter_count_cache) == self.cache_size:
            delta_meter = self.meter_count_cache[self.cache_size - 1] - self.meter_count_cache[0]
            delta_time = self.time_cache[self.cache_size - 1] - self.time_cache[0]
            try:
                if delta_time <= 0:
                    self.filament_velocity = np.nan
                else:
                    self.filament_velocity = delta_meter / delta_time
            except Exception as e:
                self.logger.error(f"Velocity compute error: {e}")
                self.filament_velocity = np.nan
        else:
            self.filament_velocity = 0.0

    @Slot()
    def stop(self):
        self.is_running = False

        if hasattr(self, "receive_task"):
            self.receive_task.cancel()
        if hasattr(self, "process_task"):
            self.process_task.cancel()
        if self.writer:
            self.writer.close()


async def mock_data_sender(_reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"Accept connection from {addr}")

    shutdown_signal = asyncio.Future()

    async def send_loop(_writer):
        while not shutdown_signal.done():
            try:
                extrusion_force = 2 + random.uniform(-0.2, 0.2)
                meter_count = 2 + random.uniform(-0.2, 0.2)
                message = {
                    "message_type": "sensor_data",
                    "payload": {
                        "extrusion_force_N": extrusion_force,
                        "meter_count_mm": meter_count,
                    },
                }
                data_to_send = json.dumps(message).encode("utf-8") + b"\n"
                writer.write(data_to_send)
                await writer.drain()
                await asyncio.sleep(0.1)
            except Exception:
                shutdown_signal.set_result(True)

    send_task = asyncio.create_task(send_loop(writer))

    await shutdown_signal

    send_task.cancel()
    writer.close()
    await writer.wait_closed()


async def _test_tcp_client():
    host, port = "127.0.0.1", 10001
    server = await asyncio.start_server(mock_data_sender, host, port)
    asyncio.create_task(server.serve_forever())
    tcp_client = TCPClient(host, port)

    recv_task = asyncio.create_task(tcp_client.run())
    await asyncio.sleep(3)
    tcp_client.stop()
    await asyncio.gather(recv_task, return_exceptions=True)


async def main():
    await _test_tcp_client()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Test interrupted.")

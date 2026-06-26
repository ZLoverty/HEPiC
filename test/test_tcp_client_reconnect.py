#!/usr/bin/env python3
"""
Test: TCPClient reconnect behavior.

Validates three bug fixes:
  1. send failure no longer sets is_running=False and kills the reconnect loop
  2. null sensor values from server become nan instead of crashing sensor.update()
  3. stale queue items from the old connection are cleared before each reconnect

Usage:
    python test/test_tcp_client_reconnect.py
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from HEPiC.communications.tcp_client import SensorData, TCPClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sensor_data_msg(payload: dict) -> bytes:
    return json.dumps({"message_type": "sensor_data", "payload": payload}).encode() + b"\n"


def _sensor_config_msg(sensor_names: list[str]) -> bytes:
    payload = {"sensors": [{"id": n, "name": n} for n in sensor_names]}
    return json.dumps({"message_type": "sensor_config", "payload": payload}).encode() + b"\n"


class MockServer:
    """Controllable TCP server that records connections and lets tests drive them.

    Each connection is kept alive by a per-connection asyncio.Event.
    drop_latest() closes the writer and signals that event so the handler exits
    immediately — no wait_closed() deadlock with the client side.
    """

    def __init__(self):
        self.host = "127.0.0.1"
        self.port: int | None = None
        self._server = None
        # (writer, done_event) for each accepted connection
        self._conns: list[tuple[asyncio.StreamWriter, asyncio.Event]] = []
        self._any_connected = asyncio.Event()
        self.connection_count = 0

    async def start(self):
        self._server = await asyncio.start_server(self._on_connect, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _on_connect(self, _reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        done = asyncio.Event()
        self._conns.append((writer, done))
        self.connection_count += 1
        self._any_connected.set()
        await done.wait()
        # Close writer here, inside the event-loop callback, so the OS
        # sends FIN in the proper asyncio context and client wait_closed() completes.
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    async def wait_for_connection(self, n: int, timeout: float = 6.0):
        """Block until at least n total connections have been made."""
        async def _poll():
            while self.connection_count < n:
                self._any_connected.clear()
                if self.connection_count >= n:
                    return
                await self._any_connected.wait()

        try:
            await asyncio.wait_for(_poll(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(
                f"Timed out waiting for connection #{n} (got {self.connection_count})"
            )

    async def send(self, data: bytes):
        """Send data to the most recently connected client."""
        if not self._conns:
            raise RuntimeError("No active connection")
        writer, _ = self._conns[-1]
        writer.write(data)
        await writer.drain()

    async def drop_latest(self):
        """Signal the latest connection to close (handler does the actual close)."""
        if not self._conns:
            return
        _, done = self._conns[-1]
        done.set()

    async def stop(self):
        for _, done in self._conns:
            done.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()


# ---------------------------------------------------------------------------
# Test: SensorData null handling (no server needed)
# ---------------------------------------------------------------------------

class TestSensorDataNullHandling(unittest.TestCase):
    def test_none_becomes_nan(self):
        sensor = SensorData(name="force")
        sensor.update(None)
        self.assertTrue(np.isnan(sensor.raw_value), "raw_value should be nan after None update")
        self.assertTrue(np.isnan(sensor.value), "value should be nan after None update")

    def test_zero_still_works(self):
        sensor = SensorData(name="force")
        sensor.update(0.0)
        self.assertEqual(sensor.raw_value, 0.0)
        self.assertEqual(sensor.value, 0.0)

    def test_none_after_valid_keeps_offset(self):
        sensor = SensorData(name="force")
        sensor.update(9.81)
        sensor.offset = 9.81
        sensor.update(None)
        self.assertTrue(np.isnan(sensor.value))
        self.assertEqual(sensor.offset, 9.81, "offset must not change on null update")

    def test_valid_after_none_recovers(self):
        sensor = SensorData(name="force")
        sensor.update(None)
        sensor.update(5.0)
        self.assertEqual(sensor.raw_value, 5.0)


# ---------------------------------------------------------------------------
# Test: send failure does NOT kill is_running (no server needed)
# ---------------------------------------------------------------------------

class TestSendFailureDoesNotKillReconnect(unittest.IsolatedAsyncioTestCase):
    async def test_send_json_failure_leaves_is_running_true(self):
        """send_json raising an exception must NOT set is_running=False."""
        client = TCPClient("127.0.0.1", 19999)
        client.writer = MagicMock()
        client.writer.drain = AsyncMock(side_effect=ConnectionResetError("simulated drop"))

        await client.send_json({"message_type": "get_sensor_config"})

        self.assertTrue(client.is_running, "is_running must stay True after send_json failure")

    async def test_send_data_failure_leaves_is_running_true(self):
        """send_data raising an exception must NOT set is_running=False."""
        client = TCPClient("127.0.0.1", 19999)
        client.writer = MagicMock()
        client.writer.drain = AsyncMock(side_effect=BrokenPipeError("simulated drop"))

        await client.send_data("hello")

        self.assertTrue(client.is_running, "is_running must stay True after send_data failure")


# ---------------------------------------------------------------------------
# Test: send failure proactively invalidates writer to trigger reconnect
# (Vulnerability 2: send failures were silently swallowed, leaving a zombie
#  writer and relying solely on the read timeout to notice the dead link.)
# ---------------------------------------------------------------------------

class TestSendFailureTriggersReconnect(unittest.IsolatedAsyncioTestCase):
    async def test_send_data_failure_closes_writer(self):
        """A failed send must close the writer so the read side gets EOF and reconnects."""
        client = TCPClient("127.0.0.1", 19999)
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock(side_effect=ConnectionResetError("drop"))
        client.writer = mock_writer

        await client.send_data("hello")

        mock_writer.close.assert_called_once()

    async def test_send_json_failure_closes_writer(self):
        client = TCPClient("127.0.0.1", 19999)
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock(side_effect=BrokenPipeError("drop"))
        client.writer = mock_writer

        await client.send_json({"message_type": "ping"})

        mock_writer.close.assert_called_once()


# ---------------------------------------------------------------------------
# Test: drain() must not block forever
# (Vulnerability 3: writer.drain() had no timeout and could hang the caller
#  indefinitely on a half-open / congested connection.)
# ---------------------------------------------------------------------------

class TestSendTimeout(unittest.IsolatedAsyncioTestCase):
    async def test_send_data_does_not_hang_when_drain_blocks(self):
        client = TCPClient("127.0.0.1", 19999, send_timeout=0.1)
        mock_writer = MagicMock()

        async def _hang(*_a, **_k):
            await asyncio.sleep(30)

        mock_writer.drain = AsyncMock(side_effect=_hang)
        client.writer = mock_writer

        # If drain were unbounded this would hit the outer 2s timeout and fail.
        await asyncio.wait_for(client.send_data("x"), timeout=2.0)
        self.assertTrue(client.is_running)

    async def test_send_json_does_not_hang_when_drain_blocks(self):
        client = TCPClient("127.0.0.1", 19999, send_timeout=0.1)
        mock_writer = MagicMock()

        async def _hang(*_a, **_k):
            await asyncio.sleep(30)

        mock_writer.drain = AsyncMock(side_effect=_hang)
        client.writer = mock_writer

        await asyncio.wait_for(client.send_json({"a": 1}), timeout=2.0)
        self.assertTrue(client.is_running)


# ---------------------------------------------------------------------------
# Test: exponential reconnect backoff
# (Vulnerability 4: fixed 3s delay with cosmetic countdown; no backoff.)
# ---------------------------------------------------------------------------

class TestReconnectBackoff(unittest.TestCase):
    def test_delay_grows_exponentially_and_caps(self):
        client = TCPClient(
            "h", 1, reconnect_base_delay=1.0, reconnect_max_delay=8.0
        )
        delays = [client._next_reconnect_delay() for _ in range(6)]
        self.assertEqual(delays, [1.0, 2.0, 4.0, 8.0, 8.0, 8.0])

    def test_successful_connection_resets_backoff(self):
        client = TCPClient(
            "h", 1, reconnect_base_delay=1.0, reconnect_max_delay=8.0
        )
        client._next_reconnect_delay()
        client._next_reconnect_delay()
        client._reset_reconnect_backoff()
        self.assertEqual(client._next_reconnect_delay(), 1.0)


# ---------------------------------------------------------------------------
# Integration tests: reconnect with a live mock server
# ---------------------------------------------------------------------------

class TestReconnectIntegration(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.server = MockServer()
        await self.server.start()
        self.client = TCPClient(self.server.host, self.server.port)
        self.client_task = asyncio.create_task(self.client.run())

    async def asyncTearDown(self):
        self.client.stop()
        self.client_task.cancel()
        try:
            await self.client_task
        except (asyncio.CancelledError, Exception):
            pass
        await self.server.stop()

    async def _wait_for_value(self, key: str, expected, timeout: float = 3.0):
        """Poll latest_sensor_data until key==expected or timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            val = self.client.latest_sensor_data.get(key)
            if isinstance(expected, float) and np.isnan(expected):
                if isinstance(val, float) and np.isnan(val):
                    return
            elif val == expected:
                return
            if loop.time() > deadline:
                raise AssertionError(
                    f"Timed out waiting for {key}={expected!r}; "
                    f"latest_sensor_data={self.client.latest_sensor_data}"
                )
            await asyncio.sleep(0.05)

    async def test_data_flows_after_reconnect(self):
        """After a connection drop, data resumes on the new connection."""
        # --- First connection ---
        await self.server.wait_for_connection(1)
        await self.server.send(_sensor_config_msg(["force"]))
        await self.server.send(_sensor_data_msg({"force": 9.81}))
        await self._wait_for_value("force", 9.81)

        # --- Drop ---
        await self.server.drop_latest()

        # --- Second connection (client reconnects after ~3 s delay) ---
        await self.server.wait_for_connection(2, timeout=7.0)
        await self.server.send(_sensor_config_msg(["force"]))
        await self.server.send(_sensor_data_msg({"force": 5.55}))
        await self._wait_for_value("force", 5.55)

    async def test_malformed_message_does_not_drop_connection(self):
        """A bad JSON / non-UTF8 line must be skipped, not trigger a reconnect.

        (Vulnerability 1: decode/json errors bubbled up and killed receive_data,
         recycling a perfectly healthy connection on a single bad message.)
        """
        await self.server.wait_for_connection(1)
        await self.server.send(_sensor_config_msg(["force"]))

        # Garbage that previously crashed receive_data and forced a reconnect.
        await self.server.send(b"this is not json\n")
        await self.server.send(b"\xff\xfe not valid utf-8\n")
        await self.server.send(b"\n")  # empty line

        # A valid message right after must still be processed on the SAME connection.
        await self.server.send(_sensor_data_msg({"force": 7.77}))
        await self._wait_for_value("force", 7.77)

        self.assertEqual(
            self.server.connection_count, 1,
            "malformed data must not trigger a reconnect",
        )

    async def test_null_values_in_payload_become_nan(self):
        """Server sending null for a sensor must result in nan, not a crash."""
        await self.server.wait_for_connection(1)
        await self.server.send(_sensor_config_msg(["force", "meter"]))
        await self.server.send(_sensor_data_msg({"force": 9.81, "meter": None}))

        await self._wait_for_value("force", 9.81)

        meter_val = self.client.latest_sensor_data.get("meter")
        self.assertTrue(
            meter_val is None or (isinstance(meter_val, float) and np.isnan(meter_val)),
            f"meter should be nan or absent for null payload, got {meter_val!r}",
        )

    async def test_stale_queue_cleared_before_reconnect(self):
        """Items left in queue from old connection must not appear in new session."""
        await self.server.wait_for_connection(1)
        await self.server.send(_sensor_config_msg(["force"]))

        # Inject stale items with a value that must never survive into the new session.
        stale = {"message_type": "sensor_data", "payload": {"force": 999.0}}
        for _ in range(5):
            await self.client.queue.put(stale)

        # Drop → triggers cleanup and queue flush in run().
        await self.server.drop_latest()

        # Allow extra time: process_task drains stale items before suspending,
        # which slightly delays EOF delivery to receive_task on loopback.
        await self.server.wait_for_connection(2, timeout=12.0)

        # Send fresh data on the new connection.
        await self.server.send(_sensor_config_msg(["force"]))
        await self.server.send(_sensor_data_msg({"force": 2.22}))

        # If stale queue wasn't cleared, the 999.0 backlog would block or corrupt
        # the fresh value. Receiving 2.22 proves the queue was flushed cleanly.
        await self._wait_for_value("force", 2.22, timeout=3.0)

    async def test_multiple_reconnects_keep_working(self):
        """Client should keep reconnecting through repeated drops."""
        for cycle in range(3):
            n = cycle + 1
            await self.server.wait_for_connection(n, timeout=8.0)
            await self.server.send(_sensor_config_msg(["force"]))
            value = float(n)
            await self.server.send(_sensor_data_msg({"force": value}))
            await self._wait_for_value("force", value)
            await self.server.drop_latest()


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

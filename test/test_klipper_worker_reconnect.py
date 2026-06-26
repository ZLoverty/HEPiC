#!/usr/bin/env python3
"""
Test: KlipperWorker reconnect behavior (multi-scenario).

Mirrors test_tcp_client_reconnect.py. Validates that the Klipper/Moonraker
websocket client survives the failure modes that would otherwise cause
spurious reconnects or leaked tasks:

  K1. A malformed / unexpectedly-shaped server message must NOT crash
      data_processor (which would tear down a healthy connection).
  K2. stop() must cancel query_task (no task leak on shutdown).
  K3. Reconnect uses exponential backoff with a cap and resets on success.

Plus baseline integration checks that genuine drops DO reconnect.

Usage:
    python test/test_klipper_worker_reconnect.py
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from HEPiC.communications.klipper_worker import KlipperWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw_run(worker: KlipperWorker):
    """Return the run() coroutine, bypassing the @asyncSlot wrapper."""
    return KlipperWorker.run.__wrapped__(worker)


class FakeWebSocket:
    """Minimal stand-in for a websocket connection used by data_processor."""

    def __init__(self):
        self.sent: list[str] = []

    async def send(self, message: str):
        self.sent.append(message)


class ControllableMoonraker:
    """A websocket server tests can drive: accept, send raw, drop, count."""

    def __init__(self):
        self.host = "127.0.0.1"
        self.port: int | None = None
        self._server = None
        self._conns: list[tuple] = []  # (websocket, close_event)
        self.connection_count = 0
        self._connected = asyncio.Event()

    async def start(self):
        self._server = await websockets.serve(self._handler, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _handler(self, websocket):
        close_event = asyncio.Event()
        self._conns.append((websocket, close_event))
        self.connection_count += 1
        self._connected.set()
        # Drain whatever the client sends (queries) so it never errors.
        drain = asyncio.create_task(self._drain(websocket))
        try:
            await close_event.wait()
        finally:
            drain.cancel()
            try:
                await websocket.close()
            except Exception:
                pass

    async def _drain(self, websocket):
        try:
            async for _ in websocket:
                pass
        except Exception:
            pass

    async def wait_for_connection(self, n: int, timeout: float = 8.0):
        async def _poll():
            while self.connection_count < n:
                self._connected.clear()
                if self.connection_count >= n:
                    return
                await self._connected.wait()

        await asyncio.wait_for(_poll(), timeout=timeout)

    async def reconnected_within(self, n: int, timeout: float) -> bool:
        """True if connection #n happens before timeout, else False."""
        try:
            await self.wait_for_connection(n, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def send_raw(self, data):
        if not self._conns:
            raise RuntimeError("No active connection")
        websocket, _ = self._conns[-1]
        payload = data if isinstance(data, (str, bytes)) else json.dumps(data)
        await websocket.send(payload)

    async def drop_latest(self):
        if self._conns:
            _, close_event = self._conns[-1]
            close_event.set()

    async def stop(self):
        for _, close_event in self._conns:
            close_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()


# ---------------------------------------------------------------------------
# K1: data_processor must survive malformed / unexpected server messages
# ---------------------------------------------------------------------------

class TestDataProcessorRobustness(unittest.IsolatedAsyncioTestCase):
    async def _run_processor_with(self, *messages):
        """Feed messages into a live data_processor task; return (worker, task, ws)."""
        worker = KlipperWorker("127.0.0.1", 1)
        ws = FakeWebSocket()
        task = asyncio.create_task(worker.data_processor(ws))
        for msg in messages:
            await worker.message_queue.put(msg)
        # Give the processor time to consume everything.
        await asyncio.sleep(0.2)
        return worker, task, ws

    async def asyncTearDown(self):
        pass

    async def test_notify_gcode_response_missing_params_does_not_crash(self):
        worker, task, ws = await self._run_processor_with(
            {"method": "notify_gcode_response"},  # no "params" -> None[0]
            {"method": "printer.objects.query"},  # valid follow-up proves liveness
        )
        self.assertFalse(task.done(), "processor crashed on missing params")
        task.cancel()

    async def test_notify_gcode_response_empty_params_does_not_crash(self):
        worker, task, ws = await self._run_processor_with(
            {"method": "notify_gcode_response", "params": []},  # IndexError
            {"method": "printer.objects.query"},
        )
        self.assertFalse(task.done(), "processor crashed on empty params list")
        task.cancel()

    async def test_error_message_missing_fields_does_not_crash(self):
        worker, task, ws = await self._run_processor_with(
            {"error": {}},  # data["error"]["code"] -> KeyError
            {"method": "printer.objects.query"},
        )
        self.assertFalse(task.done(), "processor crashed on malformed error message")
        task.cancel()

    async def test_processor_still_processes_after_bad_message(self):
        """A valid query after a bad message must still be forwarded to the socket."""
        worker, task, ws = await self._run_processor_with(
            {"method": "notify_gcode_response"},   # bad
            {"method": "printer.objects.query"},   # good -> should be sent
        )
        self.assertFalse(task.done())
        self.assertTrue(
            any("printer.objects.query" in m for m in ws.sent),
            f"valid message after a bad one was not processed; sent={ws.sent}",
        )
        task.cancel()


# ---------------------------------------------------------------------------
# K3: exponential reconnect backoff (pure logic, no I/O)
# ---------------------------------------------------------------------------

class TestReconnectBackoff(unittest.TestCase):
    def test_delay_grows_exponentially_and_caps(self):
        worker = KlipperWorker(
            "h", 1, reconnect_base_delay=1.0, reconnect_max_delay=8.0
        )
        delays = [worker._next_reconnect_delay() for _ in range(6)]
        self.assertEqual(delays, [1.0, 2.0, 4.0, 8.0, 8.0, 8.0])

    def test_successful_connection_resets_backoff(self):
        worker = KlipperWorker(
            "h", 1, reconnect_base_delay=1.0, reconnect_max_delay=8.0
        )
        worker._next_reconnect_delay()
        worker._next_reconnect_delay()
        worker._reset_reconnect_backoff()
        self.assertEqual(worker._next_reconnect_delay(), 1.0)


# ---------------------------------------------------------------------------
# Integration: reconnect against a controllable mock Moonraker server
# ---------------------------------------------------------------------------

class TestKlipperReconnectIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ControllableMoonraker()
        await self.server.start()
        self.worker = KlipperWorker(
            self.server.host, self.server.port, query_delay=0.2,
            reconnect_base_delay=0.5, reconnect_max_delay=4.0,
        )
        self.run_task = asyncio.create_task(_raw_run(self.worker))

    async def asyncTearDown(self):
        self.worker.stop()
        self.run_task.cancel()
        try:
            await self.run_task
        except (asyncio.CancelledError, Exception):
            pass
        await self.server.stop()

    async def test_reconnect_after_drop(self):
        """A genuine connection drop must reconnect."""
        await self.server.wait_for_connection(1)
        await self.server.drop_latest()
        self.assertTrue(
            await self.server.reconnected_within(2, timeout=8.0),
            "client did not reconnect after a drop",
        )

    async def test_bad_server_message_does_not_trigger_reconnect(self):
        """A malformed server message must NOT recycle a healthy connection."""
        await self.server.wait_for_connection(1)
        # Messages that crash the unguarded data_processor.
        await self.server.send_raw({"method": "notify_gcode_response"})
        await self.server.send_raw({"error": {}})
        reconnected = await self.server.reconnected_within(2, timeout=5.0)
        self.assertFalse(
            reconnected,
            "malformed server message wrongly triggered a reconnect",
        )

    async def test_multiple_reconnects_keep_working(self):
        for cycle in range(3):
            await self.server.wait_for_connection(cycle + 1, timeout=8.0)
            await self.server.drop_latest()
        # A 4th connection proves it kept recovering.
        self.assertTrue(
            await self.server.reconnected_within(4, timeout=8.0),
            "client stopped reconnecting after repeated drops",
        )


# ---------------------------------------------------------------------------
# K2: query_task must not leak when stop() is called
# ---------------------------------------------------------------------------

class TestQueryTaskLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ControllableMoonraker()
        await self.server.start()
        self.worker = KlipperWorker(
            self.server.host, self.server.port, query_delay=0.2,
            reconnect_base_delay=0.5, reconnect_max_delay=4.0,
        )
        self.run_task = asyncio.create_task(_raw_run(self.worker))

    async def asyncTearDown(self):
        self.run_task.cancel()
        try:
            await self.run_task
        except (asyncio.CancelledError, Exception):
            pass
        await self.server.stop()

    async def test_stop_cancels_query_task(self):
        await self.server.wait_for_connection(1)
        # Let query_task spin up.
        await asyncio.sleep(0.3)
        self.assertIsNotNone(self.worker.query_task, "query_task never started")

        self.worker.stop()
        await asyncio.sleep(0.5)

        qt = self.worker.query_task
        self.assertTrue(
            qt is None or qt.done(),
            "query_task leaked: still running after stop()",
        )


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

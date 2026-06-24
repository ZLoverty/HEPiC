#!/usr/bin/env python3
"""
Test: ConnectionTester self-test gating.

Behavior under test (after refactor):
  - Proceeding to the home page requires only that the data port, the
    Moonraker service, AND the Klipper service are present.
  - The Klipper printer state (ready / startup / shutdown / error) must NOT
    gate success — the home page has a restart button. Only a *disconnected*
    Klipper service (klippy_connected == False) fails the check.

Usage:
    python test/test_connection_tester.py
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A QCoreApplication makes Qt signal emit/connect robust outside a GUI loop.
from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QCoreApplication([])

from HEPiC.communications.connection_tester import ConnectionTester


def _raw_run(tester: ConnectionTester):
    """Return the run() coroutine, bypassing the @asyncSlot wrapper."""
    return ConnectionTester.run.__wrapped__(tester)


class _Recorder:
    def __init__(self, tester: ConnectionTester):
        self.messages: list[str] = []
        self.succeeded = False
        self.failed = False
        tester.test_msg.connect(self.messages.append)
        tester.success.connect(self._on_success)
        tester.fail.connect(self._on_fail)

    def _on_success(self):
        self.succeeded = True

    def _on_fail(self):
        self.failed = True


class TestConnectionTester(unittest.IsolatedAsyncioTestCase):
    def _make(self, *, ping=True, port=True, server=None, test_mode=False):
        if server is None:
            server = (True, {"klippy_connected": True, "klippy_state": "ready"})
        tester = ConnectionTester("127.0.0.1", 10001, test_mode=test_mode)
        tester._is_host_reachable_async = AsyncMock(return_value=ping)
        tester._check_tcp_port_async = AsyncMock(return_value=port)
        tester._get_server_info = AsyncMock(return_value=server)
        return tester

    async def test_success_when_services_present_and_printer_ready(self):
        tester = self._make()
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertTrue(rec.succeeded)
        self.assertFalse(rec.failed)

    async def test_success_regardless_of_printer_state(self):
        """Not-ready states must NOT block jumping to the home page."""
        for state in ("startup", "shutdown", "error", "printing", "标准未知值"):
            with self.subTest(state=state):
                tester = self._make(
                    server=(True, {"klippy_connected": True, "klippy_state": state})
                )
                rec = _Recorder(tester)
                await _raw_run(tester)
                self.assertTrue(rec.succeeded, f"state={state} should still succeed")
                self.assertFalse(rec.failed, f"state={state} should not fail")

    async def test_fail_when_klippy_not_connected(self):
        tester = self._make(
            server=(True, {"klippy_connected": False, "klippy_state": "disconnected"})
        )
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertFalse(rec.succeeded)
        self.assertTrue(rec.failed)

    async def test_fail_when_moonraker_down(self):
        tester = self._make(server=(False, {}))
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertFalse(rec.succeeded)
        self.assertTrue(rec.failed)
        # Klipper check must not even run if Moonraker is down.

    async def test_fail_when_ping_fails(self):
        tester = self._make(ping=False)
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertFalse(rec.succeeded)
        self.assertTrue(rec.failed)
        tester._check_tcp_port_async.assert_not_called()

    async def test_fail_when_data_port_closed(self):
        tester = self._make(port=False)
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertFalse(rec.succeeded)
        self.assertTrue(rec.failed)
        tester._get_server_info.assert_not_called()

    async def test_test_mode_skips_moonraker_and_klipper(self):
        tester = self._make(test_mode=True)
        rec = _Recorder(tester)
        await _raw_run(tester)
        self.assertTrue(rec.succeeded)
        self.assertFalse(rec.failed)
        tester._get_server_info.assert_not_called()


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

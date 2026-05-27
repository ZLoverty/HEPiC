import asyncio
import pytest
from HEPiC.communications.klipper_worker import KlipperWorker


def test_sigKlipperState_exists(qapp):
    worker = KlipperWorker("localhost", 7125)
    # Signal 必须存在且可连接
    received = []
    worker.sigKlipperState.connect(lambda s, m: received.append((s, m)))
    worker.sigKlipperState.emit("ready", "")
    assert received == [("ready", "")]


def test_webhooks_in_query_objects(qapp):
    worker = KlipperWorker("localhost", 7125)
    # query_klipper 的查询对象必须包含 webhooks
    import inspect, ast
    src = inspect.getsource(worker.query_klipper)
    assert '"webhooks"' in src or "'webhooks'" in src


@pytest.mark.asyncio
async def test_printer_restart_enqueues_correct_message(qapp):
    worker = KlipperWorker("localhost", 7125)
    while not worker.message_queue.empty():
        worker.message_queue.get_nowait()

    # asyncSlot 返回 Task（asyncio.ensure_future），直接 await
    await worker.printer_restart()

    msg = worker.message_queue.get_nowait()
    assert msg["method"] == "printer.restart"
    assert msg["jsonrpc"] == "2.0"

import pytest
from PySide6.QtCore import Signal, QObject, Qt
from HEPiC.tab_widgets.klipper_status_widget import KlipperStatusWidget


def test_initial_state_buttons_disabled(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    assert not w._firmware_btn.isEnabled()
    assert not w._klipper_btn.isEnabled()


def test_initial_toggle_btn_hidden(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    assert not w._toggle_btn.isVisible()
    assert not w._detail_label.isVisible()


def test_on_state_changed_ready(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.on_state_changed("ready", "")
    assert w._state_label.text() == "ready"
    assert not w._toggle_btn.isVisible()


def test_on_state_changed_error_shows_toggle(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.show()
    w.on_state_changed("error", "MCU shutdown: Timer too close")
    assert w._state_label.text() == "error"
    assert w._toggle_btn.isVisible()
    assert w._detail_label.text() == "MCU shutdown: Timer too close"
    assert not w._detail_label.isVisible()  # 折叠，默认不展开


def test_toggle_expands_and_collapses(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.show()
    w.on_state_changed("error", "some error")
    assert not w._detail_label.isVisible()
    qtbot.mouseClick(w._toggle_btn, Qt.LeftButton)
    assert w._detail_label.isVisible()
    qtbot.mouseClick(w._toggle_btn, Qt.LeftButton)
    assert not w._detail_label.isVisible()


class _MockWorker(QObject):
    sigKlipperState = Signal(str, str)
    def restart_firmware(self): pass
    def printer_restart(self): pass


def test_connect_worker_enables_buttons(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    mock_worker = _MockWorker()
    w.connect_worker(mock_worker)
    assert w._firmware_btn.isEnabled()
    assert w._klipper_btn.isEnabled()


def test_connect_worker_receives_state(qtbot):
    w = KlipperStatusWidget()
    qtbot.addWidget(w)
    w.show()
    mock_worker = _MockWorker()
    w.connect_worker(mock_worker)
    mock_worker.sigKlipperState.emit("shutdown", "Printer shutdown")
    assert w._state_label.text() == "shutdown"
    assert w._toggle_btn.isVisible()

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Slot

_STATE_COLORS = {
    "ready":    "#4CAF50",
    "startup":  "#FF9800",
    "shutdown": "#9E9E9E",
    "error":    "#F44336",
}


class KlipperStatusWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #9E9E9E; font-size: 16px;")

        self._state_label = QLabel("未连接")

        self._toggle_btn = QPushButton("▼ 详情")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setVisible(False)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self._dot)
        status_row.addWidget(self._state_label)
        status_row.addStretch()
        status_row.addWidget(self._toggle_btn)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setVisible(False)

        self._firmware_btn = QPushButton("固件重启")
        self._firmware_btn.setEnabled(False)
        self._klipper_btn = QPushButton("Klipper 重启")
        self._klipper_btn.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self._firmware_btn)
        btn_row.addWidget(self._klipper_btn)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(status_row)
        layout.addWidget(self._detail_label)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self._toggle_btn.clicked.connect(self._toggle_detail)
        self.setVisible(False)

    def connect_worker(self, worker):
        worker.sigKlipperState.connect(self.on_state_changed)
        self._firmware_btn.clicked.connect(worker.restart_firmware)
        self._klipper_btn.clicked.connect(worker.printer_restart)
        self._firmware_btn.setEnabled(True)
        self._klipper_btn.setEnabled(True)

    @Slot(str, str)
    def on_state_changed(self, state: str, message: str):
        color = _STATE_COLORS.get(state, "#9E9E9E")
        self._dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self._state_label.setText(state)
        self._detail_label.setText(message)
        has_message = bool(message.strip())
        self._toggle_btn.setVisible(has_message)
        if not has_message:
            self._detail_label.setVisible(False)
            self._toggle_btn.setText("▼ 详情")
        self.setVisible(state != "ready")

    def _toggle_detail(self):
        visible = not self._detail_label.isVisible()
        self._detail_label.setVisible(visible)
        self._toggle_btn.setText("▲ 详情" if visible else "▼ 详情")

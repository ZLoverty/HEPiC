"""Settings dialog for editing config.json values from within the GUI."""

import re

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QDialogButtonBox, QColorDialog,
    QFileDialog, QLabel, QScrollArea, QWidget,
)
from PySide6.QtGui import QColor

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class SettingsDialog(QDialog):
    """Generic editor for the app's config.json contents.

    Builds one form row per config key, using a widget type inferred from
    the value: a color picker for hex-color strings, spin boxes for
    numbers, a folder browser for path-like keys, plain text otherwise.
    """

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(480, 560)

        self._fields = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QFormLayout(form_container)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll.setWidget(form_container)

        for key, value in config.items():
            form_layout.addRow(key, self._build_row(key, value))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        note = QLabel("修改部分设置（如通信端口、采样频率）需要重启程序后生效。")
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _build_row(self, key: str, value) -> QWidget:
        if isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
            self._fields[key] = ("bool", widget)
            return widget

        if isinstance(value, str) and _COLOR_RE.match(value):
            return self._build_color_row(key, value)

        if isinstance(value, int):
            widget = QSpinBox()
            widget.setRange(-2_147_483_648, 2_147_483_647)
            widget.setValue(value)
            self._fields[key] = ("int", widget)
            return widget

        if isinstance(value, float):
            widget = QDoubleSpinBox()
            widget.setRange(-1_000_000_000.0, 1_000_000_000.0)
            widget.setDecimals(4)
            widget.setValue(value)
            self._fields[key] = ("float", widget)
            return widget

        if any(hint in key.lower() for hint in ("directory", "folder")):
            return self._build_path_row(key, str(value))

        widget = QLineEdit(str(value))
        self._fields[key] = ("str", widget)
        return widget

    def _build_color_row(self, key: str, value: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit(value)
        swatch = QPushButton()
        swatch.setFixedSize(28, 24)
        self._update_swatch(swatch, value)

        def pick_color():
            color = QColorDialog.getColor(QColor(line_edit.text()), self, "选择颜色")
            if color.isValid():
                line_edit.setText(color.name())

        line_edit.textChanged.connect(lambda text: self._update_swatch(swatch, text))
        swatch.clicked.connect(pick_color)

        row.addWidget(line_edit)
        row.addWidget(swatch)
        self._fields[key] = ("str", line_edit)
        return container

    @staticmethod
    def _update_swatch(button: QPushButton, color_text: str):
        color = QColor(color_text)
        if color.isValid():
            button.setStyleSheet(f"background-color: {color_text}; border: 1px solid #888;")

    def _build_path_row(self, key: str, value: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit(value)
        browse = QPushButton("浏览...")

        def choose():
            chosen = QFileDialog.getExistingDirectory(self, "选择路径", line_edit.text())
            if chosen:
                line_edit.setText(chosen)

        browse.clicked.connect(choose)
        row.addWidget(line_edit)
        row.addWidget(browse)
        self._fields[key] = ("str", line_edit)
        return container

    def get_values(self) -> dict:
        values = {}
        for key, (kind, widget) in self._fields.items():
            if kind == "bool":
                values[key] = widget.isChecked()
            elif kind in ("int", "float"):
                values[key] = widget.value()
            else:
                values[key] = widget.text()
        return values

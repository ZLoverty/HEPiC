import logging
from collections import deque
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StatusIndicator(QFrame):
    """Simple circular status indicator."""

    def __init__(self, size=60):
        super().__init__()
        self._size = size
        self.status = "unknown"
        self.setFixedSize(size, size)
        self.update_status("unknown")

    def update_status(self, status: str):
        self.status = status
        colors = {
            "unknown": "#888888",
            "stable": "#27ae60",
            "warning": "#f39c12",
            "unstable": "#e74c3c",
        }
        color = colors.get(status, "#888888")
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {color};
                border-radius: {self._size // 2}px;
                border: 2px solid white;
            }}
            """
        )


class QualityCheckWidget(QWidget):
    """质检模式页。"""

    quality_check_started = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.extrusion_force_cache = deque(maxlen=300)
        self.time_cache = deque(maxlen=300)
        self.current_time = 0
        self.is_checking = False
        self.default_stability_threshold = 0.1
        self.material_properties_initialized = False

        self.material_properties = {
            "PLA": {
                "expected_force": 5.0,
                "force_range": (3.0, 7.0),
                "temperature": 200,
                "speed": 30,
                "stability_threshold": 0.1,
            },
            "PETG": {
                "expected_force": 6.0,
                "force_range": (4.0, 8.0),
                "temperature": 230,
                "speed": 25,
                "stability_threshold": 0.1,
            },
            "TPU": {
                "expected_force": 3.0,
                "force_range": (1.5, 4.5),
                "temperature": 210,
                "speed": 20,
                "stability_threshold": 0.1,
            },
        }

        self.process_markdown = self._load_process_document()
        self.init_ui()

        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.on_data_update_timeout)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.material_properties_initialized:
            self.logger.info("QualityCheckWidget first shown, initializing material properties")
            QTimer.singleShot(50, self._delayed_init_material_properties)
            self.material_properties_initialized = True

    def _delayed_init_material_properties(self):
        try:
            from ..database import get_material_database

            material_db = get_material_database()
            self.set_material_properties(material_db.get_all_materials())
            self.logger.info("Material properties initialized from database")
        except Exception as exc:
            self.logger.error(f"Failed to initialize material properties: {exc}")

    def _load_process_document(self) -> str:
        doc_path = Path(__file__).parent.parent / "database" / "quality_check_process.md"
        try:
            if doc_path.exists():
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.logger.info(f"Loaded quality check process document from {doc_path}")
                return content
        except Exception as exc:
            self.logger.error(f"Failed to load quality check process document: {exc}")
        return self._get_default_process_content()

    def _get_default_process_content(self) -> str:
        return """
# 质检流程

1. 选择材料
2. 点击开始质检
3. 观察稳定性指示器和实时挤出力曲线
4. 停止质检
"""

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.create_left_panel())
        main_layout.addWidget(self.create_right_panel())
        self.setLayout(main_layout)
        self.update_material_properties_display()

    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()

        self.instruction_text = QTextEdit()
        self.instruction_text.setReadOnly(True)
        self.instruction_text.setMarkdown(self.process_markdown)
        layout.addWidget(self.instruction_text)

        panel.setLayout(layout)
        panel.setMaximumWidth(350)
        return panel

    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()

        control_row = QHBoxLayout()
        material_label = QLabel("材料选择:")
        self.material_combo = QComboBox()
        self.material_combo.addItems(list(self.material_properties.keys()))
        self.material_combo.currentTextChanged.connect(self.update_material_properties_display)
        control_row.addWidget(material_label)
        control_row.addWidget(self.material_combo)

        self.check_button = QPushButton("开始质检")
        self.check_button.clicked.connect(self.on_quality_check_clicked)
        control_row.addWidget(self.check_button)

        stability_label = QLabel("稳定性:")
        self.status_indicator = StatusIndicator(size=50)
        self.std_dev_label = QLabel("均值±标准差: -- N")
        self.std_dev_label.setStyleSheet("font-weight: bold;")
        control_row.addWidget(stability_label)
        control_row.addWidget(self.status_indicator)
        control_row.addWidget(self.std_dev_label)
        control_row.addStretch()
        layout.addLayout(control_row)

        properties_row = QHBoxLayout()
        properties_label = QLabel("预期属性:")
        properties_label.setStyleSheet("font-weight: bold;")
        self.expected_force_label = QLabel("预期挤出力: -- N")
        self.force_range_label = QLabel("力值范围: -- N")
        self.temperature_label = QLabel("温度: -- °C")
        self.speed_label = QLabel("速度: -- mm/s")
        self.stability_threshold_label = QLabel("稳定阈值: -- N")
        properties_row.addWidget(properties_label)
        properties_row.addWidget(self.temperature_label)
        properties_row.addWidget(self.speed_label)
        properties_row.addWidget(self.expected_force_label)
        properties_row.addWidget(self.force_range_label)
        properties_row.addWidget(self.stability_threshold_label)
        properties_row.addStretch()
        layout.addLayout(properties_row)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Extrusion Force", units="N")
        self.plot_widget.setTitle("实时挤出力数据")
        self.plot_widget.addLegend()
        self.force_curve = self.plot_widget.plot(
            pen=pg.mkPen("#2980b9", width=2),
            name="Extrusion Force (N)",
        )
        self.expected_upper = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine),
            label="预期上限",
        )
        self.expected_lower = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine),
            label="预期下限",
        )
        self.plot_widget.addItem(self.expected_upper)
        self.plot_widget.addItem(self.expected_lower)
        layout.addWidget(self.plot_widget, 1)

        panel.setLayout(layout)
        return panel

    def update_material_properties_display(self):
        material = self.material_combo.currentText()
        props = self.material_properties.get(material, {})
        self.expected_force_label.setText(f"预期挤出力: {props.get('expected_force', '--')} N")
        force_min, force_max = props.get("force_range", ("--", "--"))
        self.force_range_label.setText(f"力值范围: {force_min} - {force_max} N")
        self.temperature_label.setText(f"温度: {props.get('temperature', '--')} °C")
        self.speed_label.setText(f"速度: {props.get('speed', '--')} mm/s")
        stability_threshold = props.get("stability_threshold", self.default_stability_threshold)
        self.stability_threshold_label.setText(f"稳定阈值: {stability_threshold} N")
        force_range = props.get("force_range", (0, 0))
        self.expected_upper.setPos(force_range[1])
        self.expected_lower.setPos(force_range[0])

    @Slot()
    def on_quality_check_clicked(self):
        if not self.is_checking:
            self.is_checking = True
            self.check_button.setText("停止质检")
            self.check_button.setStyleSheet("background-color: #e74c3c; color: white;")
            self.extrusion_force_cache.clear()
            self.time_cache.clear()
            self.current_time = 0
            self.update_material_properties_display()
            material = self.material_combo.currentText()
            self.quality_check_started.emit(material)
            self.data_timer.start(100)
            self.logger.info(f"Quality check started for material: {material}")
        else:
            self.is_checking = False
            self.check_button.setText("开始质检")
            self.check_button.setStyleSheet("")
            self.data_timer.stop()
            self.status_indicator.update_status("unknown")
            self.logger.info("Quality check stopped")

    @Slot()
    def on_data_update_timeout(self):
        pass

    @Slot(dict)
    def update_sensor_data(self, data: dict):
        if not self.is_checking:
            return

        time_data = data.get("time_s", [])
        force_data = data.get("extrusion_force_N", [])
        if not time_data or not force_data:
            return

        latest_time = time_data[-1]
        latest_force = force_data[-1]
        self.time_cache.append(latest_time)
        self.extrusion_force_cache.append(latest_force)

        if len(self.extrusion_force_cache) == 1:
            self.logger.info(
                f"Quality check started - receiving extrusion_force_N data: {latest_force} N"
            )

        self.update_plot()
        self.update_stability_indicator()

    def update_plot(self):
        if len(self.time_cache) > 0:
            self.force_curve.setData(list(self.time_cache), list(self.extrusion_force_cache))

    def update_stability_indicator(self):
        if len(self.extrusion_force_cache) < 10:
            self.status_indicator.update_status("unknown")
            self.std_dev_label.setText("均值±标准差: -- N")
            return

        recent_data = list(self.extrusion_force_cache)[-20:]
        mean = np.mean(recent_data)
        std = np.std(recent_data)
        stability_threshold = self.get_current_stability_threshold()

        self.std_dev_label.setText(f"挤出力: {mean:.2f}±{std:.3f} N")

        if std < stability_threshold:
            self.status_indicator.update_status("stable")
        elif std < stability_threshold * 2:
            self.status_indicator.update_status("warning")
        else:
            self.status_indicator.update_status("unstable")

    def get_current_stability_threshold(self) -> float:
        material = self.material_combo.currentText() if hasattr(self, "material_combo") else ""
        props = self.material_properties.get(material, {})
        return props.get("stability_threshold", self.default_stability_threshold)

    def set_material_properties(self, properties: dict):
        self.logger.info(f"Setting material properties: {list(properties.keys())}")
        self.material_properties.update(properties)
        QTimer.singleShot(10, self._update_material_combo_box)

    def _update_material_combo_box(self):
        try:
            if hasattr(self, "material_combo") and self.material_combo is not None:
                current_material = self.material_combo.currentText()
                self.material_combo.clear()
                self.material_combo.addItems(list(self.material_properties.keys()))
                if current_material and current_material in self.material_properties:
                    index = self.material_combo.findText(current_material)
                    if index >= 0:
                        self.material_combo.setCurrentIndex(index)
                self.update_material_properties_display()
        except RuntimeError as exc:
            self.logger.error(f"Error updating material combo box: {exc}")
        except Exception as exc:
            self.logger.error(f"Unexpected error updating material combo box: {exc}")

import logging
from collections import deque
from copy import deepcopy
from pathlib import Path

import numpy as np
import pyqtgraph as pg

from ..quality_check import (
    DEFAULT_MATERIAL_FAMILIES,
    build_quality_check_gcode,
    evaluate_force_window,
)
from ..quality_check.evaluator import (
    DEFAULT_STABILITY_THRESHOLD,
    get_excellent_force_range,
    get_force_range,
    get_stability_threshold,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StatusIndicator(QFrame):
    """Circular status indicator."""

    def __init__(self, size=32):
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


class StabilityBarIndicator(QFrame):
    """Rounded bar indicator for stability."""

    def __init__(self, width=52, height=32):
        super().__init__()
        self._width = width
        self._height = height
        self.status = "unknown"
        self.setFixedSize(width, height)
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
                border-radius: {self._height // 3}px;
                border: 2px solid white;
            }}
            """
        )


class QualityCheckWidget(QWidget):
    """Quality check page."""

    quality_check_started = Signal(str)
    quality_check_gcode_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.extrusion_force_cache = deque(maxlen=300)
        self.time_cache = deque(maxlen=300)
        self.current_time = 0
        self.is_checking = False
        self.default_stability_threshold = DEFAULT_STABILITY_THRESHOLD
        self.material_properties_initialized = False
        self.material_families = deepcopy(DEFAULT_MATERIAL_FAMILIES)

        self._extrusion_duration_s = 0.0
        self._progress_elapsed_ms = 0

        self.process_markdown = self._load_process_document()
        self.init_ui()

        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.on_data_update_timeout)

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._tick_extrusion_progress)

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
            self.set_material_families(material_db.get_material_families())
            self.logger.info("Material properties initialized from database")
        except Exception as exc:
            self.logger.error(f"Failed to initialize material properties: {exc}")

    def _load_process_document(self) -> str:
        doc_path = Path(__file__).parent.parent / "database" / "quality_check_process.md"
        try:
            if doc_path.exists():
                with open(doc_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as exc:
            self.logger.error(f"Failed to load quality check process document: {exc}")
        return self._get_default_process_content()

    def _get_default_process_content(self) -> str:
        return """
# 质检流程

1. 选择材料 family
2. 选择 PI_Code
3. 点击开始质检
4. 观察系统状态、稳定性和实时挤出力曲线
5. 停止质检
"""

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.create_left_panel())
        main_layout.addWidget(self.create_right_panel(), 1)
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

    def _make_info_block(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        block = QFrame()
        block.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        block.setLayout(layout)
        return block, layout

    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()

        info_row = QHBoxLayout()

        material_block, material_layout = self._make_info_block("材料信息")

        family_selector_row = QHBoxLayout()
        family_selector_row.addWidget(QLabel("Family:"))
        self.material_family_combo = QComboBox()
        self.material_family_combo.addItems(list(self.material_families.keys()))
        self.material_family_combo.currentTextChanged.connect(self.on_material_family_changed)
        family_selector_row.addWidget(self.material_family_combo)
        material_layout.addLayout(family_selector_row)

        pi_code_selector_row = QHBoxLayout()
        pi_code_selector_row.addWidget(QLabel("PI_Code:"))
        self.material_combo = QComboBox()
        self.material_combo.currentTextChanged.connect(self.update_material_properties_display)
        pi_code_selector_row.addWidget(self.material_combo)
        material_layout.addLayout(pi_code_selector_row)

        self.temperature_label = QLabel("温度: -- °C")
        self.speed_label = QLabel("速度: -- mm/s")
        self.expected_force_label = QLabel("预期挤出力: -- N")
        self.excellent_force_range_label = QLabel("优秀范围: -- N")
        self.force_range_label = QLabel("合格范围: -- N")
        self.stability_threshold_label = QLabel("稳定阈值: -- N")
        material_layout.addWidget(self.temperature_label)
        material_layout.addWidget(self.speed_label)
        material_layout.addWidget(self.expected_force_label)
        material_layout.addWidget(self.excellent_force_range_label)
        material_layout.addWidget(self.force_range_label)
        material_layout.addWidget(self.stability_threshold_label)
        material_layout.addStretch()
        info_row.addWidget(material_block, 2)

        system_block, system_layout = self._make_info_block("系统信息")
        self.system_temperature_label = QLabel("实时温度: -- °C")
        self.system_feedrate_label = QLabel("实时挤出速度: -- mm/s")
        self.system_force_label = QLabel("实时挤出力: -- N")
        system_layout.addWidget(self.system_temperature_label)
        system_layout.addWidget(self.system_feedrate_label)
        system_layout.addWidget(self.system_force_label)
        self.extrusion_progress_bar = QProgressBar()
        self.extrusion_progress_bar.setRange(0, 100)
        self.extrusion_progress_bar.setValue(0)
        self.extrusion_progress_bar.setFormat("挤出进度: %p%")
        self.extrusion_progress_bar.setTextVisible(True)
        system_layout.addWidget(self.extrusion_progress_bar)
        system_layout.addStretch()
        info_row.addWidget(system_block, 2)

        action_block, action_layout = self._make_info_block("质检操作")
        self.check_button = QPushButton("开始质检")
        self.check_button.clicked.connect(self.on_quality_check_clicked)
        self.check_button.setMinimumHeight(56)
        self.force_expectation_indicator = StatusIndicator(size=40)
        self.status_indicator = StabilityBarIndicator(width=48, height=36)
        action_layout.addWidget(self.check_button)
        action_layout.addWidget(QLabel("挤出力 | 稳定性"))
        indicator_row = QHBoxLayout()
        indicator_row.addWidget(self.force_expectation_indicator)
        indicator_row.addWidget(self.status_indicator)
        indicator_row.addStretch()
        action_layout.addLayout(indicator_row)
        action_layout.addStretch()
        info_row.addWidget(action_block, 1)

        layout.addLayout(info_row)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Extrusion Force", units="N")
        self.plot_widget.setTitle("实时挤出力数据")
        self.plot_widget.addLegend()
        self.force_curve = self.plot_widget.plot(
            pen=pg.mkPen("#2980b9", width=2),
            name="Extrusion Force (N)",
        )
        self.qualified_band = pg.LinearRegionItem(
            values=(0, 0),
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(241, 196, 15, 35),
            pen=pg.mkPen(None),
        )
        self.qualified_band.setZValue(-20)
        self.excellent_band = pg.LinearRegionItem(
            values=(0, 0),
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(39, 174, 96, 45),
            pen=pg.mkPen(None),
        )
        self.excellent_band.setZValue(-10)
        self.excellent_upper = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine)
        )
        self.excellent_lower = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine)
        )
        self.qualified_upper = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#f1c40f", width=1, style=Qt.PenStyle.DashLine)
        )
        self.qualified_lower = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#f1c40f", width=1, style=Qt.PenStyle.DashLine)
        )
        self.plot_widget.addItem(self.qualified_band)
        self.plot_widget.addItem(self.excellent_band)
        self.plot_widget.addItem(self.excellent_upper)
        self.plot_widget.addItem(self.excellent_lower)
        self.plot_widget.addItem(self.qualified_upper)
        self.plot_widget.addItem(self.qualified_lower)
        layout.addWidget(self.plot_widget, 1)

        panel.setLayout(layout)
        self._populate_pi_code_combo_box(self.get_current_family())
        return panel

    @Slot(str)
    def on_material_family_changed(self, family: str):
        self._populate_pi_code_combo_box(family)
        self.update_material_properties_display()

    def _populate_pi_code_combo_box(self, family: str, preferred_pi_code: str | None = None):
        pi_codes = list(self.material_families.get(family, {}).keys())
        self.material_combo.blockSignals(True)
        self.material_combo.clear()
        self.material_combo.addItems(pi_codes)
        target_pi_code = preferred_pi_code if preferred_pi_code in pi_codes else None
        if target_pi_code:
            index = self.material_combo.findText(target_pi_code)
            if index >= 0:
                self.material_combo.setCurrentIndex(index)
        self.material_combo.blockSignals(False)

    def get_current_family(self) -> str:
        if hasattr(self, "material_family_combo") and self.material_family_combo is not None:
            return self.material_family_combo.currentText()
        return ""

    def get_current_pi_code(self) -> str:
        if hasattr(self, "material_combo") and self.material_combo is not None:
            return self.material_combo.currentText()
        return ""

    def get_current_material_properties(self, pi_code: str | None = None) -> dict:
        family = self.get_current_family()
        selected_pi_code = pi_code or self.get_current_pi_code()
        return self.material_families.get(family, {}).get(selected_pi_code, {})

    def update_material_properties_display(self):
        props = self.get_current_material_properties()
        self.temperature_label.setText(f"温度: {props.get('temperature', '--')} °C")
        self.speed_label.setText(f"速度: {props.get('speed', '--')} mm/s")
        self.expected_force_label.setText(f"预期挤出力: {props.get('expected_force', '--')} N")
        excellent_force_min, excellent_force_max = props.get("excellent_force_range", ("--", "--"))
        self.excellent_force_range_label.setText(
            f"优秀范围: {excellent_force_min} - {excellent_force_max} N"
        )
        force_min, force_max = props.get("force_range", ("--", "--"))
        self.force_range_label.setText(f"力值范围: {force_min} - {force_max} N")
        stability_threshold = props.get("stability_threshold", self.default_stability_threshold)
        self.stability_threshold_label.setText(f"稳定阈值: {stability_threshold} N")
        excellent_force_range = props.get("excellent_force_range", (0, 0))
        force_range = props.get("force_range", (0, 0))
        self.excellent_band.setRegion(excellent_force_range)
        self.qualified_band.setRegion(force_range)
        self.excellent_upper.setPos(excellent_force_range[1])
        self.excellent_lower.setPos(excellent_force_range[0])
        self.qualified_upper.setPos(force_range[1])
        self.qualified_lower.setPos(force_range[0])

    @Slot()
    def on_quality_check_clicked(self):
        if not self.is_checking:
            self.is_checking = True
            self.check_button.setText("停止质检")
            self.check_button.setStyleSheet("background-color: #e74c3c; color: white;")
            self.extrusion_force_cache.clear()
            self.time_cache.clear()
            self.current_time = 0
            self.system_force_label.setText("实时挤出力: -- N")
            self.force_expectation_indicator.update_status("unknown")
            self.status_indicator.update_status("unknown")
            self.update_material_properties_display()

            pi_code = self.get_current_pi_code()
            self.quality_check_started.emit(pi_code)
            self.quality_check_gcode_requested.emit(
                build_quality_check_gcode(self.get_current_material_properties(pi_code))
            )
            self.data_timer.start(100)
            self.logger.info(
                "Quality check started for material: %s/%s",
                self.get_current_family(),
                pi_code,
            )
        else:
            self.is_checking = False
            self.check_button.setText("开始质检")
            self.check_button.setStyleSheet("")
            self.data_timer.stop()
            self._progress_timer.stop()
            self.extrusion_progress_bar.setValue(0)
            self.status_indicator.update_status("unknown")
            self.force_expectation_indicator.update_status("unknown")
            self.logger.info("Quality check stopped")

    def start_extrusion_progress(self):
        """Start the extrusion progress bar based on current material properties."""
        props = self.get_current_material_properties()
        speed = float(props.get("speed", 5))
        extrude_length = float(props.get("quality_check_extrude_length_mm", speed * 60.0))
        self._extrusion_duration_s = extrude_length / speed if speed > 0 else 60.0
        self._progress_elapsed_ms = 0
        self.extrusion_progress_bar.setValue(0)
        self._progress_timer.start()
        self.logger.info("Extrusion progress started, expected duration: %.1f s", self._extrusion_duration_s)

    def _tick_extrusion_progress(self):
        self._progress_elapsed_ms += 100
        if self._extrusion_duration_s > 0:
            pct = min(int(self._progress_elapsed_ms / (self._extrusion_duration_s * 1000) * 100), 100)
            self.extrusion_progress_bar.setValue(pct)
        if self._progress_elapsed_ms >= self._extrusion_duration_s * 1000:
            self._progress_timer.stop()

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

    @Slot(dict)
    def update_klipper_status(self, data: dict):
        temperature = data.get("measured_temperature_C", np.nan)
        feedrate = data.get("feedrate_mms", np.nan)

        if np.isnan(temperature):
            self.system_temperature_label.setText("实时温度: -- °C")
        else:
            self.system_temperature_label.setText(f"实时温度: {temperature:.1f} °C")

        if np.isnan(feedrate):
            self.system_feedrate_label.setText("实时挤出速度: -- mm/s")
        else:
            self.system_feedrate_label.setText(f"实时挤出速度: {feedrate:.1f} mm/s")

    def update_plot(self):
        if len(self.time_cache) > 0:
            self.force_curve.setData(list(self.time_cache), list(self.extrusion_force_cache))

    def update_stability_indicator(self):
        evaluation = evaluate_force_window(
            list(self.extrusion_force_cache),
            self.get_current_material_properties(),
        )
        if evaluation is None:
            self.status_indicator.update_status("unknown")
            self.system_force_label.setText("实时挤出力: -- N")
            self.force_expectation_indicator.update_status("unknown")
            return

        self.system_force_label.setText(
            f"实时挤出力: {evaluation.mean:.2f} ± {evaluation.std:.2f} N"
        )
        self.status_indicator.update_status(evaluation.stability_status)
        self.force_expectation_indicator.update_status(evaluation.force_status)

    def get_current_stability_threshold(self) -> float:
        return get_stability_threshold(self.get_current_material_properties())

    def get_current_force_range(self) -> tuple[float, float]:
        return get_force_range(self.get_current_material_properties())

    def get_current_excellent_force_range(self) -> tuple[float, float]:
        return get_excellent_force_range(self.get_current_material_properties())

    def set_material_families(self, families: dict):
        self.logger.info(f"Setting material families: {list(families.keys())}")
        self.material_families = families or {}
        QTimer.singleShot(10, self._update_material_combo_box)

    def _update_material_combo_box(self):
        try:
            if (
                hasattr(self, "material_family_combo")
                and self.material_family_combo is not None
                and hasattr(self, "material_combo")
                and self.material_combo is not None
            ):
                current_family = self.get_current_family()
                current_pi_code = self.get_current_pi_code()

                self.material_family_combo.blockSignals(True)
                self.material_family_combo.clear()
                self.material_family_combo.addItems(list(self.material_families.keys()))
                if current_family and current_family in self.material_families:
                    index = self.material_family_combo.findText(current_family)
                    if index >= 0:
                        self.material_family_combo.setCurrentIndex(index)
                self.material_family_combo.blockSignals(False)

                selected_family = self.get_current_family() or self.material_family_combo.currentText()
                self._populate_pi_code_combo_box(selected_family, current_pi_code)
                self.update_material_properties_display()
        except RuntimeError as exc:
            self.logger.error(f"Error updating material combo box: {exc}")
        except Exception as exc:
            self.logger.error(f"Unexpected error updating material combo box: {exc}")

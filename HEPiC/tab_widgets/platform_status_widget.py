from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PlatformStatusWidget(QWidget):
    set_temperature = Signal(float)
    zero_sensor = Signal(str)

    def __init__(self, placeholder: str = "***", icon_path: str = "icons"):
        super().__init__()

        current_file_path = Path(__file__).resolve()
        icon_path = current_file_path.parent / icon_path
        self.zero_icon = QIcon(str(icon_path / "toZero.png"))
        self.placeholder = placeholder

        self.hotend_temperature_label = QLabel("温度:")
        self.hotend_temperature_value = QLabel(f"{placeholder:5s} /")
        self.hotend_temperature_input = QLineEdit("")
        self.hotend_temperature_input.setMaximumWidth(60)

        self.feedrate_label = QLabel("进线速度:")
        self.measured_feedrate_value = QLabel(f"{placeholder}/")
        self.feedrate_value = QLabel(f"{placeholder} mm/s")

        self.die_temperature_label = QLabel("出口熔体温度:")
        self.die_temperature_value = QLabel(f"{placeholder}")
        self.die_diameter_label = QLabel("出口熔体直径:")
        self.die_diameter_value = QLabel(f"{placeholder}")
        self.progress_label = QLabel("任务进度:")
        self.progress_value = QLabel(f"{placeholder}")

        self.tcp_sensor_widgets: dict[str, dict] = {}

        layout = QVBoxLayout()
        self.main_layout = layout

        row_layout_1 = QHBoxLayout()
        row_layout_1.addWidget(self.hotend_temperature_label)
        row_layout_1.addWidget(self.hotend_temperature_value)
        row_layout_1.addWidget(self.hotend_temperature_input)
        row_layout_1.addStretch(1)

        row_layout_2 = QHBoxLayout()
        row_layout_2.addWidget(self.feedrate_label)
        row_layout_2.addWidget(self.measured_feedrate_value)
        row_layout_2.addWidget(self.feedrate_value)
        row_layout_2.addStretch(1)

        self.tcp_sensor_layout = QVBoxLayout()

        die_temperature_row_layout = QHBoxLayout()
        die_temperature_row_layout.addWidget(self.die_temperature_label)
        die_temperature_row_layout.addWidget(self.die_temperature_value)

        die_diameter_row_layout = QHBoxLayout()
        die_diameter_row_layout.addWidget(self.die_diameter_label)
        die_diameter_row_layout.addWidget(self.die_diameter_value)

        progress_row_layout = QHBoxLayout()
        progress_row_layout.addWidget(self.progress_label)
        progress_row_layout.addWidget(self.progress_value)

        layout.addLayout(row_layout_1)
        layout.addLayout(row_layout_2)
        layout.addLayout(self.tcp_sensor_layout)
        layout.addLayout(die_temperature_row_layout)
        layout.addLayout(die_diameter_row_layout)
        layout.addLayout(progress_row_layout)

        self.setLayout(layout)
        self.hotend_temperature_input.returnPressed.connect(self.on_temp_enter_pressed)

    def configure_tcp_sensors(self, sensor_names: list[str], zeroable_sensor_names: list[str]):
        for name in list(self.tcp_sensor_widgets.keys()):
            if name not in sensor_names:
                row = self.tcp_sensor_widgets.pop(name)
                self.tcp_sensor_layout.removeItem(row["layout"])
                if row["button"] is not None:
                    row["button"].deleteLater()
                row["label"].deleteLater()
                row["value"].deleteLater()

        zeroable_set = set(zeroable_sensor_names)
        for name in sensor_names:
            if name in self.tcp_sensor_widgets:
                row = self.tcp_sensor_widgets[name]
                if row["button"] is not None:
                    row["button"].setVisible(name in zeroable_set)
                continue

            row_layout = QHBoxLayout()
            label = QLabel(f"{name}:")
            value = QLabel(f"{self.placeholder}")
            row_layout.addWidget(label)
            row_layout.addWidget(value)
            row_layout.addStretch(1)

            zero_button = None
            if name in zeroable_set:
                zero_button = QPushButton()
                zero_button.setIcon(self.zero_icon)
                zero_button.clicked.connect(lambda _checked=False, sensor_name=name: self.zero_sensor.emit(sensor_name))
                row_layout.addWidget(zero_button)

            self.tcp_sensor_layout.addLayout(row_layout)
            self.tcp_sensor_widgets[name] = {
                "layout": row_layout,
                "label": label,
                "value": value,
                "button": zero_button,
            }

    @Slot(dict)
    def update_display(self, data):
        for sensor_name, row in self.tcp_sensor_widgets.items():
            value = data.get(sensor_name, None)
            if value is None:
                continue
            try:
                row["value"].setText(f"{float(value):5.1f}")
            except Exception:
                row["value"].setText(str(value))

        if "measured_temperature_C" in data:
            temperature = data["measured_temperature_C"]
            self.hotend_temperature_value.setText(f"{temperature:5.1f} /")

        if "measured_feedrate_mms" in data:
            measured_feedrate = data["measured_feedrate_mms"]
            self.measured_feedrate_value.setText(f"{measured_feedrate:5.1f} /")

        if "feedrate_mms" in data:
            feedrate = data["feedrate_mms"]
            self.feedrate_value.setText(f"{feedrate:5.1f} mm/s")

        if "die_temperature_C" in data:
            die_temperature = data["die_temperature_C"]
            self.die_temperature_value.setText(f"{die_temperature:5.1f} ℃")

        if "die_diameter_px" in data:
            die_diameter = data["die_diameter_px"]
            self.die_diameter_value.setText(f"{die_diameter:5.1f} px")

    def on_temp_enter_pressed(self):
        self.set_temperature.emit(float(self.hotend_temperature_input.text()))

    @Slot(float)
    def update_progress(self, progress):
        self.progress_value.setText(f"{progress*100:.1f}%")


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = PlatformStatusWidget()
    widget.show()
    sys.exit(app.exec())

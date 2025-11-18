from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QLabel, QPushButton
)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QIcon
# import pyqtgraph as pg
import os

class PlatformStatusWidget(QWidget):

    set_temperature = Signal(float)
    sigMeterCountZero = Signal()
    sigExtrusionForceZero = Signal()

    def __init__(self, 
                 placeholder : str = "***",
                 icon_path : str = "icons"):
        
        super().__init__()
        
        # 组件
        self.hotend_temperature_label = QLabel("温度:")
        self.hotend_temperature_value = QLabel(f"{placeholder:5s} /")
        self.hotend_temperature_input = QLineEdit("")
        self.hotend_temperature_input.setMaximumWidth(60)
        self.extrusion_force_label = QLabel("挤出力:")
        self.extrusion_force_value = QLabel(f"{placeholder}")
        self.extrusion_force_zero_button = QPushButton()
        zero_icon = QIcon(os.path.join(icon_path, "toZero.png"))
        self.extrusion_force_zero_button.setIcon(zero_icon)
        self.meter_count_label = QLabel("当前进料量:")
        self.meter_count_value = QLabel(f"{placeholder}")
        self.meter_count_zero_button = QPushButton()
        self.meter_count_zero_button.setIcon(zero_icon)
        self.feedrate_label = QLabel("进线速度:")
        self.measured_feedrate_value = QLabel(f"{placeholder}/")
        self.feedrate_value = QLabel(f"{placeholder} mm/s")
        self.die_temperature_label = QLabel("出口熔体温度:")
        self.die_temperature_value = QLabel(f"{placeholder}")
        self.die_diameter_label = QLabel("出口熔体直径:")
        self.die_diameter_value = QLabel(f"{placeholder}")
        self.progress_label = QLabel("任务进度:")
        self.print_duration_label = QLabel(f"{placeholder} / ")
        self.total_duration_label = QLabel(f"{placeholder} s")

        # 布局
        layout = QVBoxLayout()
        row_layout_1 = QHBoxLayout()
        row_layout_2 = QHBoxLayout()
        row_layout_3 = QHBoxLayout()
        row_layout_4 = QHBoxLayout()
        die_temperature_row_layout = QHBoxLayout()
        die_diameter_row_layout = QHBoxLayout()
        progress_row_layout = QHBoxLayout()

        # temperature row
        row_layout_1.addWidget(self.hotend_temperature_label)
        row_layout_1.addWidget(self.hotend_temperature_value)
        row_layout_1.addWidget(self.hotend_temperature_input)
        row_layout_1.addStretch(1)
        # extrusion force row
        row_layout_2.addWidget(self.extrusion_force_label)
        row_layout_2.addWidget(self.extrusion_force_value)
        row_layout_2.addStretch(1)
        row_layout_2.addWidget(self.extrusion_force_zero_button)
        # meter count row
        row_layout_3.addWidget(self.meter_count_label)
        row_layout_3.addWidget(self.meter_count_value)
        row_layout_3.addStretch(1)
        row_layout_3.addWidget(self.meter_count_zero_button)
        # feedrate row
        row_layout_4.addWidget(self.feedrate_label)
        row_layout_4.addWidget(self.measured_feedrate_value)
        row_layout_4.addWidget(self.feedrate_value)
        row_layout_4.addStretch(1)
        # die temperature row
        die_temperature_row_layout.addWidget(self.die_temperature_label)
        die_temperature_row_layout.addWidget(self.die_temperature_value)
        # die diameter row
        die_diameter_row_layout.addWidget(self.die_diameter_label)
        die_diameter_row_layout.addWidget(self.die_diameter_value)
        # progress row
        progress_row_layout.addWidget(self.progress_label)
        progress_row_layout.addWidget(self.print_duration_label)
        progress_row_layout.addWidget(self.total_duration_label)

        layout.addLayout(row_layout_1)
        layout.addLayout(row_layout_2)
        layout.addLayout(row_layout_3)
        layout.addLayout(row_layout_4)
        layout.addLayout(die_temperature_row_layout)
        layout.addLayout(die_diameter_row_layout)
        # layout.addLayout(progress_row_layout)
        
        self.setLayout(layout)

        # connect signals and slots
        self.hotend_temperature_input.returnPressed.connect(self.on_temp_enter_pressed)
        self.extrusion_force_zero_button.clicked.connect(self.on_extrusion_force_zero_clicked)
        self.meter_count_zero_button.clicked.connect(self.on_meter_count_zero_clicked)

    @Slot(dict)
    def update_display(self, data):
        for item in data:
            if item == "hotend_temperature_C":
                temperature = data[item]
                if temperature:
                    self.hotend_temperature_value.setText(f"{temperature:5.1f} /")
            elif item == "extrusion_force_N":
                extrusion_force = data[item]
                self.extrusion_force_value.setText(f"{extrusion_force:5.1f} N")
            elif item == "meter_count_mm":
                meter_count = data[item]
                self.meter_count_value.setText(f"{meter_count:5.1f} mm")
            elif item == "measured_feedrate_mms":
                meansured_feedrate = data[item]
                self.measured_feedrate_value.setText(f"{meansured_feedrate:5.1f} /")
            elif item == "feedrate_mms":
                feedrate = data[item]
                if feedrate:
                    self.feedrate_value.setText(f"{feedrate:5.1f} mm/s")
            elif item == "die_temperature_C":
                die_temperature = data[item]
                self.die_temperature_value.setText(f"{die_temperature:5.1f} C")
            elif item == "die_diameter_px":
                die_diameter = data[item]
                self.die_diameter_value.setText(f"{die_diameter:5.1f} px")

    def on_temp_enter_pressed(self):
        self.set_temperature.emit(float(self.hotend_temperature_input.text()))

    @Slot(dict)
    def update_progress(self, progress):
        self.print_duration_label.setText(progress["print_duration"])
        self.total_duration_label.setText(progress["total_duration"])
    
    def on_extrusion_force_zero_clicked(self):
        self.sigExtrusionForceZero.emit()
    
    def on_meter_count_zero_clicked(self):
        self.sigMeterCountZero.emit()

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = PlatformStatusWidget()
    widget.show()
    sys.exit(app.exec())
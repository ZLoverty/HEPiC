from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent.parent
sys.path.append(str(current_path))

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout
)
from PySide6.QtCore import Slot, Signal, QThread, QObject
from tab_widgets import GcodeWidget
import pyqtgraph as pg
import logging
from utils import parse_gcode_time_series

class JobSequenceWidget(QWidget):

    def __init__(self, line_width=2):

        super().__init__()

        self.logger = logging.getLogger(__name__)
        
        # create gcode widget
        self.gcode_widget = GcodeWidget()

        # 创建 pyqtgraph widgets
        items = ["filament_velocity_mms", "hotend_temperature_C"]
        colors = ['#2980b9', '#e74c3c']
        titles = ["进线速度(mm/s)", "温度(℃)"]
        
        self.plots = {}
        self.curves = {}
        title_size = 10

        for item, color, title in zip(items, colors, titles):
            self.plots[item] = pg.PlotWidget(title=f"<span style='color: {color}; font-size: {title_size}pt; font-weight: normal; font-family: Microsoft YaHei UI'>{title}</span>")
            self.curves[item] = self.plots[item].plot(pen=pg.mkPen(color, width=line_width))

        # 布局
        layout = QHBoxLayout()

        layout.addWidget(self.gcode_widget)

        plot_layout = QVBoxLayout()

        for item in items:
            plot_layout.addWidget(self.plots[item])

        layout.addLayout(plot_layout)

        self.setLayout(layout)

        # signal - slots
        self.gcode_widget.sigGcode.connect(self.show_plots)

        

    @Slot(str)
    def show_plots(self, gcode):
        t, ve, temp = parse_gcode_time_series(gcode)
        self.curves["filament_velocity_mms"].setData(t, ve)
        self.curves["hotend_temperature_C"].setData(t, temp)

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = JobSequenceWidget()
    widget.setGeometry(900, 100, 500, 300)

    widget.show()
    sys.exit(app.exec())
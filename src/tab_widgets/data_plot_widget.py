from PySide6.QtWidgets import (
    QWidget, QVBoxLayout
)
from PySide6.QtCore import Slot
import pyqtgraph as pg

class DataPlotWidget(QWidget):

    def __init__(self):

        super().__init__()

        # 创建 pyqtgraph widgets
        self.force_plot = pg.PlotWidget(title="挤出力(N)")
        self.dietemp_plot = pg.PlotWidget(title="出口熔体温度(C)")
        self.dieswell_plot = pg.PlotWidget(title="出口熔体直径(px)")
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.force_curve = self.force_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dietemp_curve = self.dietemp_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dieswell_curve = self.dieswell_plot.plot(pen=pen) # 在图表上添加一条曲线

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.force_plot)
        layout.addWidget(self.dietemp_plot)
        layout.addWidget(self.dieswell_plot)
        self.setLayout(layout)

        self.max_len = 300
    
    @Slot(dict)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        try:
            if "extrusion_force_N" in data:
                self.force_curve.setData(list(data["time_s"])[-self.max_len:], list(data["extrusion_force_N"])[-self.max_len:])
            if "die_temperature_C" in data:
                self.dietemp_curve.setData(list(data["time_s"])[-self.max_len:], list(data["die_temperature_C"])[-self.max_len:])
            if "die_diameter_px" in data:
                self.dieswell_curve.setData(list(data["time_s"])[-self.max_len:], list(data["die_diameter_px"])[-self.max_len:])

        except (IndexError, ValueError):
            self.temp_value_label.setText("解析错误")
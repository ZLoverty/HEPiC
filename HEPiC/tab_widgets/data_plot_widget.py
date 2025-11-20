from PySide6.QtWidgets import (
    QWidget, QVBoxLayout
)
from PySide6.QtCore import Slot, Signal, QThread, QObject
import pyqtgraph as pg
import logging

class DataPlotWidget(QWidget):

    def __init__(self, logger=None, line_width=2, max_len=300):

        super().__init__()
        self.max_len = max_len

        # 创建 pyqtgraph widgets
        items = ["extrusion_force_N", "die_temperature_C", "die_diameter_px"]
        colors = ['#2980b9', '#e74c3c', '#27ae60']
        titles = ["挤出力(N)", "出口温度(℃)", "出口直径(px)"]
        
        self.plots = {}
        self.curves = {}
        title_size = 10

        for item, color, title in zip(items, colors, titles):
            self.plots[item] = pg.PlotWidget(title=f"<span style='color: {color}; font-size: {title_size}pt; font-weight: normal; font-family: Microsoft YaHei UI'>{title}</span>")
            self.curves[item] = self.plots[item].plot(pen=pg.mkPen(color, width=line_width))

        # 布局
        layout = QVBoxLayout()
        for item in self.plots:
            layout.addWidget(self.plots[item])
        self.setLayout(layout)

        self.logger = logger or logging.getLogger(__name__)
    
    @Slot(dict)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        try:
            for item in self.curves:
                if item in data:
                    self.curves[item].setData(list(data["time_s"])[-self.max_len:], list(data[item])[-self.max_len:])

        except (IndexError, ValueError) as e:
            self.logger.error(f"解析错误: {e}")
        except Exception as e:
            self.logger.error(f"data_plot_widget unknow error: {e}")

class DataGenerator(QObject):
    sigData = Signal(dict)

    def __init__(self):
        super().__init__()

    def run(self):
        import numpy as np
        import time
        from collections import deque

        data = {
            "time_s": deque(maxlen=100000),
            "extrusion_force_N": deque(maxlen=100000),
            "die_temperature_C": deque(maxlen=100000),
            "die_diameter_px": deque(maxlen=100000)
        }

        t0 = time.time()
        while True:
            for item in data:
                if item == "time_s":
                    data[item].append(time.time() - t0)
                else:
                    data[item].append(np.random.random())
            self.sigData.emit(data)
            time.sleep(.1)

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = DataPlotWidget()
    widget.setGeometry(900, 100, 500, 300)
    data_generator = DataGenerator()
    data_generator.sigData.connect(widget.update_display)
    thread = QThread()
    data_generator.moveToThread(thread)
    thread.started.connect(data_generator.run)
    thread.start()
    widget.show()
    sys.exit(app.exec())
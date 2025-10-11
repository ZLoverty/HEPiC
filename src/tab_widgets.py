"""
Tabs widgets for layout management. Contains

- connection widget
- platform status widget
- data plotting widget
- command widget
- log display widget
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget
)
from PySide6.QtCore import QObject, QThread, Signal, Slot
import pyqtgraph as pg

class ConnectionWidget(QWidget):

    ip = Signal(str)
    disconnect_button_clicked = Signal()

    def __init__(self):

        super().__init__()

        # 组件
        self.ip_label = QLabel("IP 地址:")
        self.ip_input = QLineEdit("192.168.114.48")
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)

        # 布局
        layout = QHBoxLayout()
        layout.addWidget(self.ip_label)
        layout.addWidget(self.ip_input)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.disconnect_button)
        self.setLayout(layout)

        # 信号槽连接
        self.connect_button.clicked.connect(self.on_connect_clicked)
        self.ip_input.returnPressed.connect(self.on_connect_clicked)

    @Slot()
    def on_connect_clicked(self):
        ip_address = self.ip_input.text().strip()
        if ip_address:
            self.ip.emit(ip_address)
        else:
            QMessageBox.warning(self, "输入错误", "请输入有效的 IP 地址。")

    @Slot(str)
    def update_button_status(self, status):
        """更新状态栏和按钮状态"""
        if status == "连接成功":
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
        else:
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)


class PlatformStatusWidget(QWidget):

    def __init__(self):
        
        super().__init__()

        # 组件
        self.temp_label = QLabel("温度:")
        self.temp_value_label = QLabel("N/A")
        self.force_label = QLabel("挤出力:")
        self.force_value_label = QLabel("N/A")
        self.meter_label = QLabel("当前进料量:")
        self.meter_value_label = QLabel("N/A")
        self.velocity_label = QLabel("进线速度:")
        self.velocity_value_label = QLabel("N/A")

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.temp_label)
        layout.addWidget(self.temp_value_label)
        layout.addWidget(self.force_label)
        layout.addWidget(self.force_value_label)
        layout.addWidget(self.meter_label)
        layout.addWidget(self.meter_value_label)
        layout.addWidget(self.velocity_label)
        layout.addWidget(self.velocity_value_label)
        self.setLayout(layout)

class DataPlotWidget(QWidget):

    def __init__(self):

        super().__init__()

        self.force_plot = pg.PlotWidget(title="挤出力")
        self.dietemp_plot = pg.PlotWidget(title="出口温度")
        self.dieswell_plot = pg.PlotWidget(title="胀大比")
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.force_curve = self.force_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dietemp_curve = self.dietemp_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dieswell_curve = self.dieswell_plot.plot(pen=pen) # 在图表上添加一条曲线

        layout = QVBoxLayout()
        layout.addWidget(self.force_plot)
        layout.addWidget(self.dietemp_plot)
        layout.addWidget(self.dieswell_plot)
        self.setLayout(layout)

class CommandWidget(QWidget):

    def __init__(self):

        super().__init__()

        self.command_display = QPlainTextEdit()
        self.command_display.setReadOnly(True)
        self.command_display.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: Consolas, monaco, monospace;")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("在此输入 G-code 指令 (如 G1 E10 F300)")
        self.send_button = QPushButton("发送指令")
        self.send_button.setEnabled(False)

        layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.command_input)
        input_layout.addWidget(self.send_button)
        layout.addWidget(self.command_display)
        layout.addLayout(input_layout)
        self.setLayout(layout)

        # 信号槽连接

    @Slot(str)
    def update_button_status(self, status):
        """更新按钮状态"""
        if status == "连接成功":
            self.send_button.setEnabled(True)
            self.command_input.setEnabled(True)
        else: # "连接已断开" 或 "连接失败"
            self.send_button.setEnabled(False)
            self.command_input.setEnabled(False)

class LogWidget(QWidget):

    def __init__(self):

        super().__init__()

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("这里会显示原始数据和调试信息...")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("原始数据日志:"))
        layout.addWidget(self.log_display) # 占据多行多列
        self.setLayout(layout)

class VisionWidget(QWidget):

    def __init__(self):

        super().__init__()
        # 视觉组件的初始化代码可以放在这里
        layout = QVBoxLayout()
        layout.addWidget(QLabel("视觉组件区域（施工中）"))
        self.setLayout(layout)
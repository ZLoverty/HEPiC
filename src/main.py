"""
etp_ctl: A PyQt6 GUI application for ETP experiment control, serial port data acquisition and visualization.
"""

import sys
import serial
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, 
)
from PySide6.QtCore import QObject, QThread, Signal, Slot
import pyqtgraph as pg
import time
from collections import deque
from communications import SerialWorker, IPWorker
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")


    
# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口数据显示与控制程序")
        self.setGeometry(100, 100, 700, 500)
        self.worker = None
        
        # initialize variables
        self.max_len = 1000
        self.time = deque(maxlen=self.max_len)
        self.temperature = deque(maxlen=self.max_len)
        self.initUI()

    def initUI(self):
        # --- 创建控件 ---
        # 连接部分
        self.ip_label = QLabel("IP 地址:")
        self.ip_input = QLineEdit("192.168.0.104")
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)

        # 数据接收显示部分
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("这里会显示所有从串口接收到的原始数据...")
        self.temp_plot = pg.PlotWidget(title="温度实时曲线")
        
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.temp_curve = self.temp_plot.plot(pen=pen) # 在图表上添加一条曲线
        

        # 解析数据显示部分
        self.temp_label = QLabel("当前温度:")
        self.temp_value_label = QLabel("N/A")
        # self.temp_value_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # 指令发送部分
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("在此输入指令 (如 LED_ON)")
        self.send_button = QPushButton("发送指令")
        self.send_button.setEnabled(False)

        # --- 设置布局 ---
        # 顶部连接区域
        connection_layout = QHBoxLayout()
        connection_layout.addWidget(self.ip_label)
        connection_layout.addWidget(self.ip_input)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        # 中间数据显示区域
        data_layout = QGridLayout()
        data_layout.addWidget(QLabel("原始数据日志:"), 0, 0)
        data_layout.addWidget(self.log_display, 1, 0) # 占据多行多列
        data_layout.addWidget(self.temp_plot, 1, 1)
        data_layout.addWidget(self.temp_label, 2, 0)
        data_layout.addWidget(self.temp_value_label, 2, 1)

        # 底部指令发送区域
        command_layout = QHBoxLayout()
        command_layout.addWidget(self.command_input)
        command_layout.addWidget(self.send_button)

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.addLayout(connection_layout)
        main_layout.addLayout(data_layout)
        main_layout.addLayout(command_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        self.connect_button.clicked.connect(self.connect_to_serial)
        self.disconnect_button.clicked.connect(self.disconnect_from_serial)
        self.send_button.clicked.connect(self.send_command)
        
    @Slot()
    def connect_to_serial(self):
        ip = self.ip_input.text()
        port = 12345 # 波特率可以根据需要修改
        
        # 创建并启动工作线程
        self.worker = IPWorker(ip, port)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_display)
        self.worker.connection_status.connect(self.update_status)
        self.thread.start()

        # set time 0
        self.t0 = time.time()

    @Slot()
    def disconnect_from_serial(self):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            # self.thread.wait()

    @Slot()
    def send_command(self):
        if self.worker and self.worker.ser and self.worker.ser.is_open:
            command = self.command_input.text()
            if command:
                self.log_display.appendPlainText(f"--> [发送]: {command}")
                # 串口发送需要字节串，并在末尾添加换行符
                self.worker.ser.write((command + '\n').encode('utf-8'))
                self.command_input.clear()

    @Slot(str)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        self.log_display.appendPlainText(f"<-- [接收]: {data}")
        
        # 解析特定数据
        if data.startswith("DATA,TEMP,"):
            try:
                parts = data.split(',')
                temperature = float(parts[2])
                self.temp_value_label.setText(f"{temperature:.2f} °C")
                self.update_temperature_plot(temperature)
            except (IndexError, ValueError):
                self.temp_value_label.setText("解析错误")

    @Slot(str)
    def update_status(self, status):
        """更新UI状态和状态栏信息"""
        self.statusBar().showMessage(status)
        if status is "接收数据":
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.send_button.setEnabled(True)
            self.ip_input.setEnabled(False)
        else: # "连接已断开" 或 "连接失败"
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.send_button.setEnabled(False)
            self.ip_input.setEnabled(True)

    @Slot(float)
    def update_temperature_plot(self, temperature):
        """Update temperature plot."""
        t = time.time() - self.t0
        self.time.append(t)
        self.temperature.append(temperature)
        self.temp_curve.setData(list(self.time), list(self.temperature))


    def closeEvent(self, event):
        """重写窗口关闭事件，确保线程被正确关闭"""
        if self.worker:
            self.worker.stop()
        event.accept()

# ====================================================================
# 3. 应用程序入口
# ====================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
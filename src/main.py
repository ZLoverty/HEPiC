"""
etp_ctl: A PyQt6 GUI application for ETP experiment control, serial port data acquisition and visualization.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox
)
from PySide6.QtCore import QObject, QThread, Signal, Slot
import pyqtgraph as pg
import time
from collections import deque
from communications import SerialWorker, IPWorker
import json
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")


    
# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("串口数据显示与控制程序")
        self.setGeometry(900, 100, 700, 500)
        self.worker = None
        self.t0 = None
        self.set_temperature = 200.0
        
        # initialize variables
        self.max_len = 100000
        self.time = deque(maxlen=self.max_len)
        self.temperature = deque(maxlen=self.max_len)
        self.extrusion_force = deque(maxlen=self.max_len)
        self.die_swell = deque(maxlen=self.max_len)
        self.die_temperature = deque(maxlen=self.max_len)
        self.initUI()

    def initUI(self):
        # --- 创建控件 ---
        # 连接部分
        self.ip_label = QLabel("IP 地址:")
        self.ip_input = QLineEdit("127.0.0.1")
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)

        # 数据接收显示部分
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("这里会显示所有从串口接收到的原始数据...")
        

        self.temp_label = QLabel("温度:")
        self.temp_value_label = QLabel("N/A")
        # self.temp_value_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.force_label = QLabel("挤出力:")
        self.force_value_label = QLabel("N/A")
        self.meter_label = QLabel("当前进料量:")
        self.meter_value_label = QLabel("N/A")
        self.velocity_label = QLabel("进线速度:")
        self.velocity_value_label = QLabel("N/A")
        
        # 指令发送部分
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("在此输入指令 (如 LED_ON)")
        self.send_button = QPushButton("发送指令")
        self.send_button.setEnabled(False)

        # 曲线图部分
        self.force_plot = pg.PlotWidget(title="挤出力")
        self.dietemp_plot = pg.PlotWidget(title="出口温度")
        self.dieswell_plot = pg.PlotWidget(title="胀大比")
        
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.force_curve = self.force_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dietemp_curve = self.dietemp_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dieswell_curve = self.dieswell_plot.plot(pen=pen) # 在图表上添加一条曲线

        # 视觉部分

        # --- 设置布局 ---
        # 顶部连接区域
        connection_layout = QHBoxLayout()
        connection_layout.addWidget(self.ip_label)
        connection_layout.addWidget(self.ip_input)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        # 中间数据显示区域
        data_layout = QGridLayout()
        data_layout.addWidget(self.temp_label, 0, 0)
        data_layout.addWidget(self.temp_value_label, 0, 1)
        data_layout.addWidget(self.force_label, 1, 0)
        data_layout.addWidget(self.force_value_label, 1, 1)
        data_layout.addWidget(self.meter_label, 2, 0)
        data_layout.addWidget(self.meter_value_label, 2, 1)
        data_layout.addWidget(self.velocity_label, 3, 0)
        data_layout.addWidget(self.velocity_value_label, 3, 1)
        data_layout.addWidget(QLabel("原始数据日志:"), 4, 0, 1, 2)
        data_layout.addWidget(self.log_display, 5, 0, 4, 2) # 占据多行多列
        data_layout.addWidget(self.force_plot, 0, 3, 3, 1)
        data_layout.addWidget(self.dietemp_plot, 3, 3, 3, 1)
        data_layout.addWidget(self.dieswell_plot, 6, 3, 3, 1)

        # 底部指令发送区域
        command_layout = QHBoxLayout()
        command_layout.addWidget(self.command_input)
        command_layout.addWidget(self.send_button)

        # 右边视觉区域
        vision_layout = QHBoxLayout()

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
        self.connect_button.clicked.connect(self.connect_to_ip)
        self.disconnect_button.clicked.connect(self.disconnect_from_ip)
        self.send_button.clicked.connect(self.send_command)
        
    @Slot()
    def connect_to_ip(self):
        # setup data reading worker
        ip = self.ip_input.text().strip()
        port = 10001

        

        # 创建并启动工作线程
        self.worker = IPWorker(ip, port)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_display)
        self.worker.connection_status.connect(self.update_status)
        self.worker.ip_addr_err.connect(self.ip_err)
        
        self.thread.start()
        
        
    @Slot(str)
    def ip_err(self, err_msg):
        QMessageBox.critical(self, "Error", f"连接服务器出错：{err_msg}")
        self.disconnect_from_ip()

    @Slot()
    def disconnect_from_ip(self):
        """断开连接时，清理 worker 和线程，重置数据"""
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        if self.time:
            self.time.clear()
        if self.extrusion_force:
            self.extrusion_force.clear()
        if self.die_temperature:
            self.die_temperature.clear()
        if self.die_swell:
            self.die_swell.clear()
        self.t0 = None

    @Slot()
    def send_command(self):
        if self.worker:
            command = self.command_input.text()
            if command:
                self.log_display.appendPlainText(f"--> [发送]: {command}")
                # 调用worker的方法来发送
                self.worker.send_command(command)
                self.command_input.clear()
                
    @Slot(str)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        self.log_display.appendPlainText(f"<-- [接收]: {data}")
        json_data = json.loads(data)
        try:
            if self.t0 is None:
                self.t0 = time.time()
                t = 0.0
            else:
                t = time.time() - self.t0

            self.temp_value_label.setText(f"{json_data["hotend_temperature"]:.1f} / {self.set_temperature:.1f} °C")
            self.time.append(t)
            self.die_temperature.append(json_data["die_temperature"])
            self.extrusion_force.append(json_data["extrusion_force"])
            self.die_swell.append(json_data["die_swell"])
            self.force_curve.setData(list(self.time), list(self.extrusion_force))
            self.dietemp_curve.setData(list(self.time), list(self.die_temperature))
            self.dieswell_curve.setData(list(self.time), list(self.die_swell))

        except (IndexError, ValueError):
            self.temp_value_label.setText("解析错误")

    @Slot(str)
    def update_status(self, status):
        """更新UI状态和状态栏信息"""
        self.statusBar().showMessage(status)
        if status == "接收数据":
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.send_button.setEnabled(True)
            self.ip_input.setEnabled(False)
        else: # "连接已断开" 或 "连接失败"
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.send_button.setEnabled(False)
            self.ip_input.setEnabled(True)
        
    # def closeEvent(self, event):
    #     """重写窗口关闭事件，确保线程被正确关闭"""
    #     print("正在关闭应用程序...")
    #     event.accept()

# ====================================================================
# 3. 应用程序入口
# ====================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
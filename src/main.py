"""
etp_ctl: A PySide6 GUI application for the Extrusion Test Platform experiment control, serial port data acquisition and visualization.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget
)
from PySide6.QtCore import QObject, QThread, Signal, Slot
import pyqtgraph as pg
import time
from collections import deque
from communications import SerialWorker, IPWorker, KlipperWorker
import json
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
    
# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):

    command_to_send = Signal(str)  # 定义一个信号，用于发送指令

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
        # 标签栏
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序

        # 网络连接组件
        self.ip_label = QLabel("IP 地址:")
        self.ip_input = QLineEdit("192.168.114.48")
        self.connect_button = QPushButton("连接")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setEnabled(False)

        # 日志组件
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("这里会显示所有从串口接收到的原始数据...")
        
        # 平台状态组件
        self.temp_label = QLabel("温度:")
        self.temp_value_label = QLabel("N/A")
        # self.temp_value_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.force_label = QLabel("挤出力:")
        self.force_value_label = QLabel("N/A")
        self.meter_label = QLabel("当前进料量:")
        self.meter_value_label = QLabel("N/A")
        self.velocity_label = QLabel("进线速度:")
        self.velocity_value_label = QLabel("N/A")
        
        # 指令发送组件
        self.command_display = QPlainTextEdit()
        self.command_display.setReadOnly(True)
        self.command_display.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: Consolas, monaco, monospace;")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("在此输入指令 (如 G1 E10 F300)")
        self.send_button = QPushButton("发送指令")
        self.send_button.setEnabled(False)

        # 曲线图组件
        self.force_plot = pg.PlotWidget(title="挤出力")
        self.dietemp_plot = pg.PlotWidget(title="出口温度")
        self.dieswell_plot = pg.PlotWidget(title="胀大比")
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.force_curve = self.force_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dietemp_curve = self.dietemp_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dieswell_curve = self.dieswell_plot.plot(pen=pen) # 在图表上添加一条曲线

        # 视觉组件

        # --- 设置布局 ---
        # 网络连接标签页
        connection_widget = QWidget()      
        connection_layout = QHBoxLayout(connection_widget)
        connection_layout.addWidget(self.ip_label)
        connection_layout.addWidget(self.ip_input)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        # 平台状态标签页
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.addWidget(self.temp_label)
        status_layout.addWidget(self.temp_value_label)
        status_layout.addWidget(self.force_label)
        status_layout.addWidget(self.force_value_label)
        status_layout.addWidget(self.meter_label)
        status_layout.addWidget(self.meter_value_label)
        status_layout.addWidget(self.velocity_label)
        status_layout.addWidget(self.velocity_value_label)

        # 曲线图标签页
        data_widget = QWidget()
        data_layout = QVBoxLayout(data_widget)
        data_layout.addWidget(self.force_plot)
        data_layout.addWidget(self.dietemp_plot)
        data_layout.addWidget(self.dieswell_plot)

        # 日志标签页
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.addWidget(QLabel("原始数据日志:"))
        log_layout.addWidget(self.log_display) # 占据多行多列

        # 底部指令发送区域
        command_widget = QWidget()
        command_layout = QVBoxLayout(command_widget)
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.command_input)
        input_layout.addWidget(self.send_button)
        command_layout.addWidget(self.command_display)
        command_layout.addLayout(input_layout)

        # 右边视觉区域
        vision_layout = QHBoxLayout()

        # 主布局
        # main_layout = QVBoxLayout()
        # main_layout.addLayout(connection_layout)
        # main_layout.addLayout(data_layout)
        # main_layout.addLayout(command_layout)

        # central_widget = QWidget()
        # central_widget.setLayout(main_layout)
        self.tabs.addTab(connection_widget, "连接")
        self.tabs.addTab(status_widget, "状态")
        self.tabs.addTab(data_widget, "数据")
        self.tabs.addTab(log_widget, "日志")
        self.tabs.addTab(command_widget, "指令")

        self.setCentralWidget(self.tabs)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        self.connect_button.clicked.connect(self.connect_to_ip)
        self.disconnect_button.clicked.connect(self.disconnect_from_ip)
        self.send_button.clicked.connect(self.send_command)
        self.command_input.returnPressed.connect(self.send_command)
        
        
    @Slot()
    def connect_to_ip(self):
        # setup data reading worker
        ip = self.ip_input.text().strip()
        port = 10001
        self._reset()  # 重置数据

        # 创建并启动工作线程
        self.worker = IPWorker(ip, port)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_display)
        self.worker.connection_status.connect(self.update_status)
        self.worker.ip_addr_err.connect(self.ip_err)       
        self.thread.start()

        # 创建 klipper 线程
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(ip, klipper_port)
        self.klipper_thread = QThread()
        self.klipper_worker.moveToThread(self.klipper_thread)
        connection_result = self.command_to_send.connect(self.klipper_worker.send_gcode)
        print(f"--- [DEBUG] 'command_to_send' to 'send_gcode' Connection Result: {connection_result} ---")
        self.klipper_thread.started.connect(self.klipper_worker.run)
        self.klipper_worker.connection_status.connect(self.update_status_klipper)
        # self.klipper_worker.response_received.connect(self.update_command_display)
        self.klipper_thread.start()
        
    def _reset(self):
        if self.time:
            self.time.clear()
        if self.extrusion_force:
            self.extrusion_force.clear()
        if self.die_temperature:
            self.die_temperature.clear()
        if self.die_swell:
            self.die_swell.clear()
        self.t0 = None

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
        if self.klipper_worker:
            self.klipper_worker.stop()
        if self.klipper_thread:
            self.klipper_thread.quit()
            self.klipper_thread.wait()

    @Slot()
    def send_command(self):
        command = self.command_input.text().strip()
        if command:
            print("--- [DEBUG] 'send_command' method called.")
            if self.klipper_worker:
                print(f"--- [DEBUG] klipper_worker object exists. ID: {id(self.klipper_worker)}")
            else:
                print("--- [DEBUG] ERROR: klipper_worker object is None or has been destroyed!")
            self.command_display.appendPlainText(f"{command}")
            # 调用 signal 发送指令
            self.command_to_send.emit(command)
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
            self.ip_input.setEnabled(False)
        else: # "连接已断开" 或 "连接失败"
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.ip_input.setEnabled(True)

    @Slot(str)
    def update_status_klipper(self, status):
        """更新UI状态和状态栏信息"""
        self.statusBar().showMessage(status)
        if self.klipper_thread:
            print(f"--- [DEBUG] Klipper thread is running: {self.klipper_thread.isRunning()} ---")
        
        self.statusBar().showMessage(status)
        
        if status == "Connection successful!":
            self.send_button.setEnabled(True)
            self.command_input.setEnabled(True)
        else: # "连接已断开" 或 "连接失败"
            self.send_button.setEnabled(False)
            self.command_input.setEnabled(False)

    @Slot(str)
    def update_command_display(self, message):
        try:
            data = json.loads(message)
            pretty_message = json.dumps(data, indent=4)
            self.command_display.appendPlainText(pretty_message)
        except json.JSONDecodeError:
            self.command_display.appendPlainText(message)
    
    def closeEvent(self, event):
        """关闭窗口时，优雅地停止后台线程"""
        self.log_display.appendPlainText("Closing application...")
        self.disconnect_from_ip()
        event.accept()

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
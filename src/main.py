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
from communications import TCPClient, KlipperWorker
import json
from tab_widgets import ConnectionWidget, PlatformStatusWidget, DataPlotWidget, CommandWidget, LogWidget, VisionWidget
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
        # 标签栏
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序
        # 标签页们
        self.connection_widget = ConnectionWidget()      
        self.status_widget = PlatformStatusWidget()
        self.data_widget = DataPlotWidget()
        self.command_widget = CommandWidget()
        self.log_widget = LogWidget()
        self.vision_layout = VisionWidget()
        # 添加标签页到标签栏
        self.tabs.addTab(self.connection_widget, "连接")
        self.tabs.addTab(self.status_widget, "状态")
        self.tabs.addTab(self.data_widget, "数据")
        self.tabs.addTab(self.log_widget, "日志")
        self.tabs.addTab(self.command_widget, "指令")
        self.tabs.addTab(self.vision_layout, "视觉")
        self.setCentralWidget(self.tabs)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        # self.connect_button.clicked.connect(self.connect_to_ip)
        # self.disconnect_button.clicked.connect(self.disconnect_from_ip)
        # self.send_button.clicked.connect(self.send_command)
        # self.command_input.returnPressed.connect(self.send_command)
        
        self.connection_widget.ip.connect(self.connect_to_ip)
        
    @Slot(str)
    def connect_to_ip(self, ip):
        # setup data reading worker
        self.ip = ip
        port = 10001
        self._reset()  # 重置数据

        # 启动数据接收线程
        self.worker = TCPClient(ip, port)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        # 连接信号槽
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.worker.close)
        # self.connection_widget.disconnect_button_clicked.connect(self.disconnect_from_ip)
        self.connection_widget.disconnect_button.clicked.connect(self.worker.close)
        # self.worker.data_received.connect(self.data_widget.update_display)
        self.worker.connection_status.connect(self.update_status)
        self.worker.connection_status.connect(self.connection_widget.update_button_status)
        # 启动线程      
        self.thread.start()

        # 创建 klipper 线程（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(ip, klipper_port)
        self.klipper_thread = QThread()
        self.klipper_worker.moveToThread(self.klipper_thread)
        # 连接信号槽
        # self.command_to_send.connect(self.klipper_worker.send_gcode)
        self.klipper_thread.started.connect(self.klipper_worker.run)
        self.klipper_thread.finished.connect(self.klipper_worker.stop)
        # self.klipper_thread.finished.connect(self.klipper_thread.deleteLater)
        self.klipper_worker.connection_status.connect(self.command_widget.update_button_status)
        # self.klipper_worker.response_received.connect(self.update_command_display)
        # 启动线程
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

    @Slot()
    def disconnect_from_ip(self):
        """断开连接时，清理 worker 和线程"""
        self.statusBar().showMessage("断开连接中...")
        print("断开连接中...")
        # 停止 IP worker
        if self.thread:
            print("尝试停止 IP 线程...")
            self.thread.quit() # 请求事件循环退出
            self.thread.wait()
        # if self.klipper_thread:
        #     self.klipper_thread.quit() # 请求事件循环退出
        #     self.klipper_thread.wait()
        
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
        """更新状态栏信息"""
        self.statusBar().showMessage(status)

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
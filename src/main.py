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
import asyncio
from qasync import QEventLoop, asyncSlot
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
        self.data_widget.reset()  # 重置数据

        # 创建 TCP 连接以接收数据
        
        self.worker = TCPClient(ip, port)

        # 连接信号槽
        self.connection_widget.disconnect_button.clicked.connect(self.disconnect_from_ip)
        self.worker.data_received.connect(self.data_widget.update_display)
        self.worker.data_received.connect(self.log_widget.update_log)
        self.worker.connection_status.connect(self.update_status)
        self.worker.connection_status.connect(self.connection_widget.update_button_status)
        self.worker.connection_status.connect(self.command_widget.update_button_status)
        self.worker.run()
        
        # 创建 klipper 线程（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(ip, klipper_port)
        # # 连接信号槽
        self.command_widget.command_to_send.connect(self.klipper_worker.send_gcode)
        self.klipper_worker.connection_status.connect(self.command_widget.update_button_status)
        self.klipper_worker.response_received.connect(self.update_command_display)
        self.klipper_worker.run()

    @Slot()
    def disconnect_from_ip(self):
        """断开连接时，清理 worker"""
        if self.worker:
            self.worker.stop()
            self.worker = None
        if self.klipper_worker:
            self.klipper_worker.stop()
            self.klipper_worker = None
        
    
                
    

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
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
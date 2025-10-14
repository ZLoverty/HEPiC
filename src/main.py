"""
etp_ctl: A PySide6 GUI application for the Extrusion Test Platform experiment control, serial port data acquisition and visualization.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget, QStackedWidget
)
from PySide6.QtCore import Signal, Slot, QThread
import pyqtgraph as pg
from collections import deque
from communications import TCPClient, KlipperWorker, VideoWorker, ProcessingWorker, ConnectionTester
from tab_widgets import ConnectionWidget, PlatformStatusWidget, DataPlotWidget, CommandWidget, LogWidget, VisionWidget, GcodeWidget
import asyncio
from qasync import QEventLoop, asyncSlot
from config import Config

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
    
# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    
    connected = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"挤出测试平台 v{Config.version}")
        self.setGeometry(900, 100, 700, 500)
        self.initUI()
        
    def initUI(self):
        # --- 创建控件 ---
        # 标签栏
        
        self.stacked_widget = QStackedWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序
        # 标签页们
        self.connection_widget = ConnectionWidget()      
        self.status_widget = PlatformStatusWidget()
        self.data_widget = DataPlotWidget()
        self.vision_widget = VisionWidget()
        self.gcode_widget = GcodeWidget()
        # 添加标签页到标签栏
        self.stacked_widget.addWidget(self.connection_widget)
        self.stacked_widget.addWidget(self.tabs)
        self.tabs.addTab(self.status_widget, "状态")
        self.tabs.addTab(self.data_widget, "数据")
        self.tabs.addTab(self.vision_widget, "视觉")
        self.tabs.addTab(self.gcode_widget, "G-code")
        self.setCentralWidget(self.stacked_widget)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        
        # self.connected.connect(self.command_widget.update_button_status)
        self.connection_widget.ip.connect(self.connection_test)
        # self.command_widget.send_button.clicked.connect(self.command_widget.send_command)
        # self.command_widget.command_input.returnPressed.connect(self.command_widget.send_command)
        self.gcode_widget.run_button.clicked.connect(self.run_gcode)
    

    @Slot(int)
    def show_UI(self, UI_index):
        """Show main UI"""
        self.stacked_widget.setCurrentIndex(UI_index)

    @Slot(str)
    def connection_test(self, host):
        # 树莓派服务器的 IP 地址和端口
        # IP 地址随时可能变化，所以以后应加一块屏幕方便随时读取
        # 数据端口暂定 10001
        self.host = host
        self.port = 10001

        # 1. 创建异步 Worker 实例
        self.connection_tester = ConnectionTester(host, self.port)

        # 2. 连接信号和槽
        self.connection_tester.test_msg.connect(self.connection_widget.update_self_test)
        self.connection_tester.success.connect(self.connect_to_ip)

        # 3. (推荐) 让 worker 在任务完成后自我销毁，避免内存泄漏
        self.connection_tester.success.connect(self.connection_tester.deleteLater)
        self.connection_tester.fail.connect(self.connection_tester.deleteLater)
        
        # 4. 直接调用 @asyncSlot 方法，qasync 会自动在事件循环中调度它
        self.connection_tester.run()

    @Slot()
    def connect_to_ip(self):

        self.data_widget.reset()  # 重置数据
        # 创建 TCP 连接以接收数据
        self.worker = TCPClient(self.host, self.port)
        # 连接信号槽
        
        self.worker.data_received.connect(self.data_widget.update_display)
        self.worker.connection_status.connect(self.connection_widget.update_self_test)
        self.worker.connection_status.connect(self.update_status)
        self.worker.connection_status.connect(self.connection_widget.update_button_status)
        self.worker.run()
        
        # 创建 klipper worker（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(self.host, klipper_port)
        # 连接信号槽
        self.klipper_worker.connection_status.connect(self.update_status)
        self.klipper_worker.current_step_signal.connect(self.gcode_widget.highlight_current_line)
        self.klipper_worker.run()

        # 创建 video worker （用于接收和处理视频信号）
        folder = "/home/zhengyang/Documents/GitHub/etp_ctl/test/filament_images_simulated"
        fps = 10
        self.video_worker = VideoWorker(image_folder=folder, fps=fps)
        # 连接信号槽
        self.video_worker.run()

        # 创建 image processing worker 用于处理图像，探测熔体直径
        self.processing_worker = ProcessingWorker()
        # 连接信号槽
        self.video_worker.new_frame_signal.connect(self.processing_worker.cache_frame)
        self.worker.data_received.connect(self.processing_worker.process_frame)
        self.processing_worker.proc_frame_signal.connect(self.vision_widget.update_live_display)
        
        self.connected.emit(True)
        self.show_UI(1)

    @Slot()
    def disconnect_from_ip(self):
        """断开连接时，清理 worker"""
        if self.worker:
            self.worker.stop()
            self.worker = None
        if self.klipper_worker:
            self.klipper_worker.stop()
            self.klipper_worker = None
        if self.video_worker:
            self.video_worker.stop()
        if self.processing_worker:
            self.processing_worker.stop()
        
    @Slot(str)
    def update_status(self, status):
        """更新状态栏信息"""
        self.statusBar().showMessage(status)

    @Slot()
    def run_gcode(self):
        """运行从文件里来的 gcode """
        if self.klipper_worker:
            self.gcode_widget.gcode = self.gcode_widget.gcode_display.toPlainText()
            self.klipper_worker.send_gcode(self.gcode_widget.gcode)

    def closeEvent(self, event):
        """关闭窗口时，优雅地停止后台线程"""
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
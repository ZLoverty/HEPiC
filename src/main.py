"""
etp_ctl: A PySide6 GUI application for the Extrusion Test Platform experiment control, serial port data acquisition and visualization.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget, QStackedWidget
)
from PySide6.QtCore import Signal, Slot, QThread, QTimer
import pyqtgraph as pg
from collections import deque
from communications import TCPClient, KlipperWorker, VideoWorker, ProcessingWorker, ConnectionTester, IRWorker
from tab_widgets import ConnectionWidget, PlatformStatusWidget, DataPlotWidget, CommandWidget, LogWidget, VisionPageWidget, GcodeWidget, HomeWidget, IRPageWidget
import asyncio
from qasync import QEventLoop, asyncSlot
from config import Config
import numpy as np
import pandas as pd

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
    
# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    
    sigNewData = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.name} v{Config.version}")
        self.setGeometry(900, 100, 700, 500)
        self.initUI()
        self.timer = QTimer() # set data grabbing frequency
        self.timer.timeout.connect(self.on_timer_tick)
        self.data_frequency = Config.data_frequency
        self.time_delay = 1 / self.data_frequency
        self.ircam_ok = False
        self.hikcam_ok = False
        self.init_data()
        self.current_time = 0
        self.autosave_filename = "autosave.csv"
        self.first_row = True
        
    def initUI(self):
        # --- 创建控件 ---
        # 标签栏
        
        self.stacked_widget = QStackedWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序
        # 标签页们
        self.connection_widget = ConnectionWidget()  
        self.home_widget = HomeWidget()
        self.vision_page_widget = VisionPageWidget()
        self.status_widget = self.home_widget.status_widget
        self.data_widget = self.home_widget.data_widget
        self.gcode_widget = self.home_widget.gcode_widget
        self.ir_page_widget = IRPageWidget()
        self.ir_image_widget = self.ir_page_widget.image_widget
        self.ir_roi_widget = self.home_widget.ir_roi_widget

        # 添加标签页到标签栏
        self.stacked_widget.addWidget(self.connection_widget)
        self.stacked_widget.addWidget(self.tabs)
        self.tabs.addTab(self.home_widget, "主页")
        # self.tabs.addTab(self.data_widget, "数据")
        self.tabs.addTab(self.vision_page_widget, "视觉")
        self.tabs.addTab(self.ir_page_widget, "红外")
        # self.tabs.addTab(self.gcode_widget, "G-code")
        self.setCentralWidget(self.stacked_widget)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        self.connection_widget.ip.connect(self.connection_test)
        self.gcode_widget.run_button.clicked.connect(self.run_gcode)
        self.status_widget.temp_input.returnPressed.connect(self.set_temperature)
        self.sigNewData.connect(self.data_widget.update_display)
        self.home_widget.start_button.clicked.connect(self.start_recording)
        self.home_widget.stop_button.clicked.connect(self.stop_recording)

    def init_data(self):
        """Initiate a few temperary queues for the data. This will be the pool for the final data: at each tick of the timer, one number will be taken out of the pool, forming a row of a spread sheet and saved."""
        items = ["extrusion_force_N", "die_temperature_C", "die_diameter_mm", "meter_count_mm", "gcode", "hotend_temperature_C", "feedrate_mms", "time_s"]
        # should define functions that can fetch the quantities from workers
        self.data = {}
        self.data_tmp = {}

        for item in items:
            self.data[item] = deque(maxlen=Config.final_data_maxlen)
            self.data_tmp[item] = deque(maxlen=Config.tmp_data_maxlen)

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
        # 创建 TCP 连接以接收数据
        self.worker = TCPClient(self.host, self.port)
        # 连接信号槽
        self.worker.connection_status.connect(self.update_status)
        
        # 创建 klipper worker（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(self.host, klipper_port)
        # 连接信号槽
        self.klipper_worker.connection_status.connect(self.update_status)
        self.klipper_worker.current_step_signal.connect(self.gcode_widget.highlight_current_line)
        self.klipper_worker.gcode_error.connect(self.update_status)
        self.klipper_worker.hotend_temperature.connect(self.status_widget.update_display_temperature)

        try:
            # 创建 video worker （用于接收和处理视频信号）
            self.video_worker = VideoWorker()
            self.hikcam_ok = True
        except Exception as e:
            if Config.test_mode:
                print("Warning: test_mode on, showing synthetic pictures instead of real capture.")
                self.video_worker = VideoWorker(test_mode=Config.test_mode)
            else:
                print(f"初始化熔体状态相机失败: {e}")

        if self.hikcam_ok or Config.test_mode:
            # 创建 image processing worker 用于处理图像，探测熔体直径
            self.processing_worker = ProcessingWorker()
            # 连接信号槽
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.video_worker.set_roi)
            self.video_worker.new_frame_signal.connect(self.vision_page_widget.vision_widget.update_live_display)
            self.video_worker.roi_frame_signal.connect(self.processing_worker.cache_frame)
            self.processing_worker.proc_frame_signal.connect(self.vision_page_widget.roi_vision_widget.update_live_display)
            self.processing_worker.proc_frame_signal.connect(self.home_widget.dieswell_widget.update_live_display)
            self.vision_page_widget.sigExpTime.connect(self.video_worker.set_exp_time)
        
        try: # 创建 IR image worker 处理红外成像仪图像，探测熔体出口温度   
            self.ir_worker = IRWorker()
            self.ircam_ok = True
        except Exception as e:
            print(f"初始化热成像仪失败，热成像仪不可用: {e}")
        
        if self.ircam_ok:
            self.ir_worker.sigNewFrame.connect(self.ir_image_widget.update_live_display)
            self.ir_image_widget.sigRoiChanged.connect(self.ir_worker.set_roi)
            self.ir_worker.sigRoiFrame.connect(self.ir_roi_widget.update_live_display)

        self.show_UI(1) # show main UI anyway
        
    @Slot()
    def start_recording(self):
        """Let all workers run."""
        self.worker.run()
        self.klipper_worker.run()
        if self.hikcam_ok or Config.test_mode:
            self.video_worker.run()
        else:
            print("WARNING: Failed to initiate camera. Vision module is inactive.")

        if self.ircam_ok:
            self.ir_worker.run()
        else:
            print("WARNING: Failed to initiate IR camera. Die temperature module is inactive.")
        
        self.timer.start(self.time_delay*1000)
        print("Recording started ...")

    @Slot()
    def stop_recording(self):
        """Let all workers stop."""
        self.worker.stop()
        self.klipper_worker.stop()
        self.video_worker.stop()
        self.processing_worker.stop()
        self.ir_worker.stop()
        self.timer.stop()
        print("Recording stopped.")
    
    def reset_data(self):
        """Reset the recorded data to prepare a fresh new recording."""

    @Slot(str)
    def update_status(self, status):
        """更新状态栏信息"""
        self.statusBar().showMessage(status)

    @Slot()
    def run_gcode(self):
        """运行从文本框里来的 gcode """
        if self.klipper_worker:
            self.gcode_widget.gcode = self.gcode_widget.gcode_display.toPlainText()
            self.klipper_worker.send_gcode(self.gcode_widget.gcode)

    def set_temperature(self):
        if self.klipper_worker:
            target = self.status_widget.temp_input.text()
            self.klipper_worker.send_gcode(f"M104 S{target}")
    
    @Slot()
    def on_timer_tick(self):
        """Record data into tmp queue on every timer tick."""
        for item in self.data:
            if item == "extrusion_force_N":
                self.data_tmp[item].append(self.worker.extrusion_force)
            elif item == "die_temperature_C":
                if self.ircam_ok:
                    self.data_tmp[item].append(self.ir_worker.die_temperature)
                else:
                    self.data_tmp[item].append(np.nan)
            elif item == "time_s":
                self.data_tmp[item].append(self.current_time)
            else:
                self.data_tmp[item].append(np.nan)
        self.sigNewData.emit(self.data)
        self.current_time += self.time_delay
        
        if len(self.data_tmp["extrusion_force_N"]) >= Config.tmp_data_maxlen:
            # construct pd.DataFrame
            df = pd.DataFrame(self.data_tmp)
            if self.first_row:
                df.to_csv(self.autosave_filename, index=False)
                self.first_row = False
            else:
                df.to_csv(self.autosave_filename, index=False, header=False, mode="a")
            for item in self.data_tmp:
                self.data[item].extend(self.data_tmp[item])
                self.data_tmp[item].clear()

    def closeEvent(self, event):
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
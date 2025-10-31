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
    
    sigNewData = Signal(dict) # update data plot
    sigNewStatus = Signal(dict) # update status panel

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.name} v{Config.version}")
        self.setGeometry(900, 100, 700, 500)
        self.initUI()
        self.timer = QTimer() # set data appending frequency
        self.status_timer = QTimer() # set status panel update frequency
        self.timer.timeout.connect(self.on_timer_tick)
        self.status_timer.timeout.connect(self.on_status_timer_tick)
        self.data_frequency = Config.data_frequency
        self.time_delay = 1 / self.data_frequency
        self.status_frequency = Config.status_frequency
        self.time_delay_status = 1 / self.status_frequency
        self.ircam_ok = False
        self.hikcam_ok = False
        self.init_data()
        self.current_time = 0
        self.autosave_filename = "autosave.csv"
        self.first_row = True
        self.video_worker = None
        self.ir_worker = None
        self.video_thread = None
        self.ir_thread = None
    
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
        
        self.sigNewData.connect(self.data_widget.update_display)
        self.home_widget.play_pause_button.toggled.connect(self.on_toggle_play_pause)
        self.home_widget.reset_button.clicked.connect(self.init_data)
        self.sigNewStatus.connect(self.status_widget.update_display)
        

    def init_data(self):
        """Initiate a few temperary queues for the data. This will be the pool for the final data: at each tick of the timer, one number will be taken out of the pool, forming a row of a spread sheet and saved."""
        items = ["extrusion_force_N", "die_temperature_C", "die_diameter_px", "meter_count_mm", "gcode", "hotend_temperature_C", "feedrate_mms", "time_s", "measured_feedrate_mms"]
        # should define functions that can fetch the quantities from workers
        self.data = {}
        self.data_tmp = {} # temporary buffer to slow down writing frequency
        self.data_status = {} # only stores current status of the platform

        for item in items:
            self.data[item] = deque(maxlen=Config.final_data_maxlen)
            self.data_tmp[item] = deque(maxlen=Config.tmp_data_maxlen)
            self.data_status[item] = np.nan

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
        """Create connection with the klipper host:
        1. TCP connection with the data server on Raspberry Pi
        2. Websocket connection with the Klipper host (via Moonraker) on Raspberry Pi"""
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
        self.status_widget.set_temperature.connect(self.klipper_worker.set_temperature)

        # Let all workers run
        self.worker.run()
        self.klipper_worker.run()
        self.initiate_camera()
        self.initiate_ir_imager()

    @Slot()
    def initiate_camera(self):
        """Try to initiate the Hikrobot camera. 
        Ideally, if the camera lost connect by accident, the software should attempt reconnection a few times. This should be handled in the camera class."""
        try:
            # 创建 video worker （用于接收和处理视频信号）
            self.video_worker = VideoWorker()
            self.video_thread = QThread()
            self.video_worker.moveToThread(self.video_thread)
            self.hikcam_ok = True
            print("熔体相机初始化成功！")
        except Exception as e:
            if Config.test_mode:
                print("Warning: test_mode on, showing synthetic pictures instead of real capture.")
                self.video_worker = VideoWorker(test_mode=Config.test_mode)
            else:
                print(f"初始化熔体状态相机失败: {e}")

        # 创建 image processing worker 用于处理图像，探测熔体直径
        self.processing_worker = ProcessingWorker()
        
        if self.hikcam_ok or Config.test_mode:
            # when a new frame is read by the video worker, send it over to the UI to display.
            self.video_worker.new_frame_signal.connect(self.vision_page_widget.vision_widget.update_live_display)

            # if ROI has been changed in the UI, send it to the video worker, so that it can crop later images accordingly.
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.video_worker.set_roi)
            
            # send cropped images to the processing worker for image analysis.
            self.video_worker.roi_frame_signal.connect(self.processing_worker.process_frame)

            # the processed frame shall be sent to the home page of the UI for user to monitor.
            self.processing_worker.proc_frame_signal.connect(self.vision_page_widget.roi_vision_widget.update_live_display)

            # the result of the image analysis, here specifically the die melt diameter, shall be sent to the home page to display
            self.processing_worker.proc_frame_signal.connect(self.home_widget.dieswell_widget.update_live_display)

            # allow user to set the exposure time of the camera
            self.vision_page_widget.sigExpTime.connect(self.video_worker.set_exp_time)

            # allow user to invert the black and white to meet the image processing need in specific experiment.
            self.vision_page_widget.invert_button.toggled.connect(self.processing_worker.invert_toggle)

            # thread management: when the thread is started, call the run() method; when the thread is finished, call the deleteLater() method for both video_thread and video_worker.
            self.video_thread.started.connect(self.video_worker.run)
            self.video_thread.finished.connect(self.video_worker.deleteLater)
            self.video_thread.finished.connect(self.video_thread.deleteLater)

        if self.hikcam_ok or Config.test_mode:
            self.video_thread.start()
        else:
            print("WARNING: Failed to initiate camera. Vision module is inactive.")

    @Slot()
    def initiate_ir_imager(self):
        """Try to initiate the IR image. If failed, the status flag should be marked False. Ideally, the software should attempt reconnection a few times if connection is lost. This should be handled in the IR imager class."""
        try: # 创建 IR image worker 处理红外成像仪图像，探测熔体出口温度   
            self.ir_worker = IRWorker()
            self.ir_thread = QThread()
            self.ir_worker.moveToThread(self.ir_thread)
            self.ircam_ok = True
        except Exception as e:
            print(f"初始化热成像仪失败，热成像仪不可用: {e}")
        
        if self.ircam_ok:
            # when IR worker receives a new frame, send it to the IR page to shown on the canvas
            self.ir_worker.sigNewFrame.connect(self.ir_image_widget.update_live_display)

            # if user draw an ROI on the canvas, send the ROI info to the IR worker, so that in the future, the worker can crop the later frames
            self.ir_image_widget.sigRoiChanged.connect(self.ir_worker.set_roi)

            # cropped frames inside ROI will be sent to the preview widget in home page
            self.ir_worker.sigRoiFrame.connect(self.ir_roi_widget.update_live_display)

            # use a thread to handle the image reading and showing loop
            self.ir_thread.started.connect(self.ir_worker.run)
            self.ir_thread.finished.connect(self.ir_thread.deleteLater)
            self.ir_worker.sigFinished.connect(self.ir_worker.deleteLater)

            # the Optris Xi 400 camera comes with 6 different temperature ranges (-20~100, 0~250, 150~900). Smaller ranges, intuitively, have better precision, while larger ranges do not. Here, we read out all the available temperature range options and put them in a drop down menu for users to select.
            for item in self.ir_worker.ranges:
                self.ir_page_widget.mode_menu.addItem(f"{item["min_temp"]} - {item["max_temp"]}")
            
            # if a temperature range is chosen, set it to the IR worker, so that it can re-initiate a camera object with updated params. 
            self.ir_page_widget.mode_menu.currentIndexChanged.connect(self.ir_worker.set_range)

            # a scrollbar that allows focus adjustment.
            self.ir_page_widget.focus_bar.valueChanged.connect(self.ir_worker.set_position)

        if self.ircam_ok:
            self.ir_thread.start()
        else:
            print("WARNING: Failed to initiate IR camera. Die temperature module is inactive.")

        self.show_UI(1) # show main UI anyway
        self.status_timer.start(self.time_delay_status * 1000)

    @Slot(bool)
    def on_toggle_play_pause(self, checked):
        if checked: 
            self.timer.start(self.time_delay*1000)
            self.home_widget.play_pause_button.setIcon(self.home_widget.pause_icon)
            print("Recording started ...")
        else:
            self.timer.stop()
            self.home_widget.play_pause_button.setIcon(self.home_widget.play_icon)
            print("Recording stopped.")

    @Slot(str)
    def update_status(self, status):
        """更新状态栏信息"""
        self.statusBar().showMessage(status)

    @Slot()
    def run_gcode(self):
        """运行从文本框里来的 gcode """
        if self.klipper_worker:
            gcode = self.gcode_widget.gcode_display.toPlainText()
            self.klipper_worker.send_gcode(gcode)
    
    @Slot()
    def on_timer_tick(self):
        """Record data into tmp queue on every timer tick."""
        # set variable to show on the homepage
        self.grab_status()
        for item in self.data_tmp:
            self.data_tmp[item].append(self.data_status[item])
            self.data[item].append(self.data_status[item])

        self.sigNewData.emit(self.data) # update all the displays
        self.current_time += self.time_delay # current time step forward
        
        # save additional data to file
        if len(self.data_tmp["extrusion_force_N"]) >= Config.tmp_data_maxlen:
            # construct pd.DataFrame
            df = pd.DataFrame(self.data_tmp)
            if self.first_row:
                df.to_csv(self.autosave_filename, index=False)
                self.first_row = False
            else:
                df.to_csv(self.autosave_filename, index=False, header=False, mode="a")
            for item in self.data_tmp:
                self.data_tmp[item].clear()

    def on_status_timer_tick(self):
        """Update status panel"""
        self.grab_status()
        self.sigNewStatus.emit(self.data_status)
        # update gcode highlight if 

    def grab_status(self):
        for item in self.data_status:
            # NOTE: here we append new data to both data_tmp and data. The idea is to grow both data together, so that in the preview panel we can use data to see the temporal evolution of the numbers at any time, mean time having a good file writing frequency (using the cached data_tmp) file, so that I/O is not a bottleneck.
            if item == "extrusion_force_N":
                self.data_status[item] = self.worker.extrusion_force
            elif item == "meter_count_mm":
                self.data_status[item] = self.worker.meter_count
            elif item == "die_temperature_C":
                if self.ircam_ok:
                    self.data_status[item] = self.ir_worker.die_temperature
                else:
                    self.data_status[item] = np.nan
            elif item == "hotend_temperature_C":
                self.data_status[item] = self.klipper_worker.hotend_temperature
            elif item == "feedrate_mms":
                self.data_status[item] = self.klipper_worker.active_feedrate_mms
            elif item == "measured_feedrate_mms":
                try:
                    measured_feedrate = (self.data_tmp["meter_count_mm"][-1]-self.data_tmp["meter_count_mm"][-2]) / self.time_delay
                except Exception as e:
                    measured_feedrate = np.nan
                self.data_status[item] = measured_feedrate
            elif item == "time_s":
                self.data_status[item] = self.current_time
            elif item == "die_diameter_px":
                self.data_status[item] = self.processing_worker.die_diameter
            elif item == "gcode":
                self.data_status[item] = self.klipper_worker.active_gcode
            else:
                self.data_status[item] = np.nan

    def closeEvent(self, event):
        print("正在关闭应用程序...")
        if self.worker:
            self.worker.stop()
            self.worker.deleteLater()
        if self.klipper_worker:
            self.klipper_worker.stop()
            self.klipper_worker.deleteLater()
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker.deleteLater()
        if self.ir_worker:
            self.ir_worker.stop()
            self.ir_worker.deleteLater()
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
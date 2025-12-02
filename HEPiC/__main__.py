"""
etp_ctl: A PySide6 GUI application for the Extrusion Test Platform experiment control, serial port data acquisition and visualization.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStackedWidget
)
from PySide6.QtCore import Signal, Slot, QThread, QTimer
import pyqtgraph as pg
from collections import deque
from pathlib import Path
from .communications import TCPClient, KlipperWorker, ConnectionTester
from .vision import VideoWorker, ProcessingWorker, IRWorker, VideoRecorder
from .tab_widgets import ConnectionWidget, VisionPageWidget, GcodeWidget, HomeWidget, IRPageWidget, JobSequenceWidget
import asyncio
from qasync import asyncSlot, QEventLoop
import numpy as np
import pandas as pd
from datetime import datetime
import logging
import json
import argparse
from importlib.metadata import packages_distributions, version, PackageNotFoundError

def _get_package_info():
    # 1. 获取当前模块的“导入名” (即文件夹名，例如 hepic)
    # __package__ 是 Python 内置变量，自动指向当前包名
    import_name = __package__ or "unknown"
    
    # 2. 反查这个导入名属于哪个“安装包” (即 pyproject.toml 里的 name)
    # 比如: 映射关系可能是 {'hepic': ['HEPiC']}
    # 注意：packages_distributions 返回的是字典，value 是列表
    dists = packages_distributions() 
    dist_names = dists.get(import_name, [])
    
    # 通常一个文件夹只对应一个包，取第一个即可
    dist_name = dist_names[0] if dist_names else import_name

    # 3. 获取版本
    try:
        dist_version = version(dist_name)
    except PackageNotFoundError:
        dist_version = "unknown"

    return dist_name, dist_version

# 执行获取，导出常量
__app_name__, __version__ = _get_package_info()
current_file_path = Path(__file__).resolve()


# ====================================================================
# 2. 创建主窗口类
# ====================================================================
class MainWindow(QMainWindow):
    
    sigNewData = Signal(dict) # update data plot
    sigNewStatus = Signal(dict) # update status panel
    # sigQueryRequest = Signal() # signal to query klipper status
    sigRestartFirmware = Signal()
    sigProgress = Signal(float)

    def __init__(self, test_mode=False, logger=None):
        super().__init__()
        self.test_mode = test_mode
        self.logger = logger or logging.getLogger(__name__)
        self.config_file = current_file_path.parent / "config.json"
        self.load_config()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setGeometry(900, 100, 1024, 768)
        self.setStyleSheet(f"background-color: {self.background_color}; color: {self.foreground_color}") 
        pg.setConfigOption("background", self.background_color)
        pg.setConfigOption("foreground", self.foreground_color)

        # 1. (关键) 给主窗口设置一个唯一的对象名称
        self.setObjectName("MyMainWindow") 

        # 2. (关键) 使用 QSS 并通过 #objectName 来指定样式
        # 这样可以确保样式只应用到主窗口，而不会"泄露"给子控件
        if self.test_mode:
            self.setStyleSheet("""
                QMainWindow#MyMainWindow {
                    background-color: #D2DCB6; 
                }
            """)

        self.initUI()
        self._timer = QTimer(self) # set data appending frequency
        self._timer.timeout.connect(self.on_timer_tick)
        self.status_timer = QTimer(self) # set status panel update frequency
        self.status_timer.timeout.connect(self.on_status_timer_tick)
        
        self.time_delay = 1 / self.data_frequency
        
        self.time_delay_status = 1 / self.status_frequency
        self.ircam_ok = False
        self.hikcam_ok = False
        self.init_data()
        self.current_time = 0
        
        self.first_row = True
        self.video_worker = None
        self.ir_worker = None
        self.video_thread = None
        self.ir_thread = None

        self.is_recording = False
        self.record_timelapse = True
        self.VIDEO_WORKER_OK = False
        self.IR_WORKER_OK = False

        self.frame_size = (512, 512)
    
    def load_config(self):
        with open(self.config_file, "r") as f:
            self.config = json.load(f)
        
        self.logger.debug(f"Loaded config: {self.config}")

        # set config values
        self.data_frequency = self.config.get("data_frequency", 10)
        self.status_frequency = self.config.get("status_frequency", 5)
        self.host = self.config.get("hepic_host", "192.168.0.81")
        self.port = self.config.get("hepic_port", 10001)
        self.hepic_refresh_interval_ms = self.config.get("hepic_refresh_interval_ms", 100)
        # self.test_mode = self.config.get("test_mode", False)
        self.tmp_data_maxlen = self.config.get("tmp_data_maxlen", 100)
        self.final_data_maxlen = self.config.get("final_data_maxlen", 1000000)
        self.background_color = self.config.get("background_color", "black")
        self.foreground_color = self.config.get("foreground_color", "white")

    def initUI(self):
        # --- 创建控件 ---
        # 标签栏
        
        self.stacked_widget = QStackedWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West) # 关键！把标签放到左边
        self.tabs.setMovable(True) # 让标签页可以拖动排序
        # 标签页们
        self.connection_widget = ConnectionWidget(host=self.host)  
        self.home_widget = HomeWidget()
        self.vision_page_widget = VisionPageWidget()
        self.status_widget = self.home_widget.status_widget
        self.ir_page_widget = IRPageWidget()
        self.job_sequence_widget = JobSequenceWidget()

        # 添加标签页到标签栏
        self.stacked_widget.addWidget(self.connection_widget)
        self.stacked_widget.addWidget(self.tabs)
        self.tabs.addTab(self.home_widget, "主页")
        # self.tabs.addTab(self.data_widget, "数据")
        self.tabs.addTab(self.vision_page_widget, "视觉")
        self.tabs.addTab(self.ir_page_widget, "红外")
        self.tabs.addTab(self.job_sequence_widget, "G-code")
        self.setCentralWidget(self.stacked_widget)

        # 设置状态栏
        self.statusBar().showMessage("准备就绪")

        # --- 连接信号与槽 ---
        self.connection_widget.host.connect(self.update_host_and_connect)
        
        self.sigNewData.connect(self.home_widget.data_widget.update_display)
        self.home_widget.play_pause_button.toggled.connect(self.on_toggle_play_pause)
        self.home_widget.reset_button.clicked.connect(self.on_reset_clicked)
        self.sigNewStatus.connect(self.status_widget.update_display)
        
    def init_data(self):
        """Initiate a few temperary queues for the data. This will be the pool for the final data: at each tick of the timer, one number will be taken out of the pool, forming a row of a spread sheet and saved."""
        items = ["hotend_temperature_C", "die_temperature_C", "feedrate_mms", "measured_feedrate_mms", "extrusion_force_N", "die_diameter_px", "meter_count_mm", "time_s"]
        # should define functions that can fetch the quantities from workers
        self.data = {}
        self.data_tmp = {} # temporary buffer to slow down writing frequency
        self.data_status = {} # only stores current status of the platform

        for item in items:
            self.data[item] = deque(maxlen=self.config.get("final_data_maxlen", 1000000))
            self.data_tmp[item] = deque(maxlen=self.config.get("tmp_data_maxlen", 100))
            self.data_status[item] = np.nan

    @Slot(int)
    def show_UI(self, UI_index):
        """Show main UI"""
        self.stacked_widget.setCurrentIndex(UI_index)

    @asyncSlot()
    async def connection_test(self):
        # 树莓派服务器的 IP 地址和端口
        # IP 地址随时可能变化，所以以后应加一块屏幕方便随时读取
        # 数据端口暂定 10001

        # 1. 创建异步 Worker 实例
        self.connection_tester = ConnectionTester(self.host, self.port)

        # 2. 连接信号和槽
        self.connection_tester.test_msg.connect(self.connection_widget.update_self_test)
        self.connection_tester.success.connect(self.connect_to_ip)

        # 3. (推荐) 让 worker 在任务完成后自我销毁，避免内存泄漏
        self.connection_tester.success.connect(self.connection_tester.deleteLater)
        self.connection_tester.fail.connect(self.connection_tester.deleteLater)
        
        # 4. 直接调用 @asyncSlot 方法，qasync 会自动在事件循环中调度它
        await self.connection_tester.run()

    @asyncSlot()
    async def connect_to_ip(self):
        """Create connection with the klipper host:
        1. TCP connection with the data server on Raspberry Pi
        2. Websocket connection with the Klipper host (via Moonraker) on Raspberry Pi"""
        # 创建 TCP 连接以接收数据
        self.worker = TCPClient(self.host, self.port, logger=self.logger, refresh_interval_ms=self.hepic_refresh_interval_ms)
        
        # 连接信号槽
        self.worker.connection_status.connect(self.update_status)
        self.status_widget.meter_count_zero_button.clicked.connect(self.worker.set_meter_count_offset)
        self.status_widget.extrusion_force_zero_button.clicked.connect(self.worker.set_extrusion_force_offset)
        
        # 创建 klipper worker（用于查询平台状态和发送动作指令）
        klipper_port = 7125
        self.klipper_worker = KlipperWorker(self.host, klipper_port)
        # 连接信号槽
        self.klipper_worker.connection_status.connect(self.update_status)
        self.klipper_worker.gcode_error.connect(self.home_widget.command_widget.display_message)
        self.status_widget.set_temperature.connect(self.klipper_worker.set_temperature)
        self.home_widget.command_widget.command.connect(self.klipper_worker.send_gcode)
        self.sigRestartFirmware.connect(self.klipper_worker.restart_firmware)
        self.sigProgress.connect(self.status_widget.update_progress)
        self.job_sequence_widget.gcode_widget.sigFilePath.connect(self.klipper_worker.upload_gcode_to_klipper)
        # Let all workers run
        tcp_task = self.worker.run()
        klipper_task = self.klipper_worker.run()
        self.initiate_camera()
        self.initiate_ir_imager()

        await asyncio.gather(tcp_task, klipper_task)

    @Slot()
    def initiate_camera(self):
        """Try to initiate the Hikrobot camera. 
        Ideally, if the camera lost connect by accident, the software should attempt reconnection a few times. This should be handled in the camera class."""
        try:
            # 创建 video worker （用于接收和处理视频信号）
            self.video_worker = VideoWorker(test_mode=self.test_mode, test_image_folder=self.config.get("test_image_folder", ""))
            self.video_thread = QThread()
            self.video_worker.moveToThread(self.video_thread)
            self.hikcam_ok = True
            # when a new frame is read by the video worker, send it over to the UI to display.
            self.video_worker.new_frame_signal.connect(self.vision_page_widget.vision_widget.update_live_display)

            # if ROI has been changed in the UI, send it to the video worker, so that it can crop later images accordingly.
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.video_worker.set_roi)
            
            # update frame size 
            self.vision_page_widget.vision_widget.sigRoiChanged.connect(self.update_frame_size)

            # allow user to set the exposure time of the camera
            self.vision_page_widget.sigExpTime.connect(self.video_worker.set_exp_time)

            

            # thread management: when the thread is started, call the run() method; when the thread is finished, call the deleteLater() method for both video_thread and video_worker.
            self.video_thread.started.connect(self.video_worker.run)
            self.video_thread.finished.connect(self.video_worker.deleteLater)
            self.video_thread.finished.connect(self.video_thread.deleteLater)

            self.video_thread.start()

            print("熔体相机初始化成功！")

            self.VIDEO_WORKER_OK = True

        except Exception as e:
            print(f"初始化熔体状态相机失败: {e}")
            print("WARNING: Failed to initiate camera. Vision module is inactive.")
        
        # 创建 image processing worker 用于处理图像，探测熔体直径
        self.processing_worker = ProcessingWorker()

        if self.VIDEO_WORKER_OK:

            # send cropped images to the processing worker for image analysis.
            self.video_worker.roi_frame_signal.connect(self.processing_worker.process_frame)

            # the processed frame shall be sent to the home page of the UI for user to monitor.
            self.processing_worker.proc_frame_signal.connect(self.vision_page_widget.roi_vision_widget.update_live_display)

            # the result of the image analysis, here specifically the die melt diameter, shall be sent to the home page to display
            self.processing_worker.proc_frame_signal.connect(self.home_widget.dieswell_widget.update_live_display)

            # allow user to invert the black and white to meet the image processing need in specific experiment.
            self.vision_page_widget.invert_button.toggled.connect(self.processing_worker.invert_toggle)

    @Slot()
    def initiate_ir_imager(self):
        """Try to initiate the IR image. If failed, the status flag should be marked False. Ideally, the software should attempt reconnection a few times if connection is lost. This should be handled in the IR imager class."""
        try: # 创建 IR image worker 处理红外成像仪图像，探测熔体出口温度   
            self.ir_worker = IRWorker()
            self.ir_thread = QThread()
            self.ir_worker.moveToThread(self.ir_thread)
            self.ircam_ok = True

            # when IR worker receives a new frame, send it to the IR page to shown on the canvas
            self.ir_worker.sigNewFrame.connect(self.ir_page_widget.image_widget.update_live_display)

            # if user draw an ROI on the canvas, send the ROI info to the IR worker, so that in the future, the worker can crop the later frames
            self.ir_page_widget.image_widget.sigRoiChanged.connect(self.ir_worker.set_roi)

            # cropped frames inside ROI will be sent to the preview widget in home page
            self.ir_worker.sigRoiFrame.connect(self.home_widget.ir_roi_widget.update_live_display)

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

            self.ir_thread.start()


        except Exception as e:
            print(f"初始化热成像仪失败，热成像仪不可用: {e}")
            print("WARNING: Failed to initiate IR camera. Die temperature module is inactive.")
            

        self.show_UI(1) # show main UI anyway
        self.status_timer.start(int(self.time_delay_status * 1000))
        self._timer.start(int(self.time_delay*1000))

    @Slot(bool)
    def on_toggle_play_pause(self, checked):
        if checked: 
            self.home_widget.play_pause_button.setIcon(self.home_widget.pause_icon)
            self.autosave_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.autosave_filename = Path(f"{self.autosave_prefix}_autosave.csv").resolve()
            
            self.logger.info("Recording started ...")
            self.statusBar().showMessage(f"Autosave file at {self.autosave_filename}")
            self.is_recording = True
            if self.record_timelapse and self.VIDEO_WORKER_OK:
                # init video recorder
                self.autosave_video_filename = Path(f"{self.autosave_prefix}_video.mkv").resolve()
                self.video_recorder_thread = VideoRecorder(self.autosave_video_filename, *self.frame_size)
                self.processing_worker.proc_frame_signal.connect(self.video_recorder_thread.add_frame)
                self.video_recorder_thread.start()
                # disable mouse in vision page
                self.vision_page_widget.vision_widget.disable_mouse()
                
        else:
            self.home_widget.play_pause_button.setIcon(self.home_widget.play_icon)
            self.logger.info("Recording stopped.")
            self.autosave_filename = None
            self.first_row = True
            self.is_recording = False
            if self.record_timelapse and self.VIDEO_WORKER_OK:
                self.processing_worker.proc_frame_signal.disconnect(self.video_recorder_thread.add_frame)
                self.video_recorder_thread.close()
                self.video_recorder_thread.deleteLater()
                # enable mouse after recording
                self.vision_page_widget.vision_widget.enable_mouse()

    @Slot(str)
    def update_status(self, status):
        """更新状态栏信息"""
        self.statusBar().showMessage(status)
    
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
        if len(self.data_tmp["extrusion_force_N"]) >= self.tmp_data_maxlen and self.is_recording:
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
        self.sigProgress.emit(self.klipper_worker.progress)
        # self.sigQueryRequest.emit()
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
            elif item == "target_hotend_temperature_C":
                self.data_status[item] = self.klipper_worker.target_hotend_temperature
            elif item == "feedrate_mms":
                self.data_status[item] = self.klipper_worker.active_feedrate_mms
            elif item == "measured_feedrate_mms":
                measured_feedrate = self.worker.filament_velocity
                self.data_status[item] = measured_feedrate
            elif item == "time_s":
                self.data_status[item] = self.current_time
            elif item == "die_diameter_px":
                self.data_status[item] = self.processing_worker.die_diameter
            elif item == "gcode":
                self.data_status[item] = self.klipper_worker.active_gcode
            else:
                self.data_status[item] = np.nan

    @asyncSlot(str)
    async def update_host_and_connect(self, host):
        self.host = host
        await self.connection_test()

    @Slot(tuple)
    def update_frame_size(self, roi):
        self.frame_size = (roi[2], roi[3])

    @Slot()
    def on_reset_clicked(self):
        self.init_data()
        self.home_widget.play_pause_button.setChecked(False)
        self.sigRestartFirmware.emit()

    async def closeEvent(self, event):
        print("正在关闭应用程序...")
        if self.worker:
            await self.worker.stop()
            self.worker.deleteLater()
        if self.klipper_worker:
            await self.klipper_worker.stop()
            self.klipper_worker.deleteLater()
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker.deleteLater()
        if self.ir_worker:
            self.ir_worker.stop()
            self.ir_worker.deleteLater()
        event.accept()


def start_app():
    parser = argparse.ArgumentParser(
        description="Hotend extrusion platform control software.",
        epilog="Example: python main.py -t -d"
    )
    parser.add_argument("-t", "--test", action="store_true", help="Enable test mode")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        log_lvl = logging.DEBUG
    else:
        log_lvl = logging.INFO

    logging.basicConfig(
        level=log_lvl,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    app = QApplication(sys.argv)
    window = MainWindow(test_mode=args.test)
    window.show()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        return

# ====================================================================
# 3. 应用程序入口
# ====================================================================
if __name__ == "__main__":
    start_app()
    
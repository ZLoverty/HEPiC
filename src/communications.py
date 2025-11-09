"""
communications.py
=================
Handles serial port / IP communications.
"""

import serial
from PySide6.QtCore import QObject, Signal, QTimer, Slot
import time
import asyncio
import websockets
import json
from qasync import QEventLoop, asyncSlot
import numpy as np
from vision import binarize, filament_diameter, convert_to_grayscale, draw_filament_contour, find_longest_branch, ImageStreamer
from collections import deque
import platform
import aiohttp
from pathlib import Path
import sys
from config import Config
import re
import os
import cv2
from gcode_mapper import GcodePositionMapper

if not Config.test_mode:
    if os.name == "nt":
        # if on windows OS, import the windows camera library
        from hikcam_win import HikVideoCapture
    else:
        # on Mac / Linux, use a different library
        from video_capture import HikVideoCapture   

OPTRIS_LIB_LOADED = False
try:
    from optris_camera import OptrisCamera
    OPTRIS_LIB_LOADED = True
except Exception as e:
    print(f"Fail to load Optris camera lib.")


     



class VideoWorker(QObject):
    """
    运行 ImageStreamer 的工作线程，通过信号发送图像帧。
    """
    new_frame_signal = Signal(np.ndarray)
    roi_frame_signal = Signal(np.ndarray)
    sigFinished = Signal()

    def __init__(self, test_mode=False):
        """
        Parameters
        ----------
        test_mode : bool
            if true, enable test mode, which utilizes a sequence of local images to simulate a video stream from a camera.
        """
        super().__init__()
        self.is_running = True
        self.roi = None
        self._timer = None
        self.test_mode = test_mode

        if test_mode:  # 调试用图片流
            image_folder = Path(Config.test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(image_folder), fps=10)
        else: # 真图片流
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=50000, center_roi=True)
            
        
    def run(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.read_one_frame)
        self._timer.start(0.1)
        self.thread().exec()

        print("IRWorker 事件循环已停止。")
        self.cap.release()
        self.sigFinished.emit() # 通知主线程

    def read_one_frame(self):

        if not self.cap:
            return
        
        ret, frame = self.cap.read()
        if ret:
            self.new_frame_signal.emit(frame)
            if self.roi is None:
                # if ROI is not set, show the whole frame in the ROI panel
                self.roi_frame_signal.emit(frame)
            else:
                x, y, w, h = self.roi
                self.roi_frame_signal.emit(frame[y:y+h, x:x+w])
        else:
            print("Fail to read frame.")

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot()
    def stop(self):
        print("Stopping video worker thread.")
        self.is_running = False
        self.cap.release()

    @Slot(float)
    def set_exp_time(self, exp_time):
        """
        Parameters
        ----------
        exp_time : float
            exposure time in ms.
        """
        self.cap.release()
        while self.cap.is_open:
            time.sleep(1)
        if self.test_mode:
            print("Test mode: exposure time setting will not have any effect.")
        else:
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=exp_time*1000, center_roi=True)

class ProcessingWorker(QObject):
    """基于 distance transform 计算前景图案的尺寸。"""

    proc_frame_signal = Signal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.die_diameter = np.nan
        self.invert = False
        
    @Slot(np.ndarray)
    def process_frame(self, img):
        """Find filament in image and update the `self.die_diameter` variable with detected filament diameter."""
        gray = convert_to_grayscale(img) # only process gray images    
        try:
            binary = binarize(gray)
            if self.invert:
                binary = cv2.bitwise_not(binary)
            diameter, skeleton, dist_transform = filament_diameter(binary)
            skel_px = dist_transform[skeleton]
            skeleton_refine = skeleton.copy()
            skeleton_refine[dist_transform < skel_px.mean()] = False
            # filter the pixels on skeleton where dt is smaller than 0.9 of the max
            diameter_refine = dist_transform[skeleton_refine].mean() * 2.0
            proc_frame = draw_filament_contour(gray, skeleton_refine, diameter_refine)
            self.proc_frame_signal.emit(proc_frame)
            self.die_diameter = diameter_refine
        except ValueError as e:
            # 已知纯色图片会导致检测失败，在此情况下可以不必报错继续运行，将出口直径记为 np.nan 即可
            print(f"图像无法处理: {e}")
            self.proc_frame_signal.emit(binary)
    
    @Slot(bool)
    def invert_toggle(self, checked):
        """Sometimes the filament is the darker part of the image and background is brighter. In such cases, we may invert the binary image to make the algorithm work correctly. This is a toggle for the user to manually switch on/off whether to invert."""
        self.invert = checked

   
    
class ConnectionTester(QObject):
    """初次连接时应进行一个网络自检，确定必要的硬件都已开启，且服务、端口都正确配置。这个自检应当用阻塞函数实现，因为如果自检不通过，运行之后的代码将毫无意义。因此，单独写这个自检函数。"""
    test_msg = Signal(str)
    # 【保持不变或按需修改】如果希望传递 host，就用 Signal(str)
    success = Signal() 
    fail = Signal()

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.moonraker_port = 7125
    
    # 1. 将 run 方法改为 @asyncSlot
    @asyncSlot()
    async def run(self):
        self.test_msg.emit(f"检查网络环境中 ...")

        # --- 步骤 1: 异步检查主机基础连通性 (Ping) ---
        self.test_msg.emit(f"[步骤 1/4] 正在 Ping 树莓派主机 {self.host} ...")
        ping_ok = await self._is_host_reachable_async(self.host)
        
        if ping_ok:
            self.test_msg.emit(f"✅ Ping 成功！主机 {self.host} 在网络上是可达的。")
        else:
            self.test_msg.emit(f"❌ Ping 失败，主机 {self.host} 不可达或阻止了 Ping 请求。")
            self.fail.emit()
            return

        # --- 步骤 2: 异步检查特定 TCP 端口 ---
        self.test_msg.emit(f"[步骤 2/4] 正在检查数据传输端口 {self.port} ...")
        port_ok = await self._check_tcp_port_async(self.host, self.port)

        if port_ok:
            self.test_msg.emit(f"✅ 端口检查成功！数据服务器在 {self.host}:{self.port} 上正在监听。")
        else:
            self.test_msg.emit(f"❌ 端口检查失败。主机可达，但端口 {self.port} 已关闭或被防火墙过滤。")
            self.test_msg.emit("数据端口连通性测试失败，请检查数据服务器是否启动")
            self.fail.emit()
            return


        # --- 新增步骤 3: 检查 Moonraker API ---
        self.test_msg.emit(f"[步骤 3/4] 正在检查 Moonraker 服务...")
        if not await self._check_moonraker_async():
            self.test_msg.emit(f"❌ Moonraker 服务无响应。")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Moonraker 服务 API 响应正常！")

        # --- 新增步骤 4: 检查 Klipper 状态 ---
        self.test_msg.emit(f"[步骤 4/4] 正在查询 Klipper 状态...")
        klipper_ok, klipper_state = await self._check_klipper_async()
        if not klipper_ok:
            self.test_msg.emit(f"❌ Klipper 状态异常: '{klipper_state}'")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Klipper 状态为 '{klipper_state}'，一切就绪！")
        self.test_msg.emit("所有检查通过，准备连接...")
        self.success.emit()
        
    # 2. 实现异步的 ping 方法
    async def _is_host_reachable_async(self, host: str, timeout: int = 2) -> bool:
        system_name = platform.system().lower()
        if system_name == "windows":
            command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
        else:
            command = ["ping", "-c", "1", "-W", str(timeout), host]

        try:
            # 使用 asyncio.create_subprocess_exec 替代阻塞的 subprocess.run
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # 等待进程结束
            await proc.wait()
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            print("错误：ping 命令执行失败或超时。")
            return False

    # 3. 实现异步的 TCP 端口检查方法
    async def _check_tcp_port_async(self, host: str, port: int, timeout: int = 3) -> bool:
        try:
            # 使用 asyncio.open_connection 尝试连接，并用 wait_for 控制超时
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), 
                timeout=timeout
            )
            # 连接成功后，立即关闭 writer
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError) as e:
            # 捕获超时或连接被拒绝等错误
            print(f"检查端口时发生错误: {e}")
            return False
        
    async def _check_moonraker_async(self) -> bool:
        """异步检查 Moonraker 的 /server/info API 端点。"""
        url = f"http://{self.host}:{self.moonraker_port}/server/info"
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except Exception as e:
            print(f"检查 Moonraker 时出错: {e}")
            return False

    async def _check_klipper_async(self):
        """通过 Moonraker 查询 Klipper 的状态。"""
        url = f"http://{self.host}:{self.moonraker_port}/printer/objects/query?webhooks"
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 安全地访问嵌套的字典
                        state = data.get("result", {}).get("status", {}).get("webhooks", {}).get("state", "未知")
                        if state == "ready":
                            return True, state
                        else:
                            return False, state
                    else:
                        return False, f"HTTP 错误码: {response.status}"
        except Exception as e:
            print(f"检查 Klipper 时出错: {e}")
            return False, "请求异常"
        
class IRWorker(QObject):

    sigNewFrame = Signal(np.ndarray)
    sigRoiFrame = Signal(np.ndarray)
    sigFinished = Signal()

    def __init__(self, test_mode=False):

        super().__init__()
        self.is_running = True
        self.roi = None
        self.die_temperature = np.nan
        self._timer = None

        if test_mode:  # 调试用图片流
            test_image_folder = Path(Config.test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(test_image_folder), fps=10)
        else:
            self.ranges = OptrisCamera.list_available_ranges(0)
            self.cap = OptrisCamera()
            
    def run(self):
        self._timer = QTimer(self)

        self._timer.timeout.connect(self.read_one_frame)
        self._timer.start(0)
        self.thread().exec()

        print("IRWorker 事件循环已停止。")
        self.cap.release()
        self.sigFinished.emit() # 通知主线程
    
    def read_one_frame(self):

        if not self.cap:
            return
        
        ret_img, frame = self.cap.read(timeout=0.1)
        ret_temp, temps = self.cap.read_temp(timeout=0.1)
        if ret_img and ret_temp:
            self.sigNewFrame.emit(frame)
            if self.roi is None:
                # if ROI is not set, use the whole frame as ROI
                self.sigRoiFrame.emit(frame)
                self.die_temperature = temps.max()
            else:
                x, y, w, h = self.roi
                self.sigRoiFrame.emit(frame[y:y+h, x:x+w])
                self.die_temperature = temps[y:y+h, x:x+w].max()
        else:
            print("Fail to read frame.")

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot(int)
    def set_range(self, range_index):
        if self._timer:
            self._timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.cap = OptrisCamera(temp_range_index=range_index)

        if self.cap and self._timer:
            self._timer.start(0)

    @Slot(int)
    def set_position(self, position):
        if self.cap:
            self.cap.set_focus(position)

    def stop(self):
        self.is_running = False
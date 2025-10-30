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

class TCPClient(QObject):
    # --- 信号 ---
    # 连接状态变化时发出
    connection_status = Signal(str)
    # 收到并解析完数据后发出
    connected = Signal(int)
    extrusion_force_signal = Signal(float)
    meter_count_signal = Signal(float)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = True
        self.queue = asyncio.Queue()
        self.extrusion_force = np.nan
        self.meter_count = np.nan
        
    @asyncSlot()
    async def run(self):
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=2.0)
        try:        
            await self.send_data("start")
            self.receive_task = asyncio.create_task(self.receive_data())
            self.process_task = asyncio.create_task(self.process_data())
            await asyncio.gather(self.receive_task, self.process_task)
        except Exception as e:
            print(f"未知错误: {e}")
        finally: # 无论如何中断，都关闭 writer，并关闭两个任务
            self.writer.close()
            await self.writer.wait_closed()
            self.receive_task.cancel()
            self.process_task.cancel()
            await asyncio.gather(self.receive_task, self.process_task, return_exceptions=True)

    async def send_data(self, message):
        """向服务器发送一条消息"""
        if not self.is_running or not self.writer:
            print("连接未建立，无法发送消息。")
            return

        try:
            # 客户端发送时也最好加上换行符，以方便服务器按行读取
            data_to_send = (message + '\n').encode('utf-8')
            self.writer.write(data_to_send)
            await self.writer.drain()
            print(f"已发送 -> {message}")
        except Exception as e:
            print(f"发送消息时出错: {e}")
            self.is_running = False

    async def receive_data(self):
        """
        这个函数在后台线程中运行，持续接收数据。
        """
        try:
            while self.is_running:
            
                # 读取一行数据
                data = await self.reader.readline()
                message_str = data.decode('utf-8').strip()
                message_dict = json.loads(message_str)
                await self.queue.put(message_dict)
        except (ConnectionResetError, ConnectionAbortedError):
            print("连接被重置或中止。")
            self.connection_status.emit("连接已断开")
        except Exception as e:
            print(f"位置错误: {e}")
    
    async def process_data(self):
        """这个函数持续从队列中提取数据并发射信号，最后将数据存至主程序中的list中。数据以
        
        {
            "extrusion_force": 123,
            "meter_count": 321
        }
        
        的形式从服务器发送。
        """
        try:
            while self.is_running:   
                message_dict = await self.queue.get()
                if "extrusion_force" in message_dict:
                    self.extrusion_force = message_dict["extrusion_force"]
                if "meter_count" in message_dict:
                    self.meter_count = message_dict["meter_count"]
            # 标记队列任务已完成（好习惯）
                self.queue.task_done()
        except asyncio.CancelledError:
            print("Process data task cancelled.") # 正常停止
        except Exception as e:
            # 捕获未知错误，否则任务会崩溃且主循环不知道
            print(f"Error in process_data: {e}")

    @asyncSlot()
    async def stop(self):
        """
        关闭连接并停止接收线程。
        """
        self.is_running = False
     

class KlipperWorker(QObject):
    """
    处理与 Klipper (Moonraker) 的 WebSocket 通信
    """

    connection_status = Signal(str)
    hotend_temperature = Signal(float)
    current_step_signal = Signal(int)
    gcode_error = Signal(str)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = True
        self.message_queue = asyncio.Queue() # klipper 的消息队列
        self.gcode_queue = asyncio.Queue() # gcode 的消息队列
        self.uri = f"ws://{self.host}:{self.port}/websocket"
        self.active_feedrate_mms = np.nan
        self.hotend_temperature = np.nan
        
    @asyncSlot()
    async def run(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        try:
            print(f"正在连接 Klipper {self.uri} ...")
            self.connection_status.emit(f"正在连接 Klipper {self.uri} ...")
            # async with asyncio.wait_for(websockets.connect(self.uri), timeout=2.0) as websocket:
            async with websockets.connect(self.uri, open_timeout=2.0) as websocket:
                print("Klipper 连接成功！")
                self.connection_status.emit("Klipper 连接成功！")
                subscribe_message = {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.subscribe",
                    "params": {
                        "objects": {
                            "extruder": ["temperature"]
                        }
                    },
                    "id": 1 # 一个随机的ID
                }

                # 发送订阅请求
                await websocket.send(json.dumps(subscribe_message))
                print("已发送状态订阅请求...")

                listener_task = asyncio.create_task(self.message_listener(websocket))
                sender_task = asyncio.create_task(self.gcode_sender(websocket))
                processor_task = asyncio.create_task(self.data_processor())

                await asyncio.gather(listener_task, sender_task, processor_task)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"Klipper 连接失败")
        except TimeoutError as e:
            print("Klipper 连接超时，检查服务器是否开启")
            self.connection_status.emit("Klipper 连接超时，检查服务器是否开启")

    async def message_listener(self, websocket):
        # 监听来自服务器的消息
        while self.is_running:
            async for message in websocket:
                data = json.loads(message)
                # 将收到的原始数据放入队列，交给消费者处理
                await self.message_queue.put(data)

    async def gcode_sender(self, websocket):

        # 编译正则表达式以便复用
        f_regex = re.compile(r'F([0-9.-]+)', re.IGNORECASE)
        g_regex = re.compile(r'^(G0|G1)\s', re.IGNORECASE)

        # 发送用户输入的gcode消息
        while self.is_running:
            self.gcode = await self.gcode_queue.get()

            # 从 G code 中解析进线速度
            gcode_upper = self.gcode.upper().strip() # 标准化 G-code

            # --- 关键逻辑：在发送前，解析并更新状态 ---
            try:
                # 1. 检查此行是否设置了新的 F 值
                f_match = f_regex.search(gcode_upper)
                if f_match:
                    # G-code 的 F 单位是 mm/min，我们转为 mm/s
                    self.modal_feedrate_mms = float(f_match.group(1)) / 60.0

                # 2. 检查此行是否是移动指令
                if g_regex.search(gcode_upper):
                    # 是 G0 或 G1，所以 "活动" 速度就是当前的模态速度
                    self.active_feedrate_mms = self.modal_feedrate_mms
                else:
                    # 不是移动指令 (例如 M104, G28, G90)
                    # 这些指令没有 feedrate，所以 "活动" 速度为 0
                    self.active_feedrate_mms = 0.0
                
                # 如果是空行，什么也不做，保持上一个状态

            except Exception as e:
                print(f"Feedrate 解析出错: {e}")
                self.active_feedrate_mms = 0.0 # 出错时归零

            self.current_step += 1
            gcode_message = {
                "jsonrpc": "2.0",
                "id": self.current_step, 
                "method": "printer.gcode.script",
                "params": {
                    "script": self.gcode + "\nM400"
                },
            }
            # print(f"Step {self.current_step}: {gcode}")
            await websocket.send(json.dumps(gcode_message)) 

    @asyncSlot(str)
    async def send_gcode(self, command):
        """接收来自主线程的命令，并放入队列。command 可以是多行 gcode，行用换行符隔开，此函数会将多行命令分割为单行依次送入执行队列，以便追踪命令执行进度。
        
        Parameters
        ----------
        command : str
            gcode string, can be one-liner or multi-liner
        """

        self.current_step = 0 # 用于标记 gcode 回执
        self.current_step_signal.emit(self.current_step)
        command_list = command.split("\n")
        for cmd in command_list:
            await self.gcode_queue.put(cmd)

    async def data_processor(self):
        """
        消费者：从队列中等待并获取数据，然后进行处理。本函数需要处理多种与 Klipper 的通讯信息，至少包含 i) 订阅回执，ii) gcode 发送。
        """
        print("数据处理器已启动，等待数据...")
        while True:
            # 核心：在这里await，等待队列中有新数据
            data = await self.message_queue.get()

            # Moonraker的数据有两种主要类型：
            # 1. 对你请求的响应 (包含 "result" 键)
            # 2. 服务器主动推送的状态更新 (方法为 "notify_status_update")
            if "method" in data: 
                if data["method"] == "notify_status_update": # 判断是否是状态回执
                    try:
                        self.hotend_temperature = data["params"][0]["extruder"]["temperature"]
                    except Exception as e:
                        print(f"未知错误: {e}")
                elif data["method"] == "printer.gcode.script": # 发送 G-code
                    async with websockets.connect(self.uri) as websocket:
                        await websocket.send(json.dumps(data))
                elif data["method"] == "notify_proc_stat_update":
                    pass
                elif data["method"] == "notify_gcode_response":
                    self.gcode_error.emit(data["params"][0])
                else:
                    print(data)
            elif "id" in data:
                # print(data)
                if "result" in data:
                    # print(f"--> Feedback: step {data["id"]}")
                    # 高亮当前正在执行的 G-code
                    self.current_step_signal.emit(data["id"])
                elif "error" in data:
                    # print(data)
                    self.gcode_error.emit(f"{data["error"]["code"]}: {data["error"]["message"]}")
                else:
                    pass
            else:
                print(data)

            # 标记任务完成，这对于优雅退出很重要
            self.message_queue.task_done()

    

    @asyncSlot()
    async def stop(self):
        """停止线程"""
        self.is_running = False

class VideoWorker(QObject):
    """
    运行 ImageStreamer 的工作线程，通过信号发送图像帧。
    """
    new_frame_signal = Signal(np.ndarray)
    roi_frame_signal = Signal(np.ndarray)
    finished = Signal()

    def __init__(self, test_mode=False):
        """
        Parameters
        ----------
        test_mode : bool
            if true, enable test mode, which utilizes a sequence of local images to simulate a video stream from a camera.
        """
        super().__init__()
        self.test_mode = test_mode
        if test_mode:  # 调试用图片流
            image_folder = Path(Config.test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(image_folder), fps=10)
        else: # 真图片流
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=50000, center_roi=True)
            
        self.running = True
        self.roi = None

    @asyncSlot()
    async def run(self):
        
        while self.running:
            ret, frame = await asyncio.to_thread(self.cap.read)
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
            
            # await asyncio.sleep(0.001)

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot()
    def stop(self):
        print("Stopping video worker thread.")
        self.running = False
        self.cap.release()

    @asyncSlot(float)
    async def set_exp_time(self, exp_time):
        """
        Parameters
        ----------
        exp_time : float
            exposure time in ms.
        """
        self.cap.release()
        while self.cap.is_open:
            await asyncio.sleep(.1)
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
    success = Signal(str) 
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
            return

        # --- 步骤 2: 异步检查特定 TCP 端口 ---
        self.test_msg.emit(f"[步骤 2/4] 正在检查数据传输端口 {self.port} ...")
        port_ok = await self._check_tcp_port_async(self.host, self.port)

        if port_ok:
            self.test_msg.emit(f"✅ 端口检查成功！数据服务器在 {self.host}:{self.port} 上正在监听。")
        else:
            self.test_msg.emit(f"❌ 端口检查失败。主机可达，但端口 {self.port} 已关闭或被防火墙过滤。")
            self.test_msg.emit("数据端口连通性测试失败，请检查数据服务器是否启动")
            return


        # --- 新增步骤 3: 检查 Moonraker API ---
        self.test_msg.emit(f"[步骤 3/4] 正在检查 Moonraker 服务...")
        if not await self._check_moonraker_async():
            self.test_msg.emit(f"❌ Moonraker 服务无响应。")
            return

        self.test_msg.emit(f"✅ Moonraker 服务 API 响应正常！")

        # --- 新增步骤 4: 检查 Klipper 状态 ---
        self.test_msg.emit(f"[步骤 4/4] 正在查询 Klipper 状态...")
        klipper_ok, klipper_state = await self._check_klipper_async()
        if not klipper_ok:
            self.test_msg.emit(f"❌ Klipper 状态异常: '{klipper_state}'")
            return

        self.test_msg.emit(f"✅ Klipper 状态为 '{klipper_state}'，一切就绪！")
        self.test_msg.emit("所有检查通过，准备连接...")
        self.success.emit(self.host)
        
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

        if test_mode or OPTRIS_LIB_LOADED == False:  # 调试用图片流
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
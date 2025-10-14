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
from vision import filament_diameter, convert_to_grayscale, draw_filament_contour, find_longest_branch, ImageStreamer
from collections import deque
import platform
import aiohttp

class TCPClient(QObject):
    # --- 信号 ---
    # 连接状态变化时发出
    connection_status = Signal(str)
    # 收到并解析完数据后发出
    data_received = Signal(dict)
    connected = Signal(int)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = False
    
    @asyncSlot()
    async def run(self):
        if await self.connect():
            self.is_running = True
            await self.receive_data()
        else:
            self.stop()

    async def connect(self):
        """
        连接到TCP服务器并启动接收线程。
        这是一个阻塞操作，直到连接成功或失败。
        """
        try:
            # 创建异步 TCP 连接
            print(f"正在连接树莓派 {self.host}: {self.port} ...")
            self.connection_status.emit(f"正在连接挤出测试平台树莓派 {self.host}: {self.port} ...")
            self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=2.0)
            print("树莓派连接成功！")
            self.connection_status.emit("树莓派连接成功！")
            self.connected.emit(1)
            return True
        except (asyncio.TimeoutError, OSError) as e:
            print(f"树莓派连接超时")
            self.connection_status.emit(f"树莓派连接超时，请检查设备是否开启，IP 地址是否正确")
            return False
    
    async def receive_data(self):
        """
        这个函数在后台线程中运行，持续接收数据。
        """
        while self.is_running:
            try:
                # 读取一行数据
                data = await self.reader.readline()
                if not data:
                    print("数据为空，连接被服务器关闭。")
                    self.connection_status.emit("连接已断开")
                    break
                message_str = data.decode('utf-8').strip()
                # print(f"{message_str}")
                try:
                    message_dict = json.loads(message_str)
                    self.data_received.emit(message_dict)
                except json.JSONDecodeError:
                    print(f"收到非JSON数据: {message_str}")
    
            except (ConnectionResetError, ConnectionAbortedError):
                print("连接被重置或中止。")
                self.connection_status.emit("连接已断开")
                break
        
        # 循环结束后，确保状态被更新
        self.is_running = False

    @asyncSlot()
    async def stop(self):
        """
        关闭连接并停止接收线程。
        """
        if not self.is_running:
            self.connection_status.emit("连接已断开")
            return

        print("正在关闭连接...")
        self.is_running = False
        self.connection_status.emit("连接已断开")
        print("连接已断开")

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
        # 发送用户输入的gcode消息
        while self.is_running:
            gcode = await self.gcode_queue.get()
            self.current_step += 1
            gcode_message = {
                "jsonrpc": "2.0",
                "id": self.current_step, 
                "method": "printer.gcode.script",
                "params": {
                    "script": gcode + "\nM400"
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
                        temp = data["params"][0]["extruder"]["temperature"]
                    except:
                        temp = np.nan
                    self.hotend_temperature.emit(temp)
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
    finished = Signal()

    def __init__(self, image_folder, fps):
        super().__init__()
        self.image_folder = image_folder
        self.fps = fps
        self.running = True
        self.cap = ImageStreamer(self.image_folder, fps=self.fps)
        self.frame_delay = 1 / self.fps  

    @asyncSlot()
    async def run(self):
        
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.new_frame_signal.emit(frame)
            else:
                print("Failed to read frame.")
            
            await asyncio.sleep(self.frame_delay)

    @Slot()
    def stop(self):
        print("Stopping video worker thread.")
        self.running = False
        self.cap.release()

class ProcessingWorker(QObject):

    die_diameter_signal = Signal(float)
    proc_frame_signal = Signal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.image_buffer = deque(maxlen=1000)

    @Slot(np.ndarray)
    def cache_frame(self, frame):
        self.image_buffer.append(frame)

    @Slot(dict)
    def process_frame(self, data):
        """当收到数据时，将队列里最新的图像取出分析，然后清空队列"""
        if self.image_buffer:
            img = self.image_buffer[-1] # 取最后一张
            gray = convert_to_grayscale(img) # only process gray images    
            try:
                diameter, skeleton, dist_transform = filament_diameter(gray)
                longest_branch = find_longest_branch(skeleton)
                diameter_refine = dist_transform[longest_branch].mean() * 2.0
                proc_frame = draw_filament_contour(gray, longest_branch, diameter_refine)
                self.proc_frame_signal.emit(proc_frame)                                         
            except ValueError as e:
                # 已知纯色图片会导致检测失败，在此情况下可以不必报错继续运行，将出口直径记为 np.nan 即可
                print("ValueError: 纯色图片")
                self.die_diameter_signal.emit(np.nan)
            except Exception as e:
                raise f"{e}"
        else:
            print("No image cached, check camera connection!")
            self.die_diameter_signal.emit(np.nan)
        
        self.image_buffer.clear()
    
    def stop(self):
        self.image_buffer.clear()

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
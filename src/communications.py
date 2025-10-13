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
            task = asyncio.create_task(self.receive_data())
            asyncio.wait(task)
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
                print(f"{message_str}")
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
    # 定义信号：
    # response_received: 收到打印机返回信息时发出
    # connection_status: 连接状态变化时发出
    response_received = Signal(str)
    connection_status = Signal(str)
    hotend_temperature = Signal(float)

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
                    
                await asyncio.gather(listener_task, sender_task)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"Klipper 连接失败")
        except TimeoutError as e:
            print("Klipper 连接超时，检查服务器是否开启")
            self.connection_status.emit("Klipper 连接超时，检查服务器是否开启")

    async def message_listener(self, websocket):
        # 监听来自服务器的消息
        async for message in websocket:
            data = json.loads(message)
            # 将收到的原始数据放入队列，交给消费者处理
            await self.message_queue.put(data)

    async def gcode_sender(self, websocket):
        # 发送用户输入的gcode消息
        while self.is_running:
            gcode = await self.gcode_queue.get()
            gcode_message = {
                "jsonrpc": "2.0",
                "id": 2, # 一个随机的ID
                "method": "printer.gcode.script",
                "params": {
                    "script": gcode
                },
            }
            await websocket.send(json.dumps(gcode_message)) 

    @asyncSlot(str)
    async def send_gcode(self, command):
        """接收来自主线程的命令，并放入队列"""
        print(f"[DIAG] 2. Worker received command: '{command}'")
        await self.gcode_queue.put(command)

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
            # print(data)
            if "method" in data: 
                if data["method"] == "notify_status_update": # 判断是否是状态回执
                    try:
                        temp = data["params"][0]["extruder"]["temperature"]
                    except:
                        temp = np.nan
                    self.hotend_temperature.emit(temp)
                elif data["method"] == "printer.gcode.script":
                    async with websockets.connect(self.uri) as websocket:
                        await websocket.send(json.dumps(data))
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
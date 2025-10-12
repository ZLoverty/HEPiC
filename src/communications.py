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
from queue import Queue
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

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = False
    
    @asyncSlot()
    async def run(self):
        if await self.connect():
            try:
                await self._receive_task
            finally:
                print("\n--- 准备关闭客户端 ---")
                self.stop()
        else:
            self.stop()

    async def connect(self):
        """
        连接到TCP服务器并启动接收线程。
        这是一个阻塞操作，直到连接成功或失败。
        """
        try:
            # 创建异步 TCP 连接
            print(f"正在连接到 {self.host}:{self.port}...")
            self.connection_status.emit(f"正在尝试连接 {self.host}:{self.port}...")
            self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=5.0)
            # 直到连接成功，更改状态为 running
            self.is_running = True
            print("连接成功！")
            self.connection_status.emit("连接成功")

            # 3. 启动一个专门用于接收数据的任务
            self._receive_task = asyncio.create_task(self._receive_loop())
            return True

        except (asyncio.TimeoutError, OSError) as e:
            print(f"连接超时")
            self.connection_status.emit(f"连接超时，请检查设备是否开启，IP 地址是否正确")
            return False
        
        except Exception as e:
            print(f"连接失败: {e}")
            self.connection_status.emit(f"连接失败: {e}")
            return False

    async def _receive_loop(self):
        """
        这个函数在后台线程中运行，持续接收数据。
        """
        print("数据接收循环已启动...")
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
            except Exception as e:
                # 如果_is_running是False，说明是主动关闭，这个错误是预期的
                if self.is_running:
                    print(f"接收数据时出错: {e}")
                    self.connection_status.emit(f"连接错误: {e}")
                break
        
        # 循环结束后，确保状态被更新
        self.is_running = False
        print("数据接收循环已停止。")

    @asyncSlot()
    async def stop(self):
        """
        关闭连接并停止接收线程。
        """
        if not self.is_running:
            return

        print("正在关闭连接...")
        self.is_running = False

        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        
        if self._receive_task:
            self._receive_task.cancel()

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

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self._running = True
        self.message_queue = Queue() # 线程安全的消息队列
        self.request_id = 1
        self._stop_event = asyncio.Event()

    @Slot()
    def run(self):
        """线程主循环"""
        # 使用 asyncio 运行 WebSocket 客户端
        try:
            asyncio.run(self.main_loop())
        except Exception as e:
            self.connection_status.emit(f"Klipper 连接失败: {e}")

    async def main_loop(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        uri = f"ws://{self.host}:{self.port}/websocket"
        
        while self._running:
            try:
                self.connection_status.emit(f"正在连接 Klipper 服务 {uri}...")
                print(f"[DIAG] Attempting to connect to {uri}...")
                async with websockets.connect(uri) as websocket:
                    self.connection_status.emit("连接成功")
                    print("[DIAG] WebSocket connection established.")
                    
                    # 并发处理接收消息和发送消息
                    consumer_task = asyncio.create_task(self.message_consumer(websocket))
                    producer_task = asyncio.create_task(self.message_producer(websocket))

                    tasks = [consumer_task, producer_task]
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                # 捕获已知的连接错误
                self.connection_status.emit(f"连接失败: {e}")
            except Exception as e:
                # 捕获其他未知错误
                self.connection_status.emit(f"未知错误: {e}")
        
            if self._running:
                self.connection_status.emit("5s 后尝试重连...")
                try:
                    # 等待5秒，但如果在这期间停止信号被触发，会立刻唤醒
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
                    # 如果被唤醒，说明收到了停止信号，跳出 while 循环
                    break 
                except asyncio.TimeoutError:
                    # 5秒正常结束，继续下一次重连尝试
                    pass

    async def message_consumer(self, websocket):
        """持续从 WebSocket 接收消息"""
        async for message in websocket:
            # print(f"[DIAG] 4. Worker received raw response:\n{message}\n")
            self.response_received.emit(str(message))

    async def message_producer(self, websocket):
        """从队列中获取消息并发送到 WebSocket"""
        while self._running:
            if not self.message_queue.empty():
                command = self.message_queue.get()
                
                # Moonraker 需要 JSON-RPC 格式
                request = {
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": command},
                    "id": self.request_id
                }
                self.request_id += 1

                json_request = json.dumps(request)
                
                print(f"[DIAG] 3. Worker sending JSON:\n{json_request}\n")

                await websocket.send(json_request)
            await asyncio.sleep(.1) # 避免忙循环

    @Slot(str)
    def send_gcode(self, command):
        """接收来自主线程的命令，并放入队列"""
        print(f"[DIAG] 2. Worker received command: '{command}'")
        self.message_queue.put(command)

    @asyncSlot()
    async def stop(self):
        """停止线程"""
        self._running = False

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
"""
communications.py
=================
Handles serial port / IP communications.
"""

import serial
from PySide6.QtCore import QObject, Signal, QTimer, Slot
import time
import socket
import asyncio
import threading
import websockets
import json
from queue import Queue

# ====================================================================
# 1. 创建一个工作线程类来处理所有串口通信
# ====================================================================
class SerialWorker(QObject):
    """
    Serial port operations.
    """
    # 定义信号：
    # data_received信号在收到新数据时发射，附带一个字符串
    data_received = Signal(str)
    # connection_status信号在连接状态改变时发射
    connection_status = Signal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.is_running = True
        self.ser = None

    def run(self):
        """线程启动时会自动执行这个函数"""
        try:
            # 尝试打开串口
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.connection_status.emit(f"接收数据")
            
            # 循环读取数据，直到is_running变为False
            while self.is_running and self.ser:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line:
                        # 发射信号，将数据传递给主线程
                        self.data_received.emit(line)
                time.sleep(0.01)
        except serial.SerialException as e:
            self.connection_status.emit(f"连接失败: {e}")
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.connection_status.emit("连接已断开")

    def stop(self):
        """停止线程的运行"""
        self.is_running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

# communications.py

class IPWorker(QObject):
    """处理PC和树莓派间通过网络端口的通讯"""
    # 定义信号：
    # data_received信号在收到新数据时发射，附带一个字符串
    data_received = Signal(str)
    # connection_status信号在连接状态改变时发射
    connection_status = Signal(str)
    # ip_address error信号，在主窗口显示一个错误提示对话框
    ip_addr_err = Signal(str)

    def __init__(self, ip, port):
        super().__init__()
        self.ip = ip
        self.port = port
        self.is_running = False
        self.socket = None

    @Slot()
    def run(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 向已知的远程地址发送指令
            self.socket.sendto(b"start", (self.ip, self.port))
        except Exception as e:
            print(f"连接服务器出错：{e}")
            self.ip_addr_err.emit(f"{e}")
            return

        self.connection_status.emit(f"接收数据")

        # Create the QTimer
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 5 seconds timeout
        # Connect the timer's timeout signal to a slot
        self.timer.timeout.connect(self.receive_data)
        self.timer.start()  # Start the timer

    def receive_data(self):
        """周期性接收数据"""
        try:
            # 4. Try to receive data. A while loop ensures we drain the buffer
            #    if multiple packets arrive between timer ticks.
            while True:
                data, server_address = self.socket.recvfrom(1024)
                message = data.decode('utf-8')
                self.data_received.emit(message)
        except BlockingIOError:
            # This is the expected error when no data is available on a non-blocking socket.
            # We simply ignore it and wait for the next timer tick.
            pass
        except Exception as e:
            print(f"接收消息出错：{e}")
            self.timer.stop() # Stop the timer on error
            self.socket.close()
            self.connection_status.emit("连接断开")

    def stop(self):
        self.connection_status.emit("连接断开")
        self.socket.close()
        self.deleteLater()

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

    @Slot()
    def run(self):
        """线程主循环"""
        # 使用 asyncio 运行 WebSocket 客户端
        try:
            asyncio.run(self.main_loop())
        except Exception as e:
            self.connection_status.emit(f"Worker thread error: {e}")

    async def main_loop(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        uri = f"ws://{self.host}:{self.port}/websocket"
        
        while self._running:
            try:
                self.connection_status.emit(f"Connecting to {uri}...")
                print(f"[DIAG] Attempting to connect to {uri}...")
                async with websockets.connect(uri) as websocket:
                    self.connection_status.emit("Connection successful!")
                    print("[DIAG] WebSocket connection established.")
                    
                    # 并发处理接收消息和发送消息
                    consumer_task = asyncio.create_task(self.message_consumer(websocket))
                    producer_task = asyncio.create_task(self.message_producer(websocket))
                    
                    await asyncio.gather(consumer_task, producer_task)
                        
            # 将 ConnectionClosedError 改为更通用的 ConnectionClosed
            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                self.connection_status.emit(f"Connection lost: {e}. Retrying in 5s...")
                print(f"[DIAG] Connection failed or lost: {e}. Retrying...")
                # 在重连前等待一段时间
                if self._running:
                    await asyncio.sleep(5)
            except Exception as e:
                # 捕获其他未知错误
                self.connection_status.emit(f"An unexpected error occurred: {e}")
                print(f"[DIAG] Unexpected worker error: {e}")
                break # 发生未知错误时，通常应该退出循环

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
            await asyncio.sleep(1) # 避免忙循环

    @Slot(str)
    def send_gcode(self, command):
        """接收来自主线程的命令，并放入队列"""
        print(f"[DIAG] 2. Worker received command: '{command}'")
        self.message_queue.put(command)

    def stop(self):
        """停止线程"""
        self._running = False
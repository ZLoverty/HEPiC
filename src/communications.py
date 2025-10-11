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
import socket
import threading

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
        self.sock = None
        self._is_running = False
        self._receive_thread = None
     
    def run(self):
        if self.connect():
            try:
                while self._is_running:
                    time.sleep(1)
                
            finally:
                print("\n--- 准备关闭客户端 ---")
                self.close()

    def connect(self):
        """
        连接到TCP服务器并启动接收线程。
        这是一个阻塞操作，直到连接成功或失败。
        """
        try:
            # 1. 创建一个新的socket对象
            print(f"正在连接到 {self.host}:{self.port}...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 设置一个超时，避免connect()无限期阻塞
            self.sock.settimeout(5.0)
            # 2. 连接服务器
            self.sock.connect((self.host, self.port))
            # 连接成功后，可以取消超时或设置为None，让recv()阻塞
            self.sock.settimeout(None)

            self._is_running = True
            print("连接成功！")
            self.connection_status.emit("连接成功")

            # 3. 创建并启动一个专门用于接收数据的后台线程
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()
            return True

        except socket.timeout:
            print("连接超时。")
            self.connection_status.emit("连接失败: 超时")
            self.sock = None
            return False
        except Exception as e:
            print(f"连接失败: {e}")
            self.connection_status.emit(f"连接失败: {e}")
            self.sock = None
            return False

    def _receive_loop(self):
        """
        这个函数在后台线程中运行，持续接收数据。
        """
        print("数据接收循环已启动...")
        buffer = b""
        while self._is_running:
            try:
                # 4. recv() 是一个阻塞操作。线程会在这里暂停，直到有数据到达。
                #    这不会阻塞主线程或GUI线程。
                data = self.sock.recv(1024)
                if not data:
                    # 当recv()返回空字节串时，表示对方已关闭连接
                    print("连接被服务器关闭。")
                    self.connection_status.emit("连接已断开")
                    break

                buffer += data
                # 5. 处理粘包问题：按换行符分割消息
                while b'\n' in buffer:
                    message_part, buffer = buffer.split(b'\n', 1)
                    message_str = message_part.decode('utf-8').strip()
                    if message_str:
                        try:
                            message_dict = json.loads(message_str)
                            # print(f"收到 -> {message_dict}") # 调试用
                            self.data_received.emit(message_dict)
                        except json.JSONDecodeError:
                            print(f"错误：收到无法解析的JSON数据: {message_str}")

            except (ConnectionResetError, ConnectionAbortedError):
                print("连接被重置或中止。")
                self.connection_status.emit("连接已断开")
                break
            except Exception as e:
                # 如果_is_running是False，说明是主动关闭，这个错误是预期的
                if self._is_running:
                    print(f"接收数据时出错: {e}")
                    self.connection_status.emit(f"连接错误: {e}")
                break
        
        # 循环结束后，确保状态被更新
        self._is_running = False
        print("数据接收循环已停止。")


    def send_data(self, message):
        """
        从任何线程向服务器发送一条消息。这是一个线程安全的方法。
        """
        if not self._is_running or not self.sock:
            print("连接未建立，无法发送消息。")
            return

        try:
            # 6. 为消息添加换行符，并编码
            data_to_send = (message + '\n').encode('utf-8')
            # sendall() 会确保所有数据都被发送出去
            self.sock.sendall(data_to_send)
            # print(f"已发送 -> {message}") # 调试用
        except Exception as e:
            print(f"发送消息时出错: {e}")
            # 发送失败通常意味着连接已断开
            self.close()

    def close(self):
        """
        关闭连接并停止接收线程。
        """
        if not self._is_running:
            return

        print("正在关闭连接...")
        self._is_running = False

        if self.sock:
            # 7. 关闭socket。这会让正在阻塞的 self.sock.recv() 抛出异常，
            #    从而使 _receive_loop 循环退出。
            self.sock.close()
            self.sock = None

        if self._receive_thread and self._receive_thread.is_alive():
            # 等待接收线程完全终止
            self._receive_thread.join()

        self.connection_status.emit("连接已关闭")
        print("连接已关闭。")

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
                    stop_task = asyncio.create_task(self._stop_event.wait())

                    tasks = [consumer_task, producer_task, stop_task]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                    # 如果停止事件被触发，取消其他任务
                    if stop_task in done:
                        for task in pending:
                            task.cancel()
                        return
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

    def stop(self):
        """停止线程"""
        self._running = False
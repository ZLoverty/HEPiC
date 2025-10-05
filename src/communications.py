"""
communications.py
=================
Handles serial port / IP communications.
"""

import serial
from PySide6.QtCore import QObject, Signal
import time
import socket

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
            self.connection_status.emit(f"成功连接到 {self.port}")
            
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

class IPWorker(QObject):
    """
    Serial port operations.
    """
    # 定义信号：
    # data_received信号在收到新数据时发射，附带一个字符串
    data_received = Signal(str)
    # connection_status信号在连接状态改变时发射
    connection_status = Signal(str)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = True

    def run(self):
        """线程启动时会自动执行这个函数"""
        self.connection_status.emit(f"接收数据")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:

            # 2. Bind the socket to the address and port
            try:
                s.bind((self.host, self.port))
            except Exception as e:
                self.connection_status.emit(f"绑定失败: {e}")
            
            # 3. Wait to receive data
            #    recvfrom() blocks until a packet is received.
            #    It returns the data (bytes) and the address of the sender.
            while self.is_running:
                data_bytes, address = s.recvfrom(1024) # Buffer size is 1024 bytes
                
                # 4. Decode the bytes into a string
                line = data_bytes.decode('utf-8')
                
                if line:
                    # 发射信号，将数据传递给主线程
                    self.data_received.emit(line)
                time.sleep(0.01)

    def stop(self):
        """停止线程的运行"""
        self.is_running = False
        self.connection_status.emit("停止接收数据")
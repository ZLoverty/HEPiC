"""
communications.py
=================
Handles serial port / IP communications.
"""

import serial
from PySide6.QtCore import QObject, Signal, QTimer, Slot
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
        
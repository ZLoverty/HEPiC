"""
serial2ip.py
============

Read data from a serial port and send it to a specified IP and port via UDP upon request.

The request is initiated by receiving a specific signal ("start") from the target IP and port.

The transfer can be stopped by signal "stop".
"""

import serial
import socket
import time
import sys
import threading
import queue

# --- 请在这里配置您的参数 ---

# 串口配置
if len(sys.argv) > 1:
    SERIAL_PORT = sys.argv[1]  # 从命令行参数获取串口名
else:
    raise Exception("Please provide the serial port name as a command line argument, e.g. /dev/pts/5 or COM10")

BAUD_RATE = 9600            # 波特率，必须与您的串口设备设置一致

# 网络目标配置
LISTEN_HOST = '0.0.0.0'     # 监听所有接口的请求
LISTEN_PORT = 12345      # 接收数据的计算机上监听的端口

# --- 配置结束 ---

data_queue = queue.Queue()

def udp_listener(q):
    """
    监听用户信号。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((LISTEN_HOST, LISTEN_PORT))
        print(f"线程监听器已启动于 {LISTEN_HOST}:{LISTEN_PORT}")
        while True:
            # 这里的 recvfrom 是阻塞的，但它只会阻塞这个子线程
            data, addr = s.recvfrom(1024)
            message = data.decode()
            print(f"{addr}: {message}")
            q.put((message, addr))
            time.sleep(1)

def main():
    """
    主函数，监听12345端口。
    如果端口接收到 start 请求，则循环监听串口并转发数据至目标IP和端口。
    如果接收到 stop 请求，则停止转发。
    """
    print(f"正在尝试打开串口: {SERIAL_PORT}...")
    ser = None  # 初始化串口对象
    is_running = False  # 是否正在转发数据的标志

    # 开启监听线程
    listener_thread = threading.Thread(target=udp_listener, args=(data_queue,))
    listener_thread.daemon = True
    listener_thread.start()
    
    while True:
        try:
            message, addr = data_queue.get_nowait()
            if is_running and message == "stop":
                is_running = False
            elif is_running == False and message == "start":
                TARGET_IP, TARGET_PORT = addr
                is_running = True
        except queue.Empty:
            pass
        
        if is_running:

            try:
                # 如果串口未连接，则尝试连接
                if ser is None or not ser.is_open:
                    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                    print(f"成功连接到串口 {SERIAL_PORT}")

                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    # 从串口读取一行数据
                    # readline() 会读取直到遇到换行符 '\n'
                    print("尝试从串口读取一行")
                    line = ser.readline()

                    # 如果读取到了数据
                    if line:
                        print("成功读取数据")
                        # 将读取到的 bytes 解码为 utf-8 字符串，并去除首尾的空白字符
                        data_str = line.decode('utf-8').strip()
                        
                        if data_str:
                            print(f"从串口收到: '{data_str}'")
                            
                            # 将字符串编码回 bytes，然后通过 UDP 发送
                            s.sendto(data_str.encode('utf-8'), (TARGET_IP, TARGET_PORT))
                            print(f" -> 已发送到 {TARGET_IP}:{TARGET_PORT}")
                        
                        

            except serial.SerialException as e:
                # 捕获串口相关的异常 (例如：设备拔出)
                print(f"串口错误: {e}")
                print("5秒后尝试重新连接...")
                if ser and ser.is_open:
                    ser.close()
                ser = None # 重置串口对象
                time.sleep(5)
            
            except KeyboardInterrupt:
                # 捕获 Ctrl+C 中断信号，优雅地退出程序
                print("\n程序被中断。正在关闭...")
                break
            
            except Exception as e:
                # 捕获其他未知异常
                print(f"发生未知错误: {e}")
                time.sleep(5)

        time.sleep(0.001)

    # 清理资源
    if ser and ser.is_open:
        ser.close()

    print("程序已退出。")


if __name__ == '__main__':
    main()
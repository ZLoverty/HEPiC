import serial.rfc2217
import socket
import threading
import time
import random

# ====================================================================
# 新的设置：我们将使用网络端口12345，不再需要COM口
HOST = 'localhost'  # 表示本机
PORT = 12345        # 可以是1024-65535之间的任意数字
# ====================================================================

# 模拟微控制器的内部状态
led_status = "OFF"
temperature = 25.0

def handle_client(conn, addr):
    """处理单个客户端连接的函数"""
    global led_status, temperature
    print(f"GUI已连接: {addr}")
    
    # 将网络连接包装成一个pyserial兼容的对象
    ser = serial.rfc2217.PortManager(conn)

    try:
        while True:
            # 1. 模拟接收指令 (非阻塞)
            if ser.in_waiting > 0:
                command = ser.readline().decode('utf-8').strip()
                if command:
                    print(f"收到指令: '{command}'")

                    if command == "LED_ON":
                        led_status = "ON"
                        ser.write(b"ACK:LED is now ON\n")
                        print("动作: LED已打开")
                    elif command == "LED_OFF":
                        led_status = "OFF"
                        ser.write(b"ACK:LED is now OFF\n")
                        print("动作: LED已关闭")
                    elif command == "GET_STATUS":
                        status_msg = f"STATUS:LED={led_status},TEMP={temperature:.2f}\n"
                        ser.write(status_msg.encode('utf-8'))
                        print("动作: 发送状态信息")
                    else:
                        ser.write(b"ERR:Unknown command\n")
                        print("动作: 发送未知指令错误")

            # 2. 模拟定时发送数据
            temperature += random.uniform(-0.1, 0.1)
            data_to_send = f"DATA,TEMP,{temperature:.2f}\n"
            ser.write(data_to_send.encode('utf-8'))
            print(f"发送数据: {data_to_send.strip()}")
            
            time.sleep(1)

    except (ConnectionResetError, BrokenPipeError):
        print(f"GUI连接已断开: {addr}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        conn.close()

def start_server():
    """启动服务器并监听连接"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"虚拟微控制器服务器已在 rfc2217://{HOST}:{PORT} 上启动...")
        print("正在等待GUI程序连接...")
        while True:
            conn, addr = s.accept()
            # 为每个连接创建一个新线程来处理
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()

if __name__ == "__main__":
    start_server()
import socket
import time
import random
import json
import threading
import queue

# --- 配置 ---
HOST = '0.0.0.0'  # 关键点：在树莓派上，使用 0.0.0.0 来监听所有网络接口
PORT = 10001      # 监听端口

# --- 程序 ---
print("--- 树莓派服务器已启动 ---")
print(f"正在监听 {HOST}:{PORT}")

def udp_listener(q):
    """
    监听用户信号。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, PORT))
        # 1. 等待客户端的第一个消息，以获取其地址
        print("等待客户端连接...")

        while True:
            # 这里的 recvfrom 是阻塞的，但它只会阻塞这个子线程
            data, client_address = s.recvfrom(1024)
            print(f"已连接到客户端: {client_address}")
            command = data.decode()
            print(f"收到来自 {client_address} 的指令: {command}")
            q.put((command, client_address))
            time.sleep(1)

command_queue = queue.Queue()

# 开启监听线程
listener_thread = threading.Thread(target=udp_listener, args=(command_queue,))
listener_thread.daemon = True
listener_thread.start()
is_running = False
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # 创建一个 UDP socket

# 尝试读取指令队列
while True:  
    try:
        command, client_address = command_queue.get_nowait() # 尝试读取指令，如果没有则抛出 queue.Empty 异常
        
        if command == "start":
            is_running = True
            send_address = client_address # 记录客户端地址，只给发送 start 的客户端发送数据，增加一些安全性
        # if is_running and command == "stop":
        #     is_running = False
        #     sock.close()
        # elif is_running == False and command == "start":
        #     is_running = True
        #     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except queue.Empty:
        pass

    if is_running:
        extrusion_force = 2 + random.uniform(-.2, .2)
        die_temperature = 200.0 + random.uniform(-10, 10)
        hotend_temperature = 200.0 + random.uniform(-10, 10)
        die_swell = 1.4 + random.uniform(-.1, .1)
        message = {"extrusion_force": extrusion_force,
                    "die_temperature": die_temperature,
                    "die_swell": die_swell,
                    "hotend_temperature": hotend_temperature}
        print(f"发送 -> {message}")
    
        # 将消息发送到刚刚记录的客户端地址
        sock.sendto(json.dumps(message).encode("utf-8"), send_address)

        # 由于 UDP 是无连接的协议，所以不需要检测连接状态，如果意外断开连接，在重连时会重新获取客户端地址，继续发送

    time.sleep(0.5) # 每 0.5 秒发送一次
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
        # recvfrom 会阻塞程序，直到收到数据
        data, client_address = s.recvfrom(1024)
        print(f"已连接到客户端: {client_address}")
        while True:
            # 这里的 recvfrom 是阻塞的，但它只会阻塞这个子线程
            data, addr = s.recvfrom(1024)
            command = data.decode()
            print(f"收到来自 {addr} 的指令: {command}")
            q.put((command, addr))
            time.sleep(1)

command_queue = queue.Queue()

# 开启监听线程
listener_thread = threading.Thread(target=udp_listener, args=(command_queue,))
listener_thread.daemon = True
listener_thread.start()

# 创建 UDP socket
is_running = False

# 尝试读取指令队列
while True:  
    try:
        command, client_address = command_queue.get_nowait()
        if is_running and command == "stop":
            is_running = False
            sock.close()
        elif is_running == False and command == "start":
            is_running = True
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except queue.Empty:
        pass

    if is_running:
        temperature = 200.0 + random.uniform(-10, 10)
        message = {"temperature": temperature}
        print(f"发送 -> {message}")
        
        # 将消息发送到刚刚记录的客户端地址
        sock.sendto(json.dumps(message).encode("utf-8"), client_address)

    time.sleep(0.5) # 每 0.5 秒发送一次
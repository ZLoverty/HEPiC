import socket
import time

# --- 配置 ---
HOST = '0.0.0.0'  # 关键点：在树莓派上，使用 0.0.0.0 来监听所有网络接口
PORT = 12345      # 选择一个端口号

# --- 程序 ---
print("--- 树莓派服务器已启动 ---")
print(f"正在监听 {HOST}:{PORT}")

# 创建 UDP socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    # 绑定到指定地址和端口
    s.bind((HOST, PORT))
    
    # 1. 等待客户端的第一个消息，以获取其地址
    print("等待客户端连接...")
    # recvfrom 会阻塞程序，直到收到数据
    data, client_address = s.recvfrom(1024) 
    print(f"已连接到客户端: {client_address}")
    
    # 2. 现在开始向这个客户端地址持续发送数据
    message_counter = 0
    while True:
        try:
            message = f"来自树莓派的数据 #{message_counter}"
            print(f"发送 -> {message}")
            
            # 将消息发送到刚刚记录的客户端地址
            s.sendto(message.encode('utf-8'), client_address)
            
            message_counter += 1
            time.sleep(2) # 每2秒发送一次
            
        except KeyboardInterrupt:
            print("服务器正在关闭...")
            break
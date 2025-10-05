import socket

# --- 配置 ---
# 关键点：这里填写你树莓派的真实IP地址！
RASPBERRY_PI_IP = '192.168.1.106'  # <--- !!! 修改这里 !!!
PORT = 12345                      # 必须与服务器端的端口一致

# --- 程序 ---
print("--- 电脑客户端已启动 ---")
print(f"准备从 {RASPBERRY_PI_IP}:{PORT} 读取数据")

# 创建 UDP socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    
    # 1. 先向服务器发送一个启动信号，让服务器知道我们的地址
    s.sendto(b'start', (RASPBERRY_PI_IP, PORT))

    # 2. 现在可以循环接收来自服务器的数据了
    print("正在接收数据...")
    while True:
        try:
            # recvfrom 会阻塞程序，直到收到数据
            data, server_address = s.recvfrom(1024)
            message = data.decode('utf-8')
            print(f"收到 <- {message}")
            
        except KeyboardInterrupt:
            print("客户端正在关闭...")
            break
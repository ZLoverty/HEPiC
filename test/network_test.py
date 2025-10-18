
import socket
import platform
import subprocess
import os

def is_host_reachable(host: str, timeout: int = 2) -> bool:
    """
    通过调用系统的ping命令来检查主机是否可达。

    Args:
        host: 目标主机的IP地址或域名。
        timeout: ping的超时时间（秒）。

    Returns:
        如果主机可达 (ping成功)，返回 True，否则返回 False。
    """
    # 根据操作系统构建 ping 命令
    system_name = platform.system().lower()
    if system_name == "windows":
        # -n 1: 发送1个回显请求
        # -w <ms>: 等待每次回复的超时时间（毫秒）
        command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else: # Linux, macOS, etc.
        # -c 1: 发送1个数据包
        # -W <sec>: 等待回复的超时时间（秒）
        command = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        # 执行命令并抑制输出
        response = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False # 如果命令返回非零退出码，不要抛出异常
        )
        # 如果返回码为0，表示ping成功
        return response.returncode == 0
    except FileNotFoundError:
        # 如果系统中没有ping命令
        print("错误：系统中找不到 'ping' 命令。")
        return False

def check_tcp_port(host: str, port: int, timeout: int = 3) -> bool:
    """
    检查指定主机和端口的TCP连接是否可达。
    （这是前一个回答中的函数）
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except socket.error as e:
        # 捕获如“主机名无法解析”之类的错误
        print(f"检查端口时发生错误: {e}")
        return False
    finally:
        sock.close()

def check_network_service(host: str, port: int):
    """
    一个完整的网络服务检查流程：先ping，再检查端口。
    """
    print(f"--- 开始对 {host}:{port} 进行完整网络检查 ---")
    
    # --- 步骤 1: 检查主机基础连通性 (Ping) ---
    print(f"\n[步骤 1/2] 正在 Ping 主机 {host} ...")
    if is_host_reachable(host):
        print(f"✅ Ping 成功！主机 {host} 在网络上是可达的。")
    else:
        print(f"❌ Ping 失败。主机 {host} 不可达或阻止了 Ping 请求。")
        print("--- 检查结束 ---")
        return

    # --- 步骤 2: 检查特定 TCP 端口 ---
    print(f"\n[步骤 2/2] 正在检查 TCP 端口 {port} ...")
    if check_tcp_port(host, port):
        print(f"✅ 端口检查成功！服务在 {host}:{port} 上正在监听。")
    else:
        print(f"❌ 端口检查失败。主机可达，但端口 {port} 已关闭或被防火墙过滤。")
        
    print("--- 检查结束 ---")


# --- 使用示例 ---

if __name__ == "__main__":
    # 示例1：检查一个通常能ping通且端口开放的服务（假设您的树莓派IP为 192.168.1.10，且SSH服务已开启）
    # 请将下面的IP和端口换成您自己的树莓派地址和需要检查的端口
    RASPBERRY_PI_IP = "192.168.114.48" 
    SSH_PORT = 10000
    check_network_service(RASPBERRY_PI_IP, SSH_PORT)

    print("\n" + "="*40 + "\n")

    # 示例2：检查一个能ping通但端口很可能关闭的服务
    # check_network_service("google.com", 12345)

    # print("\n" + "="*40 + "\n")

    # 示例3：检查一个无法ping通的私有网络地址（通常会失败）
    # check_network_service("10.255.255.1", 80)
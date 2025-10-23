import asyncio
import socket # 仍然需要 socket 来捕获特定的错误
import time

# --- 配置 ---
# !!! 修改为您的 IND360 服务端口的 IP 地址 !!!
IND360_IP = '192.168.0.8' 
IND360_PORT = 1026
COMMAND = "SIX1\r\n" 
TIMEOUT = 5 
BUFFER_SIZE = 1024
# --- 配置结束 ---

# --- 解析函数 (与同步版本相同) ---
def parse_six1_response(response_str):
    """
    解析 SIX1 命令的响应字符串。
    响应格式: SIX1 Sts MinW CoZ Rep Calc PosE StepE MarkE Range TM Gross NET Tare Unit
    """
    parts = response_str.strip().split()
    if len(parts) < 15 or parts[0] != 'SIX1':
        print(f"错误：收到了意外的响应格式: {response_str}")
        return None
    try:
        status_code = parts[1]
        zero_center = parts[3] == 'Z' 
        tare_mode_code = parts[10] 
        gross_str = parts[11]
        net_str = parts[12]
        tare_str = parts[13]
        unit = parts[14]

        status_map = {'S': '稳定', 'D': '动态', '+': '过载', '-': '欠载', 'I': '无效值'}
        status = status_map.get(status_code, f'未知 ({status_code})')

        tare_mode_map = {'N': '无皮重', 'P': '预设皮重', 'M': '称量皮重'}
        tare_mode = tare_mode_map.get(tare_mode_code, f'未知 ({tare_mode_code})')

        gross = float(gross_str)
        net = float(net_str)
        tare = float(tare_str)

        return {
            "status": status, "zero_center": zero_center, "tare_mode": tare_mode,
            "gross": gross, "net": net, "tare": tare, "unit": unit
        }
    except (IndexError, ValueError) as e:
        print(f"错误：解析响应时出错: {e}\n原始响应: {response_str}")
        return None

# --- 异步读取函数 ---
async def read_ind360_weight_async(ip, port, command, timeout):
    """
    异步连接到 IND360，发送 MT-SICS 命令并接收响应。
    """
    reader, writer = None, None # 初始化 reader 和 writer
    try:
        # 1. 异步打开连接，应用超时
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), 
            timeout=timeout
        )
        while True:
            # 2. 发送命令 (编码为字节)
            writer.write(command.encode('ascii'))
            await writer.drain() # 等待缓冲区清空

            # 3. 异步接收响应 (字节), 应用超时
            response_bytes = await asyncio.wait_for(
                reader.read(BUFFER_SIZE), 
                timeout=timeout
            )

            # 解码响应
            response_str = response_bytes.decode('ascii')
            
            # 解析响应
            parsed_data = parse_six1_response(response_str)
            print(f"{time.asctime()} + {parsed_data["gross"]} kg")

    except asyncio.TimeoutError:
        print(f"错误：连接或接收超时 ({timeout} 秒)")
        return None
    except ConnectionRefusedError:
        print(f"错误：连接被拒绝。请检查 IP 地址和端口，以及设备是否正在监听。")
        return None
    except OSError as e: # 捕获更广泛的网络错误，例如 'No route to host'
        print(f"错误：网络错误: {e}")
        return None
    except Exception as e:
        print(f"错误：发生意外错误: {e}")
        return None
    finally:
        # 4. 异步关闭连接
        if writer:
            print("关闭连接。")
            writer.close()
            await writer.wait_closed()

# --- 主异步函数 ---
async def main():
    print("--- 开始异步读取 IND360 重量 ---")
    await read_ind360_weight_async(IND360_IP, IND360_PORT, COMMAND, TIMEOUT)

if __name__ == "__main__":
    # 运行主异步函数
    asyncio.run(main())
import snap7
from snap7.util import get_real
import time

# --- 配置信息 (保持不变) ---
PLC_IP = '192.168.0.1'      
RACK = 0
SLOT = 1
DB_NUMBER = 16
START_ADDRESS = 6
DATA_SIZE = 4
# ------------------------------------

# 1. 在循环外，创建客户端实例
plc = snap7.client.Client()

try:
    print(f"正在连接到 PLC at {PLC_IP}...")
    
    # 2. 在循环外，只连接一次
    plc.connect(PLC_IP, RACK, SLOT)
    
    # 检查连接是否真的成功
    if plc.get_connected():
        print("连接成功！已建立长连接，开始周期性读取数据...")

        # 3. 在一个循环中持续读取数据
        while True:
            try:
                # 从已建立的连接读取数据
                db_data = plc.db_read(DB_NUMBER, START_ADDRESS, DATA_SIZE)
                
                # 解析数据
                weight = get_real(db_data, 0)
                
                print(f"{time.asctime()} - 当前重量: {weight:.3f} kg")

            except Exception as e:
                # 如果在循环中发生读取错误 (例如网络瞬断), 打印错误但程序不退出
                print(f"读取数据时发生错误: {e}")
                print("将在下一个周期重试...")
            
            # 等待下一个读取周期
            time.sleep(.1)
            
    else:
        print("连接 PLC 失败，请检查网络和 PLC 设置。")

except KeyboardInterrupt:
    # 当用户按下 Ctrl+C 时，优雅地退出
    print("\n程序被用户中断。")
except Exception as e:
    # 捕捉连接时发生的致命错误
    print(f"发生连接错误或严重问题: {e}")

finally:
    # 4. 程序结束时 (无论正常退出还是异常中断)，都确保断开连接
    if plc.get_connected():
        plc.disconnect()
        print("已从 PLC 断开连接。")
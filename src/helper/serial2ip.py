import serial
import socket
import time
import sys

# --- 请在这里配置您的参数 ---

# 串口配置
if len(sys.argv) > 1:
    SERIAL_PORT = sys.argv[1]  # 从命令行参数获取串口名
else:
    raise Exception("Please provide the serial port name as a command line argument, e.g. /dev/pts/5 or COM10")




BAUD_RATE = 9600            # 波特率，必须与您的串口设备设置一致

# 网络目标配置
TARGET_IP = '127.0.0.1'   # 本机IP，如果是发送到另一台计算机，请填写对方的IP地址
TARGET_PORT = 12345       # 接收数据的计算机上监听的端口

# --- 配置结束 ---


def main():
    """
    主函数，循环监听串口并转发数据
    """
    print(f"正在尝试打开串口: {SERIAL_PORT}...")
    ser = None  # 初始化串口对象

    # 创建 UDP socket
    # AF_INET 表示使用 IPv4, SOCK_DGRAM 表示使用 UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"UDP Socket 已创建。将数据发往 {TARGET_IP}:{TARGET_PORT}")

    while True:
        try:
            # 如果串口未连接，则尝试连接
            if ser is None or not ser.is_open:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                print(f"成功连接到串口 {SERIAL_PORT}")

            # 从串口读取一行数据
            # readline() 会读取直到遇到换行符 '\n'
            line = ser.readline()

            # 如果读取到了数据
            if line:
                # 将读取到的 bytes 解码为 utf-8 字符串，并去除首尾的空白字符
                data_str = line.decode('utf-8').strip()
                
                if data_str:
                    print(f"从串口收到: '{data_str}'")
                    
                    # 将字符串编码回 bytes，然后通过 UDP 发送
                    sock.sendto(data_str.encode('utf-8'), (TARGET_IP, TARGET_PORT))
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

    # 清理资源
    if ser and ser.is_open:
        ser.close()
    sock.close()
    print("程序已退出。")


if __name__ == '__main__':
    main()
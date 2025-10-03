"""
virtual_mcu.py
==============

Simulates a virtual microcontroller that communicates with host over a serial port. It writes data to the serial port and reads commands from it. 
"""


import serial
import time
import random

# ====================================================================
# !! 重要 !!
# 修改这里的串口号为你创建的虚拟串口对中的一个
# Windows示例: PORT_NAME = 'COM11'
# Linux/macOS示例: PORT_NAME = '/dev/pts/6'
# ====================================================================
PORT_NAME = '/dev/pts/5'  

try:
    # 初始化串口
    ser = serial.Serial(PORT_NAME, 9600, timeout=0.1)
    print(f"虚拟微控制器已在 {PORT_NAME} 上启动...")
except serial.SerialException as e:
    print(f"错误: 无法打开串口 {PORT_NAME}. {e}")
    print("请确保虚拟串口工具(com0com/socat)正在运行，并且串口号正确。")
    exit()

# 模拟微控制器的内部状态
led_status = "OFF"
temperature = 25.0

# 主循环
while True:
    try:
        # 1. 模拟接收指令 (非阻塞)
        if ser.in_waiting > 0:
            # 读取一行指令，解码并去除首尾空白
            command = ser.readline().decode('utf-8').strip()
            if command:
                print(f"收到指令: '{command}'")

                # 根据指令更新状态
                if command == "LED_ON":
                    led_status = "ON"
                    ser.write(b"ACK:LED is now ON\n") # 发送确认信息
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


        # 2. 模拟定时发送数据 (例如每秒一次)
        # 模拟温度在25度附近波动
        temperature += random.uniform(-0.1, 0.1)
        # 构建数据字符串，以换行符结尾
        data_to_send = f"DATA,TEMP,{temperature:.2f}\n"

        # 写入串口
        ser.write(data_to_send.encode('utf-8'))
        print(f"发送数据: {data_to_send.strip()}")
        
        # 等待1秒
        time.sleep(0.001)

    except KeyboardInterrupt:
        print("程序被用户中断")
        break
    except Exception as e:
        print(f"发生错误: {e}")
        break

# 关闭串口
ser.close()
print("虚拟微控制器已关闭。")
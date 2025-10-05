"""
virtual_mcu.py
==============

This script writes data to a serial port. Coupled with a virtual port pairing tool (e.g. socat), we can create a "virtual serial port", with constantly incoming data.

The purpose is to simulates a virtual microcontroller that is communicating with a host through a serial port, so that we can test the main application without needing a physical microcontroller.  

To make it work, we first need to create a pair of connected virtual serial ports using socat (Linux/macOS):

```
socat -d -d pty,raw,echo=0 pty,raw,echo=0
```

The following output will show the created virtual ports:

```
2025/10/05 11:58:00 socat[13436] N PTY is /dev/pts/1
2025/10/05 11:58:00 socat[13436] N PTY is /dev/pts/7
2025/10/05 11:58:00 socat[13436] N starting data transfer loop with FDs [5,5] and [7,7]
```

In this example, we can use 

```
python virtual_mcu.py /dev/pts/1
```

to run the virtual mcu, and use `/dev/pts/7` in the main application to read the data. 
"""


import serial
import time
import random
import sys

# ====================================================================
# !! 重要 !!
# 修改这里的串口号为你创建的虚拟串口对中的一个
# Windows示例: PORT_NAME = 'COM11'
# Linux/macOS示例: PORT_NAME = '/dev/pts/6'
# ====================================================================

if len(sys.argv) > 1:
    PORT_NAME = sys.argv[1] 
else:
    raise Exception("Please provide the port name to write to, e.g. /dev/pts/6 or COM11")

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
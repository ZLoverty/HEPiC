import requests
import json
import websockets
import asyncio
from pprint import pprint

http = False
websocket = True
# 替换成你Klipper主机的IP地址
KLIPPER_HOST = "192.168.114.48" 

if http:
    
    # Moonraker默认运行在7125端口
    URL = f"http://{KLIPPER_HOST}:7125/printer/gcode/script"

    # 定义你想查询的对象和信息
    # 这里我们查询工具头(toolhead)的位置和挤出机(extruder)的温度
    gcode_script = """
    G91
    G1 E10 F300
    """
    params = {
        "script": gcode_script
    }
    try:
        # 发送GET请求
        response = requests.post(URL, params=params)
        response.raise_for_status()  # 如果请求失败 (例如404, 500), 会抛出异常

        # 解析返回的JSON数据
        # data = response.json()

        # 美化输出
        # print("成功获取打印机状态:")
        # print(json.dumps(data, indent=4))

        # temp = data['result']['status']['extruder']['temperature']
        # target_temp = data['result']['status']['extruder']['target']
        # print(f"\n当前工具头位置 (X, Y, Z, E): {position}")
        # print(f"当前喷头温度: {temp}°C / 目标: {target_temp}°C")


    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
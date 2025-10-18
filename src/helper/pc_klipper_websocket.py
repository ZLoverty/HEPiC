import asyncio
import json
import websockets
from pprint import pprint

# --- 配置 ---
# 修改这里为你运行Klipper和Moonraker的树莓派的IP地址或主机名
KLIPPER_HOST = "192.168.114.48" 
MOONRAKER_PORT = 7125

async def klipper_monitor(queue: asyncio.Queue):
    """
    生产者：连接到Moonraker的WebSocket，订阅对象，并将收到的数据放入队列。
    """
    uri = f"ws://{KLIPPER_HOST}:{MOONRAKER_PORT}/websocket"
    
    while True: # 无限重连循环
        try:
            print(f"正在尝试连接到 {uri}...")
            async with websockets.connect(uri) as websocket:
                print("WebSocket连接成功！")
                
                # 构造订阅请求
                # 我们想获取挤出机温度、热床温度和打印状态
                subscribe_message = {
                    "jsonrpc": "2.0",
                    "id": 2, # 一个随机的ID
                    "method": "printer.gcode.script",
                    "params": {
                        "script": "G91 E1 F2"
                    },
                }
                
                # subscribe_message = {
                #     "jsonrpc": "2.0",
                #     "method": "printer.objects.subscribe",
                #     "params": {
                #         "objects": {
                #             "extruder": ["temperature", "target"]
                #         }
                #     },
                #     "id": 1 # 一个随机的ID
                # }

                # 发送订阅请求
                await websocket.send(json.dumps(subscribe_message))
                print("已发送状态订阅请求...")

                # 监听来自服务器的消息
                async for message in websocket:
                    data = json.loads(message)
                    # 将收到的原始数据放入队列，交给消费者处理
                    await queue.put(data)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"连接断开或失败: {e}")
            print("将在5秒后尝试重连...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"发生未知错误: {e}")
            print("将在5秒后尝试重连...")
            await asyncio.sleep(5)


async def data_processor(queue: asyncio.Queue):
    """
    消费者：从队列中等待并获取数据，然后进行处理。
    """
    print("数据处理器已启动，等待数据...")
    while True:
        # 核心：在这里await，等待队列中有新数据
        data = await queue.get()

        # Moonraker的数据有两种主要类型：
        # 1. 对你请求的响应 (包含 "result" 键)
        # 2. 服务器主动推送的状态更新 (方法为 "notify_status_update")
        print(data)
        if "method" in data:
            if data["method"] == "notify_status_update":
                try:
                    temp = data["params"][0]["extruder"]["temperature"]
                    print(f"temp: {temp}")
                except:
                    print("temp: N/A")
        
        # 标记任务完成，这对于优雅退出很重要
        queue.task_done()

async def send_gcode():

    uri = f"ws://{KLIPPER_HOST}:{MOONRAKER_PORT}/websocket"

    async with websockets.connect(uri) as websocket:
        print("WebSocket连接成功！")
        
        # 构造订阅请求
        # 我们想获取挤出机温度、热床温度和打印状态
        gcode_message = {
            "id": 1234, # 一个随机的ID
            "method": "gcode/script",
            "params": {
                "script": "G91\nG1 E10 F300"
            },
        }

        await websocket.send(json.dumps(gcode_message))

async def main():
    q = asyncio.Queue()
    gcode_queue = asyncio.Queue()

    # 在后台启动生产者和消费者任务
    monitor_task = asyncio.create_task(klipper_monitor(q))
    processor_task = asyncio.create_task(data_processor(q))
    # await send_gcode()
    # 等待两个任务完成 (在这个例子中它们是无限循环，所以会一直运行)
    # 使用 aio.wait 来处理正常退出和异常
    done, pending = await asyncio.wait(
        [monitor_task, processor_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 如果有任务结束（可能因为异常），取消其他任务并退出
    for task in pending:
        task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断，正在退出...")
from qasync import asyncSlot
from PySide6.QtCore import QObject, Signal, Slot
import asyncio
import websockets
import logging
import json
import random
import sys
import numpy as np
import os
import requests

class KlipperWorker(QObject):
    """
    Handle the communications with Klipper (Moonraker). In the essence, we are always talking to Moonraker through the web interface using either websocket or http request. 

    For the convenience of testing
    """

    connection_status = Signal(str)
    hotend_temperature = Signal(float)
    gcode_error = Signal(str)
    gcode_response = Signal(str)

    def __init__(self, host, port, query_delay=1):
        super().__init__()

        # connection / args
        self.host = host
        self.port = port
        self.uri = f"ws://{self.host}:{self.port}/websocket"
        self.query_delay = query_delay
        self.logger = logging.getLogger(__name__)

        # status / data
        self.is_running = True
        self._init_data()
        
        # message queue
        self.message_queue = asyncio.Queue()
        
        # task handlers
        self.listener_task = None
        self.processor_task = None
        self.query_task = None

    def _init_data(self):
        # initiate internal data container
        self.active_feedrate_mms = 0
        self.hotend_temperature = np.nan
        self.target_hotend_temperature = np.nan
        self.progress = 0.0
        self.file_position = 0
        self.active_gcode = ""

    @asyncSlot()
    async def run(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        while self.is_running:
            try:
                self.logger.info(f"正在连接 Klipper {self.uri} ...")
                self.connection_status.emit(f"正在连接 Klipper {self.uri} ...")
                # async with asyncio.wait_for(websockets.connect(self.uri), timeout=2.0) as websocket:
                async with websockets.connect(self.uri, open_timeout=2.0) as websocket:
                    self.logger.info("Klipper 连接成功！")
                    self.connection_status.emit("Klipper 连接成功！")

                    # clear message queue if it's not empty
                    while not self.message_queue.empty():
                        try: self.message_queue.get_nowait()
                        except: pass

                    self.listener_task = asyncio.create_task(self.message_listener(websocket))
                    self.processor_task = asyncio.create_task(self.data_processor(websocket))
                    self.query_task = asyncio.create_task(self.query_klipper(websocket))
                    
                    done, pending = await asyncio.wait(
                        [self.listener_task, self.processor_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    self.logger.warning("连接已中断，正在清理任务...")
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
            
            except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
                self.logger.error(f"Klipper 连接失败")
            except TimeoutError as e:
                self.logger.error("Klipper 连接超时，检查服务器是否开启")
                self.connection_status.emit("Klipper 连接超时，检查服务器是否开启")

            # 如果 is_running 依然为 True，说明是意外断开，需要重连
            if self.is_running:
                self.connection_status.emit("连接断开，3秒后重连...")
                self.logger.info("将在 3 秒后尝试重连...")
                await asyncio.sleep(3)
            
    async def message_listener(self, websocket):
        self.logger.info("消息监听器已启动")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.message_queue.put(data)
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON 解析失败: {e}. 消息体: {message}")
                except Exception as e:
                    self.logger.error(f"放入队列时出错: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"监听器: WebSocket 连接已关闭 (代码: {e.code}, 原因: {e.reason})")
        except Exception as e:
            # 捕获其他所有未知错误
            self.logger.error(f"消息监听器崩溃: {e}")
        finally:
            self.logger.debug("消息监听器已退出")

    @asyncSlot(str)
    async def send_gcode(self, gcode):
        """接收来自主线程的 gcode，并发给 Klipper。本程序会将整个 gcode 文本一次性发送给 Klipper.
        
        Parameters
        ----------
        gcode : str
            gcode string
        """
        self.gcode = gcode
        
        gcode_message = {
            "jsonrpc": "2.0",
            "id": 3, 
            "method": "printer.gcode.script",
            "params": {
                "script": self.gcode,
            },
        }

        await self.message_queue.put(gcode_message)
        self.logger.debug("put gcode message into queue: {self.gcode[:30]} ..")
       
    async def data_processor(self, websocket):
        """
        消费者：从队列中等待并获取数据，然后进行处理。本函数需要处理多种与 Klipper 的通讯信息，至少包含 i) 订阅回执，ii) gcode 发送。
        """
        self.logger.info("数据处理器已启动，等待数据...")
        while True:
            # 核心：在这里await，等待队列中有新数据
            data = await self.message_queue.get()

            # Moonraker的数据的主要类型：
            # 1. 对你请求的响应 (包含 "result" 键)
            # 2. 服务器主动推送的状态更新 (方法为 "notify_status_update")
            # 3. 我发送的 gcode 请求，包含 "method" 键，方法为 "printer.gcode.script"
            
            if "method" in data: 
                if data["method"] in ["printer.gcode.script", "printer.objects.subscribe", "printer.objects.query", "printer.emergency_stop"]: # 发送 G-code
                    await websocket.send(json.dumps(data))
                elif data["method"] == "notify_gcode_response":
                    response = data.get("params")[0]
                    self.gcode_response.emit(response)
                else:
                    self.logger.debug(data)
            elif "error" in data:
                    err_msg = f"Error {data["error"]["code"]}: {data["error"]["message"]}"
                    self.logger.error(f"error message: {err_msg}")
                    self.gcode_error.emit(err_msg)
                    self.connection_status.emit(err_msg)
            elif "result" in data:
                self.logger.debug(data)     
                if "id" in data:
                    if data["id"] == 2:
                        sub_msg = data.get("result", {}).get("status", {})
                        self.hotend_temperature = sub_msg.get("extruder", {}).get("temperature", np.nan)
                        self.target_hotend_temperature = sub_msg.get("extruder", {}).get("target", np.nan)
                        self.active_feedrate_mms = sub_msg.get("motion_report", {}).get("live_extruder_velocity")
                        self.progress = sub_msg.get("virtual_sdcard", {}).get("progress")
                        self.file_position = sub_msg.get("virtual_sdcard", {}).get("file_position")
            else:
                self.logger.debug(data)

            # 标记任务完成，这对于优雅退出很重要
            self.message_queue.task_done()

    @Slot()
    def stop(self):
        """停止线程"""
        self.is_running = False
        if self.listener_task:
            self.listener_task.cancel()
        if self.processor_task:
            self.processor_task.cancel()

    @asyncSlot(float)
    async def set_temperature(self, target):
        gcode_message = {
            "jsonrpc": "2.0",
            "id": 104, 
            "method": "printer.gcode.script",
            "params": {
                "script": f"M104 S{target}",
            },
        }
        await self.message_queue.put(gcode_message)
        self.logger.debug("set temperature to: {target} C")

    async def subscribe_printer_status(self):
        subscribe_message = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "extruder": None,
                    "print_stats": None,
                    "motion_report": None,
                    "toolhead": None,
                    "virtual_sdcard": None
                }
            },
            "id": 1
        }
        
        await self.message_queue.put(subscribe_message)
    
    async def query_klipper(self, websocket):
        query_msg = {
            "jsonrpc": "2.0",
            "method": "printer.objects.query",
            "params": {
                "objects": {
                    "extruder": None,
                    "motion_report": None,
                    "virtual_sdcard": None
                }
            },
            "id": 2
        }
        while True:
            await self.message_queue.put(query_msg)
            await asyncio.sleep(self.query_delay)

    def upload_gcode_to_klipper(self, file_path, print_after_upload=True):
        """
        上传 G-code 文件到 Klipper (Moonraker)。
        
        :param ip_address: 上位机 (树莓派) 的 IP 地址
        :param file_path: 本地 G-code 文件的路径
        :param print_after_upload: 是否上传后立即开始打印 (True/False)
        """
        
        # Moonraker 的上传 API 端点
        url = f"http://{self.host}/server/files/upload"
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            self.logger.error(f"错误: 找不到文件 {file_path}")
            return

        # 获取文件名
        filename = os.path.basename(file_path)

        # 准备 Payload
        # 'root': 通常是 'gcodes'，表示上传到 G-code 文件夹
        data = {
            'root': 'gcodes',
            'print': 'true' if print_after_upload else 'false'
        }

        try:
            with open(file_path, 'rb') as f:
                # 构建 multipart/form-data
                files = {'file': (filename, f)}
                
                self.logger.info(f"正在上传 {filename} 到 {self.host}...")
                response = requests.post(url, data=data, files=files)
                
                # 检查响应
                if response.status_code in [200, 201]:
                    self.logger.info("上传成功！")
                    self.logger.info("服务器响应:", response.json())
                else:
                    self.logger.info(f"上传失败，状态码: {response.status_code}")
                    self.logger.info("错误信息:", response.text)
                    
        except requests.exceptions.RequestException as e:
            self.logger.error(f"连接错误: {e}")
        
        finally:
            # delete the temporary gcode file
            os.remove(file_path)

    @asyncSlot()
    async def restart_firmware(self):
        self.logger.info("Restarting firmware ...")
        await self.send_gcode("FIRMWARE_RESTART")

    @asyncSlot()
    async def emergency_stop(self):
        """
        发送最高优先级的急停指令
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "printer.emergency_stop", # 注意：不是 gcode.script
            "id": 0
        }
        self.logger.warning("!!! SENDING EMERGENCY STOP !!!")
        await self.message_queue.put(payload)

    @Slot()
    def set_active_gcode(self, gcode):
        self.active_gcode = gcode
    
class MockMoonrakerServer:
    """
    一个虚拟的 Moonraker WebSocket 服务器，用于测试 Klipper/Moonraker 客户端。
    """
    
    def __init__(self, host, port, logger=None):
        self.host = host
        self.port = port
        self.server = None
        # 存储每个连接的订阅状态
        self.client_subscriptions = {}
        
        # 我们的“虚拟Klipper打印机”的完整状态
        self.printer_state = {
            "print_stats": {
                "state": "standby",
                "filename": "",
                "total_duration": 0,
                "print_duration": 0,
                "filament_used": 0,
            },
            "gcode_move": {
                "gcode_position": [0.0, 0.0, 0.0, 0.0], # X, Y, Z, E
                "homing_origin": [0.0, 0.0, 0.0, 0.0],
                "speed": 100,
            },
            "extruder": {
                "temperature": 25.0,
                "target": 0.0,
                "power": 0.0,
            },
            "heater_bed": {
                "temperature": 25.0,
                "target": 0.0,
                "power": 0.0,
            },
            "toolhead": {
                "position": [0.0, 0.0, 0.0, 0.0], # 实时位置
                "homed_axes": "",
            },
            "webhooks": { # 客户端启动时经常查询这个
                "state": "ready"
            }
        }

        self.logger = logger or logging.getLogger(__name__)

        self.logger.info("虚拟打印机状态已初始化。")

    async def start(self):
        """启动 WebSocket 服务器"""
        self.logger.info(f"启动 Mock Moonraker 服务器于 ws://{self.host}:{self.port}")
        self.server = await websockets.serve(self.handler, self.host, self.port)
        await self.server.wait_closed()

    async def stop(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.logger.info("Mock Moonraker 服务器已停止。")

    async def handler(self, websocket):
        """处理单个客户端连接"""
        
        client_id = websocket.remote_address
        self.logger.info(f"客户端 {client_id} 已连接。")
        self.client_subscriptions[websocket] = set()
        
        # 为这个客户端启动一个模拟器任务
        simulation_task = asyncio.create_task(self.simulate_printer_activity(websocket))

        try:
            # 循环接收来自客户端的消息
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"客户端 {client_id} 断开连接: {e}")
        except Exception as e:
            self.logger.error(f"处理客户端 {client_id} 消息时出错: {e}", exc_info=True)
        finally:
            # 清理
            simulation_task.cancel()
            del self.client_subscriptions[websocket]
            self.logger.info(f"客户端 {client_id} 清理完毕。")

    async def process_message(self, websocket, message):
        """解析并分发 JSON-RPC 消息"""
        try:
            data = json.loads(message)
            self.logger.debug(f"收到 C->S: {data}")
        except json.JSONDecodeError:
            self.logger.error(f"收到无效的JSON: {message}")
            return

        # 获取请求 ID，通知消息没有 ID
        request_id = data.get("id")
        method = data.get("method")
        params = data.get("params", {})

        response = None

        if method == "printer.objects.subscribe":
            # --- 模拟订阅 ---
            # 1. 注册订阅
            objects_to_subscribe = params.get("objects", {}).keys()
            self.client_subscriptions[websocket].update(objects_to_subscribe)
            self.logger.info(f"客户端订阅了: {objects_to_subscribe}")
            
            # 2. 发送订阅成功的 "result"
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "objects": list(self.client_subscriptions[websocket])
                }
            }
            await self.send(websocket, response)
            
            # 3. 立即发送一次完整的状态更新通知
            await self.notify_status_update(websocket)

        elif method == "printer.objects.query":
            # --- 模拟查询 ---
            objects_to_query = params.get("objects", {}).keys()
            self.logger.info(f"客户端查询: {objects_to_query}")
            
            status = self.get_objects_state(objects_to_query)
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "status": status
                }
            }
            await self.send(websocket, response)
            
        elif method == "printer.gcode.script":
            # --- 模拟 G-code ---
            script = params.get("script", "").strip()
            self.logger.info(f"正在'运行' G-code: {script}")
            
            # 模拟 G-code 效果
            if "G28" in script: # 归位
                self.printer_state["toolhead"]["homed_axes"] = "xyz"
                self.printer_state["toolhead"]["position"] = [0.0, 0.0, 0.0, 0.0]
                self.printer_state["gcode_move"]["gcode_position"] = [0.0, 0.0, 0.0, 0.0]
            elif script.startswith("M104"): # 设置热端温度
                temp = float(script.split("S")[1])
                self.printer_state["extruder"]["target"] = temp
            elif script.startswith("M140"): # 设置热床温度
                temp = float(script.split("S")[1])
                self.printer_state["heater_bed"]["target"] = temp
            
            # 1. 发送 G-code 响应
            gcode_response = {
                "jsonrpc": "2.0",
                "method": "notify_gcode_response",
                "params": [f"// G-code 响应: {script} (Mock)"]
            }
            await self.send(websocket, gcode_response)
            
            # 2. 发送 "ok" result
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": "ok"
            }
            await self.send(websocket, response)
            
            # 3. 立即发送状态更新
            await self.notify_status_update(websocket)

        elif method == "server.info":
            # --- 模拟服务器信息 ---
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "klipper_version": "v0.12.0-mock",
                    "moonraker_version": "v0.8.0-mock",
                    "websocket_count": len(self.client_subscriptions),
                }
            }
            await self.send(websocket, response)
            
        else:
            # --- 未知方法 ---
            self.logger.warning(f"收到未知方法: {method}")
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Method not found"
                }
            }
            await self.send(websocket, response)

    async def notify_status_update(self, websocket):
        """向客户端发送其订阅对象的状态更新"""
        if websocket not in self.client_subscriptions:
            return # 客户端可能刚断开

        subscribed_objects = self.client_subscriptions[websocket]
        if not subscribed_objects:
            return # 客户端什么都没订阅

        status_update = self.get_objects_state(subscribed_objects)
        
        notification = {
            "jsonrpc": "2.0",
            "method": "notify_status_update",
            "params": [status_update]
        }
        await self.send(websocket, notification)

    def get_objects_state(self, object_keys):
        """从主状态中提取特定对象"""
        return {
            key: self.printer_state[key]
            for key in object_keys
            if key in self.printer_state
        }

    async def simulate_printer_activity(self, websocket):
        """
        后台任务，模拟打印机状态随时间变化。
        这会触发 notify_status_update。
        """
        try:
            while True:
                await asyncio.sleep(2.0) # 每2秒更新一次状态

                # 1. 模拟温度变化 (简单逼近目标)
                for key in ["extruder", "heater_bed"]:
                    target = self.printer_state[key]["target"]
                    current = self.printer_state[key]["temperature"]
                    if target > current:
                        self.printer_state[key]["temperature"] = min(current + 1.5, target)
                    elif target < current:
                        self.printer_state[key]["temperature"] = max(current - 1.5, target)
                
                # 2. 模拟打印机移动 (如果归位了)
                if "xyz" in self.printer_state["toolhead"]["homed_axes"]:
                    new_x = self.printer_state["toolhead"]["position"][0] + random.uniform(-1, 1)
                    new_y = self.printer_state["toolhead"]["position"][1] + random.uniform(-1, 1)
                    self.printer_state["toolhead"]["position"][0] = max(0, min(new_x, 250)) # 假设 250mm 床
                    self.printer_state["toolhead"]["position"][1] = max(0, min(new_y, 250))
                    # 确保 gcode_position 也更新
                    self.printer_state["gcode_move"]["gcode_position"] = self.printer_state["toolhead"]["position"]

                # 3. 向客户端发送更新
                await self.notify_status_update(websocket)

        except asyncio.CancelledError:
            self.logger.info(f"客户端 {websocket.remote_address} 的模拟器已停止。")
        except Exception as e:
            self.logger.error(f"模拟器任务出错: {e}", exc_info=True)
    
    async def send(self, websocket, data):
        """统一的发送方法，带日志记录"""
        try:
            message = json.dumps(data)
            self.logger.info(f"发送 S->C: {message}")
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning(f"尝试发送到已关闭的连接: {data}")
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}", exc_info=True)

async def _test_klipper_worker():
    HOST = "192.168.22.65"
    PORT = 7125
    klipper_worker = KlipperWorker(HOST, PORT)
    # moonraker_server = MockMoonrakerServer(HOST, PORT)
    # moonraker_task = asyncio.create_task(moonraker_server.start())
    klipper_task = klipper_worker.run()

    await asyncio.sleep(1)
    print("test send gcode ...")
    await klipper_worker.send_gcode("G28 ; home all axes")
    print("\n" + "-"*40 + "\n")

    await asyncio.sleep(1)
    print("test set temperature ...")
    await klipper_worker.set_temperature(200)
    print("\n" + "-"*40 + "\n")

    await asyncio.sleep(1)
    print("test send subscribe message ...")
    await klipper_worker.subscribe_printer_status()

    await asyncio.sleep(5)
    print("\n" + "-"*40 + "\n")

    print("test upload gcode file ...")
    file_path = "tmp.gcode"
    gcode = """
    M117 test1 
    M117 test2
    """
    with open(file_path, "w") as f:
        f.write(gcode)
    klipper_worker.upload_gcode_to_klipper(file_path, print_after_upload=False)
    os.remove(file_path)
    await asyncio.sleep(2)
    print("\n" + "-"*40 + "\n")

async def main():
    # print("test gcode mapper ...")
    # _test_gcode_mapper()

    # await asyncio.sleep(1)
    print("test klipper worker ...")
    await _test_klipper_worker()
    

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("程序被用户中断。")
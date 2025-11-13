from qasync import asyncSlot
from PySide6.QtCore import QObject, Signal
import asyncio
import websockets
import logging
import json
import bisect
import time
import random
import sys
import numpy as np

class KlipperWorker(QObject):
    """
    Handle the communications with Klipper (Moonraker). In the essence, we are always talking to Moonraker through the web interface using either websocket or http request. 

    For the convenience of testing
    """

    connection_status = Signal(str)
    hotend_temperature = Signal(float)
    current_step_signal = Signal(int)
    gcode_error = Signal(str)
    sigPrintStats = Signal(dict)

    def __init__(self, host, port, logger=None):
        super().__init__()

        # connection
        self.host = host
        self.port = port
        self.uri = f"ws://{self.host}:{self.port}/websocket"
        
        # status / flags
        self.is_running = True
        self.active_feedrate_mms = 0
        self.active_gcode = None
        self.hotend_temperature = np.nan

        # message queue
        self.message_queue = asyncio.Queue()

        # logger
        self.logger = logger or logging.getLogger(__name__)
        
    @asyncSlot()
    async def run(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        try:
            self.logger.info(f"正在连接 Klipper {self.uri} ...")
            self.connection_status.emit(f"正在连接 Klipper {self.uri} ...")
            # async with asyncio.wait_for(websockets.connect(self.uri), timeout=2.0) as websocket:
            async with websockets.connect(self.uri, open_timeout=2.0) as websocket:
                self.logger.info("Klipper 连接成功！")
                self.connection_status.emit("Klipper 连接成功！")
                
                await self.subscribe_printer_status()
                self.logger.info("已发送状态订阅请求...")

                listener_task = asyncio.create_task(self.message_listener(websocket))
                processor_task = asyncio.create_task(self.data_processor(websocket))

                await asyncio.gather(listener_task, processor_task)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            self.logger.error(f"Klipper 连接失败")
        except TimeoutError as e:
            self.logger.error("Klipper 连接超时，检查服务器是否开启")
            self.connection_status.emit("Klipper 连接超时，检查服务器是否开启")

    async def message_listener(self, websocket):
        self.logger.debug("消息监听器已启动")
        try:
            async for message in websocket:
                # print(f"--- [DEBUG] 收到原始消息: {message}") # <--- 增加原始打印
                try:
                    data = json.loads(message)
                    await self.message_queue.put(data)
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON 解析失败: {e}. 消息体: {message}")
                except Exception as e:
                    self.logger.error(f"放入队列时出错: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"--- [DEBUG] 监听器: WebSocket 连接已关闭 (代码: {e.code}, 原因: {e.reason}) ---")
        except Exception as e:
            # 捕获其他所有未知错误
            self.logger.error(f"!!! [ERROR] 消息监听器崩溃: {e}")
        finally:
            self.logger.debug("--- [DEBUG] 消息监听器已退出 ---")
            self.is_running = False # 确保其他循环也能退出

    @asyncSlot(str)
    async def send_gcode(self, gcode):
        """接收来自主线程的 gcode，并发给 Klipper。本程序会将整个 gcode 文本一次性发送给 Klipper.
        
        Parameters
        ----------
        gcode : str
            gcode string, can be one-liner or multi-liner
        """
        self.gcode = gcode
        
        gcode_message = {
            "jsonrpc": "2.0",
            "id": 12345, 
            "method": "printer.gcode.script",
            "params": {
                "script": self.gcode,
            },
        }

        await self.message_queue.put(gcode_message)
        self.logger.debug("put gcode message into queue: {self.gcode[:30]} ..")

        # create mapper
        # self.gcode_mapper = GcodePositionMapper(self.gcode)
       
    async def data_processor(self, websocket):
        """
        消费者：从队列中等待并获取数据，然后进行处理。本函数需要处理多种与 Klipper 的通讯信息，至少包含 i) 订阅回执，ii) gcode 发送。
        """
        print("数据处理器已启动，等待数据...")
        while True:
            # 核心：在这里await，等待队列中有新数据
            data = await self.message_queue.get()

            # Moonraker的数据的主要类型：
            # 1. 对你请求的响应 (包含 "result" 键)
            # 2. 服务器主动推送的状态更新 (方法为 "notify_status_update")
            # 3. 我发送的 gcode 请求，包含 "method" 键，方法为 "printer.gcode.script"
            
            if "method" in data: 
                if data["method"] == "notify_status_update": # 判断是否是状态回执
                    try:
                        sub_msg = data["params"][0]
                        print(sub_msg)
                    except Exception as e:
                        print(f"Unknown error: {e}")
                        continue

                    hotend_temperature = sub_msg.get("extruder", {}).get("temperature")    
                    if hotend_temperature:
                        self.hotend_temperature = hotend_temperature

                    active_feedrate_mms = sub_msg.get("motion_report", {}).get("live_extruder_velocity")
                    if active_feedrate_mms:
                        self.active_feedrate_mms = active_feedrate_mms
                    
                    if "print_stats" in sub_msg:
                        self.sigPrintStats.emit(sub_msg["print_stats"])
                elif data["method"] == "printer.gcode.script": # 发送 G-code
                    await websocket.send(json.dumps(data))
                elif data["method"] == "printer.objects.subscribe": # 发送查询请求
                    await websocket.send(json.dumps(data))
                    self.logger.info("已发送状态订阅请求...")
                elif data["method"] == "notify_proc_stat_update":
                    pass
                elif data["method"] == "notify_gcode_response":
                    self.gcode_error.emit(data["params"][0])
                else:
                    print(data)
            elif "result" in data:
                print(data)
                if "error" in data:
                    self.gcode_error.emit(f"{data["error"]["code"]}: {data["error"]["message"]}")
                elif "id" in data:
                    try:
                        self.file_position = data["result"].get("status", {}).get("virtual_sdcard", {}).get("file_position")
                    except Exception as e:
                        print(f"读取文件位置发生未知错误: {e}")
                    try:
                        self.progress = data["result"].get("status", {}).get("virtual_sdcard", {}).get("progress")
                    except Exception as e:
                        print(f"读取打印进度发生未知错误: {e}")
                    try:
                        self.active_feedrate_mms = data["result"].get("status", {}).get("gcode_move", {}).get("speed")
                    except Exception as e:
                        print(f"读取打印速度发生未知错误: {e}")
            else:
                print(data)

            # 标记任务完成，这对于优雅退出很重要
            self.message_queue.task_done()

    @asyncSlot()
    async def stop(self):
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

class GcodePositionMapper:
    """
    此类用于将 Klipper 的 file_position (字节偏移量)
    高效地映射回 G-code 文件的行号。
    """
    
    def __init__(self, gcode_content: str):
        print("正在构建 G-code 字节偏移量映射表...")
        self.gcode_content = gcode_content
        # self.line_start_offsets 存储 *每一行* 的 *起始字节偏移量*
        # 列表的索引 0 对应行号 1, 索引 1 对应行号 2...
        self.line_start_offsets = []
        self.total_lines = 0
        
        self._build_map()
        print(f"映射表构建完毕。总行数: {self.total_lines}, 总字节: {self.total_bytes}")

    def _build_map(self):
        """
        遍历 G-code 字符串，填充 line_start_offsets 列表。
        必须按“字节”计算，而不是“字符”。
        """
        current_byte_offset = 0
        
        # 我们按行分割字符串，保留换行符
        for line in self.gcode_content.splitlines(True):
            # 将此行的起始字节偏移量添加到列表中
            self.line_start_offsets.append(current_byte_offset)
            
            # 计算此行（包括 \n）的 *字节* 长度，并累加
            # Klipper (Python 3) 默认使用 UTF-8
            current_byte_offset += len(line.encode('utf-8'))
        
        self.total_lines = len(self.line_start_offsets)
        self.total_bytes = current_byte_offset

    def get_line_number(self, target_byte_position: int) -> int:
        """
        使用二分查找 (bisect) 来高效地找到对应的行号。
        
        bisect_right 在排序列表中找到一个插入点，该插入点
        位于所有小于或等于 target_byte_position 的条目之后。
        
        这完美地对应了我们的需求：
        - offsets = [0, 10, 25] (第1行在0, 第2行在10, 第3行在25)
        - target = 0  -> bisect_right(offsets, 0)  -> 1 (第1行)
        - target = 9  -> bisect_right(offsets, 9)  -> 1 (第1行)
        - target = 10 -> bisect_right(offsets, 10) -> 2 (第2行)
        - target = 26 -> bisect_right(offsets, 26) -> 3 (第3行)
        
        返回的是 1-based 的行号。
        """
        if target_byte_position < 0:
            return 1
            
        # bisect_right 返回的是 1-based 的索引（即行号）
        line_number = bisect.bisect_right(self.line_start_offsets, target_byte_position)
        
        # 确保不会返回一个不存在的行号（例如，如果 Klipper 报告的位置 > 文件总字节）
        return min(line_number, self.total_lines)
    

def _test_gcode_mapper():
    # --- 演示如何使用 ---

    # 1. 假设这是您上传到 Klipper 的 G-code 文件内容
    gcode_file_content = """
    G21 ; 使用毫米
    G90 ; 绝对坐标
    M107 ; 关闭风扇

    ; 一个包含非 ASCII 字符的注释 (测试 UTF-8)
    ; 注释：你好世界
    G28 ; 归位

    M140 S60 ; 设置热床 (不等待)
    G1 X10 Y10 F3000
    G1 X20 Y10
    G1 X20 Y20
    G1 X10 Y20
    M105
    """

    # 2. (在您的客户端) 文件上传时，创建映射器实例
    # 这一步（预处理）应该只做一次。
    start_time = time.perf_counter()
    mapper = GcodePositionMapper(gcode_file_content)
    end_time = time.perf_counter()
    print(f"构建映射表耗时: {(end_time - start_time) * 1000:.4f} 毫秒")

    print("-" * 30)

    # 3. (在您的 Websocket 监听器中) 模拟从 Klipper 收到 file_position
    #    您会实时调用 get_line_number()
    klipper_positions_stream = [
        0, 10, 25, 30, 75, 100, 
        160, 178, 195, 212, 229, 235
    ]

    print("模拟 Klipper 实时 `file_position` 更新：\n")
    for pos in klipper_positions_stream:
        line_num = mapper.get_line_number(pos)
        
        # 为了演示，我们同时获取该行的内容
        # 注意：self.line_start_offsets 的索引是 0-based (line_num - 1)
        line_content = gcode_file_content.splitlines()[line_num - 1].strip()
        
        print(f"Klipper 报告: file_position = {pos:3d}  ->  客户端映射到: 行 {line_num:2d} ({line_content})")
        time.sleep(0.5)

    print("\n--- 模拟结束 ---")

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
    HOST = "127.0.0.1"
    PORT = 7125
    klipper_worker = KlipperWorker(HOST, PORT)
    moonraker_server = MockMoonrakerServer(HOST, PORT)
    moonraker_task = asyncio.create_task(moonraker_server.start())
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
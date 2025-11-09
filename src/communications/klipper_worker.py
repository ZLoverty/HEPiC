from qasync import asyncSlot
from PySide6.QtCore import QObject, Signal
import asyncio
import websockets
import logging
import json
import bisect
import time

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
        self.active_feedrate_mms = None
        self.active_gcode = None
        self.hotend_temperature = None

        # message queue
        self.message_queue = asyncio.Queue()

        # logger
        self.logger = logger or logging.getLogger(__name__)
        
    @asyncSlot()
    async def run(self):
        """Asyncio 事件循环，处理 WebSocket 连接和通信"""
        try:
            print(f"正在连接 Klipper {self.uri} ...")
            self.connection_status.emit(f"正在连接 Klipper {self.uri} ...")
            # async with asyncio.wait_for(websockets.connect(self.uri), timeout=2.0) as websocket:
            async with websockets.connect(self.uri, open_timeout=2.0) as websocket:
                print("Klipper 连接成功！")
                self.connection_status.emit("Klipper 连接成功！")
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

                # 发送订阅请求
                await websocket.send(json.dumps(subscribe_message))
                print("已发送状态订阅请求...")

                listener_task = asyncio.create_task(self.message_listener(websocket))
                processor_task = asyncio.create_task(self.data_processor(websocket))

                await asyncio.gather(listener_task, processor_task)

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"Klipper 连接失败")
        except TimeoutError as e:
            print("Klipper 连接超时，检查服务器是否开启")
            self.connection_status.emit("Klipper 连接超时，检查服务器是否开启")

    async def message_listener(self, websocket):
        print("--- [DEBUG] 消息监听器已启动 ---")
        try:
            async for message in websocket:
                # print(f"--- [DEBUG] 收到原始消息: {message}") # <--- 增加原始打印
                try:
                    data = json.loads(message)
                    await self.message_queue.put(data)
                except json.JSONDecodeError as e:
                    print(f"!!! [ERROR] JSON 解析失败: {e}. 消息体: {message}")
                except Exception as e:
                    print(f"!!! [ERROR] 放入队列时出错: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            print(f"--- [DEBUG] 监听器: WebSocket 连接已关闭 (代码: {e.code}, 原因: {e.reason}) ---")
        except Exception as e:
            # 捕获其他所有未知错误
            print(f"!!! [ERROR] 消息监听器崩溃: {e}")
        finally:
            print("--- [DEBUG] 消息监听器已退出 ---")
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

        # create mapper
        self.gcode_mapper = GcodePositionMapper(self.gcode)
       
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
                        self.file_position = data["result"]["status"]["virtual_sdcard"]["file_position"]
                    except Exception as e:
                        print(f"读取文件位置发生未知错误: {e}")
                    try:
                        self.progress = data["result"]["status"]["virtual_sdcard"]["progress"]
                    except Exception as e:
                        print(f"读取打印进度发生未知错误: {e}")
                    try:
                        self.active_feedrate_mms = data["result"]["status"]["gcode_move"]["speed"]
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

    @asyncSlot()
    async def query_status(self):
        subscribe_message = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "extruder": ["temperature"],
                    "virtual_sdcard": ["file_position", "progress"],
                    "gcode_move": ["speed"]
                }
            },
            "id": 1 # 一个随机的ID
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

async def main():
    print("test gcode mapper ...")
    _test_gcode_mapper()

    await asyncio.sleep(1)
    print("test klipper worker ...")

    

if __name__ == "__main__":
    main()
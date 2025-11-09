import asyncio
import json
import logging
import random
import websockets

# --- 配置日志 ---
# 这对于调试你的 KlipperWorker 至关重要
logging.basicConfig(
    level=logging.INFO,
    format="[MockServer] %(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("MockServer")

class MockMoonrakerServer:
    """
    一个虚拟的 Moonraker WebSocket 服务器，用于测试 Klipper/Moonraker 客户端。
    """
    
    def __init__(self, host, port):
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
        log.info("虚拟打印机状态已初始化。")

    async def start(self):
        """启动 WebSocket 服务器"""
        log.info(f"启动 Mock Moonraker 服务器于 ws://{self.host}:{self.port}")
        self.server = await websockets.serve(self.handler, self.host, self.port)
        await self.server.wait_closed()

    async def stop(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            log.info("Mock Moonraker 服务器已停止。")

    async def handler(self, websocket):
        """处理单个客户端连接"""
        
        client_id = websocket.remote_address
        log.info(f"客户端 {client_id} 已连接。")
        self.client_subscriptions[websocket] = set()
        
        # 为这个客户端启动一个模拟器任务
        simulation_task = asyncio.create_task(self.simulate_printer_activity(websocket))

        try:
            # 循环接收来自客户端的消息
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed as e:
            log.warning(f"客户端 {client_id} 断开连接: {e}")
        except Exception as e:
            log.error(f"处理客户端 {client_id} 消息时出错: {e}", exc_info=True)
        finally:
            # 清理
            simulation_task.cancel()
            del self.client_subscriptions[websocket]
            log.info(f"客户端 {client_id} 清理完毕。")

    async def process_message(self, websocket, message):
        """解析并分发 JSON-RPC 消息"""
        try:
            data = json.loads(message)
            log.info(f"收到 C->S: {data}")
        except json.JSONDecodeError:
            log.error(f"收到无效的JSON: {message}")
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
            log.info(f"客户端订阅了: {objects_to_subscribe}")
            
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
            log.info(f"客户端查询: {objects_to_query}")
            
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
            log.info(f"正在'运行' G-code: {script}")
            
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
            log.warning(f"收到未知方法: {method}")
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
            log.info(f"客户端 {websocket.remote_address} 的模拟器已停止。")
        except Exception as e:
            log.error(f"模拟器任务出错: {e}", exc_info=True)
    
    async def send(self, websocket, data):
        """统一的发送方法，带日志记录"""
        try:
            message = json.dumps(data)
            log.info(f"发送 S->C: {message}")
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            log.warning(f"尝试发送到已关闭的连接: {data}")
        except Exception as e:
            log.error(f"发送消息时出错: {e}", exc_info=True)


# --- 如何运行这个 Mock Server ---
async def main():
    HOST = "127.0.0.1"
    PORT = 7125 # Moonraker 默认端口
    
    server = MockMoonrakerServer(HOST, PORT)
    try:
        await server.start()
    except KeyboardInterrupt:
        log.info("收到关闭信号...")
    finally:
        await server.stop()

if __name__ == "__main__":
    asyncio.run(main())
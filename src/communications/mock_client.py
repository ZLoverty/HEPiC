import asyncio
import json
import websockets
import logging

# --- 配置客户端日志 ---
logging.basicConfig(
    level=logging.INFO,
    format="[TestClient] %(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("TestClient")

# 用于跟踪请求 ID
_request_id = 0

async def send_request(websocket, method, params={}):
    """
    一个辅助函数，用于构建、发送和记录 JSON-RPC 请求。
    """
    global _request_id
    _request_id += 1
    
    message = {
        "jsonrpc": "2.0",
        "id": _request_id,
        "method": method,
        "params": params
    }
    
    log.info(f"发送 C->S: {json.dumps(message)}")
    await websocket.send(json.dumps(message))
    return _request_id

async def receive_loop(websocket):
    """
    一个专门的任务，用于持续接收和打印来自服务器的所有消息。
    """
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                # 使用 indent=2 漂亮地打印收到的 JSON，便于调试
                log.info(f"收到 S->C:\n{json.dumps(data, indent=2)}")
            except json.JSONDecodeError:
                log.warning(f"收到无效的JSON: {message}")
    except asyncio.CancelledError:
        log.info("接收循环已取消。")
        raise
    except websockets.exceptions.ConnectionClosed as e:
        log.warning(f"连接已关闭 (接收方): {e}")
    except Exception as e:
        log.error(f"接收循环出错: {e}", exc_info=True)


async def run_test_scenario(websocket):
    """
    执行一系列的测试步骤来验证 Mock Server。
    """
    try:
        # --- 步骤 1: 订阅对象 ---
        log.info("--- 步骤 1: 订阅对象 (extruder, heater_bed, toolhead) ---")
        await send_request(
            websocket,
            "printer.objects.subscribe",
            {
                "objects": {
                    "extruder": None,
                    "heater_bed": None,
                    "toolhead": None,
                    "gcode_move": None
                }
            }
        )
        
        # 等待几秒钟，观察来自服务器的自动通知
        # (Mock Server 默认每 2 秒发送一次更新)
        await asyncio.sleep(5.0)

        # --- 步骤 2: 发送 G-code (设置热端温度) ---
        log.info("--- 步骤 2: 发送 G-code 'M104 S150' (设置热端 150°C) ---")
        await send_request(
            websocket,
            "printer.gcode.script",
            {"script": "M104 S150"}
        )
        
        # 等待 6 秒，观察温度在通知中逐渐上升
        log.info("...等待 6 秒，观察温度变化...")
        await asyncio.sleep(6.0)

        # --- 步骤 3: 发送 G-code (归位) ---
        log.info("--- 步骤 3: 发送 G-code 'G28' (归位) ---")
        await send_request(
            websocket,
            "printer.gcode.script",
            {"script": "G28"}
        )
        
        # 等待 4 秒，观察归位状态和位置变化
        log.info("...等待 4 秒，观察位置变化...")
        await asyncio.sleep(4.0)

        # --- 步骤 4: 发送 G-code (关闭热端) ---
        log.info("--- 步骤 4: 发送 G-code 'M104 S0' (关闭热端) ---")
        await send_request(
            websocket,
            "printer.gcode.script",
            {"script": "M104 S0"}
        )
        
        # 等待 6 秒，观察温度下降
        log.info("...等待 6 秒，观察温度变化...")
        await asyncio.sleep(6.0)

        log.info("--- 测试场景完成 ---")

    except Exception as e:
        log.error(f"测试场景出错: {e}", exc_info=True)


async def main():
    """
    主函数：连接到服务器并运行测试。
    """
    uri = "ws://127.0.0.1:7125"
    
    try:
        async with websockets.connect(uri) as websocket:
            log.info(f"已成功连接到 Mock Server at {uri}")
            
            # 创建一个后台任务来处理所有传入的消息
            recv_task = asyncio.create_task(receive_loop(websocket))
            
            # 运行主测试逻辑
            await run_test_scenario(websocket)
            
            # 测试完成后，取消接收任务
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass # 这是预期的
            
    except ConnectionRefusedError:
        log.error(f"连接失败！请确保 MockMoonrakerServer 正在 {uri} 上运行。")
    except Exception as e:
        log.error(f"主协程出错: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("客户端被用户中断。")
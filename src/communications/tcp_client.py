from PySide6.QtCore import QObject, Signal, QTimer
import asyncio
from qasync import asyncSlot
import json
import random
import logging
import sys
import numpy as np
from collections import deque

class TCPClient(QObject):
    # --- 信号 ---
    # 连接状态变化时发出
    connection_status = Signal(str)
    # 收到并解析完数据后发出
    connected = Signal(int)
    extrusion_force_signal = Signal(float)
    meter_count_signal = Signal(float)

    def __init__(self, 
                 host: str, 
                 port: int, 
                 logger = None,
                 rotary_encoder_steps_total: int = 1000,
                 rotary_encoder_wheel_diameter: float = 28.6,
                 meter_count_cache_size: int = 10,
                 refresh_interval_ms: int = 100):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = True
        self.queue = asyncio.Queue()
        self.extrusion_force = np.nan
        self.extrusion_force_offset = 0.0
        self.extrusion_force_raw = np.nan
        self.meter_count_raw = np.nan
        self.meter_count_offset = 0.0
        self.meter_count = np.nan
        self.steps_total = rotary_encoder_steps_total
        self.wheel_diameter = rotary_encoder_wheel_diameter
        self.filament_velocity = 0.0
        self.cache_size = meter_count_cache_size
        self.meter_count_cache = deque(maxlen=self.cache_size) # cache for computing velocity
        self._timer = QTimer()
        self.refresh_interval_ms = refresh_interval_ms
        self._timer.timeout.connect(self.compute_filament_velocity)

        self.logger = logger or logging.getLogger(__name__)
        
    @asyncSlot()
    async def run(self):
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=2.0)

        self._timer.start(self.refresh_interval_ms)

        try:        
            await self.send_data("start")
            self.receive_task = asyncio.create_task(self.receive_data())
            self.process_task = asyncio.create_task(self.process_data())
            await asyncio.gather(self.receive_task, self.process_task)
        except Exception as e:
            self.logger.error(f"未知错误: {e}")
        finally: # 无论如何中断，都关闭 writer，并关闭两个任务
            self.writer.close()
            await self.writer.wait_closed()
            self.receive_task.cancel()
            self.process_task.cancel()
            await asyncio.gather(self.receive_task, self.process_task, return_exceptions=True)

    async def send_data(self, message):
        """向服务器发送一条消息"""
        if not self.is_running or not self.writer:
            self.logger.info("连接未建立，无法发送消息。")
            return

        try:
            # 客户端发送时也最好加上换行符，以方便服务器按行读取
            data_to_send = (message + '\n').encode('utf-8')
            self.writer.write(data_to_send)
            await self.writer.drain()
            self.logger.info(f"已发送 -> {message}")
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}")
            self.is_running = False

    async def receive_data(self):
        """
        这个函数在后台线程中运行，持续接收数据。
        """
        try:
            while self.is_running:
            
                # 读取一行数据
                data = await self.reader.readline()
                message_str = data.decode('utf-8').strip()
                # self.logger.debug(f"receive message: {message_str}")
                message_dict = json.loads(message_str)
                await self.queue.put(message_dict)
        except (ConnectionResetError, ConnectionAbortedError):
            self.logger.error("连接被重置或中止。")
            self.connection_status.emit("连接已断开")
        except Exception as e:
            self.logger.error(f"位置错误: {e}")
    
    async def process_data(self):
        """这个函数持续从队列中提取数据并发射信号，最后将数据存至主程序中的list中。数据以
        
        {
            "extrusion_force": 123,
            "meter_count": 321
        }
        
        的形式从服务器发送。
        """
        try:
            while self.is_running:   
                message_dict = await self.queue.get()
                if "extrusion_force" in message_dict:
                    self.extrusion_force_raw = message_dict["extrusion_force"]
                    self.extrusion_force = self.extrusion_force_raw - self.extrusion_force_offset
                if "meter_count" in message_dict:
                    self.meter_count_raw = message_dict["meter_count"]
                    self.meter_count = (self.meter_count_raw - self.meter_count_offset) / self.steps_total * np.pi * self.wheel_diameter
            # 标记队列任务已完成（好习惯）
                self.queue.task_done()

        except asyncio.CancelledError:
            self.logger.info("Process data task cancelled.") # 正常停止
        except Exception as e:
            # 捕获未知错误，否则任务会崩溃且主循环不知道
            self.logger.error(f"Error in process_data: {e}")

    def set_extrusion_force_offset(self):
        """将当前的挤出力读数设为零点偏移"""
        if self.extrusion_force_raw is not None:
            self.extrusion_force_offset = self.extrusion_force_raw
            self.logger.info(f"挤出力零点已设为 {self.extrusion_force_offset}")
            print("set 0")
        else:
            self.logger.warning("无法设定挤出力零点，当前无读数。")
    
    def set_meter_count_offset(self):
        """将当前的米数读数设为零点偏移"""
        if self.meter_count_raw is not None:
            self.meter_count_offset = self.meter_count_raw
            self.logger.info(f"米数零点已设为 {self.meter_count_offset}")
        else:
            self.logger.warning("无法设定米数零点，当前无读数。")

    def compute_filament_velocity(self):
        """Compute filament velocity based on meter_count changes over time."""
        self.meter_count_cache.append(self.meter_count_raw)
        self.logger.debug(f"Cached {len(self.meter_count_cache)} values for velocity computation.")

        if len(self.meter_count_cache) == self.cache_size:
            delta_meter = self.meter_count_cache[-1] - self.meter_count_cache[0]
            delta_time = (self.cache_size - 1) * self.refresh_interval_ms / 1000.0 # convert ms to s
            self.filament_velocity = delta_meter / delta_time
        else:
            self.filament_velocity = 0.0

        self.logger.debug(f"Computed filament velocity: {self.filament_velocity} mm/s")

    @asyncSlot()
    async def stop(self):
        """
        关闭连接并停止接收线程。
        """
        self.is_running = False

        # cancel all existing tasks when stopped
        if hasattr(self, 'receive_task'):
            self.receive_task.cancel()
        if hasattr(self, 'process_task'):
            self.process_task.cancel()
            
        # run() 方法中的 finally 块将处理 writer 的关闭
        # 我们也可以在这里关闭 writer 以更快地中止 receive_task
        if hasattr(self, 'writer') and self.writer:
            self.writer.close()




async def mock_data_sender(reader, writer):
    """This function listens on host:port and send data to any client that connect to this address. Its main purpose is to test the logic in the TCPClient class."""
    
    addr = writer.get_extra_info('peername')
    print(f"接受来自 {addr} 的新连接")

    shutdown_signal = asyncio.Future()

    async def send_loop(writer):
        """周期性地生成并发送数据给这个客户端"""

        while not shutdown_signal.done():
            try:
                # --- 这是您提供的代码，经过TCP适配 ---
                extrusion_force = 2 + random.uniform(-.2, .2)
                meter_count = 2 + random.uniform(-.2, .2)
                message = {
                    "extrusion_force": extrusion_force,
                    "meter_count": meter_count
                }
          
                # 1. 序列化成 JSON 字符串，然后编码成 bytes
                data_to_send = json.dumps(message).encode("utf-8") + b'\n' # 加一个换行符作为分隔符
                
                print(f"向 {addr} 发送 -> {message}")

                # 2. 使用 writer 写入数据，不再需要地址
                writer.write(data_to_send)

                # 3. 关键：确保数据被发送出去
                await writer.drain()
                
                # 4. 等待一段时间再发送下一次，避免刷屏和CPU 100%
                await asyncio.sleep(.1)

            except Exception as e:
                print(f"向 {addr} 发送数据时出错: {e}")
                shutdown_signal.set_result(True) # 通知接收循环也停止

    send_task = asyncio.create_task(send_loop(writer))

    await shutdown_signal

    send_task.cancel()

    writer.close()
    await writer.wait_closed()

async def _test_tcp_client():

    HOST, PORT = '127.0.0.1', 10001
    server = await asyncio.start_server(mock_data_sender, HOST, PORT)
    send_task = asyncio.create_task(server.serve_forever())
    tcp_client = TCPClient(HOST, PORT)
    
    print("testing run method ...")
    recv_task = tcp_client.run()
    await asyncio.sleep(3)

    print("testing stop method ...")
    await tcp_client.stop()

    print("test completed.")

async def main():
    await _test_tcp_client()
    
if __name__ == "__main__":

    # configure basic logging 
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Test interrupted.") 
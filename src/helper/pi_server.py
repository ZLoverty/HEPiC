import asyncio
import json
import random
import logging
import logging.handlers
import signal
import sys
from pathlib import Path
import snap7
from snap7.util import get_real

class PiServer:
    """
    一个健壮的、可作为服务运行的异步TCP服务器。
    它从配置文件加载设置，使用专业的日志系统，并能优雅地处理关闭信号。
    """
    def __init__(self, config_path):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.server = None
        self.tasks = set()


    def _load_config(self, path):
        """加载 JSON 配置文件"""
        config_file = Path(path).expanduser()
        if not config_file.is_file():
            print(f"错误：配置文件 {path} 未找到！", file=sys.stderr)
            sys.exit(1)
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _setup_logging(self):
        """配置日志系统，同时输出到控制台和可轮换的文件"""
        logger = logging.getLogger("TCPServer")
        logger.setLevel(self.config.get("log_level", "INFO").upper())
        
        # 格式化
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 控制台输出
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
        # 文件输出 (如果配置了)
        log_file = self.config.get("log_file")
        if log_file:
            # 使用 RotatingFileHandler 实现日志文件自动分割
            # 10MB一个文件，最多保留5个
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
        return logger

    def connect_devices(self):
        self.plc_ip = self.config.get("plc_ip")
        self.weight_db = self.config.get("weight_db")
        self.weight_start = self.config.get("weight_start")
        self.meter_db = self.config.get("meter_db")
        self.meter_start = self.config.get("meter_start")

        self.plc = snap7.client.Client()
        print(f"正在连接到 PLC at {self.plc_ip}...")
        RACK = 0
        SLOT = 1
        # 2. 在循环外，只连接一次
        self.plc.connect(self.plc_ip, RACK, SLOT)

    async def _handle_client(self, reader, writer):
        """为每个客户端连接创建独立的处理器"""
        addr = writer.get_extra_info('peername')
        self.logger.info(f"接受来自 {addr} 的新连接")

        shutdown_signal = asyncio.Future()

        async def send_loop():
            """周期性地发送数据给客户端"""
            while not shutdown_signal.done():
                try:
                    # read weight and meter from PLC
                    db_data = self.plc.db_read(self.weight_db, self.weight_start, 4)
                    weight = get_real(db_data, 0)
                    db_data = self.plc.db_read(self.meter_db, self.meter_start, 4)
                    meter = get_real(db_data, 0)

                    message = {
                        "weight": weight,
                        "meter": meter
                    }
                    data_to_send = json.dumps(message).encode("utf-8") + b'\n'
                    
                    self.logger.debug(f"向 {addr} 发送 -> {message}")
                    writer.write(data_to_send)
                    await writer.drain()
                    
                    await asyncio.sleep(self.config.get("send_delay", 0.01))
                except (ConnectionResetError, BrokenPipeError) as e:
                    self.logger.warning(f"与 {addr} 的连接异常断开: {e}")
                    if not shutdown_signal.done():
                        shutdown_signal.set_result(True)
                except Exception as e:
                    self.logger.error(f"向 {addr} 发送数据时发生未知错误: {e}", exc_info=True)
                    if not shutdown_signal.done():
                        shutdown_signal.set_result(True)

        async def receive_loop():
            """从客户端接收数据"""
            while not shutdown_signal.done():
                try:
                    data = await reader.read(1024)
                    if not data:
                        self.logger.info(f"客户端 {addr} 已主动断开连接。")
                        if not shutdown_signal.done():
                            shutdown_signal.set_result(True)
                        break
                    
                    message = data.decode().strip()
                    self.logger.info(f"从 {addr} 收到消息: {message!r}")
                except Exception as e:
                    self.logger.error(f"从 {addr} 接收数据时出错: {e}", exc_info=True)
                    if not shutdown_signal.done():
                        shutdown_signal.set_result(True)

        async def image_send_loop(exposure_time=50000):
            """读取相机图片并发送给客户端。"""
            self.cap = AsyncHikVideoCapture(width=512, height=512, exposure_time=exposure_time, center_roi=True)
            # 应该把所有数据都做成 json，有一个固定的结构描述类型和实际数据，可以

        send_task = asyncio.create_task(send_loop())
        receive_task = asyncio.create_task(receive_loop())
        self.tasks.add(send_task)
        self.tasks.add(receive_task)

        await shutdown_signal
        
        send_task.cancel()
        receive_task.cancel()
        self.tasks.remove(send_task)
        self.tasks.remove(receive_task)
        
        self.logger.info(f"关闭与 {addr} 的连接。")
        writer.close()
        await writer.wait_closed()

    async def _shutdown(self, sig):
        """优雅地关闭服务器"""
        self.logger.info(f"收到关闭信号: {sig.name}. 服务器正在关闭...")
        
        # 停止接受新连接
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # 取消所有正在运行的客户端任务
        for task in list(self.tasks):
            task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        loop = asyncio.get_running_loop()
        loop.stop()

    async def run(self):
        """启动服务器并监听信号"""
        loop = asyncio.get_running_loop()
        # 为 SIGINT (Ctrl+C) 和 SIGTERM (来自 systemd) 添加信号处理器
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._shutdown(s)))

        host = self.config.get("host", "0.0.0.0")
        port = self.config.get("port", 10001)

        try:
            self.server = await asyncio.start_server(self._handle_client, host, port)
            addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
            self.logger.info(f"服务器已启动，正在监听 {addrs}")
            await self.server.serve_forever()
        except Exception as e:
            self.logger.critical(f"服务器启动失败: {e}", exc_info=True)
            sys.exit(1)


import cv2
import asyncio # 1. 导入 asyncio
import time
import numpy as np
from typing import Tuple, Optional

# hikrobotcamlib 依赖仍然是可选的，只在实际使用时导入
try:
    from hikrobotcamlib import Camera, DeviceList, Frame, DeviceTransport
except ImportError:
    print("警告: hikrobotcamlib 未安装。此类将无法工作。")
    Camera = DeviceList = Frame = DeviceTransport = None


class AsyncHikVideoCapture:
    """
    一个使用 asyncio 的异步接口，用于海康机器人工业相机。
    read() 方法是一个协程，在没有新帧时它会交出控制权，允许事件循环运行其他任务。

    用法:
        async def main():
            cap = AsyncHikVideoCapture(width=640, height=480)
            async with cap: # 使用异步上下文管理器
                while True:
                    ret, frame = await cap.read() # 'await' 是关键
                    if not ret:
                        print("获取帧失败，退出...")
                        break
                    cv2.imshow('Async Hikvision Feed', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            cv2.destroyAllWindows()

        if __name__ == '__main__':
            asyncio.run(main())
    """

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None, exposure_time: Optional[float] = None, center_roi: bool = True):
        if Camera is None:
            raise ImportError("hikrobotcamlib 未安装，无法初始化相机。")
        
        self.cam: Optional[Camera] = None
        self._is_opened = False
        self.frame_queue = asyncio.Queue(maxsize=2) # 2. 使用 asyncio.Queue
        self.loop = None # 用于线程安全地与事件循环交互

        # --- 初始化逻辑与之前类似，但增加了对 event loop 的处理 ---
        try:
            # 在__init__中获取当前事件循环，因为回调需要它
            # 注意: 这要求 AsyncHikVideoCapture 的实例必须在一个正在运行的事件循环中创建
            self.loop = asyncio.get_running_loop() 
            
            print("正在搜索设备...")
            dev_info = next(iter(DeviceList(DeviceTransport.GIGE | DeviceTransport.USB)), None)
            if dev_info is None:
                raise RuntimeError("错误: 未找到任何相机设备。")

            self.cam = Camera(dev_info)
            self.cam.open()
            
            # 设置ROI和曝光时间的逻辑保持不变
            # ... (这部分代码与你原来的版本完全相同) ...
            if width is not None and height is not None:
                self.cam.set_int("Width", width)
                self.cam.set_int("Height", height)
                if center_roi:
                    width_max = self.cam.get_int("WidthMax")
                    height_max = self.cam.get_int("HeightMax")
                    offset_x = (width_max - width) // 2
                    offset_y = (height_max - height) // 2
                    self.cam.set_int("OffsetX", offset_x)
                    self.cam.set_int("OffsetY", offset_y)
            if exposure_time is not None:
                self.cam.set_float("ExposureTime", exposure_time)
            self.cam.set_enum("PixelFormat", "Mono8")

            # 设置回调函数
            self.cam.frame_callback = self._frame_callback
            self.cam.trigger_enable(False)
            self.cam.start()
            
            self._is_opened = True
            print(f"相机 {self.cam.info.model} ({self.cam.info.serialno}) 已成功打开并开始采集。")

        except Exception as e:
            print(f"初始化相机时出错: {e}")
            if self.cam:
                self.cam.close()
            self._is_opened = False
            # 重新抛出异常，让调用者知道初始化失败
            raise

    def _frame_callback(self, frame, cam) -> None:
        # 3. 这是关键：从外部线程安全地将数据放入 asyncio.Queue
        if self.frame_queue.full():
            # 尝试清空一个元素，为新帧腾出空间
            try: self.frame_queue.get_nowait()
            except asyncio.QueueEmpty: pass
        
        # 图像处理逻辑与之前相同
        height = frame.infoptrcts.nHeight
        width = frame.infoptrcts.nWidth
        img_data = np.ctypeslib.as_array(frame.dataptr, shape=(frame.len,)).copy()
        
        try:
            img = img_data.reshape((height, width))
            # 使用 call_soon_threadsafe 将 put_nowait 操作调度到事件循环
            self.loop.call_soon_threadsafe(self.frame_queue.put_nowait, img)
        except (ValueError, asyncio.QueueFull):
            pass

    def isOpened(self) -> bool:
        return self._is_opened

    async def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        # 4. 将 read 变成一个协程 (async def)
        if not self.isOpened():
            return False, None
        try:
            # 'await' 会在这里暂停，直到队列中有新帧，期间事件循环可以运行其他任务
            frame = await asyncio.wait_for(self.frame_queue.get(), timeout=1.0)
            self.frame_queue.task_done() # 推荐的做法
            return True, frame
        except asyncio.TimeoutError:
            print("警告: 等待帧超时。")
            return False, None

    def release(self):
        if self.cam and self.isOpened():
            print("正在释放相机资源...")
            self.cam.stop()
            self.cam.close()
            self._is_opened = False
            print("相机资源已释放。")

    # 5. 实现异步上下文管理器，方便使用 `async with`
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()

# --- 如何使用 (异步版本) ---

async def other_logic():
    """一个模拟其他任务的协程，证明在等待图像时程序没有被阻塞。"""
    counter = 0
    while True:
        print(f"其他逻辑正在运行... Counter: {counter}")
        counter += 1
        await asyncio.sleep(1) # 每秒执行一次

async def main():
    """主异步函数"""
    try:
        # 必须在 async 函数内部创建实例
        cap = AsyncHikVideoCapture(width=640, height=480, exposure_time=100000, center_roi=True)
    except (RuntimeError, ImportError) as e:
        print(f"无法启动相机: {e}，程序退出。")
        return
        
    # 创建一个后台任务来运行 'other_logic'
    background_task = asyncio.create_task(other_logic())

    async with cap: # 使用 async with 自动管理资源的释放
        while True:
            # 当这里在 'await' 时，事件循环会去运行 'other_logic'
            print("主逻辑：正在等待下一帧图像...")
            ret, frame = await cap.read()
            
            if not ret:
                break
            
            print("主逻辑：已收到新帧！")
            cv2.imshow('Async Hikvision Feed', frame)
            
            # 注意：cv2.waitKey() 是一个阻塞调用，但设为1ms影响很小
            # 在纯异步GUI框架(如Qt for Python)中，这一步也会是异步的
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    # 清理
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        print("后台任务已成功取消。")
    
    cv2.destroyAllWindows()
    print("程序结束。")

if __name__ == "__main__":
    # 假设配置文件与脚本在同一目录下
    server_app = PiServer("~/Documents/GitHub/etp_ctl/src/helper/config.json")
    try:
        asyncio.run(server_app.run())
    except (KeyboardInterrupt, SystemExit):
        server_app.logger.info("程序已终止。")

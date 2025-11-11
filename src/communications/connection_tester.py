from PySide6.QtCore import QObject, Signal, Slot
import asyncio
from qasync import asyncSlot
import platform
import aiohttp

class ConnectionTester(QObject):
    """初次连接时应进行一个网络自检，确定必要的硬件都已开启，且服务、端口都正确配置。这个自检应当用阻塞函数实现，因为如果自检不通过，运行之后的代码将毫无意义。因此，单独写这个自检函数。"""
    test_msg = Signal(str)
    # 【保持不变或按需修改】如果希望传递 host，就用 Signal(str)
    success = Signal() 
    fail = Signal()

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.moonraker_port = 7125
    
    # 1. 将 run 方法改为 @asyncSlot
    @asyncSlot()
    async def run(self):
        self.test_msg.emit(f"检查网络环境中 ...")

        # --- 步骤 1: 异步检查主机基础连通性 (Ping) ---
        self.test_msg.emit(f"[步骤 1/4] 正在 Ping 树莓派主机 {self.host} ...")
        ping_ok = await self._is_host_reachable_async(self.host)
        
        if ping_ok:
            self.test_msg.emit(f"✅ Ping 成功！主机 {self.host} 在网络上是可达的。")
        else:
            self.test_msg.emit(f"❌ Ping 失败，主机 {self.host} 不可达或阻止了 Ping 请求。")
            self.fail.emit()
            return

        # --- 步骤 2: 异步检查特定 TCP 端口 ---
        self.test_msg.emit(f"[步骤 2/4] 正在检查数据传输端口 {self.port} ...")
        port_ok = await self._check_tcp_port_async(self.host, self.port)

        if port_ok:
            self.test_msg.emit(f"✅ 端口检查成功！数据服务器在 {self.host}:{self.port} 上正在监听。")
        else:
            self.test_msg.emit(f"❌ 端口检查失败。主机可达，但端口 {self.port} 已关闭或被防火墙过滤。")
            self.test_msg.emit("数据端口连通性测试失败，请检查数据服务器是否启动")
            self.fail.emit()
            return


        # --- 新增步骤 3: 检查 Moonraker API ---
        self.test_msg.emit(f"[步骤 3/4] 正在检查 Moonraker 服务...")
        if not await self._check_moonraker_async():
            self.test_msg.emit(f"❌ Moonraker 服务无响应。")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Moonraker 服务 API 响应正常！")

        # --- 新增步骤 4: 检查 Klipper 状态 ---
        self.test_msg.emit(f"[步骤 4/4] 正在查询 Klipper 状态...")
        klipper_ok, klipper_state = await self._check_klipper_async()
        if not klipper_ok:
            self.test_msg.emit(f"❌ Klipper 状态异常: '{klipper_state}'")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Klipper 状态为 '{klipper_state}'，一切就绪！")
        self.test_msg.emit("所有检查通过，准备连接...")
        self.success.emit()
        
    # 2. 实现异步的 ping 方法
    async def _is_host_reachable_async(self, host: str, timeout: int = 2) -> bool:
        system_name = platform.system().lower()
        if system_name == "windows":
            command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
        else:
            command = ["ping", "-c", "1", "-W", str(timeout), host]

        try:
            # 使用 asyncio.create_subprocess_exec 替代阻塞的 subprocess.run
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # 等待进程结束
            await proc.wait()
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            print("错误：ping 命令执行失败或超时。")
            return False

    # 3. 实现异步的 TCP 端口检查方法
    async def _check_tcp_port_async(self, host: str, port: int, timeout: int = 3) -> bool:
        try:
            # 使用 asyncio.open_connection 尝试连接，并用 wait_for 控制超时
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), 
                timeout=timeout
            )
            # 连接成功后，立即关闭 writer
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError) as e:
            # 捕获超时或连接被拒绝等错误
            print(f"检查端口时发生错误: {e}")
            return False
        
    async def _check_moonraker_async(self) -> bool:
        """异步检查 Moonraker 的 /server/info API 端点。"""
        url = f"http://{self.host}:{self.moonraker_port}/server/info"
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except Exception as e:
            print(f"检查 Moonraker 时出错: {e}")
            return False

    async def _check_klipper_async(self):
        """通过 Moonraker 查询 Klipper 的状态。"""
        url = f"http://{self.host}:{self.moonraker_port}/printer/objects/query?webhooks"
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 安全地访问嵌套的字典
                        state = data.get("result", {}).get("status", {}).get("webhooks", {}).get("state", "未知")
                        if state == "ready":
                            return True, state
                        else:
                            return False, state
                    else:
                        return False, f"HTTP 错误码: {response.status}"
        except Exception as e:
            print(f"检查 Klipper 时出错: {e}")
            return False, "请求异常"
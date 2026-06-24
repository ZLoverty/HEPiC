from PySide6.QtCore import QObject, Signal, Slot
import asyncio
from qasync import asyncSlot
import logging
import platform
import aiohttp

class ConnectionTester(QObject):
    """初次连接时应进行一个网络自检，确定必要的硬件都已开启，且服务、端口都正确配置。这个自检应当用阻塞函数实现，因为如果自检不通过，运行之后的代码将毫无意义。因此，单独写这个自检函数。"""
    test_msg = Signal(str)
    # 【保持不变或按需修改】如果希望传递 host，就用 Signal(str)
    success = Signal()
    fail = Signal()

    def __init__(self, host, port, test_mode=False):
        super().__init__()
        self.host = host
        self.port = port
        self.moonraker_port = 7125
        self.test_mode = test_mode
        self.logger = logging.getLogger(__name__)
    
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

        if self.test_mode:
            self.test_msg.emit("🧪 测试模式：跳过 Moonraker 和 Klipper 检查。")
            self.test_msg.emit("所有检查通过，准备连接...")
            self.success.emit()
            return

        # --- 步骤 3: 检查 Moonraker 服务（同时取回 Klipper 服务状态）---
        self.test_msg.emit(f"[步骤 3/4] 正在检查 Moonraker 服务...")
        moonraker_ok, server_info = await self._get_server_info()
        if not moonraker_ok:
            self.test_msg.emit(f"❌ Moonraker 服务无响应。")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Moonraker 服务 API 响应正常！")

        # --- 步骤 4: 检查 Klipper 服务是否在线 ---
        # 注意：不再要求 Klipper 处于 'ready'。只要 Klipper 服务已连接，
        # 即允许进入主页（主页提供重启按钮，可处理 shutdown/error 等状态）。
        self.test_msg.emit(f"[步骤 4/4] 正在检查 Klipper 服务...")
        klippy_state = server_info.get("klippy_state", "未知")
        if not server_info.get("klippy_connected", False):
            self.test_msg.emit(f"❌ Klipper 服务未连接（状态: '{klippy_state}'），请检查 Klipper 服务是否启动。")
            self.fail.emit()
            return

        self.test_msg.emit(f"✅ Klipper 服务在线（状态: '{klippy_state}'）。")

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
            # 使用 asyncio.create_subprocess_exec 替代阻塞的 subprocess.run。
            # stdout/stderr 重定向到 DEVNULL：避免 PIPE 缓冲写满导致 wait() 死锁。
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.logger.warning("未找到 ping 命令，跳过 ping，由后续端口检查判断可达性。")
            return True
        except NotImplementedError:
            # 某些事件循环（如 Windows 上的 Selector/qasync 组合）不支持子进程。
            self.logger.warning("当前事件循环不支持子进程 ping，跳过 ping，由后续端口检查判断可达性。")
            return True

        try:
            # 给 proc.wait() 加硬超时，防止 ping 卡死时永久阻塞。
            await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
        except asyncio.TimeoutError:
            self.logger.warning("ping 超时，已终止进程。")
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return False
        return proc.returncode == 0

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
        
    async def _get_server_info(self):
        """异步查询 Moonraker 的 /server/info 端点。

        该端点同时反映两个服务的状态：
          - HTTP 200 表示 Moonraker 服务在线；
          - 返回体中的 `klippy_connected` / `klippy_state` 表示 Klipper 服务状态。

        返回 (moonraker_ok, info)，info 为 result 字典（失败时为空字典）。
        """
        url = f"http://{self.host}:{self.moonraker_port}/server/info"
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        self.logger.warning(f"Moonraker 返回非 200: {response.status}")
                        return False, {}
                    data = await response.json()
                    return True, data.get("result", {})
        except Exception as e:
            self.logger.warning(f"检查 Moonraker 时出错: {e}")
            return False, {}
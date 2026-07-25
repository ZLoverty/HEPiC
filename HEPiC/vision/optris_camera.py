import sys
import threading
import queue
import numpy as np
import os
import time
import logging

logger = logging.getLogger(__name__)

# --- 自动检测并添加 SDK 路径 ---
if os.name == "nt":
    sdk_path_options = [
        r"C:\Program Files\Optris\otcsdk\bindings\python3",
        r"C:\Program Files (x86)\Optris\otcsdk\bindings\python3"
    ]
    sdk_path_found = None
    for path in sdk_path_options:
        if os.path.exists(path):
            sdk_path_found = path
            break
    if sdk_path_found:
        logger.info("找到 Optris SDK 路径: %s", sdk_path_found)
        sys.path.append(sdk_path_found)
    else:
        logger.warning("未能在常见位置找到 Optris SDK 路径。请确保它在 PYTHONPATH 中。")
else:
    logger.info("在 Linux/macOS 上，请确保 Optris SDK Python 绑定在您的 PYTHONPATH 中。")

# --- 导入 SDK ---
# 有意不在这里捕获导入失败、也不在这里记日志：SDK 是否可用是调用方（例如 ir_worker.py）
# 才知道的上下文（比如是否处于 test_mode），应该由调用方决定捕获后如何处理/降级并记录日志。
import optris.otcsdk as otc


import cv2

# --- SDK 初始化锁 ---
_SDK_INITIALIZED_LOCK = threading.Lock()
_SDK_INITIALIZED = False


# --- 主类 ---
class OptrisCamera(otc.IRImagerClient):
    """
    一个封装了 Optris SDK 的类，提供了类似 cv2.VideoCapture 的接口。

    它在后台线程中处理相机数据，并通过线程安全的队列
    向主线程提供伪色图像和温度数据。
    """

    @staticmethod
    def _ensure_sdk_init():
        """[内部] 确保 SDK 被初始化的辅助函数"""
        global _SDK_INITIALIZED, _SDK_INITIALIZED_LOCK
        if _SDK_INITIALIZED:
            return
        with _SDK_INITIALIZED_LOCK:
            if not _SDK_INITIALIZED:
                logger.info("Initializing Optris SDK...")
                otc.Sdk.init(otc.Verbosity_Info, otc.Verbosity_Off, "")
                _SDK_INITIALIZED = True
                logger.info("Optris SDK Initialized.")

    @staticmethod
    def _query_operation_modes(serial_number):
        """
        [内部] 临时连接指定序列号的相机，获取其支持的操作模式，然后断开。

        :return: (actual_serial, op_modes)
        """
        imager = otc.IRImagerFactory.getInstance().create('native')
        try:
            imager.connect(serial_number)
            actual_serial = imager.getSerialNumber()
            op_modes = imager.getOperationModes()
            return actual_serial, op_modes
        finally:
            try:
                if imager.isConnected():
                    imager.disconnect()
            except Exception:
                logger.exception("断开临时查询连接时出错")

    @staticmethod
    def list_available_ranges(serial_number=0):
        """
        [辅助工具]
        临时连接相机，列出所有可用的操作模式（包括温度范围和扩展范围），然后断开。

        :param serial_number: 目标相机序列号 (0 = 自动检测第一个找到的相机)
        :return: list[dict] 包含所有可用范围的信息, 或者在错误时返回空列表
        """
        OptrisCamera._ensure_sdk_init()

        label = serial_number if serial_number != 0 else 'any'
        logger.info("正在查询 S/N %s 的可用测量范围...", label)

        try:
            actual_serial, op_modes = OptrisCamera._query_operation_modes(serial_number)
        except otc.SDKException:
            logger.exception("查询可用范围时出错")
            return []
        except Exception:
            logger.exception("查询过程中发生意外错误")
            return []

        logger.info("已连接到 S/N %s。正在获取操作模式...", actual_serial)

        if not op_modes:
            logger.warning("未找到 S/N %s 的操作模式。", actual_serial)
            return []

        logger.info("S/N %s 找到了 %d 种操作模式:", actual_serial, len(op_modes))

        ranges = []
        for i, mode in enumerate(op_modes):
            min_t = mode.getTemperatureNormalLowerLimit()
            max_t = mode.getTemperatureNormalUpperLimit()
            min_t_ext = mode.getTemperatureExtendedLowerLimit()
            max_t_ext = mode.getTemperatureExtendedUpperLimit()
            supports_extended = (min_t != min_t_ext or max_t != max_t_ext)

            range_info = {
                "index": i,
                "min_temp": min_t,
                "max_temp": max_t,
                "min_temp_extended": min_t_ext,
                "max_temp_extended": max_t_ext,
                "supports_extended": supports_extended,
                "width": mode.getFrameWidth(),
                "height": mode.getFrameHeight(),
                "fps": mode.getFramerate(),
                "description": str(mode)  # SDK 的 __str__ 提供了很好的概览
            }
            ranges.append(range_info)

            ext_info = ""
            if supports_extended:
                ext_info = f" (扩展可达: [{min_t_ext:.1f}, {max_t_ext:.1f}] C)"
            logger.info(
                "  [Index %d]: T [%.1f, %.1f] C @ %dx%d @ %d Hz%s",
                i, min_t, max_t, range_info['width'], range_info['height'],
                range_info['fps'], ext_info,
            )

        return ranges

    def __init__(self, serial_number=0, temp_range_index=None, use_extended_range=False):
        """
        初始化相机并开始数据采集。

        :param serial_number: 相机序列号 (0 = 自动检测第一个找到的相机)
        :param temp_range_index:
            硬件测量范围的索引 (0, 1, 2, ...)。
            使用 OptrisCamera.list_available_ranges() 来查看可用索引。
            如果为 None, 则使用相机的默认范围 (通常是索引 0)。
        :param use_extended_range:
            布尔值，是否尝试启用扩展温度范围（如果所选模式支持）。
            默认为 False。
        """
        super().__init__()
        OptrisCamera._ensure_sdk_init()

        # --- 变量和队列初始化 ---
        self._imager = None
        self._builder = None
        self._thread = None
        self._running = False
        self._color_frame_queue = queue.Queue(maxsize=1)
        self._temp_frame_queue = queue.Queue(maxsize=1)
        self._flag_state_lock = threading.Lock()
        self._flag_state = otc.FlagState_Initializing
        self._width = 0
        self._height = 0
        self._requested_serial = serial_number
        self._actual_serial = "Unknown"
        self._device_type = "Initializing"

        # --- 构建配置或使用默认 ---
        config = None

        try:
            if temp_range_index is not None:
                label = self._requested_serial if self._requested_serial != 0 else 'any'
                logger.info("Querying modes for S/N %s to build config...", label)

                self._actual_serial, op_modes = OptrisCamera._query_operation_modes(self._requested_serial)
                if not op_modes:
                    raise otc.SDKException(f"No operation modes found for device S/N {self._actual_serial}.")

                if not (0 <= temp_range_index < len(op_modes)):
                    logger.warning(
                        "temp_range_index %d 无效 (应在 0-%d 之间)。将使用索引 0。",
                        temp_range_index, len(op_modes) - 1,
                    )
                    temp_range_index = 0

                target_mode = op_modes[temp_range_index]

                # 构建 IRImagerConfig 对象
                logger.info(
                    "Building config for S/N %s using mode index %d: %s",
                    self._actual_serial, temp_range_index, str(target_mode),
                )
                config = otc.IRImagerConfig()

                # 填充配置 (强制转换为 int 以匹配 SDK 绑定要求)
                config.serialNumber = self._actual_serial
                min_temp_float = target_mode.getTemperatureNormalLowerLimit()
                max_temp_float = target_mode.getTemperatureNormalUpperLimit()
                config.minTemperature = int(min_temp_float)
                config.maxTemperature = int(max_temp_float)

                try:
                    config.fieldOfView = int(target_mode.getFieldOfView())
                except ValueError:
                    config.fieldOfView = target_mode.getFieldOfView()

                config.opticsText = target_mode.getOpticsText()
                config.width = int(target_mode.getFrameWidth())
                config.height = int(target_mode.getFrameHeight())
                config.framerate = int(target_mode.getFramerate())

                config.enableExtendedTemperatureRange = use_extended_range
                if use_extended_range:
                    logger.info("  (请求启用扩展温度范围)")

                try:
                    config.validate()
                    logger.debug("  (Generated config validated successfully.)")
                except otc.SDKException:
                    logger.warning("  (配置验证失败)", exc_info=True)

            # --- 初始化和连接相机 ---
            factory = otc.IRImagerFactory.getInstance()
            self._imager = factory.create('native')
            self._imager.addClient(self)

            if config:
                logger.info(
                    "Connecting with S/N %s using specified config %s...",
                    config.serialNumber,
                    '(Extended Range requested)' if use_extended_range else '',
                )
                self._imager.connect(config)
                self._actual_serial = self._imager.getSerialNumber()
                logger.info("Successfully connected to S/N %s with config.", self._actual_serial)
            else:
                label = self._requested_serial if self._requested_serial != 0 else 'any'
                logger.info("Connecting with S/N %s using default settings...", label)
                self._imager.connect(self._requested_serial)
                self._actual_serial = self._imager.getSerialNumber()
                logger.info("Successfully connected to S/N %s using defaults.", self._actual_serial)

            # --- 初始化伪色图像构建器 ---
            self._builder = otc.ImageBuilder(otc.ColorFormat_BGR, otc.WidthAlignment_OneByte)
            self._builder.setPaletteScalingMethod(otc.PaletteScalingMethod_MinMax)
            logger.debug("ImageBuilder initialized with BGR format and MinMax scaling.")

            # --- 启动 SDK 运行线程 ---
            self._running = True
            self._thread = threading.Thread(target=self._imager.run, name=f"OptrisSDK_SN{self._actual_serial}")
            self._thread.daemon = True
            self._thread.start()
            logger.info("Optris camera SDK thread for S/N %s started.", self._actual_serial)

        except otc.SDKException:
            logger.exception("初始化或连接 Optris 相机失败")
            self.release()
            raise
        except Exception:
            logger.exception("初始化过程中发生意外错误")
            self.release()
            raise

    def isOpened(self):
        return self._running and self._thread is not None and self._thread.is_alive()

    def read(self, timeout=1.0):
        if not self.isOpened():
            return False, None
        try:
            frame = self._color_frame_queue.get(block=True, timeout=timeout)
            if frame is None:
                self._running = False
                return False, None
            return True, frame
        except queue.Empty:
            return False, None
        except Exception:
            logger.exception("Error reading color frame")
            return False, None

    def read_temp(self, timeout=1.0):
        if not self.isOpened():
            return False, None
        try:
            temps = self._temp_frame_queue.get(block=True, timeout=timeout)
            if temps is None:
                self._running = False
                return False, None
            return True, temps
        except queue.Empty:
            return False, None
        except Exception:
            logger.exception("Error reading temp frame")
            return False, None

    def release(self):
        """一个更健壮、更耐心的 release 版本。"""
        if not self._running:
            return

        logger.info("Releasing Optris camera (S/N %s)...", self._actual_serial)
        self._running = False  # 1. 告诉回调函数停止处理新帧

        if self._imager:
            try:
                logger.debug("Calling _imager.stopRunning()...")
                self._imager.stopRunning()  # 2. 告诉 SDK 停止
            except Exception:
                logger.exception("Error in stopRunning()")

        # 3. 清理队列
        try:
            self._color_frame_queue.put_nowait(None)
            self._temp_frame_queue.put_nowait(None)
        except queue.Full:
            pass

        if self._thread and self._thread.is_alive():
            # 必须等待内部线程完全退出，不能设 timeout 提前放弃
            logger.debug("Waiting for internal thread to join()...")
            self._thread.join()
            logger.debug("Internal thread successfully joined.")

        if self._imager:
            try:
                logger.debug("Removing client from _imager...")
                self._imager.removeClient(self)
            except Exception:
                logger.exception("Error in removeClient()")

            # 尝试强制触发 C++ 侧析构
            try:
                logger.debug("Deleting _imager object...")
                del self._imager
            except Exception:
                logger.exception("Error in del _imager")

            self._imager = None

        self._builder = None

        # 给操作系统留出时间释放 USB 设备句柄；实测需要 4s 才稳定（早期注释误写为 1s）
        logger.debug("Release complete. Waiting 4s for OS handle...")
        time.sleep(4.0)

        logger.info("Optris camera S/N %s fully released.", self._actual_serial)

    def force_flag_event(self):
        if self._imager and self.isOpened():
            try:
                self._imager.forceFlagEvent()
            except otc.SDKException:
                logger.exception("Error forcing flag event")
        else:
            logger.warning("Cannot force flag event: Not running.")

    def get_flag_state(self):
        with self._flag_state_lock:
            return self._flag_state

    def get_properties(self):
        w = self._width if self._width > 0 else (self._imager.getWidth() if self._imager else 0)
        h = self._height if self._height > 0 else (self._imager.getHeight() if self._imager else 0)
        return {
            "requested_serial": self._requested_serial,
            "actual_serial": self._actual_serial,
            "device_type": self._device_type,
            "width": w, "height": h}

    def get(self, propId):
        if propId == cv2.CAP_PROP_FRAME_WIDTH:
            return self._width if self._width > 0 else (self._imager.getWidth() if self._imager else 0)
        if propId == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._height if self._height > 0 else (self._imager.getHeight() if self._imager else 0)
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @staticmethod
    def _put_latest(q, item):
        """将 item 放入 maxsize=1 的队列：丢弃队列中已有的旧帧，只保留最新一帧。"""
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass

    def onThermalFrame(self, thermal, meta):
        if not self._running:
            return
        if self._width == 0:
            try:
                self._width = thermal.getWidth()
                self._height = thermal.getHeight()
                if self._imager:
                    self._actual_serial = self._imager.getSerialNumber()
                    self._device_type = otc.deviceTypeToString(self._imager.getDeviceType())
                    logger.info(
                        "First frame received S/N %s (%dx%d). Type: %s",
                        self._actual_serial, self._width, self._height, self._device_type,
                    )
                else:
                    logger.info("First frame received (%dx%d).", self._width, self._height)
            except Exception:
                logger.exception("Error getting device info in callback")

        if self._builder:
            try:
                self._builder.setThermalFrame(thermalFrame=thermal)
                self._builder.convertTemperatureToPaletteImage()
                image = np.empty((self._height, self._width, 3), dtype=np.uint8)
                self._builder.copyImageDataTo(image)
                self._put_latest(self._color_frame_queue, image)
            except Exception:
                logger.exception("Error processing color frame")

        try:
            temp_data = np.empty((self._height, self._width), dtype=np.float32)
            thermal.copyTemperaturesTo(temp_data)
            self._put_latest(self._temp_frame_queue, temp_data)
        except Exception:
            logger.exception("Error processing temp frame")

    def onFlagStateChange(self, flagState):
        with self._flag_state_lock:
            self._flag_state = flagState

    def onConnectionLost(self):
        logger.error("连接丢失 S/N %s (不可恢复)。", self._actual_serial)
        self._running = False
        self._cleanup_queues()

    def onConnectionTimeout(self):
        logger.error("连接超时 S/N %s。", self._actual_serial)
        self._running = False
        self._cleanup_queues()

    def _cleanup_queues(self):
        logger.debug("Cleaning up frame queues...")
        for q in (self._color_frame_queue, self._temp_frame_queue):
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        logger.debug("Frame queues cleaned.")

    def set_focus(self, position):
        """
        设置马达对焦的位置。

        参数:
            position (int): 焦距马达的目标位置 (步数)。
                             这个值的有效范围 (例如 0-1000) 取决于您的镜头。
        """
        if self._imager and self._running:
            try:
                self._imager.setFocusMotorPosition(position)
                return True
            except Exception:
                logger.exception("Error setting focus position")
                return False
        return False

    def get_focus(self):
        """获取当前马达对焦的位置 (int)。"""
        if self._imager and self._running:
            try:
                return self._imager.getFocusMotorPosition()
            except Exception:
                logger.exception("Error getting focus position")
                return None
        return None

# --- 用法示例 ---
def main():
    """演示如何使用封装的 OptrisCamera 类。"""
    # --- 步骤 1: 查询可用范围 ---
    logger.info("-" * 30 + "\n步骤 1: 查询可用温度范围\n" + "-" * 30)
    available_ranges = OptrisCamera.list_available_ranges(serial_number=0)

    TARGET_RANGE_INDEX = None  # 默认为 None (使用默认)
    USE_EXTENDED_RANGE = True  # 默认不使用扩展范围

    if not available_ranges:
        logger.warning("未能获取可用范围。将尝试使用默认设置连接...")
    else:
        # --- 步骤 2: 选择范围索引和是否扩展 ---
        # 示例：假设我们想用索引 4, 并且尝试启用扩展范围
        TARGET_RANGE_INDEX = 4
        USE_EXTENDED_RANGE = True  # *** 设置为 True 来尝试启用扩展范围 ***

        logger.info("选择使用范围索引: %d", TARGET_RANGE_INDEX)
        if 0 <= TARGET_RANGE_INDEX < len(available_ranges):
            selected_range_info = available_ranges[TARGET_RANGE_INDEX]
            logger.info(
                "  对应范围: [%.1f, %.1f] C",
                selected_range_info['min_temp'], selected_range_info['max_temp'],
            )
            if selected_range_info['supports_extended']:
                logger.info(
                    "  此范围支持扩展至: [%.1f, %.1f] C",
                    selected_range_info['min_temp_extended'], selected_range_info['max_temp_extended'],
                )
                if USE_EXTENDED_RANGE:
                    logger.info("  *** 将尝试启用扩展范围 ***")
                else:
                    logger.info("  (当前未启用扩展范围)")
            elif USE_EXTENDED_RANGE:
                logger.warning("此范围不支持扩展，但请求了扩展。将忽略请求。")
                USE_EXTENDED_RANGE = False  # 强制改回 False
        else:
            logger.warning("选择的索引无效，将使用默认范围 (None)")
            TARGET_RANGE_INDEX = None
            USE_EXTENDED_RANGE = False  # 默认不扩展

    logger.info(
        "-" * 30 + "\n步骤 3: 使用索引 %s %s 初始化相机\n" + "-" * 30,
        TARGET_RANGE_INDEX if TARGET_RANGE_INDEX is not None else 'Default',
        '并请求扩展范围' if USE_EXTENDED_RANGE else '',
    )

    try:
        with OptrisCamera(serial_number=0,
                          temp_range_index=TARGET_RANGE_INDEX,
                          use_extended_range=USE_EXTENDED_RANGE) as cap:

            logger.info("等待相机初始化和第一帧 (最多 10 秒)...")
            start_wait = time.time()
            props = cap.get_properties()
            while props['width'] == 0 and time.time() - start_wait < 10.0:
                if not cap.isOpened():
                    logger.error("相机未能打开或已关闭。")
                    return
                time.sleep(0.1)
                props = cap.get_properties()

            if props['width'] == 0:
                logger.error("等待第一帧超时。")
                return

            logger.info("相机初始化完成:")
            logger.info("  实际序列号: %s", props['actual_serial'])
            logger.info("  设备类型: %s", props['device_type'])
            logger.info("  分辨率: %sx%s", props['width'], props['height'])
            logger.info("-" * 30 + "\n开始显示图像...\n" + "-" * 30)

            while cap.isOpened():
                ret_img, frame = cap.read(timeout=0.1)
                ret_temp, temps = cap.read_temp(timeout=0.1)

                if ret_img and frame is not None:
                    display_frame = frame.copy()
                    if ret_temp and temps is not None:
                        max_temp, min_temp, mean_temp = np.max(temps), np.min(temps), np.mean(temps)
                        cv2.putText(display_frame, f"Max: {max_temp:.1f} C", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                        cv2.putText(display_frame, f"Min: {min_temp:.1f} C", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                        cv2.putText(display_frame, f"Mean: {mean_temp:.1f} C", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                    else:
                        cv2.putText(display_frame, "Temp: N/A", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1, cv2.LINE_AA)

                    flag_state_str = otc.flagStateToString(cap.get_flag_state())
                    cv2.putText(display_frame, f"Flag: {flag_state_str}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                    cv2.imshow("Optris Camera Feed", display_frame)

                elif not ret_img and cap.isOpened():
                    pass  # 超时

                key = cv2.waitKey(10) & 0xFF
                if key == ord('q'):
                    logger.info("检测到 'q'，退出...")
                    break
                elif key == ord('r'):
                    logger.info("检测到 'r'，触发快门...")
                    cap.force_flag_event()

            logger.info("主循环结束。")

    except otc.SDKException:
        logger.exception("发生 SDK 错误")
    except KeyboardInterrupt:
        logger.info("用户中断 (Ctrl+C)。")
    except Exception:
        logger.exception("发生意外错误")
    finally:
        cv2.destroyAllWindows()
        logger.info("所有窗口已关闭。示例结束。")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    main()

import sys
import threading
import queue
import numpy as np
import os
import time

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
        print(f"找到 Optris SDK 路径: {sdk_path_found}")
        sys.path.append(sdk_path_found)
    else:
        print("警告: 未能在常见位置找到 Optris SDK 路径。请确保它在 PYTHONPATH 中。")
else:
    print("提示: 在 Linux/macOS 上，请确保 Optris SDK Python 绑定在您的 PYTHONPATH 中。")
    pass

# --- 尝试导入 SDK ---
try:
    import optris.otcsdk as otc
    OPTRIS_LIB_LOADED = True
except ImportError as e:
    print(f"错误: 导入 Optris SDK 失败: {e}")
    print("请确保:")
    print("1. Optris SDK 已安装。")
    print("2. Python 绑定路径已正确添加到 sys.path 或 PYTHONPATH。")
    print("3. Python 版本与 SDK 绑定兼容。")
    OPTRIS_LIB_LOADED = False
except Exception as e:
    print(f"错误: 加载 Optris SDK 时发生意外错误: {e}")
    OPTRIS_LIB_LOADED = False


import cv2

# --- SDK 初始化锁 ---
_SDK_INITIALIZED_LOCK = threading.Lock()
_SDK_INITIALIZED = False

# --- 主类 ---
if OPTRIS_LIB_LOADED:
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
                    print("Initializing Optris SDK...")
                    otc.Sdk.init(otc.Verbosity_Info, otc.Verbosity_Off, "")
                    _SDK_INITIALIZED = True
                    print("Optris SDK Initialized.")

        @staticmethod
        def list_available_ranges(serial_number=0):
            """
            [辅助工具]
            临时连接相机，列出所有可用的操作模式（包括温度范围和扩展范围），然后断开。
            
            :param serial_number: 目标相机序列号 (0 = 自动检测第一个找到的相机)
            :return: list[dict] 包含所有可用范围的信息, 或者在错误时返回空列表
            """
            if not OPTRIS_LIB_LOADED:
                print("错误: Optris SDK 未加载，无法查询范围。")
                return []

            OptrisCamera._ensure_sdk_init()

            print(f"正在查询 S/N {serial_number if serial_number != 0 else 'any'} 的可用测量范围...")
            imager = None
            factory = otc.IRImagerFactory.getInstance()
            try:
                imager = factory.create('native')
                print(f"尝试连接到 S/N {serial_number if serial_number != 0 else 'any'}...")
                imager.connect(serial_number)
                actual_serial = imager.getSerialNumber()
                print(f"已连接到 S/N {actual_serial}。正在获取操作模式...")

                op_modes = imager.getOperationModes()
                if not op_modes:
                    print(f"警告: 未找到 S/N {actual_serial} 的操作模式。")
                    imager.disconnect()
                    return []
                    
                print(f"S/N {actual_serial} 找到了 {len(op_modes)} 种操作模式:")
                
                ranges = []
                for i, mode in enumerate(op_modes):
                    # --- [修改] 获取正常和扩展范围 ---
                    min_t = mode.getTemperatureNormalLowerLimit()
                    max_t = mode.getTemperatureNormalUpperLimit()
                    min_t_ext = mode.getTemperatureExtendedLowerLimit()
                    max_t_ext = mode.getTemperatureExtendedUpperLimit()
                    supports_extended = (min_t != min_t_ext or max_t != max_t_ext)
                    # --- [修改结束] ---
                    
                    range_info = {
                        "index": i,
                        "min_temp": min_t,
                        "max_temp": max_t,
                        "min_temp_extended": min_t_ext, # [新增]
                        "max_temp_extended": max_t_ext, # [新增]
                        "supports_extended": supports_extended, # [新增]
                        "width": mode.getFrameWidth(),
                        "height": mode.getFrameHeight(),
                        "fps": mode.getFramerate(),
                        "description": str(mode) # SDK 的 __str__ 提供了很好的概览
                    }
                    ranges.append(range_info)
                    
                    # --- [修改] 打印信息包含扩展范围 ---
                    ext_info = ""
                    if supports_extended:
                        ext_info = f" (扩展可达: [{min_t_ext:.1f}, {max_t_ext:.1f}] C)"
                    print(f"  [Index {i}]: T [{min_t:.1f}, {max_t:.1f}] C @ {range_info['width']}x{range_info['height']} @ {range_info['fps']} Hz{ext_info}")
                    # --- [修改结束] ---
                    
                imager.disconnect()
                print(f"与 S/N {actual_serial} 的查询连接已断开。")
                imager = None
                return ranges

            except otc.SDKException as ex:
                print(f"查询可用范围时出错: {ex}")
                if imager and imager.isConnected():
                     try: imager.disconnect(); print("查询连接已断开。")
                     except: pass
                return []
            except Exception as e:
                 print(f"查询过程中发生意外错误: {e}")
                 if imager and imager.isConnected():
                     try: imager.disconnect()
                     except: pass
                 return []

        # --- [修改] __init__ 签名增加了 use_extended_range ---
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
            temp_imager = None

            try:
                if temp_range_index is not None:
                    print(f"Querying modes for S/N {self._requested_serial if self._requested_serial != 0 else 'any'} to build config...")
                    temp_imager = otc.IRImagerFactory.getInstance().create('native')
                    temp_imager.connect(self._requested_serial)
                    self._actual_serial = temp_imager.getSerialNumber()
                    
                    op_modes = temp_imager.getOperationModes()
                    if not op_modes: raise otc.SDKException(f"No operation modes found for device S/N {self._actual_serial}.")
                    
                    if not (0 <= temp_range_index < len(op_modes)):
                        print(f"警告: temp_range_index {temp_range_index} 无效 (应在 0-{len(op_modes)-1} 之间)。将使用索引 0。")
                        temp_range_index = 0
                    
                    target_mode = op_modes[temp_range_index]
                    
                    # 构建 IRImagerConfig 对象
                    print(f"Building config for S/N {self._actual_serial} using mode index {temp_range_index}: {str(target_mode)}")
                    config = otc.IRImagerConfig()
                    
                    # 填充配置 (强制转换为 int 以匹配 SDK 绑定要求)
                    config.serialNumber = self._actual_serial
                    min_temp_float = target_mode.getTemperatureNormalLowerLimit()
                    max_temp_float = target_mode.getTemperatureNormalUpperLimit()
                    config.minTemperature = int(min_temp_float) 
                    config.maxTemperature = int(max_temp_float)
                    
                    try: config.fieldOfView = int(target_mode.getFieldOfView())
                    except ValueError: config.fieldOfView = target_mode.getFieldOfView()
                        
                    config.opticsText = target_mode.getOpticsText()
                    config.width = int(target_mode.getFrameWidth())
                    config.height = int(target_mode.getFrameHeight())
                    config.framerate = int(target_mode.getFramerate())
                    
                    # --- [修改] 设置扩展范围标志 ---
                    config.enableExtendedTemperatureRange = use_extended_range
                    if use_extended_range:
                         print(f"  (请求启用扩展温度范围)")
                    # --- [修改结束] ---

                    # 验证配置 (可选)
                    try: config.validate(); print("  (Generated config validated successfully.)")
                    except otc.SDKException as vex: print(f"  (警告: 配置验证失败: {vex})")

                    temp_imager.disconnect()
                    temp_imager = None
                    print("Temporary query connection closed.")
            
                # --- 初始化和连接相机 ---
                factory = otc.IRImagerFactory.getInstance()
                self._imager = factory.create('native')
                self._imager.addClient(self)
                
                if config:
                    print(f"Connecting with S/N {config.serialNumber} using specified config {'(Extended Range requested)' if use_extended_range else ''}...")
                    self._imager.connect(config)
                    self._actual_serial = self._imager.getSerialNumber()
                    print(f"Successfully connected to S/N {self._actual_serial} with config.")
                else:
                    print(f"Connecting with S/N {self._requested_serial if self._requested_serial != 0 else 'any'} using default settings...")
                    self._imager.connect(self._requested_serial)
                    self._actual_serial = self._imager.getSerialNumber()
                    print(f"Successfully connected to S/N {self._actual_serial} using defaults.")
                
                # --- 初始化伪色图像构建器 ---
                self._builder = otc.ImageBuilder(otc.ColorFormat_BGR, otc.WidthAlignment_OneByte)
                self._builder.setPaletteScalingMethod(otc.PaletteScalingMethod_MinMax)
                print("ImageBuilder initialized with BGR format and MinMax scaling.")
                
                # --- 启动 SDK 运行线程 ---
                self._running = True
                self._thread = threading.Thread(target=self._imager.run, name=f"OptrisSDK_SN{self._actual_serial}")
                self._thread.daemon = True
                self._thread.start()
                print(f"Optris camera SDK thread for S/N {self._actual_serial} started.")

            except otc.SDKException as ex:
                print(f"错误: 初始化或连接 Optris 相机失败: {ex}")
                if temp_imager and temp_imager.isConnected():
                    try: temp_imager.disconnect() 
                    except: pass
                self.release()
                raise
            except Exception as e:
                print(f"错误: 初始化过程中发生意外错误: {e}")
                if temp_imager and temp_imager.isConnected():
                    try: temp_imager.disconnect()
                    except: pass
                self.release()
                raise

        # --- [isOpened, read, read_temp, release, force_flag_event, get_flag_state, get_properties, get 方法保持不变] ---
        def isOpened(self):
            return self._running and self._thread is not None and self._thread.is_alive()

        def read(self, timeout=1.0):
            if not self.isOpened(): return False, None
            try:
                frame = self._color_frame_queue.get(block=True, timeout=timeout)
                if frame is None: self._running = False; return False, None
                return True, frame
            except queue.Empty: return False, None
            except Exception as e: print(f"Error reading color frame: {e}"); return False, None

        def read_temp(self, timeout=1.0):
            if not self.isOpened(): return False, None
            try:
                temps = self._temp_frame_queue.get(block=True, timeout=timeout)
                if temps is None: self._running = False; return False, None
                return True, temps
            except queue.Empty: return False, None
            except Exception as e: print(f"Error reading temp frame: {e}"); return False, None

        # def release(self):
        #     if not self._running and not (self._thread and self._thread.is_alive()): return
        #     print(f"Releasing Optris camera S/N {self._actual_serial}...")
        #     self._running = False
        #     if self._imager:
        #         try:
        #             if self._imager.isRunning(): self._imager.stopRunning()
        #         except Exception as e: print(f"Error stopping imager: {e}")
        #     self._cleanup_queues()
        #     if self._thread and self._thread.is_alive():
        #         self._thread.join(timeout=2.0)
        #         if self._thread.is_alive(): print("Warning: SDK thread join timeout.")
        #     self._thread = None
        #     if self._imager:
        #         try: self._imager.removeClient(self)
        #         except Exception as e: print(f"Error removing client: {e}")
        #         try:
        #             if self._imager.isConnected(): self._imager.disconnect()
        #         except Exception as e: print(f"Error disconnecting: {e}")
        #         finally: self._imager = None
        #     self._builder = None
        #     print(f"Optris camera S/N {self._actual_serial} released.")

        # (这个方法属于 OptrisCamera 类, 不是 IRWorker)
        def release(self):
            """
            一个更健壮、更耐心的 release 版本
            """
            if not self._running:
                return

            print(f"Releasing Optris camera (S/N {self._actual_serial})...")
            self._running = False # 1. 告诉回调函数停止处理新帧

            if self._imager:
                try:
                    print("  Calling _imager.stopRunning()...")
                    self._imager.stopRunning() # 2. 告诉 SDK 停止
                except Exception as e:
                    print(f"  Error in stopRunning(): {e}")

            # 3. 清理队列 (这一步是好的)
            try:
                self._color_frame_queue.put_nowait(None)
                self._temp_frame_queue.put_nowait(None)
            except queue.Full:
                pass 

            if self._thread and self._thread.is_alive():
                print("  Waiting for internal thread to join()... (必须等待)")
                
                # 4. 【关键修复 1】移除 timeout
                #    我们必须 100% 确认此线程已退出，无论花多久
                self._thread.join() 
                
                print("  Internal thread successfully joined.")

            if self._imager:
                try:
                    print("  Removing client from _imager...")
                    self._imager.removeClient(self)
                except Exception as e:
                    print(f"  Error in removeClient(): {e}")
                
                # 5. 【关键修复 2】尝试强制 C++ 析构
                print("  Deleting _imager object...")
                try:
                    del self._imager
                except Exception as e:
                    print(f"  Error in del _imager: {e}")
                
                self._imager = None
            
            self._builder = None
            
            # 6. 【关键修复 3】
            #    在返回之前，强制暂停 1 秒钟
            #    给 Windows/Linux 操作系统足够的时间来释放 USB 设备句柄
            print("  Release complete. Waiting 1s for OS handle...")
            import time
            time.sleep(4.0) 
            
            print(f"Optris camera S/N {self._actual_serial} fully released.")

        def force_flag_event(self):
            if self._imager and self.isOpened():
                 try: self._imager.forceFlagEvent()
                 except otc.SDKException as e: print(f"Error forcing flag event: {e}")
            else: print("Cannot force flag event: Not running.")

        def get_flag_state(self):
            with self._flag_state_lock: return self._flag_state

        def get_properties(self):
            w = self._width if self._width > 0 else (self._imager.getWidth() if self._imager else 0)
            h = self._height if self._height > 0 else (self._imager.getHeight() if self._imager else 0)
            return {
                "requested_serial": self._requested_serial,
                "actual_serial": self._actual_serial,
                "device_type": self._device_type,
                "width": w, "height": h }

        def get(self, propId):
            if propId == cv2.CAP_PROP_FRAME_WIDTH: return self._width if self._width > 0 else (self._imager.getWidth() if self._imager else 0)
            if propId == cv2.CAP_PROP_FRAME_HEIGHT: return self._height if self._height > 0 else (self._imager.getHeight() if self._imager else 0)
            return None

        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): self.release()

        # --- [回调函数 onThermalFrame, onFlagStateChange, onConnectionLost, onConnectionTimeout, _cleanup_queues 保持不变] ---
        def onThermalFrame(self, thermal, meta):
            if not self._running: return
            if self._width == 0:
                try:
                    self._width = thermal.getWidth()
                    self._height = thermal.getHeight()
                    if self._imager:
                        self._actual_serial = self._imager.getSerialNumber()
                        self._device_type = otc.deviceTypeToString(self._imager.getDeviceType())
                        print(f"First frame received S/N {self._actual_serial} ({self._width}x{self._height}). Type: {self._device_type}")
                    else: print(f"First frame received ({self._width}x{self._height}).")
                except Exception as e: print(f"Error getting device info in callback: {e}")

            if self._builder:
                try:
                    try: self._color_frame_queue.get_nowait()
                    except queue.Empty: pass
                    self._builder.setThermalFrame(thermalFrame=thermal)
                    self._builder.convertTemperatureToPaletteImage()
                    image = np.empty((self._height, self._width, 3), dtype=np.uint8)
                    self._builder.copyImageDataTo(image)
                    self._color_frame_queue.put_nowait(image)
                except queue.Full: pass
                except Exception as e: print(f"Error processing color frame: {e}")

            try:
                try: self._temp_frame_queue.get_nowait()
                except queue.Empty: pass
                temp_data = np.empty((self._height, self._width), dtype=np.float32)
                thermal.copyTemperaturesTo(temp_data)
                self._temp_frame_queue.put_nowait(temp_data)
            except queue.Full: pass
            except Exception as e: print(f"Error processing temp frame: {e}")

        def onFlagStateChange(self, flagState):
            with self._flag_state_lock: self._flag_state = flagState

        def onConnectionLost(self):
            print(f"错误: 连接丢失 S/N {self._actual_serial} (不可恢复)。")
            self._running = False; self._cleanup_queues()

        def onConnectionTimeout(self):
            print(f"错误: 连接超时 S/N {self._actual_serial}。")
            self._running = False; self._cleanup_queues()

        def _cleanup_queues(self):
            # print("Cleaning up frame queues...") # 可以取消注释以进行调试
            for q in (self._color_frame_queue, self._temp_frame_queue):
                try:
                    while True: q.get_nowait()
                except queue.Empty: pass
                try: q.put_nowait(None)
                except queue.Full: pass
            # print("Frame queues cleaned.") # 可以取消注释以进行调试

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
                except Exception as e:
                    print(f"Error setting focus position: {e}")
                    return False
            return False

        def get_focus(self):
            """
            获取当前马达对焦的位置 (int)。
            """
            if self._imager and self._running:
                try:
                    position = self._imager.getFocusMotorPosition()
                    return position
                except Exception as e:
                    print(f"Error getting focus position: {e}")
                    return None
            return None

# --- 用法示例 ---
def main():
    """ 演示如何使用封装的 OptrisCamera 类。 """
    if not OPTRIS_LIB_LOADED:
        print("无法运行示例，Optris SDK 未加载。")
        return

    # --- 步骤 1: 查询可用范围 ---
    print("-" * 30 + "\n步骤 1: 查询可用温度范围\n" + "-" * 30)
    available_ranges = OptrisCamera.list_available_ranges(serial_number=0)

    TARGET_RANGE_INDEX = None # 默认为 None (使用默认)
    USE_EXTENDED_RANGE = True # 默认不使用扩展范围

    if not available_ranges:
        print("\n未能获取可用范围。将尝试使用默认设置连接...")
    else:
        # --- 步骤 2: 选择范围索引和是否扩展 ---
        # 示例：假设我们想用索引 1 (例如 0-250 C), 并且尝试启用扩展范围
        TARGET_RANGE_INDEX = 4
        USE_EXTENDED_RANGE = True # *** 设置为 True 来尝试启用扩展范围 ***

        print(f"\n选择使用范围索引: {TARGET_RANGE_INDEX}")
        if 0 <= TARGET_RANGE_INDEX < len(available_ranges):
             selected_range_info = available_ranges[TARGET_RANGE_INDEX]
             print(f"  对应范围: [{selected_range_info['min_temp']:.1f}, {selected_range_info['max_temp']:.1f}] C")
             if selected_range_info['supports_extended']:
                 print(f"  此范围支持扩展至: [{selected_range_info['min_temp_extended']:.1f}, {selected_range_info['max_temp_extended']:.1f}] C")
                 if USE_EXTENDED_RANGE:
                      print("  *** 将尝试启用扩展范围 ***")
                 else:
                      print("  (当前未启用扩展范围)")
             elif USE_EXTENDED_RANGE:
                 print("  *** 警告: 此范围不支持扩展，但请求了扩展。将忽略请求。 ***")
                 USE_EXTENDED_RANGE = False # 强制改回 False
        else:
             print("警告: 选择的索引无效，将使用默认范围 (None)")
             TARGET_RANGE_INDEX = None
             USE_EXTENDED_RANGE = False # 默认不扩展

    print("-" * 30 + f"\n步骤 3: 使用索引 {TARGET_RANGE_INDEX if TARGET_RANGE_INDEX is not None else 'Default'} {'并请求扩展范围' if USE_EXTENDED_RANGE else ''} 初始化相机\n" + "-" * 30)

    cap = None
    try:
        with OptrisCamera(serial_number=0,
                          temp_range_index=TARGET_RANGE_INDEX,
                          use_extended_range=USE_EXTENDED_RANGE) as cap: # <-- 传递新参数

            print("等待相机初始化和第一帧 (最多 10 秒)...")
            start_wait = time.time()
            props = cap.get_properties()
            while props['width'] == 0 and time.time() - start_wait < 10.0:
                if not cap.isOpened(): print("错误: 相机未能打开或已关闭。"); return
                time.sleep(0.1); props = cap.get_properties()

            if props['width'] == 0: print("错误: 等待第一帧超时。"); return

            print("\n相机初始化完成:")
            print(f"  实际序列号: {props['actual_serial']}")
            print(f"  设备类型: {props['device_type']}")
            print(f"  分辨率: {props['width']}x{props['height']}")
            # 你可以在这里再次调用 imager.getActiveOperationMode() 来确认实际生效的范围
            # 但这需要稍微修改类以暴露 _imager 或添加一个新方法
            # 例如: print(f"  当前模式: {str(cap._imager.getActiveOperationMode())}")
            print("-" * 30 + "\n开始显示图像...\n" + "-" * 30)

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
                    else: cv2.putText(display_frame, "Temp: N/A", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1, cv2.LINE_AA)

                    flag_state_str = otc.flagStateToString(cap.get_flag_state())
                    cv2.putText(display_frame, f"Flag: {flag_state_str}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                    cv2.imshow("Optris Camera Feed", display_frame)

                elif not ret_img and cap.isOpened(): pass # 超时

                key = cv2.waitKey(10) & 0xFF
                if key == ord('q'): print("检测到 'q'，退出..."); break
                elif key == ord('r'): print("检测到 'r'，触发快门..."); cap.force_flag_event()

            print("主循环结束。")

    except otc.SDKException as ex: print(f"\n发生 SDK 错误: {ex}")
    except KeyboardInterrupt: print("\n用户中断 (Ctrl+C)。")
    except Exception as e: print(f"\n发生意外错误: {e}")
    finally:
        cv2.destroyAllWindows()
        print("所有窗口已关闭。示例结束。")

if __name__ == "__main__":
    # 确保 SDK 已加载才运行 main
    if OPTRIS_LIB_LOADED:
        main()
    else:
        print("\n由于 Optris SDK 加载失败，无法运行 main() 函数。")
        # 在某些系统上，可能需要按 Enter 键退出
        # input("按 Enter 退出...")
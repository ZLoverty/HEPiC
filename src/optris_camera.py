import sys
import threading
import queue  # 使用队列进行线程安全的数据交换
import numpy as np
try:
    import optris.otcsdk as otc
    OPTRIS_LIB_LOADED = True
except ImportError:
    print(f"没找到 optris 红外成像仪的开发包")
    OPTRIS_LIB_LOADED = False
import cv2  # 仅用于 get() 方法的常量

# 确保 SDK 只被初始化一次
_SDK_INITIALIZED_LOCK = threading.Lock()
_SDK_INITIALIZED = False

if OPTRIS_LIB_LOADED:
    class OptrisCamera(otc.IRImagerClient):
        """
        一个封装了 Optris SDK 的类，提供了类似 cv2.VideoCapture 的接口。

        它在后台线程中处理相机数据，并通过线程安全的队列
        向主线程提供伪色图像和温度数据。
        """

        def __init__(self, serial_number=0):
            """
            初始化相机并开始数据采集。
            """
            global _SDK_INITIALIZED, _SDK_INITIALIZED_LOCK
            super().__init__()

            # --- 1. SDK 初始化 (线程安全) ---
            with _SDK_INITIALIZED_LOCK:
                if not _SDK_INITIALIZED:
                    otc.Sdk.init(otc.Verbosity_Info, otc.Verbosity_Off, "")
                    _SDK_INITIALIZED = True

            self._imager = None
            self._builder = None
            self._thread = None
            self._running = False

            # --- 2. 线程安全队列 (maxsize=1 确保我们总是处理最新帧) ---
            self._color_frame_queue = queue.Queue(maxsize=1)
            self._temp_frame_queue = queue.Queue(maxsize=1)

            # --- 3. 状态锁和变量 ---
            self._flag_state_lock = threading.Lock()
            self._flag_state = otc.FlagState_Initializing
            
            # --- 4. 属性 (将在 onThermalFrame 中被设置) ---
            self._width = 0
            self._height = 0
            self._serial = serial_number  # 存储 *请求* 的序列号
            self._device_type = "Initializing"

            try:
                # --- 5. 初始化和连接相机 ---
                factory = otc.IRImagerFactory.getInstance()
                self._imager = factory.create('native')
                
                self._imager.addClient(self)
                self._imager.connect(serial_number)
                
                # --- 6. 初始化伪色图像构建器 ---
                self._builder = otc.ImageBuilder(
                    colorFormat=otc.ColorFormat_BGR, 
                    widthAlignment=otc.WidthAlignment_OneByte
                )
                
                # --- 7. 启动 SDK 运行线程 ---
                self._running = True
                self._thread = threading.Thread(target=self._imager.run)
                self._thread.daemon = True
                self._thread.start()

                print(f"Optris camera (S/N: {self._serial}) connection process started...")

            except otc.SDKException as ex:
                print(f"Error initializing Optris camera: {ex}")
                self.release()
                raise

        # ... [isOpened, read, read_temp, release, etc. 保持不变] ...
        def isOpened(self):
            """ 检查相机连接是否仍在运行。 """
            return self._running

        def read(self, timeout=1.0):
            """
            读取一帧伪色图像 (BGR)。
            """
            if not self._running:
                return False, None

            try:
                frame = self._color_frame_queue.get(timeout=timeout)
                if frame is None:
                    self._running = False
                    return False, None
                return True, frame
            except queue.Empty:
                return False, None

        def read_temp(self, timeout=1.0):
            """
            读取一帧温度数据 (摄氏度)。
            """
            if not self._running:
                return False, None

            try:
                temps = self._temp_frame_queue.get(timeout=timeout)
                if temps is None:
                    self._running = False
                    return False, None
                return True, temps
            except queue.Empty:
                return False, None

        def release(self):
            """
            停止相机线程，断开连接并释放所有资源。
            """
            if not self._running:
                return

            print(f"Releasing Optris camera S/N {self._serial}...")
            self._running = False

            if self._imager:
                self._imager.stopRunning()

            try:
                self._color_frame_queue.put_nowait(None)
                self._temp_frame_queue.put_nowait(None)
            except queue.Full:
                pass 

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

            if self._imager:
                self._imager.removeClient(self)
                self._imager = None
            
            self._builder = None
            print(f"Optris camera S/N {self._serial} released.")

        def force_flag_event(self):
            """ 手动触发一次快门（校准）事件。 """
            if self._imager and self._running:
                self._imager.forceFlagEvent()

        def get_flag_state(self):
            """ 获取当前的快门状态。 """
            with self._flag_state_lock:
                return self._flag_state

        def get_properties(self):
            """ 返回相机属性字典。 """
            return {
                "serial": self._serial,
                "device": self._device_type,
                "width": self._width,
                "height": self._height
            }

        def get(self, propId):
            """
            模拟 cv2.VideoCapture.get()。
            """
            if propId == cv2.CAP_PROP_FRAME_WIDTH:
                return self._width
            if propId == cv2.CAP_PROP_FRAME_HEIGHT:
                return self._height
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()

        # --- IRImagerClient 回调 (由 SDK 线程调用) ---

        def onThermalFrame(self, thermal, meta):
            """
            [SDK 线程] 
            当新帧可用时由 SDK 在后台调用。
            """
            if not self._running:
                return

            # 1. 更新尺寸和设备信息 (仅在第一帧时执行)
            # -----------------------------------------------------------------
            if self._width == 0:
                self._width = thermal.getWidth()
                self._height = thermal.getHeight()
                
                # !! 关键修正 !!
                # 只有在第一帧到达后，我们才能安全地获取序列号和设备类型
                try:
                    self._serial = self._imager.getSerialNumber()
                    self._device_type = otc.deviceTypeToString(self._imager.getDeviceType())
                    print(f"Optris camera S/N {self._serial} connected ({self._width}x{self._height}).")
                except Exception as e:
                    print(f"Error getting device info in callback: {e}")
            # -----------------------------------------------------------------

            # --- 2. 处理伪色图像 (read() 方法) ---
            try:
                self._color_frame_queue.get_nowait()
            except queue.Empty:
                pass  
            
            try:
                self._builder.setThermalFrame(thermalFrame=thermal)
                self._builder.convertTemperatureToPaletteImage()
                image = np.empty((self._height, self._width, 3), dtype=np.uint8)
                self._builder.copyImageDataTo(image)
                self._color_frame_queue.put_nowait(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)) # 使用 put_nowait
            except queue.Full:
                pass # 如果主线程处理不及时，丢弃此帧
            except Exception as e:
                print(f"Error in color frame processing: {e}")


            # --- 3. 处理温度数据 (read_temp() 方法) ---
            try:
                self._temp_frame_queue.get_nowait()
            except queue.Empty:
                pass 

            try:
                temp_data = np.empty((self._height, self._width), dtype=np.float32)
                thermal.copyTemperaturesTo(temp_data) 
                
                self._temp_frame_queue.put_nowait(temp_data) # 使用 put_nowait
            except queue.Full:
                pass # 如果主线程处理不及时，丢弃此帧
            except Exception as e:
                print(f"Error in temperature frame processing: {e}")


        def onFlagStateChange(self, flagState):
            """ [SDK 线程] 当快门状态改变时调用。 """
            with self._flag_state_lock:
                self._flag_state = flagState
                # print(f"Flag state changed to: {otc.flagStateToString(flagState)}")

        def onConnectionLost(self):
            """ [SDK 线程] 当连接丢失时调用。 """
            print("Error: Connection to imager lost.")
            self._running = False
            self._cleanup_queues()

        def onConnectionTimeout(self):
            """ [SDK 线程] 当连接超时时调用。 """
            print("Error: Connection to imager timed out.")
            self._running = False
            self._cleanup_queues()

        def _cleanup_queues(self):
            """ [SDK 线程] 发生错误时，清空队列并放入 None 信号。 """
            for q in (self._color_frame_queue, self._temp_frame_queue):
                try:
                    while True: q.get_nowait() # 清空队列
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(None) # 放入 None 信号
                except queue.Full:
                    pass


    # --- 用法示例 (保持不变) ---

    def main():
        """
        演示如何使用封装的 OptrisCamera 类。
        """
        try:
            with OptrisCamera(serial_number=0) as cap:
                
                # 等待第一帧以获取正确的属性
                print("Waiting for first frame to get properties...")
                while cap.get(cv2.CAP_PROP_FRAME_WIDTH) == 0:
                    if not cap.isOpened():
                        print("Camera failed to open.")
                        return
                    cv2.waitKey(10) # 等待

                props = cap.get_properties()
                print(f"Device: {props['device']}, S/N: {props['serial']}")
                print(f"Resolution: {props['width']}x{props['height']}")
                
                while cap.isOpened():
                    
                    ret_img, frame = cap.read(timeout=0.1)
                    ret_temp, temps = cap.read_temp(timeout=0.1)

                    if ret_img and ret_temp:
                        mean_temp = np.mean(temps)
                        flag_state_str = otc.flagStateToString(cap.get_flag_state())
                        
                        cv2.putText(frame, f"Mean Temp: {mean_temp:.2f} C", (10, 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(frame, f"Flag: {flag_state_str}", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                        cv2.imshow("Optris Camera", frame)
                    
                    key = cv2.waitKey(10) & 0xFF
                    if key == ord('q'):
                        break
                    elif key == ord('r'):
                        print("Forcing flag event (refresh)...")
                        cap.force_flag_event()

        except otc.SDKException as ex:
            print(f"SDK Error: {ex}")
        except KeyboardInterrupt:
            print("User interrupted.")
        finally:
            cv2.destroyAllWindows()
            print("Demo finished.")


if __name__ == "__main__":
    main()
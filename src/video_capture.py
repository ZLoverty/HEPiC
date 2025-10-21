import cv2
import queue
import time
import numpy as np
from hikrobotcamlib import Camera, DeviceList, Frame, DeviceTransport 

class HikVideoCapture:
    """
    一个模拟 cv2.VideoCapture 接口的类，用于海康机器人工业相机。
    增加了在初始化时配置分辨率、曝光时间，并能自动将ROI居中的功能。

    用法:
        # 使用默认设置 (全分辨率)
        cap = HikVideoCapture()

        # 自定义分辨率和曝光，并自动居中ROI
        cap = HikVideoCapture(width=1280, height=1024, exposure_time=10000)

        # 自定义分辨率，但不自动居中 (ROI将位于左上角)
        cap = HikVideoCapture(width=1280, height=1024, center_roi=False)
    """

    def __init__(self, width: int | None = None, height: int | None = None, exposure_time: float | None = None, center_roi: bool = True):
        
        self.cam: Camera | None = None
        self._is_opened = False
        self.frame_queue = queue.Queue(maxsize=2)

        try:
            print("正在搜索设备...")
            dev_info = next(iter(DeviceList(DeviceTransport.GIGE | DeviceTransport.USB)), None)
            if dev_info is None:
                print("错误: 未找到任何相机设备。")
                return

            self.cam = Camera(dev_info)
            self.cam.open()
            
            # --- 核心逻辑：设置ROI并居中 ---
            if width is not None and height is not None:
                # 1. 设置用户请求的ROI尺寸
                if self.cam.set_int("Width", width): print(f"成功设置宽度为: {width}")
                else: print(f"警告: 设置宽度 {width} 失败。")
                
                if self.cam.set_int("Height", height): print(f"成功设置高度为: {height}")
                else: print(f"警告: 设置高度 {height} 失败。")

                # 2. 如果需要，计算并设置偏移量以居中ROI
                if center_roi:
                    try:
                        width_max = self.cam.get_int("WidthMax")
                        height_max = self.cam.get_int("HeightMax")
                        
                        # 使用整数除法计算偏移量
                        offset_x = (width_max - width) // 2
                        offset_y = (height_max - height) // 2
                        
                        print(f"传感器最大分辨率: {width_max}x{height_max}。正在计算居中偏移...")
                        
                        if self.cam.set_int("OffsetX", offset_x): print(f"成功设置 OffsetX 为: {offset_x}")
                        else: print(f"警告: 设置 OffsetX {offset_x} 失败。")
                        
                        if self.cam.set_int("OffsetY", offset_y): print(f"成功设置 OffsetY 为: {offset_y}")
                        else: print(f"警告: 设置 OffsetY {offset_y} 失败。")

                    except Exception as e:
                        print(f"警告: 自动居中ROI时出错: {e}。ROI可能未居中。")
            
            # --------------------------

            if exposure_time is not None:
                if self.cam.set_float("ExposureTime", exposure_time): print(f"成功设置曝光时间为: {exposure_time} us")
                else: print(f"警告: 设置曝光时间 {exposure_time} us 失败。")
            
            if not self.cam.set_enum("PixelFormat", "Mono8"):
                print("警告: 设置 Mono8 失败。")

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

    def _frame_callback(self, frame, cam) -> None:
        if self.frame_queue.full():
            try: self.frame_queue.get_nowait()
            except queue.Empty: pass
        
        height = frame.infoptrcts.nHeight
        width = frame.infoptrcts.nWidth
        img_data = np.ctypeslib.as_array(frame.dataptr, shape=(frame.len,)).copy()
        
        try:
            img = img_data.reshape((height, width))
            self.frame_queue.put_nowait(img)
        except (ValueError, queue.Full):
            pass

    def isOpened(self) -> bool:
        return self._is_opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.isOpened():
            return False, None
        try:
            frame = self.frame_queue.get(timeout=1.0)
            return True, frame
        except queue.Empty:
            print("警告: 等待帧超时。")
            return False, None

    def release(self):
        if self.cam and self.isOpened():
            print("正在释放相机资源...")
            self.cam.stop()
            self.cam.close()
        self._is_opened = False

# --- 如何使用 ---
if __name__ == '__main__':
    # === 示例: 设置一个 640x480 的视窗，并让它在传感器上自动居中 ===
    print("--- 正在以自定义参数启动 (ROI居中) ---")
    cap = HikVideoCapture(width=640, height=480, exposure_time=100000, center_roi=True)
    
    if not cap.isOpened():
        print("无法启动相机，程序退出。")
    else:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 在图像上显示尺寸，方便验证
            
            cv2.imshow('Hikvision Feed (Centered ROI)', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    print("程序结束。")
    cap.release()
    cv2.destroyAllWindows()
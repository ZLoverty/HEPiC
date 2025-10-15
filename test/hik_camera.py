# from typing import Optional
# import time

# from hikrobotcamlib import Camera, DeviceList, Frame, DeviceTransport

# def frame_callback(frame: Frame, cam: Camera) -> None:
#     """Handle frames from camera"""
#     # TODO: Do something with the frame

# cam: Optional[Camera] = None
# for devinfo in DeviceList(DeviceTransport.GIGE | DeviceTransport.USB):
#     cam = Camera(devinfo)
#     break

# if not cam:
#     raise RuntimeError("No camera")

# cam.open()
# cam.frame_callback = frame_callback
# cam.trigger_enable(False)
# cam.set_framerate(10.0)
# cam.start()
# time.sleep(2.5)
# cam.stop()
# cam.close()

import cv2
import threading
import time
from hikrobotcamlib import Camera, DeviceList, Frame, DeviceTransport
import numpy as np

# --- 全局变量 ---
# 用于在回调函数和主线程之间安全地传递最新一帧图像
latest_frame = None
# 线程锁，防止在读取和写入帧时发生冲突
frame_lock = threading.Lock()
# -----------------

def frame_callback(frame: Frame, cam: Camera) -> None:
    """
    This is the camera's callback function.
    It now gets the frame's dimensions directly from the camera object.
    """
    global latest_frame
    
    pixel_format = cam.get_pixelformat()

    w, h = frame.infoptrcts.nWidth, frame.infoptrcts.nHeight
    img_data = np.frombuffer(frame.data, dtype=np.uint8).reshape(h, w)
    
    with frame_lock:
        latest_frame = img_data

def main():
    """主函数"""
    global latest_frame

    # 1. 查找并初始化相机 (与官方示例相同)
    cam: Camera | None = None
    print("正在搜索GigE和USB3设备...")
    # 使用 for 循环找到第一个可用的相机
    for devinfo in DeviceList(DeviceTransport.GIGE | DeviceTransport.USB):
        # 打印找到的设备信息，方便调试
        print(f"找到设备: {devinfo.model} ({devinfo.serialno})")
        cam = Camera(devinfo)
        break

    if not cam:
        print("错误: 未找到任何相机设备。请检查连接和网络配置。")
        return

    # 2. 打开相机并开始采集
    # 使用 'with' 语句可以确保相机资源在结束时被自动、安全地释放
    try:
        cam.open()
        # print(f"已成功打开相机: {cam.device_info.model}")

        # 注册我们的回调函数
        cam.frame_callback = frame_callback

        # 关闭触发模式，让相机自由运行在连续采集模式
        cam.trigger_enable(False)

        # 设置黑白 8-bit
        cam.set_enum("PixelFormat", "Mono8")
        
        # 开始图像采集
        cam.start()
        print("相机已开始采集。按 'q' 键或关闭窗口退出。")
        
        window_created = False

        # 3. 主循环，用于显示图像
        while True:
            display_frame = None
            
            # 从全局变量中获取最新一帧
            with frame_lock:
                if latest_frame is not None:
                    # 复制帧以尽快释放锁，让回调函数可以继续更新
                    display_frame = latest_frame.copy()

            # 如果成功获取到帧，就用OpenCV显示它
            if display_frame is not None:
                cv2.imshow('Hikvision Camera Feed', display_frame)
                window_created = True

            # 等待1毫秒，并检查按键。如果按下'q'，则退出循环
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            
            # 检查窗口是否被用户关闭
            if window_created and cv2.getWindowProperty('Hikvision Camera Feed', cv2.WND_PROP_VISIBLE) < 1:
                break

    finally:
        print("程序结束，正在清理资源...")
        # 销毁所有OpenCV窗口
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
# from image_streamer import ImageStreamer # 如果保存在单独文件中
import time
import cv2
from image_streamer import ImageStreamer
from pathlib import Path
# --- 配置 ---
IMAGE_FOLDER = '/home/zhengyang/Documents/GitHub/etp_ctl/test/filament_images_simulated'
FPS = 60
# ----------------

# 创建 ImageStreamer 实例，就像创建 VideoCapture 一样
# cap = cv2.VideoCapture(0)  # 这是您原来的代码
cap = ImageStreamer(IMAGE_FOLDER, fps=FPS, loop=True) # 这是新的替代代码

if not cap.isOpened():
    print("Error: Could not open image stream.")
    exit()

frame_delay = 1 / cap.get(cv2.CAP_PROP_FPS)

while True:
    # 读取一帧，接口完全相同！
    ret, frame = cap.read()
    
    # 如果读取失败（例如，不循环播放且已到结尾）
    if not ret:
        print("End of stream.")
        break
        
    # --- 在这里是您的图像分析和数据同步逻辑 ---
    # timestamp = time.time()
    # analysis_result = your_analysis_function(frame)
    # video_queue.append((timestamp, analysis_result))
    # ---------------------------------------------
    
    cv2.imshow('My App - Simulated Video', frame)
    
    # 在主循环中控制帧率
    time.sleep(frame_delay)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()
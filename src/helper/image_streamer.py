"""
image_streamer.py
===============
Simulate a video stream to test the filament detection module. This script makes use of a few filament detection test images, basically send them over to a buffer at a specified rate and let the main process access the images. Note that the `ImageStreamer` class can be directly replaced by cv2.VideoCapture in production.
"""

import cv2
import os
import glob
import time

class ImageStreamer:
    """
    一个模拟 cv2.VideoCapture 的类，用于从一系列静态图片创建一个视频流。
    """
    def __init__(self, image_folder, fps=30, loop=True):
        """
        初始化
        :param image_folder: 包含图片的文件夹路径
        :param fps: 模拟的帧率
        :param loop: 是否循环播放
        """
        self.image_folder = image_folder
        self.fps = fps
        self.loop = loop
        
        # 获取并排序图片文件
        self.image_files = sorted(glob.glob(os.path.join(self.image_folder, '*.[pP][nN][gG]')) + 
                                  glob.glob(os.path.join(self.image_folder, '*.[jJ][pP][gG]')) +
                                  glob.glob(os.path.join(self.image_folder, '*.[jJ][pP][eE][gG]')))
        
        if not self.image_files:
            raise FileNotFoundError(f"No images found in the directory: {self.image_folder}")

        self.num_frames = len(self.image_files)
        self.current_frame_index = 0
        self._is_opened = True

    def isOpened(self):
        """模拟 isOpened() 方法。"""
        return self._is_opened and self.current_frame_index < self.num_frames

    def read(self):
        """
        模拟 read() 方法。
        返回一个元组 (success, frame)。
        """
        if not self.isOpened():
            return (False, None)

        # 获取当前帧的路径
        image_path = self.image_files[self.current_frame_index]
        frame = cv2.imread(image_path)
        
        if frame is None:
            # 读取失败
            print(f"Warning: Failed to read {image_path}")
            # 尝试移动到下一帧
            self.current_frame_index += 1
            if self.loop:
                self.current_frame_index %= self.num_frames
            return self.read() # 递归调用以获取下一个有效帧

        # 移动到下一帧
        self.current_frame_index += 1
        
        # 处理循环
        if self.loop and self.current_frame_index >= self.num_frames:
            self.current_frame_index = 0
            
        return (True, frame)

    def release(self):
        """模拟 release() 方法。"""
        self._is_opened = False
        self.current_frame_index = 0
        self.image_files = []

    def get(self, propId):
        """模拟 get() 方法，可以返回FPS等信息。"""
        if propId == cv2.CAP_PROP_FPS:
            return self.fps
        # 可以根据需要添加其他属性
        return None
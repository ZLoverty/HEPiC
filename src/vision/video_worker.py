from PySide6.QtCore import QObject, Signal, Slot, QTimer
import numpy as np
from pathlib import Path
from config import Config
import os
from .vision import binarize, filament_diameter, convert_to_grayscale, draw_filament_contour, find_longest_branch, ImageStreamer
import time
import cv2

if not Config.test_mode:
    if os.name == "nt":
        # if on windows OS, import the windows camera library
        from hikcam_win import HikVideoCapture
    else:
        # on Mac / Linux, use a different library
        from .video_capture import HikVideoCapture  

class VideoWorker(QObject):
    """
    运行 ImageStreamer 的工作线程，通过信号发送图像帧。
    """
    new_frame_signal = Signal(np.ndarray)
    roi_frame_signal = Signal(np.ndarray)
    sigFinished = Signal()

    def __init__(self, test_mode=False):
        """
        Parameters
        ----------
        test_mode : bool
            if true, enable test mode, which utilizes a sequence of local images to simulate a video stream from a camera.
        """
        super().__init__()
        self.is_running = True
        self.roi = None
        self._timer = None
        self.test_mode = test_mode

        if test_mode:  # 调试用图片流
            image_folder = Path(Config.test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(image_folder), fps=10)
        else: # 真图片流
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=50000, center_roi=True)
            
        
    def run(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.read_one_frame)
        self._timer.start(0.1)
        self.thread().exec()

        print("IRWorker 事件循环已停止。")
        self.cap.release()
        self.sigFinished.emit() # 通知主线程

    def read_one_frame(self):

        if not self.cap:
            return
        
        ret, frame = self.cap.read()
        if ret:
            self.new_frame_signal.emit(frame)
            if self.roi is None:
                # if ROI is not set, show the whole frame in the ROI panel
                self.roi_frame_signal.emit(frame)
            else:
                x, y, w, h = self.roi
                self.roi_frame_signal.emit(frame[y:y+h, x:x+w])
        else:
            print("Fail to read frame.")

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot()
    def stop(self):
        print("Stopping video worker thread.")
        self.is_running = False
        self.cap.release()

    @Slot(float)
    def set_exp_time(self, exp_time):
        """
        Parameters
        ----------
        exp_time : float
            exposure time in ms.
        """
        self.cap.release()
        while self.cap.is_open:
            time.sleep(1)
        if self.test_mode:
            print("Test mode: exposure time setting will not have any effect.")
        else:
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=exp_time*1000, center_roi=True)

class ProcessingWorker(QObject):
    """基于 distance transform 计算前景图案的尺寸。"""

    proc_frame_signal = Signal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.die_diameter = np.nan
        self.invert = False
        
    @Slot(np.ndarray)
    def process_frame(self, img):
        """Find filament in image and update the `self.die_diameter` variable with detected filament diameter."""
        gray = convert_to_grayscale(img) # only process gray images    
        try:
            binary = binarize(gray)
            if self.invert:
                binary = cv2.bitwise_not(binary)
            diameter, skeleton, dist_transform = filament_diameter(binary)
            skel_px = dist_transform[skeleton]
            skeleton_refine = skeleton.copy()
            skeleton_refine[dist_transform < skel_px.mean()] = False
            # filter the pixels on skeleton where dt is smaller than 0.9 of the max
            diameter_refine = dist_transform[skeleton_refine].mean() * 2.0
            proc_frame = draw_filament_contour(gray, skeleton_refine, diameter_refine)
            self.proc_frame_signal.emit(proc_frame)
            self.die_diameter = diameter_refine
        except ValueError as e:
            # 已知纯色图片会导致检测失败，在此情况下可以不必报错继续运行，将出口直径记为 np.nan 即可
            print(f"图像无法处理: {e}")
            self.proc_frame_signal.emit(binary)
    
    @Slot(bool)
    def invert_toggle(self, checked):
        """Sometimes the filament is the darker part of the image and background is brighter. In such cases, we may invert the binary image to make the algorithm work correctly. This is a toggle for the user to manually switch on/off whether to invert."""
        self.invert = checked
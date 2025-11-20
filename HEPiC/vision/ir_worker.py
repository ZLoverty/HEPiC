"""
communications.py
=================
Handles serial port / IP communications.
"""

from PySide6.QtCore import QObject, Signal, QTimer, Slot
import numpy as np
from pathlib import Path
from .vision import ImageStreamer

OPTRIS_LIB_LOADED = False
try:
    from .optris_camera import OptrisCamera
    OPTRIS_LIB_LOADED = True
except Exception as e:
    print(f"Fail to load Optris camera lib.")
        
class IRWorker(QObject):

    sigNewFrame = Signal(np.ndarray)
    sigRoiFrame = Signal(np.ndarray)
    sigFinished = Signal()

    def __init__(self, test_mode=False, test_image_folder=""):

        super().__init__()
        self.is_running = True
        self.roi = None
        self.die_temperature = np.nan
        self._timer = None

        if test_mode:  # 调试用图片流
            test_image_folder = Path(test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(test_image_folder), fps=10)
        else:
            self.ranges = OptrisCamera.list_available_ranges(0)
            self.cap = OptrisCamera()
            
    def run(self):
        self._timer = QTimer(self)

        self._timer.timeout.connect(self.read_one_frame)
        self._timer.start(0)
        self.thread().exec()

        print("IRWorker 事件循环已停止。")
        self.cap.release()
        self.sigFinished.emit() # 通知主线程
    
    def read_one_frame(self):

        if not self.cap:
            return
        
        ret_img, frame = self.cap.read(timeout=0.1)
        ret_temp, temps = self.cap.read_temp(timeout=0.1)
        if ret_img and ret_temp:
            self.sigNewFrame.emit(frame)
            if self.roi is None:
                # if ROI is not set, use the whole frame as ROI
                self.sigRoiFrame.emit(frame)
                self.die_temperature = temps.max()
            else:
                x, y, w, h = self.roi
                self.sigRoiFrame.emit(frame[y:y+h, x:x+w])
                self.die_temperature = temps[y:y+h, x:x+w].max()
        else:
            print("Fail to read frame.")

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot(int)
    def set_range(self, range_index):
        if self._timer:
            self._timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.cap = OptrisCamera(temp_range_index=range_index)

        if self.cap and self._timer:
            self._timer.start(0)

    @Slot(int)
    def set_position(self, position):
        if self.cap:
            self.cap.set_focus(position)

    def stop(self):
        self.is_running = False
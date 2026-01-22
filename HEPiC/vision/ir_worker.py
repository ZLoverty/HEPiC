"""
communications.py
=================
Handles serial port / IP communications.
"""
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer, Slot
import numpy as np
from vision_utils import ImageStreamer
import logging

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
        self.test_mode = test_mode
        self.test_image_folder = test_image_folder
        self.is_running = True
        self.roi = None
        self.die_temperature = np.nan
        self._timer = QTimer(self)
        self.cap = None

        # logging 
        self.logger = logging.getLogger(__name__)
        
    
    def _initialize_cap(self, range_index=0):

        if self.test_mode:  # 调试用图片流
            test_image_folder = Path(self.test_image_folder).expanduser().resolve()
            return ImageStreamer(str(test_image_folder), fps=10)
        else:
            return OptrisCamera(temp_range_index=range_index)
            
    def run(self):

        try:
            if not self.test_mode:
                self.ranges = OptrisCamera.list_available_ranges(0)
                self.logger.debug(f"Available Optris ranges: {self.ranges}")
            self.cap = self._initialize_cap()
            self._timer.timeout.connect(self.read_one_frame)
            self._timer.start(30)
            self.thread().exec()
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        self._timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None

        self.sigFinished.emit() # 通知主线程
        self.logger.info("IRWorker resources released.")
    
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
            self.logger.warning("Fail to read frame.")

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot(int)
    def set_range(self, range_index):
        if self.test_mode:
            return
        if self._timer:
            self._timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None

        self.cap = OptrisCamera(temp_range_index=range_index)

        if self.cap and self._timer:
            self._timer.start(30)

    @Slot(int)
    def set_position(self, position):
        if self.cap:
            self.cap.set_focus(position)

    def stop(self):
        """Properly shuts down the worker."""
        self._timer.stop()
        self.thread().quit() # Stops the exec() loop
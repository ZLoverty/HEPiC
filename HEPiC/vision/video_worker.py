from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent
sys.path.append(str(current_path))

from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThread
import numpy as np
import os
from vision_utils import binarize, filament_diameter, convert_to_grayscale, draw_filament_contour, ImageStreamer
import time
import cv2
import logging
import asyncio
from qasync import asyncSlot
from myimagelib import to8bit

if os.name == "nt":
    # if on windows OS, import the windows camera library
    from .hikcam_win import HikVideoCapture
else:
    # on Mac / Linux, use a different library
    # from .video_capture import HikVideoCapture  
    pass

class VideoWorker(QObject):
    """
    运行 ImageStreamer 的工作线程，通过信号发送图像帧。
    """
    new_frame_signal = Signal(np.ndarray)
    roi_frame_signal = Signal(np.ndarray)

    def __init__(self, test_mode=False, test_image_folder=""):
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
            image_folder = Path(test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(image_folder), fps=10)
        else: # 真图片流
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=50000, center_roi=True)
        
        self.fps = 10
        self.frame = None
        self.logger = logging.getLogger(__name__)
            
    def run(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.read_one_frame)
        self._timer.start(10) # a very high frequency, make sure that the newest frame is always read

        self._timer_get = QTimer(self)
        self._timer_get.timeout.connect(self.get_frame)
        self._timer_get.start(int(1000/self.fps))
            
    def read_one_frame(self):
        """Emit current frame and roi."""
        if not self.cap:
            return 
        ret, frame = self.cap.read()
        if ret:
            self.frame = frame

    def get_frame(self):
        """Emit current frame and roi at the specified fps."""
        if self.frame is not None:
            self.new_frame_signal.emit(self.frame)
            if self.roi is None:
                # if ROI is not set, show the whole frame in the ROI panel
                self.roi_frame_signal.emit(self.frame)
            else:
                x, y, w, h = self.roi
                self.roi_frame_signal.emit(self.frame[y:y+h, x:x+w])

    @Slot(tuple)
    def set_roi(self, roi):
        self.roi = roi

    @Slot(float)
    def set_fps(self, fps):
        self.fps = fps
        if self._timer:
            self._timer.stop()
            self._timer.start(int(1000/self.fps))
    
    def get_fps(self):
        return self.fps

    @Slot()
    def stop(self):
        self.logger.debug("Stopping video worker thread.")
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
            self.logger.warning("Test mode: exposure time setting will not have any effect.")
        else:
            self.cap = HikVideoCapture(width=512, height=512, exposure_time=exp_time*1000, center_roi=True)

class ProcessingWorker(QObject):
    """Image processing utilities:
    1. Calculated foreground pattern size based on distance transform algorithm.
    2. Measure grid size of a chessboard calibrator upon selecting "calibration mode".
    """

    proc_frame_signal = Signal(np.ndarray)
    sigMPP = Signal(float)
    sigCalibrationMsg = Signal(str)

    def __init__(self):
        super().__init__()
        self.die_diameter = np.nan
        self.invert = False
        self.calibration = False
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.image_queue = asyncio.Queue(maxsize=10)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4,4))
        
    
    async def run(self):
        self.is_running = True
        self.logger.debug("开始图像处理工作线程。")
        while self.is_running:
            try:
                img = await self.image_queue.get()
                if img is not None:
                    self.process_frame(img)
                else:
                    self.logger.debug("Received stop signal for processing worker.")
                    break
            except asyncio.CancelledError:
                break

    @asyncSlot(np.ndarray)
    async def add_frame_to_queue(self, img):
        """Add frame to processing queue."""
        try:
            self.image_queue.put_nowait(img)
        except asyncio.QueueFull:
            self.logger.warning("Processing queue is full. Dropping frame.")
    
    
    def process_frame(self, img):
        """Find filament in image and update the `self.die_diameter` variable with detected filament diameter."""
        gray = convert_to_grayscale(img) # only process gray images
        gray = to8bit(gray)
        try:
            # preprocessing: CLAHE
            gray = self.clahe.apply(gray)

            # preprocessing: binarization
            binary = binarize(gray)
            if self.invert:
                binary = cv2.bitwise_not(binary)

            if binary.std() == 0:
                raise ValueError("No valid skeleton pixels found after refinement.")
            
            # measure rough filament diameter
            diameter, skeleton, dist_transform = filament_diameter(binary)
            skel_px = dist_transform[skeleton]
            skeleton_refine = skeleton.copy()
            
            # filter the pixels on skeleton where dt pixel value is above average
            skeleton_refine[dist_transform < skel_px.mean()] = False
            
            diameter_refine = dist_transform[skeleton_refine].mean() * 2.0

            # measure the time required for visualization
            t0 = time.time()
            proc_frame = draw_filament_contour(gray, skeleton_refine, diameter_refine)
            t1 = time.time()
            self.logger.debug(f"Visualizing extrudate contour took {t1 - t0:.3f} seconds.")
            self.proc_frame_signal.emit(proc_frame)
            self.die_diameter = diameter_refine
        except ValueError as e:
            # 已知纯色图片会导致检测失败，在此情况下可以不必报错继续运行，将出口直径记为 np.nan 即可
            self.logger.warning(f"图像无法处理: {e}")
            self.proc_frame_signal.emit(binary)
    
    @Slot(bool)
    def invert_toggle(self, checked):
        """Sometimes the filament is the darker part of the image and background is brighter. In such cases, we may invert the binary image to make the algorithm work correctly. This is a toggle for the user to manually switch on/off whether to invert."""
        self.invert = checked
    
    def stop(self):
        self.is_running = False
        self.image_queue.put_nowait(None)
        self.deleteLater()

if __name__ == "__main__":

    from PySide6.QtWidgets import QApplication
    current_path = Path(__file__).resolve().parent.parent
    sys.path.append(str(current_path))
    from tab_widgets import VisionPageWidget
    from PySide6.QtCore import QThread
    
    test_image_folder = current_path / ".." / "test" / "filament_images_captured"

    try:
        app = QApplication(sys.argv)
        widget = VisionPageWidget()
        
        # display synthesized images
        
        video_worker = VideoWorker(test_mode=True, test_image_folder=str(test_image_folder))
        thread = QThread()
        video_worker.moveToThread(thread)
        thread.started.connect(video_worker.run)
        thread.start()
        
        video_worker.new_frame_signal.connect(widget.vision_widget.update_live_display)

        processing_worker = ProcessingWorker()
        widget.vision_widget.sigRoiImage.connect(processing_worker.process_frame)
        processing_worker.proc_frame_signal.connect(widget.roi_vision_widget.update_live_display)
        widget.sigFPS.connect(video_worker.set_fps)

        widget.show()
        sys.exit(app.exec())

    except Exception as e:
        print(f"error: {e}")

    finally:
        if video_worker:
            video_worker.stop()
            video_worker.deleteLater()
        if thread:
            thread.deleteLater()
    
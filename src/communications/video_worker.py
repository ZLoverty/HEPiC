from PySide6.QtCore import QObject, Signal, Slot, QTimer
import numpy as np
from pathlib import Path



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
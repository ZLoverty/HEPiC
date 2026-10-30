from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent
sys.path.append(str(current_path))

from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThread, QMutex, QMutexLocker
import numpy as np
import os
from vision_utils import binarize, filament_diameter, convert_to_grayscale, draw_filament_contour, ImageStreamer, to8bit
import time
import cv2
import logging
import asyncio
from qasync import asyncSlot

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

    def __init__(self, test_mode=False, test_image_folder="", decimation=2):
        """
        Parameters
        ----------
        test_mode : bool
            if true, enable test mode, which utilizes a sequence of local images to simulate a video stream from a camera.
        decimation : int
            相机硬件降采样倍数 (1/2/4/8)。全幅采集时用于降低数据量与读出时间,不影响视场角。
        """
        super().__init__()
        self.is_running = True
        self.roi = None
        self._timer = None
        self.test_mode = test_mode
        self.decimation = decimation

        if test_mode:  # 调试用图片流
            image_folder = Path(test_image_folder).expanduser().resolve()
            self.cap = ImageStreamer(str(image_folder), fps=10)
        else: # 真图片流
            self.cap = HikVideoCapture(decimation=self.decimation, exposure_time=50000, center_roi=True)
        
        self.fps = 10
        self.frame = None
        self._frame_mutex = QMutex()
        self._latest_frame = None
        self._latest_roi_frame = None
        self.logger = logging.getLogger(__name__)

        # 采集耗时统计 (INFO 日志用)
        self._read_time_sum = 0.0
        self._read_count = 0
            
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
        t0 = time.time()
        ret, frame = self.cap.read()
        if ret:
            self.frame = frame
            # 采集耗时统计:read() 阻塞等待帧,耗时反映实际帧率上限
            self._read_time_sum += time.time() - t0
            self._read_count += 1
            if self._read_count >= 50:
                avg_ms = self._read_time_sum / self._read_count * 1000.0
                self.logger.info(f"相机读取: 平均 {avg_ms:.1f} ms/帧 (等效 {1000.0/avg_ms:.1f} fps)")
                self._read_time_sum = 0.0
                self._read_count = 0

    def get_frame(self):
        """Update shared frame buffer and emit roi frame for processing."""
        if self.frame is not None:
            roi_frame = self.frame if self.roi is None else self.frame[self.roi[1]:self.roi[1]+self.roi[3], self.roi[0]:self.roi[0]+self.roi[2]]
            with QMutexLocker(self._frame_mutex):
                self._latest_frame = self.frame
                self._latest_roi_frame = roi_frame
            self.roi_frame_signal.emit(roi_frame)

    def get_latest_frame(self) -> np.ndarray | None:
        with QMutexLocker(self._frame_mutex):
            return self._latest_frame

    def get_latest_roi_frame(self) -> np.ndarray | None:
        with QMutexLocker(self._frame_mutex):
            return self._latest_roi_frame

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
        if self.cap:
            self.cap.release()
            self.cap = None

    @Slot(float)
    def set_exp_time(self, exp_time):
        """
        Parameters
        ----------
        exp_time : float
            exposure time in ms.
        """
        if self.test_mode:
            self.logger.warning("Test mode: exposure time setting will not have any effect.")
            return
        if self.cap:
            self.cap.release()
            while getattr(self.cap, "is_open", False):
                time.sleep(0.1)
        self.cap = HikVideoCapture(decimation=self.decimation, exposure_time=exp_time*1000, center_roi=True)

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
        self._latest_proc_frame: np.ndarray | None = None

        # 处理阶段耗时统计 (INFO 日志用)
        self._stage_time_sum = np.zeros(3)
        self._stage_count = 0
        self._crop_area_sum = 0.0
        
    
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
        """Add frame to processing queue, dropping stale frames if any."""
        # 处理速度跟不上采集时，丢弃积压的旧帧，保证处理线程总是拿到最新一帧
        dropped = 0
        while not self.image_queue.empty():
            try:
                self.image_queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            self.logger.debug(f"Processing lagging behind; dropped {dropped} stale frame(s).")
        self.image_queue.put_nowait(img)
    
    
    def process_frame(self, img):
        """Find filament in image and update the `self.die_diameter` variable with detected filament diameter."""
        gray = convert_to_grayscale(img) # only process gray images
        try:
            # ============ 粗定位:在 1/4 下采样图上找丝的位置 ============
            # 全幅上跑 CLAHE/骨架化/距离变换极慢,先用小图定位前景区域
            t0 = time.time()
            coarse_scale = 0.25
            small = cv2.resize(gray, None, fx=coarse_scale, fy=coarse_scale, interpolation=cv2.INTER_AREA)
            binary_small = binarize(small)
            if self.invert:
                binary_small = cv2.bitwise_not(binary_small)
            # connectedComponents 把 0 视为背景;若 invert 后前景变黑,需再取反保证前景为 255
            fg = cv2.bitwise_not(binary_small) if self.invert else binary_small
            n_labels, _, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
            if n_labels <= 1:
                raise ValueError("No valid skeleton pixels found after refinement.")

            # 保留面积不小于最大连通域 20% 的碎片(丝可能被二值化打断),取它们的并集 bbox
            areas = stats[1:, cv2.CC_STAT_AREA]
            keep = areas >= 0.2 * areas.max()
            left   = stats[1:, cv2.CC_STAT_LEFT][keep].min()
            top    = stats[1:, cv2.CC_STAT_TOP][keep].min()
            right  = (stats[1:, cv2.CC_STAT_LEFT][keep] + stats[1:, cv2.CC_STAT_WIDTH][keep]).max()
            bottom = (stats[1:, cv2.CC_STAT_TOP][keep] + stats[1:, cv2.CC_STAT_HEIGHT][keep]).max()

            # 映射回全分辨率坐标;以丝宽作为 margin 裁剪,保证距离变换在轮廓外有足够背景像素
            x0, x1 = int(round(left / coarse_scale)), int(round(right / coarse_scale))
            y0, y1 = int(round(top / coarse_scale)), int(round(bottom / coarse_scale))
            margin = max(x1 - x0, 8)
            H, W = gray.shape[:2]
            x0, x1 = max(0, x0 - margin), min(W, x1 + margin)
            y0, y1 = max(0, y0 - margin), min(H, y1 + margin)
            crop = gray[y0:y1, x0:x1]
            t1 = time.time()

            # ============ 精测量:crop 上跑原有管线 ============
            # 超大 crop 再降一次分辨率(距离变换/CLAHE/二值化都随面积缩放,耗时 ÷4);
            # 直径最后乘回比例系数,保持 full-res 像素语义,恒定比例由 MPP 标定吸收
            crop_area = crop.shape[0] * crop.shape[1]
            fine_scale = 1.0
            if crop_area > 1_500_000:
                fine_scale = 0.5
                crop = cv2.resize(crop, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            crop = to8bit(crop)
            crop = self.clahe.apply(crop)

            # preprocessing: binarization
            binary = binarize(crop)
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

            self.logger.debug(f"Skeleton has {skeleton_refine.astype(int).sum():d} points.")
            # fine_scale 下采样过则乘回比例系数,直径保持 full-res 像素语义
            diameter_refine = dist_transform[skeleton_refine].mean() * 2.0 / fine_scale

            # ============ 可视化:画在 1/4 全幅画布上 ============
            # 显示分辨率足够,同时避免 6MP 级别的 to8bit/findContours 开销
            t2 = time.time()
            skel_ys, skel_xs = np.where(skeleton_refine)
            disp_skeleton = np.zeros(small.shape, dtype=bool)
            # 骨架坐标:fine 局部 -> crop 局部 -> 全幅 -> 1/4 显示画布
            disp_ys = np.clip((y0 + skel_ys / fine_scale) * coarse_scale, 0, small.shape[0] - 1).astype(int)
            disp_xs = np.clip((x0 + skel_xs / fine_scale) * coarse_scale, 0, small.shape[1] - 1).astype(int)
            disp_skeleton[disp_ys, disp_xs] = True
            proc_frame = draw_filament_contour(small, disp_skeleton, diameter_refine * coarse_scale)
            t3 = time.time()
            self.logger.debug(f"粗定位 {t1 - t0:.3f}s, 精测量 {t2 - t1:.3f}s, 可视化 {t3 - t2:.3f}s, crop {crop.shape}")

            # 阶段耗时滚动统计:每 50 帧输出一次 INFO 摘要
            self._stage_time_sum += (t1 - t0, t2 - t1, t3 - t2)
            self._stage_count += 1
            self._crop_area_sum += crop_area
            if self._stage_count >= 50:
                avg = self._stage_time_sum / self._stage_count
                avg_area = self._crop_area_sum / self._stage_count / 1e6
                self.logger.info(f"处理耗时: 粗定位 {avg[0]*1000:.1f}ms, 精测量 {avg[1]*1000:.1f}ms, 可视化 {avg[2]*1000:.1f}ms, crop 平均 {avg_area:.2f}MP")
                self._stage_time_sum[:] = 0.0
                self._stage_count = 0
                self._crop_area_sum = 0.0

            self._latest_proc_frame = proc_frame
            self.proc_frame_signal.emit(proc_frame)
            self.die_diameter = diameter_refine
        except ValueError as e:
            # 已知纯色图片会导致检测失败，在此情况下可以不必报错继续运行，将出口直径记为 np.nan 即可
            self.logger.warning(f"图像无法处理: {e}")
            self._latest_proc_frame = binary_small
            self.proc_frame_signal.emit(binary_small)
    
    def get_latest_proc_frame(self) -> np.ndarray | None:
        return self._latest_proc_frame

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
    
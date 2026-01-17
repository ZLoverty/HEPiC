from pathlib import Path
import sys

from qasync import QEventLoop
current_path = Path(__file__).resolve().parent
sys.path.append(str(current_path))

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, 
    QLineEdit, QLabel, QPushButton
)
from PySide6.QtCore import Signal, QObject
from vision_widget import VisionWidget
from calibration_dialog import CalibrationDialog
import numpy as np
import logging

class VisionPageWidget(QWidget):
    """Video + control widgets"""

    sigExpTime = Signal(float)
    sigFPS = Signal(float)
    sigCapturedFrame = Signal(np.ndarray)
    sigMPP = Signal(float)

    def __init__(self):
        # 设定曝光时间的窗口
        super().__init__()
        self.exp_time_label = QLabel("曝光时间")
        self.exp_time = QLineEdit("50")
        self.exp_time.setMaximumWidth(30)
        self.exp_time_unit = QLabel("ms")
        self.vision_widget = VisionWidget()
        self.roi_vision_widget = VisionWidget()
        self.roi_vision_widget.mouse_enabled = False
        self.invert_button = QCheckBox("黑白反转")
        self.calibration_button = QPushButton("棋盘校准")

        self.fps_label = QLabel("FPS")
        self.fps = QLineEdit("10")

        layout = QHBoxLayout(self)
        control_layout = QVBoxLayout()
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.exp_time_label)
        button_layout.addWidget(self.exp_time)
        button_layout.addWidget(self.exp_time_unit)
        button_layout.addStretch(1)
        button_layout_2 = QHBoxLayout()
        button_layout_2.addWidget(self.fps_label)
        button_layout_2.addWidget(self.fps)
        control_layout.addLayout(button_layout)
        control_layout.addLayout(button_layout_2)
        control_layout.addWidget(self.invert_button)
        control_layout.addWidget(self.calibration_button)
        control_layout.addStretch(1)
        layout.addLayout(control_layout)
        layout.addWidget(self.vision_widget)
        layout.addWidget(self.roi_vision_widget)
        

        self.setLayout(layout)

        # 连接信号槽
        self.exp_time.returnPressed.connect(self.on_exp_time_pressed)
        self.fps.returnPressed.connect(self.on_fps_pressed)
        self.calibration_button.pressed.connect(self.on_calibration_pressed)

    def on_exp_time_pressed(self):
        exp_time = float(self.exp_time.text())
        self.sigExpTime.emit(exp_time)

    def on_fps_pressed(self):
        fps = float(self.fps.text())
        self.sigFPS.emit(fps)
    
    def on_calibration_pressed(self):

        dialog = CalibrationDialog(self)
        self.sigCapturedFrame.connect(dialog.vision_widget.update_live_display)
        self.sigCapturedFrame.emit(self.vision_widget.frame)
        
        if dialog.exec():
            mpp = dialog.get_mpp()
            self.sigMPP.emit(mpp)
        else:
            print("用户取消了校准")

        

class ImageGenerator(QObject):
    
    sigImage = Signal(np.ndarray)

    def __init__(self):
        super().__init__()

    def generate(self):

        import time

        X, Y = np.meshgrid(np.linspace(0, 4*np.pi, 512), np.linspace(0, 4*np.pi, 512))

        offset = 0
        while True:
            img = np.sin(X+Y+offset)
            self.sigImage.emit(img)
            offset += .1
            time.sleep(.033)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from threading import Thread
    from vision import ProcessingWorker

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    logging.getLogger("vision_widget").setLevel(logging.DEBUG)
    app = QApplication(sys.argv)
    widget = VisionPageWidget()

    # display synthesized images
    ig = ImageGenerator()
    ig.sigImage.connect(widget.vision_widget.update_live_display)
    thread = Thread(target=ig.generate)
    thread.start()
    
    processing_worker = ProcessingWorker()
    widget.vision_widget.sigRoiImage.connect(processing_worker.process_frame)
    processing_worker.proc_frame_signal.connect(widget.roi_vision_widget.update_live_display)
    
    widget.show()

    sys.exit(app.exec())
    

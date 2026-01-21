import sys
from pathlib import Path
current_path = Path(__file__).resolve().parent
sys.path.append(str(current_path))
sys.path.append(str(current_path.parent))
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QDialog, 
                               QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, 
                               QDialogButtonBox, QMessageBox, QWidget, QLabel, QSizePolicy)
from vision_widget import VisionWidget
from log_widget import LogWidget

from PySide6.QtCore import Slot, Signal, QObject
from vision import calibration, vision_utils
import numpy as np

class CalibrationDialog(QDialog):
    """自定义参数输入对话框"""

    sigMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("棋盘格尺寸校准")
        self.resize(800, 600)

        self.vision_widget = VisionWidget()
        self.vision_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.vision_widget.set_mode("measure")
        self.calibration_button = QPushButton("校准")
        # self.mpp_label = QLabel("像素尺寸（mm）: ")
        self.log_widget = LogWidget()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.realsize_input = QLineEdit()

        # layout
        layout = QHBoxLayout()
        form_layout = QFormLayout()
        form_layout.addRow("实际尺寸（mm）:", self.realsize_input)
        info_widget = QWidget()
        info_layout = QVBoxLayout()
        info_widget.setLayout(info_layout)
        info_widget.setMaximumWidth(400)
        info_layout.addLayout(form_layout)
        info_layout.addWidget(self.calibration_button)
        info_layout.addWidget(self.log_widget)
        info_layout.addWidget(self.buttons)
        layout.addWidget(info_widget)
        layout.addWidget(self.vision_widget)
        self.setLayout(layout)

        # 5. 连接信号与槽
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.calibration_button.pressed.connect(self.on_calibration_pressed)
        self.sigMessage.connect(self.log_widget.update_log)

        # variables
        self.mpp = float("nan")

    def get_mpp(self):
        """Return MPP value."""

        return self.mpp

    @Slot()
    def on_calibration_pressed(self):
        # inspect if grid size has a valid value
        try:
            size_mm = float(self.realsize_input.text())
            self.sigMessage.emit(f"棋盘格子尺寸为 {size_mm:.1f} mm")
        except:
            msgBox = QMessageBox()
            msgBox.setText(f"无效尺寸{self.realsize_input.text()}，请输入一个数字。")
            msgBox.exec()
            return
        
        messages = []
        
        # show analysis result message
        size_px = self.vision_widget.get_measure_length()
        if size_px is not None:
            mpp = size_mm / size_px
            messages.append(f"测量长度为 {size_px:.2f} px, 对应实际长度 {size_mm:.2f} mm。")
            messages.append(f"像素尺寸为 {mpp:.4f} mm/px。")
        else:
            messages = "请先画出测量线段。"
        
        for message in messages:
            self.sigMessage.emit(message)

class ImageGenerator(QObject):
    
    sigImage = Signal(np.ndarray)

    def __init__(self):
        super().__init__()

    def generate(self):

        import time

        test_folder = current_path.parent.parent / "test" / "calibration"
        cap = vision_utils.ImageStreamer(image_folder=str(test_folder), fps=3)

        while True:
            ret, frame = cap.read()
            if ret:
                self.sigImage.emit(frame)
            time.sleep(.33)

if __name__ == "__main__":

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from threading import Thread
    from vision import ProcessingWorker
    from vision_page_widget import VisionPageWidget
    
    app = QApplication(sys.argv)

    widget = VisionPageWidget()
    processing_worker = ProcessingWorker()
    widget.vision_widget.sigRoiImage.connect(processing_worker.process_frame)
    processing_worker.proc_frame_signal.connect(widget.roi_vision_widget.update_live_display)

    # display synthesized images
    ig = ImageGenerator()
    ig.sigImage.connect(widget.vision_widget.update_live_display)
    thread = Thread(target=ig.generate)
    thread.start()

   
    
    
    widget.show()
    sys.exit(app.exec())
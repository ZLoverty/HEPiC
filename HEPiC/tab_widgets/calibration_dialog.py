import sys
from pathlib import Path
current_path = Path(__file__).resolve().parent
sys.path.append(str(current_path))
sys.path.append(str(current_path.parent))
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QDialog, 
                               QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, 
                               QDialogButtonBox, QMessageBox, QWidget, QLabel)
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
        self.resize(300, 450)

        self.vision_widget = VisionWidget()
        self.vision_widget.disable_mouse()
        self.calibration_button = QPushButton("校准")
        self.mpp_label = QLabel("像素尺寸（mm）: ")
        self.log_widget = LogWidget()

        # layout
        layout = QVBoxLayout()
        
        # form layout
        form_layout = QFormLayout()
        self.gridsize_input = QLineEdit()
        self.rnum_input = QSpinBox()
        self.rnum_input.setRange(2, 20)
        self.rnum_input.setValue(9)
        self.cnum_input = QSpinBox()
        self.cnum_input.setRange(2, 20)
        self.cnum_input.setValue(12)

        form_layout.addRow("棋盘格格子尺寸（mm）:", self.gridsize_input)
        form_layout.addRow("行数", self.rnum_input)
        form_layout.addRow("列数", self.cnum_input)

        # 4. 创建标准按钮 (OK / Cancel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        
        # 5. 连接信号与槽
        # accept() 会关闭对话框并返回 1 (True)
        # reject() 会关闭对话框并返回 0 (False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.calibration_button.pressed.connect(self.on_calibration_pressed)
        self.sigMessage.connect(self.log_widget.update_log)

        # 6. 组装布局
        layout.addWidget(self.vision_widget)
        layout.addLayout(form_layout)
        layout.addWidget(self.mpp_label)
        layout.addWidget(self.calibration_button)
        layout.addWidget(self.log_widget)

        layout.addWidget(self.buttons)
        self.setLayout(layout)

        # variables
        self.mpp = float("nan")

    def get_mpp(self):
        """Return MPP value."""

        return self.mpp

    @Slot()
    def on_calibration_pressed(self):
        # inspect if grid size has a valid value
        try:
            size_mm = float(self.gridsize_input.text())
            self.sigMessage.emit(f"棋盘格子尺寸为 {size_mm:.1f} mm")
        except:
            msgBox = QMessageBox()
            msgBox.setText(f"无效尺寸{self.gridsize_input.text()}，请输入一个数字。")
            msgBox.exec()
            return
        
        # get grid pattern size
        rnum = self.rnum_input.value()
        cnum = self.cnum_input.value()
        pattern_size = (rnum-1, cnum-1)

        # execute the grid recognization algorithm
        try:
            frame = self.vision_widget.frame
            result = calibration.analyze_raw_pixel_sizes(frame, pattern_size=pattern_size)

            if result: # not None
                img_labeled, messages, size_px = result
            else:
                self.sigMessage.emit("Chessboard not detected.")
                return
        except:
            self.sigMessage.emit("Failed to analyze image.")
            return
        
        # show analysis result message
        for message in messages:
            self.log_widget.update_log(message)

        # display labeled image
        self.vision_widget.update_live_display(img_labeled)

        # display size in pixel size label
        mpp = size_mm / size_px
        self.mpp_label.setText(f"像素尺寸（mm）: {mpp:.3f}")

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
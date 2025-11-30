from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent.parent
sys.path.append(str(current_path))

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, 
    QLineEdit, QLabel
)
from PySide6.QtCore import Signal, QObject
from tab_widgets import VisionWidget
import numpy as np

class VisionPageWidget(QWidget):
    """Video + control widgets"""

    sigExpTime = Signal(float)

    def __init__(self):
        # 设定曝光时间的窗口
        super().__init__()
        self.exp_time_label = QLabel("曝光时间")
        self.exp_time = QLineEdit("50")
        self.exp_time_unit = QLabel("ms")
        self.vision_widget = VisionWidget()
        self.roi_vision_widget = VisionWidget()
        self.roi_vision_widget.mouse_enabled = False
        self.invert_button = QCheckBox("黑白反转")
        layout = QHBoxLayout(self)
        control_layout = QVBoxLayout()
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.exp_time_label)
        button_layout.addWidget(self.exp_time)
        button_layout.addWidget(self.exp_time_unit)
        button_layout.addStretch(1)
        control_layout.addLayout(button_layout)
        control_layout.addWidget(self.invert_button)
        # control_layout.addStretch(1)
        control_layout.addWidget(self.roi_vision_widget, 4)
        layout.addWidget(self.vision_widget)
        layout.addLayout(control_layout)
        self.setLayout(layout)

        # 连接信号槽
        self.exp_time.returnPressed.connect(self.on_exp_time_pressed)
    
    def on_exp_time_pressed(self):
        exp_time = float(self.exp_time.text())
        self.sigExpTime.emit(exp_time)

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
    
    app = QApplication(sys.argv)
    widget = VisionPageWidget()

    # display synthesized images
    ig = ImageGenerator()
    ig.sigImage.connect(widget.vision_widget.update_live_display)
    thread = Thread(target=ig.generate)
    thread.start()

    widget.show()
    sys.exit(app.exec())
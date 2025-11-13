from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, 
    QLineEdit, QLabel
)
from PySide6.QtCore import Signal
from .vision_widget import VisionWidget

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

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = VisionPageWidget()
    widget.show()
    sys.exit(app.exec())
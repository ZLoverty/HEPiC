from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QScrollBar
)
from PySide6.QtCore import QThread, Qt
from .vision_widget import VisionWidget

class IRPageWidget(QWidget):
    """红外相机模块页面组件"""

    def __init__(self):
        super().__init__()
        # widgets
        self.mode_menu = QComboBox()
        self.focus_bar = QScrollBar(Qt.Orientation.Horizontal)
        self.focus_bar.setMinimum(0)
        self.focus_bar.setMaximum(100)
        self.image_widget = VisionWidget()
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.mode_menu)
        control_layout.addWidget(self.focus_bar)
        layout = QVBoxLayout()
        layout.addLayout(control_layout)
        layout.addWidget(self.image_widget)
        self.setLayout(layout)

if __name__ == "__main__":
    import sys
    from qasync import QEventLoop, asyncSlot
    import asyncio
    from vision import IRWorker

    app = QApplication(sys.argv)
    window = QMainWindow()
    ir_widget = IRPageWidget()
    window.setCentralWidget(ir_widget)
    
    ir_worker = IRWorker()
    ir_thread = QThread()
    ir_worker.moveToThread(ir_thread)

    # signal slot
    ir_thread.started.connect(ir_worker.run)
    ir_worker.sigNewFrame.connect(ir_widget.image_widget.update_live_display)
    ir_thread.finished.connect(ir_thread.deleteLater)
    ir_worker.sigFinished.connect(ir_worker.deleteLater)

    ## change temp range
    for item in ir_worker.ranges:
        ir_widget.mode_menu.addItem(f"{item["min_temp"]} - {item["max_temp"]}")
    ir_widget.mode_menu.currentIndexChanged.connect(ir_worker.set_range)

    ## change focus 
    ir_widget.focus_bar.valueChanged.connect(ir_worker.set_position)
    ir_thread.start()
    window.show()
    
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
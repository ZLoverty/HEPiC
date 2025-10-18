"""
test a single widget
"""

from tab_widgets import VisionWidget
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer, Signal
from qasync import QEventLoop, asyncSlot
from communications import VideoWorker, ProcessingWorker
import sys
import asyncio

class MainWindow(QMainWindow):
    sig = Signal(dict)
    def __init__(self):
        super().__init__()
        self.vision_widget = VisionWidget()
        self.video_worker = VideoWorker(test_mode=True)
        # 连接信号槽
        
        self.video_worker.run()

        # 创建 image processing worker 用于处理图像，探测熔体直径
        self.processing_worker = ProcessingWorker()
        # 连接信号槽
        self.video_worker.new_frame_signal.connect(self.processing_worker.cache_frame)
        self.timer = QTimer()
        self.timer.timeout.connect(self.emit_dict)
        self.sig.connect(self.processing_worker.process_frame)
        self.processing_worker.proc_frame_signal.connect(self.vision_widget.update_live_display)
        self.timer.start(100)
        
    def emit_dict(self):
        self.sig.emit({"data": None})

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
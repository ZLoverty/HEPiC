import sys
import numpy as np
import pyqtgraph as pg
# --- 更改导入 ---
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Signal, Slot, QPointF # <-- 'pyqtSignal' 变为 'Signal'

class VisionWidget(pg.GraphicsLayoutWidget):
    """
    一个集成了视频显示和鼠标ROI绘制功能的可视化组件 (使用 PySide6)。
    """
    # --- 更改信号定义 ---
    sigRoiChanged = Signal(tuple) # 发射 (x, y, w, h)

    def __init__(self):
        super().__init__()

        self.roi = None
        self.roi_start_pos = None

        self.view_box = self.addViewBox(row=0, col=0)
        self.view_box.setAspectLocked(True)
        self.view_box.invertY(True)
        self.img_item = pg.ImageItem()
        self.view_box.addItem(self.img_item)
    
    @Slot(np.ndarray)
    def update_display(self, frame):
        """更新图像显示的槽函数。"""
        self.img_item.setImage(frame, axisOrder="row-major")

    def mousePressEvent(self, event):
        # pyqtgraph 内部会处理好 PyQt/PySide 的差异，所以这部分逻辑不变
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton and self.view_box.sceneBoundingRect().contains(event.scenePosition()):
            if self.roi:
                self.view_box.removeItem(self.roi)
                self.roi = None
            
            self.roi_start_pos = self.view_box.mapSceneToView(event.scenePosition())
            
            # 创建新的RectROI
            self.roi = pg.RectROI(self.roi_start_pos, [1, 1], pen='y', removable=True)
            self.view_box.addItem(self.roi)
            
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.roi and event.buttons() == pg.QtCore.Qt.MouseButton.LeftButton:
            current_pos = self.view_box.mapSceneToView(event.scenePosition())
            # 更新ROI的位置和大小，以确保拖拽行为符合直觉
            # min()确保左上角坐标正确，abs()确保宽高为正
            start_x, start_y = self.roi_start_pos.x(), self.roi_start_pos.y()
            curr_x, curr_y = current_pos.x(), current_pos.y()
            
            new_pos = QPointF(min(start_x, curr_x), min(start_y, curr_y))
            new_size = QPointF(abs(start_x - curr_x), abs(start_y - curr_y))

            self.roi.setPos(new_pos)
            self.roi.setSize(new_size)

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.roi and event.button() == pg.QtCore.Qt.MouseButton.LeftButton:
            self.roi.sigRegionChangeFinished.connect(self.on_roi_changed)
            self.on_roi_changed() # 首次绘制完成时，主动触发一次
            self.roi_start_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def on_roi_changed(self):
        """当ROI被用户修改完成时被调用。"""
        if not self.roi:
            return
            
        pos = self.roi.pos()
        size = self.roi.size()
        
        roi_info = (int(pos.x()), int(pos.y()), int(size.x()), int(size.y()))
        self.sigRoiChanged.emit(roi_info)

# --- 主应用程序 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 + PyQtGraph ROI绘制示例")
        self.setGeometry(100, 100, 600, 600)
        
        self.vision_widget = VisionWidget()
        self.setCentralWidget(self.vision_widget)
        
        # 将自定义信号连接到槽函数
        self.vision_widget.sigRoiChanged.connect(self.print_roi_info)
        
        # 创建并显示一个静态的测试图像
        self.create_test_image()

    def create_test_image(self):
        """创建一个简单的灰度渐变图像作为背景。"""
        width, height = 640, 480
        # 创建一个从左到右的水平渐变
        x_grad = np.linspace(0, 255, width, dtype=np.uint8)
        # 创建一个从上到下的垂直渐变
        y_grad = np.linspace(0, 255, height, dtype=np.uint8)
        # 组合成二维图像
        xx, yy = np.meshgrid(x_grad, y_grad)
        image_data = (xx + yy) // 2
        
        # 显示图像
        self.vision_widget.update_display(image_data)

    @Slot(tuple)
    def print_roi_info(self, roi_info):
        print(f"ROI 更新: x={roi_info[0]}, y={roi_info[1]}, w={roi_info[2]}, h={roi_info[3]}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
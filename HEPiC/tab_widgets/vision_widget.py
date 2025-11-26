import pyqtgraph as pg
import numpy as np
from PySide6.QtCore import Signal, Slot, QPointF
import logging

class VisionWidget(pg.GraphicsLayoutWidget):

    sigRoiChanged = Signal(tuple) # 发射 (x, y, w, h)

    def __init__(self, logger=None):

        super().__init__()

        self.roi = {
            "item": None,
            "pos": (0, 0),
            "size": (0, 0)
        }
        self.roi_start_pos = None
        self.mouse_enabled = True
        self.mousePressed = False

        # 告诉布局管理器，让ViewBox占据所有可用空间，从而最小化边距
        # self.ci.layout.setContentsMargins(0, 0, 0, 0)

        # 组件
        # 1. 创建 PlotItem，这是一个包含 ViewBox 和坐标轴的复合组件
        self.plot_item = self.addPlot(row=0, col=0)
        
        # # 2. 【关键步骤】从 PlotItem 中获取其内部的 ViewBox
        self.view_box = self.plot_item.getViewBox()
        
        # 3. 将所有 ViewBox 相关的设置应用到这个内部 ViewBox 上
        self.view_box.setAspectLocked(True)
        self.view_box.invertY(True)
        self.view_box.setMouseEnabled(x=False, y=False)

        # 4. 对于纯图像显示，我们通常不希望看到坐标轴，可以隐藏它们
        self.plot_item.hideAxis('left')
        self.plot_item.hideAxis('bottom')
        
        # 5. 创建 ImageItem 并将其添加到 PlotItem 中
        self.img_item = pg.ImageItem()
        self.plot_item.addItem(self.img_item)

        # logger
        self.logger = logger or logging.getLogger(__name__)

    @Slot(np.ndarray)
    def update_live_display(self, frame):
        self.img_item.setImage(frame, axisOrder="row-major")
    
    def mousePressEvent(self, event):
        # pyqtgraph 内部会处理好 PyQt/PySide 的差异，所以这部分逻辑不变
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
            if self.roi:
                self.plot_item.removeItem(self.roi["item"])

            pos = event.scenePosition()
            mousePoint = self.plot_item.vb.mapSceneToView(pos)
            self.roi_start_pos = mousePoint
            
            self.mousePressed = True

            # 创建新的RectROI
            x0, y0 = self.roi_start_pos.x(), self.roi_start_pos.y()
            self.roi["item"] = pg.Qt.QtWidgets.QGraphicsRectItem(x0, y0, 0, 0)
            self.pen = pg.mkPen(color=(200, 0, 0), width=3, style=pg.QtCore.Qt.PenStyle.DashLine)
            self.roi["item"].setPen(self.pen)
            self.logger.debug(f"create ROI starting at {x0}, {y0}")
            self.plot_item.addItem(self.roi["item"])
            
            # event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.roi and event.buttons() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
            current_pos = self.plot_item.getViewBox().mapSceneToView(event.scenePosition())
            # 更新ROI的位置和大小，以确保拖拽行为符合直觉
            # min()确保左上角坐标正确，abs()确保宽高为正
            if 'item' in self.roi:
                self.plot_item.removeItem(self.roi['item'])

            x0, y0 = self.roi_start_pos.x(), self.roi_start_pos.y()
            curr_x, curr_y = current_pos.x(), current_pos.y()
            
            # new_pos = QPointF(min(start_x, curr_x), min(start_y, curr_y))
            new_size = curr_x - x0, curr_y - y0

            self.roi["size"] = new_size
            self.roi["item"] = pg.Qt.QtWidgets.QGraphicsRectItem(x0, y0, new_size[0], new_size[1])
            self.plot_item.addItem(self.roi["item"])
            self.roi["item"].setPen(self.pen)
            
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.roi and event.button() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
            self.on_roi_changed() # 首次绘制完成时，主动触发一次
            self.roi_start_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def on_roi_changed(self):
        """当ROI被用户修改完成时被调用。"""
        if not self.roi:
            return
        roi_info = (int(self.roi["pos"][0]), int(self.roi["pos"][1]), int(self.roi["size"][0]), int(self.roi["size"][1]))
        self.sigRoiChanged.emit(roi_info) 
        self.logger.debug(f"New ROI info {roi_info} emitted.")

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    import numpy as np

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    app = QApplication(sys.argv)
    widget = VisionWidget()
    widget.update_live_display(np.random.rand(512, 512))
    widget.show()
    sys.exit(app.exec())
import pyqtgraph as pg
import numpy as np
from PySide6.QtCore import Signal, Slot, QPointF

class VisionWidget(pg.GraphicsLayoutWidget):

    sigRoiChanged = Signal(tuple) # 发射 (x, y, w, h)

    def __init__(self):

        super().__init__()

        self.roi = None
        self.roi_start_pos = None
        self.mouse_enabled = True
        self.mousePressed = False

        # 告诉布局管理器，让ViewBox占据所有可用空间，从而最小化边距
        # self.ci.layout.setContentsMargins(0, 0, 0, 0)

        # 组件
        # 1. 创建 PlotItem，这是一个包含 ViewBox 和坐标轴的复合组件
        self.plot_item = self.addPlot(row=0, col=0)
        
        # 2. 【关键步骤】从 PlotItem 中获取其内部的 ViewBox
        self.view_box = self.plot_item.getViewBox()
        
        # 3. 将所有 ViewBox 相关的设置应用到这个内部 ViewBox 上
        self.view_box.setAspectLocked(True)
        self.view_box.invertY(True)
        self.view_box.setMouseEnabled(x=False, y=False)

        # 4. 对于纯图像显示，我们通常不希望看到坐标轴，可以隐藏它们
        # self.plot_item.hideAxis('left')
        # self.plot_item.hideAxis('bottom')
        
        # 5. 创建 ImageItem 并将其添加到 PlotItem 中
        self.img_item = pg.ImageItem()
        self.plot_item.addItem(self.img_item)

    @Slot(np.ndarray)
    def update_live_display(self, frame):
        self.img_item.setImage(frame, axisOrder="row-major")
    
    def mousePressEvent(self, event):
        # pyqtgraph 内部会处理好 PyQt/PySide 的差异，所以这部分逻辑不变
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
            if self.roi:
                self.plot_item.removeItem(self.roi)
                self.roi = None

            pos = event.scenePosition()
            mousePoint = self.plot_item.vb.mapSceneToView(pos)
            self.roi_start_pos = mousePoint

            # --- 诊断代码 ---
            # scene_pos = event.scenePosition()
            # view_pos = self.view_box.mapSceneToView(scene_pos)
            # image_pos = self.img_item.mapFromScene(scene_pos)
            

            # print("--- 坐标诊断 ---")
            # print(f"Scene Coords (墙壁坐标):     x={scene_pos.x():.2f}, y={scene_pos.y():.2f}")
            # print(f"ViewBox Coords (画框坐标):   x={view_pos.x():.2f}, y={view_pos.y():.2f}")
            # print(f"ImageItem Coords (画布坐标): x={image_pos.x():.2f}, y={image_pos.y():.2f}")
            # print(f"ImageItem 自身位置: x={self.img_item.pos().x()}, y={self.img_item.pos().y()}")
            # print("-----------------")
            
            self.mousePressed = True

            # 创建新的RectROI
            self.roi = pg.RectROI(self.roi_start_pos, [0, 0], pen='y', removable=True)
            self.plot_item.addItem(self.roi)
            
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.roi and event.buttons() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
            current_pos = self.plot_item.getViewBox().mapSceneToView(event.scenePosition())
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
        if self.roi and event.button() == pg.QtCore.Qt.MouseButton.LeftButton and self.mouse_enabled:
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


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = VisionWidget()
    widget.show()
    sys.exit(app.exec())
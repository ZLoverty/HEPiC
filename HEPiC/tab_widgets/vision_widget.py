import pyqtgraph as pg
import numpy as np
from PySide6.QtCore import Signal, Slot, QPointF, QLineF
import logging
from PySide6 import QtWidgets, QtCore

class VisionWidget(pg.GraphicsLayoutWidget):

    sigRoiChanged = Signal(tuple) # 发射 (x, y, w, h)
    sigRoiImage = Signal(np.ndarray)

    def __init__(self):

        super().__init__()

        # 1. 获取中央布局对象 (Central Item)
        layout = self.ci 
        
        # 2. 核心修复：将布局的边距设置为 0
        # GraphicsLayout 内部封装了 QGraphicsGridLayout
        layout.layout.setContentsMargins(0, 0, 0, 0)
        layout.layout.setSpacing(0)

        self.roi = None

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
        self.logger = logging.getLogger(__name__)
        self.frame = None

        # modes, can be "roi", "measure", "view"
        self.mode = "view"

    @Slot(np.ndarray)
    def update_live_display(self, frame):
        self.frame = frame
        self.img_item.setImage(frame, axisOrder="row-major")
        if hasattr(self, "roi_info"):
            x0, y0, w, h = self.roi_info
            roi_image = frame[x0:x0+w, y0:y0+h]
            self.sigRoiImage.emit(roi_image)
        else:
            self.sigRoiImage.emit(frame)
         
    def mousePressEvent(self, event):
        # pyqtgraph 内部会处理好 PyQt/PySide 的差异，所以这部分逻辑不变
        
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton:
            pos = event.position()
            scene_pos = self.plot_item.mapToScene(pos)
            mousePoint = self.plot_item.vb.mapSceneToView(scene_pos)
            
            # check if click is on existing ROI

            self.is_click_on_roi = False
            if self.roi:
                items = self.plot_item.scene().items(scene_pos)
                # 判断点击的是否是当前 ROI 本身或其子对象（句柄）
                
                for item in items:
                    # 如果 item 是 ROI 本身，或者是 ROI 的子元素（如 Handle）
                    if item is self.roi or item.parentItem() is self.roi:
                        self.is_click_on_roi = True
                        break

            # 如果点在了 ROI 上，直接调用父类方法，让 ROI 处理伸缩/拖动逻辑
            if self.is_click_on_roi:
                super().mousePressEvent(event)
                return

            # 3. 如果没点在 ROI 上，则执行“删除旧的，新建一个”的逻辑
            if self.roi:
                self.plot_item.removeItem(self.roi)

            if self.mode == "roi":
                self.roi = pg.RectROI((mousePoint.x(), mousePoint.y()), (1, 1))
                self.roi.addScaleHandle([1, 1], [0, 0])      # 在右上角添加缩放句柄
            elif self.mode == "measure":
                pt1 = (mousePoint.x(), mousePoint.y())
                pt2 = (mousePoint.x()+1, mousePoint.y()+1)
                self.roi = pg.LineSegmentROI(positions=[pt1, pt2], pen="y")
            self.plot_item.addItem(self.roi)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "is_click_on_roi") and self.is_click_on_roi:
            super().mouseMoveEvent(event)
            return
        if event.buttons() == pg.QtCore.Qt.MouseButton.LeftButton:
            pos = event.position()
            scene_pos = self.plot_item.mapToScene(pos)
            current_pos = self.plot_item.getViewBox().mapSceneToView(scene_pos)

            if self.mode == "roi":
                if self.roi:
                    state = self.roi.getState()
                    new_size = current_pos.x() - state["pos"][0], current_pos.y() - state["pos"][1]

                    # if new_size[0] < 1 or new_size[1] < 1:
                    #     self.roi = None
                    #     return
                    # else:
                    self.roi.setSize(new_size)

            elif self.mode == "measure":
                if self.roi:
                    handle2 = self.roi.getHandles()[1]
                    self.roi.movePoint(handle2, current_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "is_click_on_roi") and self.is_click_on_roi:
            super().mouseReleaseEvent(event)
            self.is_click_on_roi = False
            return
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton:
            if self.roi:
                self.on_roi_changed() # 首次绘制完成时，主动触发一次
                event.accept()  
        else:
            super().mouseReleaseEvent(event)
            
    def on_roi_changed(self):
        """当ROI被用户修改完成时被调用。"""
        if self.roi:
            if self.mode == "roi":
                state = self.roi.getState()
                self.roi_info = (int(state["pos"][0]), int(state["pos"][1]), int(state["size"][0]), int(state["size"][1]))
                self.sigRoiChanged.emit(self.roi_info) 
                self.logger.debug(f"New ROI set {self.roi_info}.")
            elif self.mode == "measure":
                handles = self.roi.getHandles()
                p1 = self.roi.mapToView(handles[0].pos())
                p2 = self.roi.mapToView(handles[1].pos())
                line = QLineF(p1, p2)
                length = line.length()
                self.logger.debug(f"Measurement line length: {length:.2f} pixels.")
    
    def set_mode(self, mode):
        """Set the interaction mode of the widget.

        Parameters
        ----------
        mode : str
            Can be "roi", "measure", "view"
        """
        self.mode = mode
    
    def get_measure_length(self):
        """Get the length of the measurement line in pixels.

        Returns
        -------
        float
            Length in pixels. Returns NaN if no measurement line is set.
        """
        if self.mode != "measure" or not self.roi:
            return
        handles = self.roi.getHandles()
        p1 = self.roi.mapToView(handles[0].pos())
        p2 = self.roi.mapToView(handles[1].pos())
        line = QLineF(p1, p2)
        length = line.length()
        return length
        

class ROIDemo(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 创建绘图窗口
        self.view = pg.PlotWidget()
        self.setCentralWidget(self.view)
        self.view.setXRange(0, 100)
        self.view.setYRange(0, 100)

        # 1. 创建 RectROI 对象
        # pos: 初始位置, size: 初始大小, pen: 边框颜色
        self.roi = pg.RectROI([20, 20], [20, 20], pen=(0, 9))
        
        # 2. 添加交互句柄
        # [0.5, 0.5] 是中心点，用于缩放
        # [1, 1] 是右上角，用于旋转
        self.roi.addScaleHandle([1, 1], [0, 0])      # 在右上角添加缩放句柄
        # self.roi.addRotateHandle([0, 0], [0.5, 0.5]) # 在左下角添加旋转句柄

        # 3. 将 ROI 添加到绘图区
        self.view.addItem(self.roi)

        # 4. 连接信号：当 ROI 被拖动或改变大小时触发
        self.roi.sigRegionChanged.connect(self.roi_changed)

        # 用于实时显示坐标的 Label
        self.label = pg.TextItem(anchor=(0, 1))
        self.view.addItem(self.label)

    def roi_changed(self, roi):
        # 获取 ROI 的位置和大小
        pos = roi.pos()
        size = roi.size()
        angle = roi.angle()
        
        text = f"Pos: ({pos.x():.1f}, {pos.y():.1f})\nSize: {size.x():.1f} x {size.y():.1f}\nAngle: {angle:.1f}°"
        self.label.setText(text)
        self.label.setPos(pos.x(), pos.y() + size.y() + 2)

class LineROIDemo(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.view = pg.PlotWidget()
        self.setCentralWidget(self.view)
        self.view.setXRange(0, 10)
        self.view.setYRange(0, 10)

        # 1. 创建线段 ROI
        # positions: 指定两个端点的初始坐标 [(x1, y1), (x2, y2)]
        self.line_roi = pg.LineSegmentROI(positions=[(2, 2), (8, 8)], pen='y')
        self.view.addItem(self.line_roi)

        # 2. 监听变化信号
        self.line_roi.sigRegionChanged.connect(self.update_info)
        
        # 用于显示信息的 Label
        self.label = pg.TextItem(color='w', anchor=(0, 0))
        self.view.addItem(self.label)
        self.update_info()

    def update_info(self):
        # 获取两个句柄（Handles）的当前位置
        # getSceneHandlePositions 返回的是场景坐标，我们需要转为 View 坐标
        handles = self.line_roi.getHandles()
        # 也可以直接获取 pos 和 size 计算，但 LineSegmentROI 推荐这种方式：
        p1 = self.line_roi.mapToView(handles[0].pos())
        p2 = self.line_roi.mapToView(handles[1].pos())

        dist = pg.Point(p1 - p2).length()
        self.label.setText(f"Length: {dist:.2f}")
        self.label.setPos(p1.x(), p1.y())

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
    widget.set_mode("roi")
    X, Y = np.meshgrid(np.linspace(0, np.pi, 512), np.linspace(0, np.pi, 512))
    widget.update_live_display(np.sin(X+Y))
    widget.show()
    sys.exit(app.exec())

    # app = QtWidgets.QApplication(sys.argv)
    # demo = LineROIDemo()
    # demo.show()
    # sys.exit(app.exec())
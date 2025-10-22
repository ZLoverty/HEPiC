"""
Tabs widgets for layout management. Contains

- connection widget
- platform status widget
- data plotting widget
- command widget
- log display widget
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget, QFileDialog, QTextEdit, QLabel, QStyle
)
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QSize, QPointF
import pyqtgraph as pg
import time
from collections import deque
import numpy as np
import cv2
from PySide6.QtGui import QImage, QPixmap
import json
from config import Config

class ConnectionWidget(QWidget):

    ip = Signal(str)

    def __init__(self):

        super().__init__()

        self.status_list = deque(maxlen=10)

        # 组件
        self.ip_label = QLabel("树莓派 IP 地址 ")
        self.ip_input = QLineEdit(f"{Config.default_host}")
        self.connect_button = QPushButton("连接")
        self.self_test = QLabel("...")
        # self.disconnect_button = QPushButton("断开")
        # self.disconnect_button.setEnabled(False)

        # 布局
        layout = QVBoxLayout()
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(self.ip_label)
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(self.connect_button)
        message_layout = QHBoxLayout()
        message_layout.addWidget(self.self_test)
        layout.addLayout(ip_layout)
        layout.addStretch(1)
        layout.addLayout(message_layout)
        self.setLayout(layout)

        # 信号槽连接
        self.connect_button.clicked.connect(self.on_connect_clicked)
        self.ip_input.returnPressed.connect(self.on_connect_clicked)

    @Slot()
    def on_connect_clicked(self):
        ip_address = self.ip_input.text().strip()
        if ip_address:
            self.ip.emit(ip_address)
        else:
            QMessageBox.warning(self, "输入错误", "请输入有效的 IP 地址。")

    @Slot(str)
    def update_button_status(self, status):
        """更新状态栏和按钮状态"""
        if status == "连接成功":
            self.connect_button.setEnabled(False)
            # self.disconnect_button.setEnabled(True)
        else:
            self.connect_button.setEnabled(True)
            # self.disconnect_button.setEnabled(False)
    @Slot(str)
    def update_self_test(self, status):
        self.status_list.append(status)
        self.self_test.setText("\n".join(self.status_list))
        
class PlatformStatusWidget(QWidget):

    set_temperature = Signal(float)

    def __init__(self):
        
        super().__init__()
        placeholder = "***"
        # 组件
        self.hotend_temperature_label = QLabel("温度:")
        self.hotend_temperature_value = QLabel(f"{placeholder:5s} /")
        self.hotend_temperature_input = QLineEdit("")
        self.hotend_temperature_input.setMaximumWidth(60)
        self.extrusion_force_label = QLabel("挤出力:")
        self.extrusion_force_value = QLabel(f"{placeholder}")
        self.meter_count_label = QLabel("当前进料量:")
        self.meter_count_value = QLabel(f"{placeholder}")
        self.feedrate_label = QLabel("进线速度:")
        self.measured_feedrate_value = QLabel(f"{placeholder}/")
        self.feedrate_value = QLabel(f"{placeholder} mm/s")
        self.die_temperature_label = QLabel("出口熔体温度")
        self.die_temperature_value = QLabel(f"{placeholder}")
        self.die_diameter_label = QLabel("出口熔体直径")
        self.die_diameter_value = QLabel(f"{placeholder}")

        # 布局
        layout = QVBoxLayout()
        row_layout_1 = QHBoxLayout()
        row_layout_2 = QHBoxLayout()
        row_layout_3 = QHBoxLayout()
        row_layout_4 = QHBoxLayout()
        die_temperature_row_layout = QHBoxLayout()
        die_diameter_row_layout = QHBoxLayout()

        # temperature row
        row_layout_1.addWidget(self.hotend_temperature_label)
        row_layout_1.addWidget(self.hotend_temperature_value)
        row_layout_1.addWidget(self.hotend_temperature_input)
        row_layout_1.addStretch(1)
        # extrusion force row
        row_layout_2.addWidget(self.extrusion_force_label)
        row_layout_2.addWidget(self.extrusion_force_value)
        row_layout_2.addStretch(1)
        # meter count row
        row_layout_3.addWidget(self.meter_count_label)
        row_layout_3.addWidget(self.meter_count_value)
        row_layout_3.addStretch(1)
        # feedrate row
        row_layout_4.addWidget(self.feedrate_label)
        row_layout_4.addWidget(self.measured_feedrate_value)
        row_layout_4.addWidget(self.feedrate_value)
        row_layout_4.addStretch(1)
        # die temperature row
        die_temperature_row_layout.addWidget(self.die_temperature_label)
        die_temperature_row_layout.addWidget(self.die_temperature_value)
        # die diameter row
        die_diameter_row_layout.addWidget(self.die_diameter_label)
        die_diameter_row_layout.addWidget(self.die_diameter_value)

        layout.addLayout(row_layout_1)
        layout.addLayout(row_layout_2)
        layout.addLayout(row_layout_3)
        layout.addLayout(row_layout_4)
        layout.addLayout(die_temperature_row_layout)
        layout.addLayout(die_diameter_row_layout)
        
        self.setLayout(layout)

    @Slot(dict)
    def update_display(self, data):
        for item in data:
            if item == "hotend_temperature_C":
                temperature = data[item]
                self.hotend_temperature_value.setText(f"{temperature:5.1f} /")
            elif item == "extrusion_force_N":
                extrusion_force = data[item]
                self.extrusion_force_value.setText(f"{extrusion_force:5.1f} N")
            elif item == "meter_count_mm":
                meter_count = data[item]
                self.meter_count_value.setText(f"{meter_count:5.1f} mm")
            elif item == "measured_feedrate_mms":
                meansured_feedrate = data[item]
                self.measured_feedrate_value.setText(f"{meansured_feedrate:5.1f} /")
            elif item == "feedrate_mms":
                feedrate = data[item]
                self.feedrate_value.setText(f"{feedrate:5.1f} mm/s")
            elif item == "die_temperature_C":
                die_temperature = data[item]
                self.die_temperature_value.setText(f"{die_temperature:5.1f} C")
            elif item == "die_diameter_px":
                die_diameter = data[item]
                self.die_diameter_value.setText(f"{die_diameter:5.1f} px")



class DataPlotWidget(QWidget):

    def __init__(self):

        super().__init__()

        # 创建 pyqtgraph widgets
        self.force_plot = pg.PlotWidget(title="挤出力(N)")
        self.dietemp_plot = pg.PlotWidget(title="出口熔体温度(C)")
        self.dieswell_plot = pg.PlotWidget(title="出口熔体直径(px)")
        pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.force_curve = self.force_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dietemp_curve = self.dietemp_plot.plot(pen=pen) # 在图表上添加一条曲线
        self.dieswell_curve = self.dieswell_plot.plot(pen=pen) # 在图表上添加一条曲线

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.force_plot)
        layout.addWidget(self.dietemp_plot)
        layout.addWidget(self.dieswell_plot)
        self.setLayout(layout)

        self.max_len = 300
    
    @Slot(dict)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        try:
            if "extrusion_force_N" in data:
                self.force_curve.setData(list(data["time_s"])[-self.max_len:], list(data["extrusion_force_N"])[-self.max_len:])
            if "die_temperature_C" in data:
                self.dietemp_curve.setData(list(data["time_s"])[-self.max_len:], list(data["die_temperature_C"])[-self.max_len:])
            if "die_diameter_px" in data:
                self.dieswell_curve.setData(list(data["time_s"])[-self.max_len:], list(data["die_diameter_px"])[-self.max_len:])

        except (IndexError, ValueError):
            self.temp_value_label.setText("解析错误")

class CommandWidget(QWidget):

    command_to_send = Signal(str)

    def __init__(self):

        super().__init__()

        self.command_display = QPlainTextEdit()
        self.command_display.setReadOnly(True)
        self.command_display.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: Consolas, monaco, monospace;")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("在此输入 G-code 指令 (如 G1 E10 F300)")
        self.send_button = QPushButton("发送指令")
        self.send_button.setEnabled(False)

        layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.command_input)
        input_layout.addWidget(self.send_button)
        layout.addWidget(self.command_display)
        layout.addLayout(input_layout)
        self.setLayout(layout)

        # 信号槽连接
        self.send_button.clicked.connect(self.send_command)
        self.command_input.returnPressed.connect(self.send_command)

    @Slot(bool)
    def update_button_status(self, connected):
        """更新按钮状态"""
        if connected:
            self.send_button.setEnabled(True)
            self.command_input.setEnabled(True)
        else:
            self.send_button.setEnabled(False)
            self.command_input.setEnabled(False)

    @Slot()
    def send_command(self):
        command = self.command_input.text().strip()
        if command:
            print("--- [DEBUG] 'send_command' method called.")
            self.command_display.appendPlainText(f"{command}")
            # 调用 signal 发送指令
            self.command_to_send.emit(command)
            self.command_input.clear()
    
    @Slot(str)
    def update_command_display(self, message):
        try:
            data = json.loads(message)
            pretty_message = json.dumps(data, indent=4)
            self.command_display.appendPlainText(pretty_message)
        except json.JSONDecodeError:
            self.command_display.appendPlainText(message)
            
class LogWidget(QWidget):

    def __init__(self):

        super().__init__()

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("这里会显示原始数据和调试信息...")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("原始数据日志:"))
        layout.addWidget(self.log_display) # 占据多行多列
        self.setLayout(layout)

    @Slot(str)
    def update_log(self, message):
        self.log_display.appendPlainText(f"<-- [接收]: {message}")

class VisionWidget(pg.GraphicsLayoutWidget):

    sigRoiChanged = Signal(tuple) # 发射 (x, y, w, h)

    def __init__(self):

        super().__init__()

        self.roi = None
        self.roi_start_pos = None
        self.mouse_enabled = True

        # 告诉布局管理器，让ViewBox占据所有可用空间，从而最小化边距
        self.ci.layout.setContentsMargins(0, 0, 0, 0)

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
        self.plot_item.hideAxis('left')
        self.plot_item.hideAxis('bottom')
        
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


            # 创建新的RectROI
            self.roi = pg.RectROI(self.roi_start_pos, [1, 1], pen='y', removable=True)
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
        layout = QHBoxLayout(self)
        control_layout = QVBoxLayout()
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.exp_time_label)
        button_layout.addWidget(self.exp_time)
        button_layout.addWidget(self.exp_time_unit)
        button_layout.addStretch(1)
        control_layout.addLayout(button_layout)
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

class GcodeWidget(QWidget):

    gcode_save_signal = Signal()

    def __init__(self):
        super().__init__()

        # 组件
        self.gcode_title = QLabel("输入 G-code 或打开文件")
        style = self.style()
        warning_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.warning_label = QLabel()
        icon_size = QSize(16, 16)
        self.warning_label.setPixmap(warning_icon.pixmap(icon_size))
        tooltip_text = """
        <p>注意：点击运行后，下面的 G-code 会原封不动发给 Klipper。如果文本包含无效的 G-code，平台不会执行该行，并会报错。请留意最下方状态栏中的报错信息。本软件不会对文本进行任何检查，因为输入无效 G-code 导致的测试失败由测试者本人负责。<p>
        """
        self.warning_label.setToolTip(tooltip_text)
        self.gcode_title.setMaximumWidth(300)
        self.gcode_display = QTextEdit()
        # self.gcode_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.open_button = QPushButton("打开")
        # self.clear_button = QPushButton("清除")
        self.run_button = QPushButton("运行")

        # 布局
        layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        label_layout.addWidget(self.gcode_title)
        label_layout.addWidget(self.warning_label)
        label_layout.addStretch(1)
        button_layout1 = QHBoxLayout()
        # button_layout2 = QHBoxLayout()
        button_layout1.addWidget(self.open_button)
        # button_layout1.addWidget(self.clear_button)
        button_layout1.addWidget(self.run_button, stretch=3)

        layout.addLayout(label_layout)
        layout.addWidget(self.gcode_display, stretch=4)
        layout.addLayout(button_layout1)
        # layout.addLayout(button_layout2)
        self.setLayout(layout)

        # 信号槽连接
        self.open_button.clicked.connect(self.on_click_open)
        # self.clear_button.clicked.connect(self.on_click_clear)
        self.gcode_save_signal.connect(self.update_display)

    def on_click_open(self):
        """打开 gcode 文件，清理注释，显示在 display 窗口"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择一个文件",
            "",
            "G-code (*.gcode)"
        )

        if file_path:
            print(f"选择的文件路径是: {file_path}")
            with open(file_path, "r") as f:
                gcode = f.read()
            self.gcode = self.clean_gcode(gcode)
            self.update_display()
        else:
            print("没有选择任何文件")
            return
        
    def on_click_clear(self):
        """清理 gcode 显示，重置 gcode 变量"""
        self.gcode = None
        self.update_display()

    def clean_gcode(self, gcode):
        """移除 gcode 注释，返回干净的 gcode
        
        Parameters
        ----------
        gcode : string
            Original gcode text
        
        Returns
        -------
        string
            cleaned gcode text
        """
        gcode_list = []
        for line in gcode.split("\n"):
            # 查找注释字符';'的位置
            comment_index = line.find(';')

            # 如果找到了注释
            if comment_index != -1:
                # 截取分号之前的部分
                command_part = line[:comment_index]
            else:
                # 如果没有注释，则保留整行
                command_part = line

            # 去除处理后字符串两端的空白字符（如空格、换行符）
            cleaned_line = command_part.strip()

            if cleaned_line:
                gcode_list.append(cleaned_line)
        
        return "\n".join(gcode_list)
    
    @Slot()
    def update_display(self):
        self.gcode_display.setPlainText(self.gcode)

    @Slot(int)
    def highlight_current_line(self, line_number):

        manual_selection = QTextEdit.ExtraSelection()
            
        # 设置高亮格式 (背景色)
        manual_format = QTextCharFormat()
        manual_format.setBackground(QColor("lightblue"))
        # <<< 关键改动 1: 必须设置这个属性才能让高亮填满整行
        manual_format.setProperty(QTextCharFormat.FullWidthSelection, True)
        manual_selection.format = manual_format

        # 定位到指定行
        doc = self.gcode_display.document()
        block = doc.findBlockByNumber(line_number)
        
        if block.isValid():
            cursor = QTextCursor(block)
            manual_selection.cursor = cursor
            selections = [manual_selection]
            self.gcode_display.setExtraSelections(selections)
        
    @Slot(int)
    def reset_line_highlight(self, line_number):
        """将高亮 gcode 恢复为普通样式。注意，这里接收的 line_number 仍然是当前执行行，所以 cursor 需要选择到 line_number-1 行进行操作。"""

        if line_number > 1:
            cursor = self.gcode_display.textCursor()
            cursor.movePosition(QTextCursor.StartOfBlock)
            for i in range(line_number-1):
                cursor.movePosition(QTextCursor.NextBlock)
            cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            
            # 恢复普通样式
            char_format = QTextCharFormat()
            char_format.setBackground(QColor("white"))  # 恢复背景为白色
            char_format.setForeground(QColor("black"))  # 恢复字体颜色为黑色
            cursor.setCharFormat(char_format)
            
            # 这一句是什么作用？
            self.gcode_display.setTextCursor(cursor)
        else: # 如果这是第一行，则不执行恢复操作
            return
        
class HomeWidget(QWidget):
    """主页控件，包含 G-code 控件和数据状态监视控件"""

    def __init__(self):
        super().__init__()
        self.gcode_widget = GcodeWidget()
        self.gcode_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.data_widget = DataPlotWidget()
        self.status_widget = PlatformStatusWidget()
        self.dieswell_widget = VisionWidget() # hik cam roi
        self.dieswell_widget.mouse_enabled = False
        self.ir_roi_widget = VisionWidget()
        self.ir_roi_widget.mouse_enabled = False
        self.start_button = QPushButton("开始")
        self.stop_button = QPushButton("停止")
        self.reset_button = QPushButton("重置")

        # 布局
        layout = QHBoxLayout()
        control_layout = QVBoxLayout()
        control_layout.addWidget(self.gcode_widget)
        control_button_layout = QHBoxLayout()
        control_button_layout.addWidget(self.start_button)
        control_button_layout.addWidget(self.stop_button)
        control_button_layout.addWidget(self.reset_button)
        control_layout.addLayout(control_button_layout)
        data_layout = QVBoxLayout()
        status_and_vision_layout = QHBoxLayout()
        status_and_vision_layout.addWidget(self.status_widget)
        status_and_vision_layout.addWidget(self.dieswell_widget)
        status_and_vision_layout.addWidget(self.ir_roi_widget)
        data_layout.addLayout(status_and_vision_layout)
        data_layout.addWidget(self.data_widget)
        layout.addLayout(control_layout)
        layout.addLayout(data_layout)
        self.setLayout(layout)

class IRPageWidget(QWidget):
    """红外相机模块页面组件"""

    def __init__(self):
        super().__init__()
        self.image_widget = VisionWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.image_widget)
        self.setLayout(layout)
        
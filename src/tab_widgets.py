"""
Tabs widgets for layout management. Contains

- connection widget
- platform status widget
- data plotting widget
- command widget
- log display widget
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QLabel, QGridLayout, QMessageBox, QTabWidget, QFileDialog, QTextEdit, QLabel, QStyle
)
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QSize
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
        self.ip_input = QLineEdit("192.168.114.48")
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
        self.temp_label = QLabel("温度:")
        self.temp_value_label = QLabel(f"{placeholder:5s} /")
        self.temp_input = QLineEdit("")
        self.temp_input.setMaximumWidth(60)
        self.force_label = QLabel("挤出力:")
        self.force_value_label = QLabel(f"{placeholder}")
        self.meter_label = QLabel("当前进料量:")
        self.meter_value_label = QLabel(f"{placeholder}")
        self.velocity_label = QLabel("进线速度:")
        self.velocity_value_label = QLabel(f"{placeholder}")

        # 布局
        layout = QVBoxLayout()
        row_layout_1 = QHBoxLayout()
        row_layout_2 = QHBoxLayout()
        row_layout_3 = QHBoxLayout()
        row_layout_4 = QHBoxLayout()

        row_layout_1.addWidget(self.temp_label)
        row_layout_1.addWidget(self.temp_value_label)
        row_layout_1.addWidget(self.temp_input)
        row_layout_1.addStretch(1)
        row_layout_2.addWidget(self.force_label)
        row_layout_2.addWidget(self.force_value_label)
        row_layout_2.addStretch(1)
        row_layout_3.addWidget(self.meter_label)
        row_layout_3.addWidget(self.meter_value_label)
        row_layout_3.addStretch(1)
        row_layout_4.addWidget(self.velocity_label)
        row_layout_4.addWidget(self.velocity_value_label)
        row_layout_4.addStretch(1)
        layout.addLayout(row_layout_1)
        layout.addLayout(row_layout_2)
        layout.addLayout(row_layout_3)
        layout.addLayout(row_layout_4)
        
        self.setLayout(layout)

    @Slot(float)
    def update_display_temperature(self, temperature):
        self.temp_value_label.setText(f"{temperature:5.1f} /")

class DataPlotWidget(QWidget):

    def __init__(self):

        super().__init__()

        # 创建 pyqtgraph widgets
        self.force_plot = pg.PlotWidget(title="挤出力")
        self.dietemp_plot = pg.PlotWidget(title="出口温度")
        self.dieswell_plot = pg.PlotWidget(title="胀大比")
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

        # 初始化存储数据的变量
        self.initialize_variables()

    def initialize_variables(self):
        # initialize variables
        self.max_len = 100000
        self.time = deque(maxlen=self.max_len)
        self.temperature = deque(maxlen=self.max_len)
        self.extrusion_force = deque(maxlen=self.max_len)
        self.die_swell = deque(maxlen=self.max_len)
        self.die_temperature = deque(maxlen=self.max_len)
        self.t0 = None
    
    @Slot(dict)
    def update_display(self, data):
        """处理从工作线程传来的数据"""
        # 在日志中显示原始数据
        
        try:
            if self.t0 is None:
                self.t0 = time.time()
                t = 0.0
            else:
                t = time.time() - self.t0

            # self.temp_value_label.setText(f"{json_data["hotend_temperature"]:.1f} / {self.set_temperature:.1f} °C")
            self.time.append(t)
            self.die_temperature.append(data["die_temperature"])
            self.extrusion_force.append(data["extrusion_force"])
            self.die_swell.append(data["die_swell"])
            self.force_curve.setData(list(self.time), list(self.extrusion_force))
            self.dietemp_curve.setData(list(self.time), list(self.die_temperature))
            self.dieswell_curve.setData(list(self.time), list(self.die_swell))

        except (IndexError, ValueError):
            self.temp_value_label.setText("解析错误")

    def reset(self):
        if self.time:
            self.time.clear()
        if self.extrusion_force:
            self.extrusion_force.clear()
        if self.die_temperature:
            self.die_temperature.clear()
        if self.die_swell:
            self.die_swell.clear()
        self.t0 = None

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

    def __init__(self):

        super().__init__()

        # 组件
        self.view_box = self.addViewBox(row=0, col=0)
        self.view_box.setAspectLocked(True) # 保持图像原始宽高比
        self.view_box.invertY(True)
        self.img_item = pg.ImageItem()
        self.view_box.addItem(self.img_item)
    
    @Slot(np.ndarray)
    def update_live_display(self, frame):
        self.img_item.setImage(frame, axisOrder="row-major")
    
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
        # self.gcode_display.setReadOnly(True)
        self.open_button = QPushButton("打开")
        self.clear_button = QPushButton("清除")
        self.run_button = QPushButton("运行")

        # 布局
        layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        label_layout.addWidget(self.gcode_title)
        label_layout.addWidget(self.warning_label)
        label_layout.addStretch(1)
        button_layout1 = QHBoxLayout()
        button_layout2 = QHBoxLayout()
        button_layout1.addWidget(self.open_button)
        button_layout1.addWidget(self.clear_button)
        button_layout2.addWidget(self.run_button)

        layout.addLayout(label_layout)
        layout.addWidget(self.gcode_display)
        layout.addLayout(button_layout1)
        layout.addLayout(button_layout2)
        self.setLayout(layout)

        # 信号槽连接
        self.open_button.clicked.connect(self.on_click_open)
        self.clear_button.clicked.connect(self.on_click_clear)
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
        super().__init__(self)
        self.gcode_widget = GcodeWidget()
        self.data_widget = DataPlotWidget()
        self.status_widget = PlatformStatusWidget()

        # 布局
        layout = QHBoxLayout()
        data_layout = QVBoxLayout()
        data_layout.addWidget(self.status_widget)
        data_layout.addWidget(self.data_widget)
        layout.addWidget(self.gcode_widget)
        layout.addLayout(data_layout)
        self.setLayout(layout)
        
from pathlib import Path
import sys
current_path = Path(__file__).resolve().parent.parent
sys.path.append(str(current_path))

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QTextEdit, QLabel, QStyle
)
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtCore import Signal, Slot, QSize, QObject
from utils import GcodePositionMapper
import time
from threading import Thread
import logging

class GcodeWidget(QWidget):

    sigGcode = Signal(str)
    sigFilePath = Signal(str)
    sigCurrentLine = Signal(int)

    def __init__(self, hightlight_color="#456882", logger=None):
        
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
        self.gcode_display.setReadOnly(True)
        # self.gcode_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.open_button = QPushButton("打开")
        self.run_button = QPushButton("运行")

        # 布局
        layout = QVBoxLayout()
        label_layout = QHBoxLayout()
        label_layout.addWidget(self.gcode_title)
        label_layout.addWidget(self.warning_label)
        label_layout.addStretch(1)
        button_layout1 = QHBoxLayout()

        button_layout1.addWidget(self.open_button)
        button_layout1.addWidget(self.run_button, stretch=3)

        layout.addLayout(label_layout)
        layout.addWidget(self.gcode_display, stretch=4)
        layout.addLayout(button_layout1)
        self.setLayout(layout)

        # 信号槽连接
        self.open_button.clicked.connect(self.on_click_open)
        self.run_button.clicked.connect(self.on_click_run)
        self.sigCurrentLine.connect(self.highlight_current_line)
        # self.sigCurrentLine.connect(self.reset_line_highlight)

        # variables
        self.file_path = None
        self.highlight_color = hightlight_color

        # logger
        self.logger = logger or logging.getLogger(__name__)

    def on_click_open(self):
        """打开 gcode 文件，清理注释，显示在 display 窗口"""
        self.file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择一个文件",
            "",
            "G-code (*.gcode)"
        )

        if self.file_path:
            print(f"选择的文件路径是: {self.file_path}")
            with open(self.file_path, "r") as f:
                gcode = f.read()
                self.set_gcode(gcode)
            
            # self.gcode_display.setPlainText(self.gcode)
            self.display_gcode()
            
        else:
            print("没有选择任何文件")
            return

    def on_click_run(self):
        if self.file_path:
            # emit file path
            self.sigFilePath.emit(self.file_path)
            
    
    def display_gcode(self):
        self.gcode_display.setPlainText(self.gcode)
    
    def set_gcode(self, gcode):
        self.gcode = gcode
        # emit gcode
        self.sigGcode.emit(self.gcode)
        # create gcode position mapper
        self.mapper = GcodePositionMapper(self.gcode)

    @Slot(int)
    def highlight_current_line(self, line_number):
        self.logger.debug(f"highlight line {line_number}")

        manual_selection = QTextEdit.ExtraSelection()
            
        # 设置高亮格式 (背景色)
        manual_format = QTextCharFormat()
        manual_format.setBackground(QColor(self.highlight_color))
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
            self.logger.debug(f"reset line {line_number}")
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
    
    @Slot(int)
    def update_file_position(self, file_position):
        self.logger.debug(f"file position: {file_position}")
        if self.mapper:
            current_line = self.mapper.get_line_number(file_position) - 1
            self.logger.debug(f"current line: {current_line}")
            self.sigCurrentLine.emit(current_line)
        else:
            pass

def update_position_test(widget):
    pos = range(0, 300, 10)
    for fp in pos:
        widget.update_file_position(fp)
        time.sleep(1)


if __name__ == "__main__":

    from PySide6.QtWidgets import QApplication

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] # 确保输出到 stdout
    )

    test_gcode_content = """
    G91
    M104 S200 ; Set Temp
    G1 F100 ; Set speed 20mm/s
    G1 E1 ; Move and Extrude
    G1 F200
    G1 E2 ; Move and Extrude
    G1 F300
    G1 E3 ; Retract (E goes from 2 to 1)
    M104 S210 ; Change Temp
    G1 X30 E3 ; Move and Extrude
    """

    app = QApplication(sys.argv)
    widget = GcodeWidget()
    widget.set_gcode(test_gcode_content)
    widget.display_gcode()
    # widget.update_file_position(100)
    thread = Thread(target=update_position_test, args=(widget, ))
    thread.start()
    widget.show()
    sys.exit(app.exec())

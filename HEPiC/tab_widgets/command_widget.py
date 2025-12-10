from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit
)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from datetime import datetime

class CommandWidget(QWidget):

    command = Signal(str)

    def __init__(self):

        super().__init__()

        self.command_display = QPlainTextEdit()
        self.command_display.setReadOnly(True)
        self.command_display.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: Consolas, monaco, monospace;")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入 G-code 指令 (如 G1 E10 F300)")
        self.send_button = QPushButton("发送指令")
        # self.send_button.setEnabled(False)

        layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.command_input)
        input_layout.addWidget(self.send_button)
        layout.addWidget(self.command_display)
        layout.addLayout(input_layout)
        self.setMinimumWidth(300)
        self.setLayout(layout)

        # 信号槽连接
        self.send_button.clicked.connect(self.on_send_clicked)
        self.command_input.returnPressed.connect(self.on_send_clicked)

        # constants
        self.colors = {
            "error": QColor("#f44336"),   # 红色 !!
            "info":  QColor("#bdbdbd"),   # 灰色 //
            "action": QColor("#ff9800"),  # 橙色 action:
            "command": QColor("#4caf50"), # 绿色 (用户发送的指令)
            "normal": QColor("#ffffff")   # 白色
        }

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
    def on_send_clicked(self):
        command = self.command_input.text().strip()
        if command:
            self.display_message(command)
            # 调用 signal 发送指令
            self.command.emit(command)
            self.command_input.clear()
    
    @Slot(str)
    def display_message(self, message):
        """
        核心方法：解析消息类型并应用颜色
        """

        # 1. 确定消息类型和颜色
        msg_type = "normal"

        if message.startswith("!!"):
            msg_type = "error"
        elif "action:" in message:
            # Fluidd 通常会把 action 特殊高亮，或者这是系统提示
            msg_type = "action"
        elif message.startswith("//"):
            msg_type = "info"
        elif message.startswith(">"): 
            # 假设你自己发送的指令回显以 > 开头
            msg_type = "command"
        
        # 2. 获取对应的颜色格式
        color = self.colors.get(msg_type, self.colors["normal"])
        tf = QTextCharFormat()
        tf.setForeground(color)

        # 3. 移动光标到末尾并插入文本
        cursor = self.command_display.textCursor()
        # cursor.movePosition(QTextCursor.End)

        # time stamp
        now = datetime.now()
        time_str = now.strftime("%H:%M")
                
        # 插入带格式的文本
        cursor.insertText(f"{time_str} | {message}\n", tf)
        
        # 4. 自动滚动到底部
        self.command_display.setTextCursor(cursor)
        self.command_display.ensureCursorVisible()
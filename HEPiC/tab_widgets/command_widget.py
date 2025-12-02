from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit
)
from PySide6.QtCore import Signal, Slot
import json

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
        self.send_button.setEnabled(False)

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
            print("--- [DEBUG] 'send_command' method called.")
            self.command_display.appendPlainText(f"{command}")
            # 调用 signal 发送指令
            self.command.emit(command)
            self.command_input.clear()
    
    @Slot(str)
    def display_message(self, message):
        self.command_display.appendPlainText("//"+message)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit
)
from PySide6.QtCore import Signal, Slot
import json

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
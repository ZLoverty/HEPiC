from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox, QLabel, 
)
from PySide6.QtCore import Signal, Slot
from collections import deque

class ConnectionWidget(QWidget):
    """The front page of the app, user needs to input the IP address of Raspberry Pi"""

    host = Signal(str)

    def __init__(self, host=""):

        super().__init__()

        self.status_list = deque(maxlen=10)

        # 组件
        self.ip_label = QLabel("树莓派 IP 地址 ")
        self.ip_input = QLineEdit(f"{host}")
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
            self.host.emit(ip_address)
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

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = ConnectionWidget(host="192.168.0.81")
    widget.show()
    sys.exit(app.exec())
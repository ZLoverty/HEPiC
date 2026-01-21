from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
    QPlainTextEdit, QLabel, QLabel
)
from PySide6.QtCore import Slot
from datetime import datetime

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
        # time stamp
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        self.log_display.appendPlainText(f"{time_str}    {message}")


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = LogWidget()
    widget.show()
    sys.exit(app.exec())
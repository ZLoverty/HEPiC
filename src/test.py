import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QStyle
from PySide6.QtGui import QIcon
from PySide6.QtCore import Slot, QSize

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("圆形播放/暂停按钮")
        self.setGeometry(100, 100, 300, 150)

        # --- 获取图标 ---
        style = self.style()
        self.play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)

        # --- 创建按钮 ---
        self.play_pause_button = QPushButton(self)
        self.play_pause_button.setIcon(self.play_icon)
        self.play_pause_button.move(110, 35) # 移动到窗口中间

        # 1. 设置一个固定的、正方形的尺寸
        button_size = 80
        self.play_pause_button.setFixedSize(button_size, button_size)
        
        # (可选) 设置图标大小
        self.play_pause_button.setIconSize(QSize(button_size // 2, button_size // 2))

        # 2. 使其可切换 (用于播放/暂停)
        self.play_pause_button.setCheckable(True)

        # 3. 定义 QSS 样式表
        qss_style = f"""
        QPushButton {{
            /* 关键: border-radius 必须是 宽/高 的一半 */
            border-radius: {button_size // 2}px; 
            
            /* (可选) 添加边框 */
            border: 2px solid #aaaaaa; 
            
            /* (可选) 默认背景色 */
            background-color: #f0f0f0;
        }}
        
        /* (可选) 鼠标悬停时的样式 */
        QPushButton:hover {{
            background-color: #e0e0e0;
        }}

        /* (可选) 鼠标按下时的样式 */
        QPushButton:pressed {{
            background-color: #d0d0d0;
        }}

        /* (可选) 选中状态 (checked) 时的样式 */
        QPushButton:checked {{
            background-color: #cce5ff; /* 浅蓝色 */
            border: 2px solid #0078d7; /* 蓝色边框 */
        }}
        """

        # 4. 应用样式表
        self.play_pause_button.setStyleSheet(qss_style)

        # 5. 连接信号
        self.play_pause_button.toggled.connect(self.on_button_toggled)

    @Slot(bool)
    def on_button_toggled(self, checked):
        if checked:
            self.play_pause_button.setIcon(self.pause_icon)
            print("状态：播放中")
        else:
            self.play_pause_button.setIcon(self.play_icon)
            print("状态：已暂停")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
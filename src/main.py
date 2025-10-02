import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton
)

# 1. 定义你的主窗口类，继承自 QMainWindow
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__() # 调用父类的构造函数

        # --- 窗口基础设置 ---
        self.setWindowTitle("我的第一个PySide6应用")
        self.setGeometry(300, 300, 400, 200) # 设置窗口初始位置和大小 (x, y, width, height)

        # --- 创建UI组件 (Widgets) ---
        # 标签
        self.greeting_label = QLabel("请在下方输入你的名字：")
        
        # 单行输入框
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("在这里输入...") # 设置提示文本

        # 按钮
        self.greet_button = QPushButton("点击这里")
        
        # --- 核心：连接信号与槽 ---
        # 当按钮被点击(clicked信号)时，执行 self.update_greeting 方法(槽)
        self.greet_button.clicked.connect(self.update_greeting)
        
        # --- 设置布局 (Layout) ---
        # 布局是组织窗口内组件的方式，QVBoxLayout是垂直布局
        layout = QVBoxLayout()
        layout.addWidget(self.greeting_label) # 按顺序添加组件
        layout.addWidget(self.name_input)
        layout.addWidget(self.greet_button)
        
        # QMainWindow 需要一个中心小部件(central widget)来承载布局
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    # 2. 定义槽(Slot)函数，处理按钮点击事件
    def update_greeting(self):
        """当按钮被点击时，这个函数会被调用"""
        name = self.name_input.text() # 获取输入框中的文本
        if name:
            self.greeting_label.setText(f"你好, {name}!")
        else:
            self.greeting_label.setText("请输入你的名字！")


# 3. 应用程序入口
if __name__ == "__main__":
    # 每个PySide应用都需要一个QApplication实例
    app = QApplication(sys.argv)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 启动应用的事件循环
    sys.exit(app.exec())
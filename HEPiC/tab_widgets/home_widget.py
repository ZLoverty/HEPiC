from PySide6.QtWidgets import (
     QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QPushButton, QStyle
)
from PySide6.QtCore import QSize, Signal, Slot
from .command_widget import CommandWidget
from .data_plot_widget import DataPlotWidget
from .platform_status_widget import PlatformStatusWidget
from .vision_widget import VisionWidget

class HomeWidget(QWidget):
    """主页控件，包含 G-code 控件和数据状态监视控件"""

    sigRestart = Signal()

    def __init__(self):
        super().__init__()
        self.command_widget = CommandWidget()
        self.command_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.data_widget = DataPlotWidget()
        self.status_widget = PlatformStatusWidget()
        self.dieswell_widget = VisionWidget() # hik cam roi
        self.dieswell_widget.mouse_enabled = False
        self.ir_roi_widget = VisionWidget()
        self.ir_roi_widget.mouse_enabled = False
        # play pause button
        style = self.style()
        self.play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.play_pause_button = QPushButton()
        self.play_pause_button.setCheckable(True)
        self.play_pause_button.setIcon(self.play_icon)
        button_size = 80
        self.play_pause_button.setFixedSize(button_size, button_size)
        self.play_pause_button.setIconSize(QSize(button_size // 2, button_size // 2))
        # 定义 QSS 样式表
        qss_style = f"""
        QPushButton {{
            /* 关键: border-radius 必须是 宽/高 的一半 */
            border-radius: {button_size // 2}px; 
            
            /* (可选) 添加边框 */
            border: 2px solid #aaaaaa; 
            
            /* (可选) 默认背景色 */
            background-color: #f0f0f0;

            font-size: 24pt;
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
        self.play_pause_button.setStyleSheet(qss_style)

        self.stop_button = QPushButton()
        self.stop_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        self.stop_button.setIcon(self.stop_icon)
        self.stop_button.setFixedSize(button_size, button_size)
        self.stop_button.setIconSize(QSize(button_size // 2, button_size // 2))
        self.stop_button.setStyleSheet(qss_style)

        self.restart_button = QPushButton("🍓")
        # self.restart_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
        # self.restart_button.setIcon(self.restart_icon)
        self.restart_button.setFixedSize(button_size, button_size)
        self.restart_button.setIconSize(QSize(button_size // 2, button_size // 2))
        self.restart_button.setStyleSheet(qss_style)

        # 布局
        layout = QHBoxLayout()
        control_layout = QVBoxLayout()
        control_layout.addWidget(self.command_widget)
        control_button_layout = QHBoxLayout()
        control_button_layout.addWidget(self.play_pause_button)
        # control_button_layout.addWidget(self.stop_button)
        control_button_layout.addWidget(self.stop_button)
        control_button_layout.addWidget(self.restart_button)
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

        # Signal and slot
        self.restart_button.clicked.connect(self.on_restart_clicked)

    @Slot()
    def on_restart_clicked(self):
        self.sigRestart.emit()
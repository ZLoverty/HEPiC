from PySide6.QtWidgets import (
     QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QPushButton, QStyle
)
from PySide6.QtCore import QSize, Signal, Slot, QTimer
from .command_widget import CommandWidget
from .data_plot_widget import DataPlotWidget
from .platform_status_widget import PlatformStatusWidget
from .vision_widget import VisionWidget
from .klipper_status_widget import KlipperStatusWidget
import logging

class HomeWidget(QWidget):
    """主页控件，包含 G-code 控件和数据状态监视控件"""

    sigRestart = Signal()
    sigExtrude = Signal(str)
    sigRetract = Signal(str)

    def __init__(self, time_window_s=60):
        super().__init__()

        self.logger = logging.getLogger(__name__)
        self.command_widget = CommandWidget()
        self.command_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.data_widget = DataPlotWidget(time_window_s=time_window_s)
        self.status_widget = PlatformStatusWidget()
        self.dieswell_widget = VisionWidget() # hik cam roi
        self.ir_roi_widget = VisionWidget()

        # play / pause button, emergency stop button, restart button
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
        self.restart_button.setFixedSize(button_size, button_size)
        self.restart_button.setIconSize(QSize(button_size // 2, button_size // 2))
        self.restart_button.setStyleSheet(qss_style)

        # extrude, retract buttons (按住连续挤出/回抽，松开立即停止)
        self.extrude_button = QPushButton("挤出（长按）")
        self.retract_button = QPushButton("回抽（长按）")
        self.klipper_status_widget = KlipperStatusWidget()

        # 长按连续挤出参数
        self.extrude_feedrate = 200  # mm/min
        self.jog_interval_ms = 1000   # 每隔多少毫秒发送一次小段挤出
        # 每段的长度使其运动时间约等于发送间隔，避免运动队列堆积，
        # 这样松开按钮后最多再挤出一小段即停止。
        self.jog_step_mm = self.extrude_feedrate / 60 * (self.jog_interval_ms / 1000)

        self._extrude_timer = QTimer(self)
        self._extrude_timer.setInterval(self.jog_interval_ms)
        self._extrude_timer.timeout.connect(self.on_extrude_tick)

        self._retract_timer = QTimer(self)
        self._retract_timer.setInterval(self.jog_interval_ms)
        self._retract_timer.timeout.connect(self.on_retract_tick)

        # 布局
        layout = QHBoxLayout()
        control_layout = QVBoxLayout()
        extrude_retract_layout = QHBoxLayout()
        extrude_retract_layout.addWidget(self.extrude_button)
        extrude_retract_layout.addWidget(self.retract_button)
        control_layout.addLayout(extrude_retract_layout)
        control_layout.addWidget(self.command_widget)
        control_button_layout = QHBoxLayout()
        control_button_layout.addWidget(self.play_pause_button)
        # control_button_layout.addWidget(self.stop_button)
        control_button_layout.addWidget(self.stop_button)
        control_button_layout.addWidget(self.restart_button)
        control_layout.addLayout(control_button_layout)
        data_layout = QVBoxLayout()
        klipper_row = QHBoxLayout()
        klipper_row.addStretch()
        klipper_row.addWidget(self.klipper_status_widget)
        data_layout.addLayout(klipper_row)
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
        self.extrude_button.pressed.connect(self.on_extrude_pressed)
        self.extrude_button.released.connect(self.on_extrude_released)
        self.retract_button.pressed.connect(self.on_retract_pressed)
        self.retract_button.released.connect(self.on_retract_released)

    @Slot()
    def on_restart_clicked(self):
        self.sigRestart.emit()
    
    def on_extrude_pressed(self):
        self.logger.debug("Extrude button pressed")
        self.on_extrude_tick()      # 立即挤出一段，提升按下的响应感
        self._extrude_timer.start()

    def on_extrude_released(self):
        self.logger.debug("Extrude button released")
        self._extrude_timer.stop()

    def on_extrude_tick(self):
        self.sigExtrude.emit(f"G91\nG1 E{self.jog_step_mm:.3f} F{self.extrude_feedrate}\n")

    def on_retract_pressed(self):
        self.logger.debug("Retract button pressed")
        self.on_retract_tick()      # 立即回抽一段，提升按下的响应感
        self._retract_timer.start()

    def on_retract_released(self):
        self.logger.debug("Retract button released")
        self._retract_timer.stop()

    def on_retract_tick(self):
        self.sigRetract.emit(f"G91\nG1 E-{self.jog_step_mm:.3f} F{self.extrude_feedrate}\n")
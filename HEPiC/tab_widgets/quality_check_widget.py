import logging
from pathlib import Path
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QLabel,
    QTextEdit, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QColor
import pyqtgraph as pg
import numpy as np


class StatusIndicator(QFrame):
    """圆形会变色的状态指示器"""
    def __init__(self, size=60):
        super().__init__()
        self._size = size
        self.status = "unknown"  # unknown, stable, unstable
        self.setFixedSize(size, size)
        self.setStyleSheet("border-radius: {}px;".format(size // 2))
        self.update_status("unknown")

    def update_status(self, status: str):
        """更新状态: unknown (灰), stable (绿), unstable (红)"""
        self.status = status
        colors = {
            "unknown": "#888888",
            "stable": "#27ae60",
            "unstable": "#e74c3c"
        }
        color = colors.get(status, "#888888")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: {self._size // 2}px;
                border: 2px solid white;
            }}
        """)


class QualityCheckWidget(QWidget):
    """质检模式 Tab Widget"""
    
    # 信号定义
    quality_check_started = Signal(str)  # 发送选中的材料名称
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # 数据存储
        self.extrusion_force_cache = deque(maxlen=300)
        self.time_cache = deque(maxlen=300)
        self.current_time = 0
        self.is_checking = False
        self.stability_threshold = 2.0  # 标准差阈值
        
        # 材料属性数据库（简单版本，可后续扩展为真实数据库）
        self.material_properties = {
            "PLA": {
                "expected_force": 5.0,
                "force_range": (3.0, 7.0),
                "temperature": 200,
                "speed": 30,
            },
            "PETG": {
                "expected_force": 6.0,
                "force_range": (4.0, 8.0),
                "temperature": 230,
                "speed": 25,
            },
            "TPU": {
                "expected_force": 3.0,
                "force_range": (1.5, 4.5),
                "temperature": 210,
                "speed": 20,
            },
        }
        
        # 读取质检流程文档
        self.process_markdown = self._load_process_document()
        
        self.init_ui()
        
        # 数据更新定时器
        self.data_timer = QTimer()
        self.data_timer.timeout.connect(self.on_data_update_timeout)
        
        # 标记是否已经初始化材料属性
        self.material_properties_initialized = False
    
    def showEvent(self, event):
        """当widget第一次显示时初始化材料属性"""
        super().showEvent(event)
        if not self.material_properties_initialized:
            self.logger.info("QualityCheckWidget first shown, initializing material properties")
            # 延迟到显示后设置材料属性
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, self._delayed_init_material_properties)
            self.material_properties_initialized = True
    
    def _delayed_init_material_properties(self):
        """延迟初始化材料属性（从数据库加载）"""
        try:
            from ..database import get_material_database
            material_db = get_material_database()
            self.set_material_properties(material_db.get_all_materials())
            self.logger.info("Material properties initialized from database")
        except Exception as e:
            self.logger.error(f"Failed to initialize material properties: {e}")
    
    def _load_process_document(self) -> str:
        """加载质检流程文档"""
        # 默认路径：database/quality_check_process.md
        doc_path = Path(__file__).parent.parent / "database" / "quality_check_process.md"
        
        try:
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.logger.info(f"Loaded quality check process document from {doc_path}")
                return content
            else:
                self.logger.warning(f"Quality check process document not found: {doc_path}")
                return self._get_default_process_content()
        except Exception as e:
            self.logger.error(f"Failed to load quality check process document: {e}")
            return self._get_default_process_content()
    
    def _get_default_process_content(self) -> str:
        """获取默认的质检流程内容"""
        return """
# 质检流程

## 基本操作步骤

1. **选择材料** 从下拉菜单选择待检验的材料

2. **启动质检** 点击"开始质检"按钮启动数据采集

3. **监控稳定性** 观察右侧指示器颜色变化
   - 🔘 灰色: 未检验
   - 🟢 绿色: 数据稳定
   - 🔴 红色: 数据不稳定

4. **查看属性** 核对材料的预期属性是否匹配

5. **停止质检** 点击"停止质检"按钮结束检验

## 说明
- 稳定性基于挤出力的波动情况
- 绿色表示数据方差低于阈值
- 所有数据实时显示在右侧

*注意：无法加载外部文档，使用默认内容*
        """
    
    def set_material_properties(self, properties: dict):
        """
        设置材料属性数据库（供外部调用）
        
        参数:
            properties: 材料属性字典
                {
                    "材料名": {
                        "expected_force": 值,
                        "force_range": (最小, 最大),
                        "temperature": 值,
                        "speed": 值,
                    },
                    ...
                }
        """
        self.logger.info(f"Setting material properties: {list(properties.keys())}")
        self.material_properties.update(properties)
        
        # 延迟更新UI，确保Qt对象已经完全初始化
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10, self._update_material_combo_box)
    
    def _update_material_combo_box(self):
        """安全地更新材料下拉菜单"""
        try:
            if hasattr(self, 'material_combo') and self.material_combo is not None and not self.material_combo.isHidden():
                self.logger.info("Updating material combo box safely")
                current_material = self.material_combo.currentText()
                self.material_combo.clear()
                self.material_combo.addItems(list(self.material_properties.keys()))
                
                # 恢复之前的选择
                if current_material and current_material in self.material_properties:
                    index = self.material_combo.findText(current_material)
                    if index >= 0:
                        self.material_combo.setCurrentIndex(index)
                self.logger.info("Material combo box updated successfully")
            else:
                self.logger.warning("material_combo not ready for update")
        except RuntimeError as e:
            self.logger.error(f"Error updating material combo box: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error updating material combo box: {e}")
    
    def _load_process_document(self) -> str:
        """加载质检流程文档"""
        # 默认路径：database/quality_check_process.md
        doc_path = Path(__file__).parent.parent / "database" / "quality_check_process.md"
        
        try:
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.logger.info(f"Loaded quality check process document from {doc_path}")
                return content
            else:
                self.logger.warning(f"Quality check process document not found: {doc_path}")
                return self._get_default_process_content()
        except Exception as e:
            self.logger.error(f"Failed to load quality check process document: {e}")
            return self._get_default_process_content()
    
    def init_ui(self):
        """初始化用户界面"""
        main_layout = QHBoxLayout()
        
        # ===== 左侧控制面板 =====
        left_panel = self.create_left_panel()
        
        # ===== 右侧显示区域 =====
        right_panel = self.create_right_panel()
        
        # 添加面板到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
        self.setLayout(main_layout)
        
        # 初始化材料属性显示
        self.update_material_properties_display()
    
    def create_left_panel(self):
        """创建左侧控制面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # 富文本编辑器显示操作流程
        self.instruction_text = QTextEdit()
        self.instruction_text.setReadOnly(True)
        self.instruction_text.setMarkdown(self.process_markdown)
        layout.addWidget(self.instruction_text)
        
        panel.setLayout(layout)
        panel.setMaximumWidth(350)
        return panel
    
    def create_right_panel(self):
        """创建右侧显示面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # ===== 第一行：材料选择、质检按钮、稳定性指示器 =====
        control_row = QHBoxLayout()
        
        # 材料选择下拉菜单
        material_label = QLabel("材料选择:")
        self.material_combo = QComboBox()
        # 初始时填充默认材料，稍后会通过set_material_properties更新
        self.material_combo.addItems(list(self.material_properties.keys()))
        self.material_combo.currentTextChanged.connect(self.update_material_properties_display)
        control_row.addWidget(material_label)
        control_row.addWidget(self.material_combo)
        
        # 质检按钮
        self.check_button = QPushButton("开始质检")
        self.check_button.clicked.connect(self.on_quality_check_clicked)
        control_row.addWidget(self.check_button)
        
        # 稳定性指示器
        stability_label = QLabel("稳定性:")
        self.status_indicator = StatusIndicator(size=50)
        control_row.addWidget(stability_label)
        control_row.addWidget(self.status_indicator)
        
        control_row.addStretch()
        layout.addLayout(control_row)
        
        # ===== 第二行：材料预期属性 =====
        properties_row = QHBoxLayout()
        
        # 标题
        properties_label = QLabel("预期属性:")
        properties_label.setStyleSheet("font-weight: bold;")
        
        # 属性显示（使用 Label 或 QLineEdit 只读版本）
        self.expected_force_label = QLabel("预期挤出力: -- N")
        self.force_range_label = QLabel("力值范围: -- N")
        self.temperature_label = QLabel("温度: -- °C")
        self.speed_label = QLabel("速度: -- mm/s")
        
        properties_row.addWidget(properties_label)
        properties_row.addWidget(self.temperature_label)
        properties_row.addWidget(self.speed_label)
        properties_row.addWidget(self.expected_force_label)
        properties_row.addWidget(self.force_range_label)
        properties_row.addStretch()
        
        layout.addLayout(properties_row)
        
        # ===== 第三行：动态折线图 =====
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Extrusion Force", units="N")
        self.plot_widget.setTitle("实时挤出力数据")
        self.plot_widget.addLegend()
        
        # 创建曲线
        self.force_curve = self.plot_widget.plot(
            pen=pg.mkPen("#2980b9", width=2),
            name="Extrusion Force (N)"
        )
        
        # 添加参考线（预期值）
        self.expected_upper = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine),
            label="预期上限"
        )
        self.plot_widget.addItem(self.expected_upper)
        
        self.expected_lower = pg.InfiniteLine(
            pos=0,
            angle=0,
            pen=pg.mkPen("#27ae60", width=1, style=Qt.PenStyle.DashLine),
            label="预期下限"
        )
        self.plot_widget.addItem(self.expected_lower)
    
        layout.addWidget(self.plot_widget, 1)

        
        
        panel.setLayout(layout)
        return panel
    
    def update_material_properties_display(self):
        """更新材料属性显示"""
        material = self.material_combo.currentText()
        props = self.material_properties.get(material, {})
        
        self.expected_force_label.setText(
            f"预期挤出力: {props.get('expected_force', '--')} N"
        )
        force_min, force_max = props.get('force_range', ('--', '--'))
        self.force_range_label.setText(
            f"力值范围: {force_min} - {force_max} N"
        )
        self.temperature_label.setText(
            f"温度: {props.get('temperature', '--')} °C"
        )
        self.speed_label.setText(
            f"速度: {props.get('speed', '--')} mm/s"
        )
        
        # 更新参考线位置
        expected_force = props.get('expected_force', 0)
        self.expected_upper.setPos(props.get('force_range', (0, 0))[1])
        self.expected_lower.setPos(props.get('force_range', (0, 0))[0])
    @Slot()
    def on_quality_check_clicked(self):
        """处理质检按钮点击事件"""
        if not self.is_checking:
            # 开始质检
            self.is_checking = True
            self.check_button.setText("停止质检")
            self.check_button.setStyleSheet(
                "background-color: #e74c3c; color: white;"
            )
            
            # 清空数据
            self.extrusion_force_cache.clear()
            self.time_cache.clear()
            self.current_time = 0
            
            # 更新属性显示
            self.update_material_properties_display()
            
            # 发送信号并启动数据更新
            material = self.material_combo.currentText()
            self.quality_check_started.emit(material)
            self.data_timer.start(100)  # 100ms 更新一次
            self.logger.info(f"Quality check started for material: {material}")
        else:
            # 停止质检
            self.is_checking = False
            self.check_button.setText("开始质检")
            self.check_button.setStyleSheet("")
            self.data_timer.stop()
            self.status_indicator.update_status("unknown")
            self.logger.info("Quality check stopped")
    
    @Slot()
    def on_data_update_timeout(self):
        """定时更新数据（模拟或接收真实数据）"""
        # 这个方法会被主窗口的数据信号驱动
        # 这里只是一个占位符，实际数据会通过 update_sensor_data() 传入
        pass
    
    @Slot(dict)
    def update_sensor_data(self, data: dict):
        """
        接收传感器数据更新
        
        参数:
            data: 包含传感器数据的字典，应包含 'time_s' 和 'extrusion_force_N' 等字段
        """
        if not self.is_checking:
            return
        
        # 获取最新数据
        time_data = data.get("time_s", [])
        force_data = data.get("extrusion_force_N", [])
        
        if not time_data or not force_data:
            return
        
        # 只取最新的数据点
        if len(time_data) > 0 and len(force_data) > 0:
            latest_time = time_data[-1]
            latest_force = force_data[-1]
            
            self.time_cache.append(latest_time)
            self.extrusion_force_cache.append(latest_force)
            
            # 只在开始时记录一次数据信息
            if len(self.extrusion_force_cache) == 1:
                self.logger.info(f"Quality check started - receiving extrusion_force_N data: {latest_force} N")
        
        # 更新图表
        self.update_plot()
        
        # 更新稳定性指示
        self.update_stability_indicator()
    
    def update_plot(self):
        """更新折线图"""
        if len(self.time_cache) > 0:
            times = list(self.time_cache)
            forces = list(self.extrusion_force_cache)
            self.force_curve.setData(times, forces)
    
    def update_stability_indicator(self):
        """更新稳定性指示器"""
        if len(self.extrusion_force_cache) < 10:
            # 数据太少，无法判断
            self.status_indicator.update_status("unknown")
            return
        
        # 计算最近数据的标准差
        recent_data = list(self.extrusion_force_cache)[-20:]
        std = np.std(recent_data)
        
        # 根据标准差判断稳定性
        if std < self.stability_threshold:
            self.status_indicator.update_status("stable")
        else:
            self.status_indicator.update_status("unstable")
    
    def set_material_properties(self, properties: dict):
        """
        设置材料属性数据库（供外部调用）
        
        参数:
            properties: 材料属性字典
                {
                    "材料名": {
                        "expected_force": 值,
                        "force_range": (最小, 最大),
                        "temperature": 值,
                        "speed": 值,
                    },
                    ...
                }
        """
        self.logger.info(f"Setting material properties: {list(properties.keys())}")
        self.material_properties.update(properties)
        
        # 延迟更新UI，确保Qt对象已经完全初始化
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10, self._update_material_combo_box)
    
    def _update_material_combo_box(self):
        """安全地更新材料下拉菜单"""
        try:
            if hasattr(self, 'material_combo') and self.material_combo is not None and not self.material_combo.isHidden():
                self.logger.info("Updating material combo box safely")
                current_material = self.material_combo.currentText()
                self.material_combo.clear()
                self.material_combo.addItems(list(self.material_properties.keys()))
                
                # 恢复之前的选择
                if current_material and current_material in self.material_properties:
                    index = self.material_combo.findText(current_material)
                    if index >= 0:
                        self.material_combo.setCurrentIndex(index)
                self.logger.info("Material combo box updated successfully")
            else:
                self.logger.warning("material_combo not ready for update")
        except RuntimeError as e:
            self.logger.error(f"Error updating material combo box: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error updating material combo box: {e}")

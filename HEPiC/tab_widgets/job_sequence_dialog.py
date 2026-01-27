import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QDialog, 
                               QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, 
                               QDialogButtonBox, QMessageBox, QWidget)
import numpy as np

class JobSequenceDialog(QDialog):
    """自定义参数输入对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成动作序列")
        self.resize(300, 150)

        # 1. 创建布局
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        # 2. 创建输入控件
        self.vmin_input = QLineEdit()
        self.vmax_input = QLineEdit()
        self.vnum_input = QSpinBox()
        self.vnum_input.setRange(0, 100)
        self.vnum_input.setValue(20)

        self.tmin_input = QLineEdit()
        self.tmax_input = QLineEdit()
        self.tnum_input = QSpinBox()
        self.tnum_input.setRange(0, 100)
        self.tnum_input.setValue(20)

        self.tstep_input = QLineEdit()

        # 3. 将控件添加到表单布局
        form_layout.addRow("最小速度:", self.vmin_input)
        form_layout.addRow("最大速度:", self.vmax_input)
        form_layout.addRow("速度个数:", self.vnum_input)
        form_layout.addRow("最小温度:", self.tmin_input)
        form_layout.addRow("最大温度:", self.tmax_input)
        form_layout.addRow("温度个数:", self.tnum_input)
        form_layout.addRow("每步时间:", self.tstep_input)

        # 4. 创建标准按钮 (OK / Cancel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        
        # 5. 连接信号与槽
        # accept() 会关闭对话框并返回 1 (True)
        # reject() 会关闭对话框并返回 0 (False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        # 6. 组装布局
        layout.addLayout(form_layout)
        layout.addWidget(self.buttons)
        self.setLayout(layout)

    def get_job_sequence(self):
        """返回用户输入的数据"""

        job_sequence_list = [
            "M118 Set to relative mode",
            "G91",
            "M118 Nozzle heating"
        ]

        Ts = np.linspace(float(self.tmin_input.text()), float(self.tmax_input.text()), self.tnum_input.value())
        Vs = np.linspace(float(self.vmin_input.text()), float(self.vmax_input.text()), self.vnum_input.value())
        t_each = float(self.tstep_input.text())

        # adjusting temperature to the first temperature of the real test
        job_sequence_list.extend([
            "M118 adjusting temperature to real test ...",
        ])
            
        for num, T in enumerate(Ts):
            job_sequence_list.append(f"M109 S{T:.2f}")
            if num == 0:
                job_sequence_list.extend([
                    "M400",
                    "M118 Temperature reached. Programmed test starts in 3 seconds.",
                    "G4 P2000",
                    "M118 If you'd like to record the test, please start recording now.",
                    "G4 P1500",
                    "M118 Make sure to zero extrusion force and meter values.",
                    "G4 P1500",
                    "M118 Starting test in 3 seconds ...",
                    "G4 P1000",
                    "M118 3 ...",
                    "M400",
                    "G4 P1000",
                    "M118 2 ...",
                    "M400",
                    "G4 P1000",
                    "M118 1 ...",
                    "M400",
                    "M118 -- Test starts now! --"
                ])
            for V in Vs:
                job_sequence_list.append(f"M118 V = {V:.2f} mm/s")
                ext_length = V*t_each
                job_sequence_list.append(f"G1 E{ext_length:.2f} F{V*60:.2f}")
                job_sequence_list.append("M400")
                
        job_sequence_list.append("M118 Test finished. Lowering hotend temperature.")
        job_sequence_list.append("M109 S0")

        return "\n".join(job_sequence_list)
    
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("主窗口")
        self.resize(400, 300)

        # 设置中心部件和按钮
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.btn = QPushButton("输入参数")
        self.btn.clicked.connect(self.show_dialog)
        layout.addWidget(self.btn)

    def show_dialog(self):
        # 创建对话框实例，传入 self 作为父对象，使其居中显示在主窗口之上
        dialog = JobSequenceDialog(self)
        
        # exec() 是模态运行，会阻塞主窗口直到对话框关闭
        # 如果点击了 OK，exec() 返回 True
        if dialog.exec():
            data = dialog.get_job_sequence()
            print(f"生成动作序列如下:\n {data}")
        else:
            print("用户取消了输入")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
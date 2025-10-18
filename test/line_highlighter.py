import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, 
    QTextEdit, QPushButton, QLineEdit, QLabel
)
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtCore import Qt

class HighlightExample(QWidget):
    def __init__(self):
        super().__init__()
        # 用于存储手动指定要高亮的行号
        self.manual_highlight_line = None 
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("QTextEdit 行高亮 (修正版)")
        self.layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("这是第一行。\n"
                                    "这是第二行。\n"
                                    "这是第三行。\n"
                                    "这是第四行，比较长的一行。\n"
                                    "第五行。\n"
                                    "第六行。\n"
                                    "第七行。\n"
                                    "第八行。\n")
        self.text_edit.setFontPointSize(14)

        self.label = QLabel("输入要高亮的行号 (从1开始):")
        self.line_input = QLineEdit()
        self.line_input.setPlaceholderText("例如: 3")
        self.highlight_button = QPushButton("高亮指定行")
        self.clear_button = QPushButton("清除指定高亮")

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.line_input)
        self.layout.addWidget(self.highlight_button)
        self.layout.addWidget(self.clear_button)
        self.layout.addWidget(self.text_edit)

        # 信号连接
        self.highlight_button.clicked.connect(self.set_manual_highlight_line)
        self.clear_button.clicked.connect(self.clear_manual_highlight)
        # 光标移动时，也需要更新所有高亮
        self.text_edit.cursorPositionChanged.connect(self.update_all_highlights)
        
        # 初始时更新一次高亮（此时只会高亮当前行）
        self.update_all_highlights()

    def set_manual_highlight_line(self):
        """
        当按钮被点击时，记录下要高亮的行号，并触发更新
        """
        try:
            self.manual_highlight_line = int(self.line_input.text())
        except ValueError:
            self.manual_highlight_line = None
            print("请输入一个有效的行号。")
        
        self.update_all_highlights()

    def clear_manual_highlight(self):
        """
        清除手动指定的高亮
        """
        self.manual_highlight_line = None
        self.line_input.clear()
        self.update_all_highlights()

    def update_all_highlights(self):
        """
        这是核心函数。它会收集所有需要的高亮，并一次性应用。
        """
        selections = []

        # 1. 添加当前光标行的高亮
        current_line_selection = QTextEdit.ExtraSelection()
        current_line_color = QColor(Qt.yellow).lighter(160)
        current_line_selection.format.setBackground(current_line_color)
        current_line_selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        current_line_selection.cursor = self.text_edit.textCursor()
        current_line_selection.cursor.clearSelection()
        selections.append(current_line_selection)

        # 2. 如果有手动指定的行，也添加它的高亮
        if self.manual_highlight_line is not None:
            manual_selection = QTextEdit.ExtraSelection()
            
            # 设置高亮格式 (背景色)
            manual_format = QTextCharFormat()
            manual_format.setBackground(QColor("lightblue"))
            # <<< 关键改动 1: 必须设置这个属性才能让高亮填满整行
            manual_format.setProperty(QTextCharFormat.FullWidthSelection, True)
            manual_selection.format = manual_format

            # 定位到指定行
            doc = self.text_edit.document()
            block = doc.findBlockByNumber(self.manual_highlight_line - 1)
            
            if block.isValid():
                cursor = QTextCursor(block)
                manual_selection.cursor = cursor
                selections.append(manual_selection)

        # 3. 一次性应用所有高亮
        self.text_edit.setExtraSelections(selections)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = HighlightExample()
    ex.show()
    sys.exit(app.exec())
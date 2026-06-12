# -*- coding: utf-8 -*-
"""
自定义样式消息框
与主界面主题保持一致
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QStyle, QApplication

# 浅色主题样式
LIGHT_STYLE = """
QDialog {
    background-color: #ffffff;
    border: 1px solid #dcecf5;
    border-radius: 8px;
}
QLabel#title_label {
    color: #1e2732;
    font-size: 14px;
    font-weight: bold;
}
QLabel#message_label {
    color: #1e2732;
    font-size: 13px;
}
QPushButton {
    background-color: #3498db;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #2980b9;
}
QPushButton:pressed {
    background-color: #2472a4;
}
QPushButton#cancel_btn {
    background-color: #f0f4f8;
    color: #1e2732;
    border: 1px solid #dcecf5;
}
QPushButton#cancel_btn:hover {
    background-color: #e0e8f0;
}
"""

# 深色主题样式
DARK_STYLE = """
QDialog {
    background-color: #2d2d2d;
    border: 1px solid #4d4d4d;
    border-radius: 8px;
}
QLabel#title_label {
    color: #e0e0e0;
    font-size: 14px;
    font-weight: bold;
}
QLabel#message_label {
    color: #e0e0e0;
    font-size: 13px;
}
QPushButton {
    background-color: #334d6e;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: bold;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #4a6a8a;
}
QPushButton:pressed {
    background-color: #2a3d5e;
}
QPushButton#cancel_btn {
    background-color: #363636;
    color: #e0e0e0;
    border: 1px solid #4d4d4d;
}
QPushButton#cancel_btn:hover {
    background-color: #404040;
}
"""


class StyledMessageBox(QDialog):
    """自定义样式的消息框"""
    
    # 图标类型
    Information = 1
    Warning = 2
    Question = 3
    Critical = 4
    
    # 按钮类型
    Ok = 0x00000400
    Cancel = 0x00400000
    Yes = 0x00004000
    No = 0x00010000
    
    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self._theme = theme
        self._result = None
        self._apply_theme(theme)
        self._init_ui()
        
    def _apply_theme(self, theme):
        if theme == "dark":
            self.setStyleSheet(DARK_STYLE)
        else:
            self.setStyleSheet(LIGHT_STYLE)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        
        # 标题栏
        title_layout = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        title_layout.addWidget(self.icon_label)
        
        self.title_label = QLabel("提示")
        self.title_label.setObjectName("title_label")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #dcecf5;" if self._theme == "light" else "background-color: #4d4d4d;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
        # 消息内容
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)
        
        self.big_icon_label = QLabel()
        self.big_icon_label.setFixedSize(48, 48)
        content_layout.addWidget(self.big_icon_label, 0, Qt.AlignTop)
        
        self.message_label = QLabel()
        self.message_label.setObjectName("message_label")
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumWidth(250)
        content_layout.addWidget(self.message_label, 1)
        
        layout.addLayout(content_layout)
        layout.addSpacing(8)
        
        # 按钮区
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch()
        layout.addLayout(self.button_layout)
        
    def set_icon(self, icon_type):
        """设置图标"""
        style = QApplication.style()
        if icon_type == self.Information:
            pixmap = style.standardPixmap(QStyle.SP_MessageBoxInformation)
        elif icon_type == self.Warning:
            pixmap = style.standardPixmap(QStyle.SP_MessageBoxWarning)
        elif icon_type == self.Question:
            pixmap = style.standardPixmap(QStyle.SP_MessageBoxQuestion)
        elif icon_type == self.Critical:
            pixmap = style.standardPixmap(QStyle.SP_MessageBoxCritical)
        else:
            pixmap = style.standardPixmap(QStyle.SP_MessageBoxInformation)
        
        self.icon_label.setPixmap(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.big_icon_label.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    
    def set_title(self, title):
        self.title_label.setText(title)
        
    def set_message(self, message):
        self.message_label.setText(message)
        
    def add_button(self, text, button_type, is_default=False):
        """添加按钮"""
        btn = QPushButton(text)
        if button_type in (self.Cancel, self.No):
            btn.setObjectName("cancel_btn")
        btn.clicked.connect(lambda: self._on_button_clicked(button_type))
        if is_default:
            btn.setDefault(True)
        self.button_layout.addWidget(btn)
        return btn
    
    def _on_button_clicked(self, button_type):
        self._result = button_type
        self.accept()
    
    def result_button(self):
        return self._result
    
    @staticmethod
    def information(parent, title, message, theme="light"):
        """显示信息提示框"""
        box = StyledMessageBox(parent, theme)
        box.set_icon(StyledMessageBox.Information)
        box.set_title(title)
        box.set_message(message)
        box.add_button("确定", StyledMessageBox.Ok, True)
        box.exec_()
        return StyledMessageBox.Ok
    
    @staticmethod
    def warning(parent, title, message, theme="light"):
        """显示警告提示框"""
        box = StyledMessageBox(parent, theme)
        box.set_icon(StyledMessageBox.Warning)
        box.set_title(title)
        box.set_message(message)
        box.add_button("确定", StyledMessageBox.Ok, True)
        box.exec_()
        return StyledMessageBox.Ok
    
    @staticmethod
    def question(parent, title, message, buttons=None, default_button=None, theme="light", 
                 yes_text="是", no_text="否"):
        """显示询问对话框
        
        Args:
            yes_text: 自定义"是"按钮的文本
            no_text: 自定义"否"按钮的文本
        """
        if buttons is None:
            buttons = StyledMessageBox.Yes | StyledMessageBox.No
        if default_button is None:
            default_button = StyledMessageBox.No
            
        box = StyledMessageBox(parent, theme)
        box.set_icon(StyledMessageBox.Question)
        box.set_title(title)
        box.set_message(message)
        
        if buttons & StyledMessageBox.Yes:
            box.add_button(yes_text, StyledMessageBox.Yes, default_button == StyledMessageBox.Yes)
        if buttons & StyledMessageBox.No:
            box.add_button(no_text, StyledMessageBox.No, default_button == StyledMessageBox.No)
        if buttons & StyledMessageBox.Ok:
            box.add_button("确定", StyledMessageBox.Ok, default_button == StyledMessageBox.Ok)
        if buttons & StyledMessageBox.Cancel:
            box.add_button("取消", StyledMessageBox.Cancel, default_button == StyledMessageBox.Cancel)
        
        box.exec_()
        return box.result_button()
    
    @staticmethod
    def critical(parent, title, message, theme="light"):
        """显示错误提示框"""
        box = StyledMessageBox(parent, theme)
        box.set_icon(StyledMessageBox.Critical)
        box.set_title(title)
        box.set_message(message)
        box.add_button("确定", StyledMessageBox.Ok, True)
        box.exec_()
        return StyledMessageBox.Ok

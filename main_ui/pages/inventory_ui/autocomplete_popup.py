# -*- coding: utf-8 -*-
"""
自动补全弹窗组件
- 显示候选词列表
- 支持上下键选择
- 支持 Enter 确认、Esc 取消
- 支持浅色/深色主题
"""

from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QVBoxLayout, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QFont

# 主题样式定义
LIGHT_STYLE = """
    #autocomplete_popup {
        background-color: #ffffff;
        border: 1px solid #dcecf5;
        border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    QListWidget {
        background-color: transparent;
        border: none;
        outline: none;
        color: #1e2732;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-bottom: 1px solid #f0f4f8;
    }
    QListWidget::item:selected {
        background-color: #3498db;
        color: #ffffff;
    }
    QListWidget::item:hover:!selected {
        background-color: #f0f4f8;
    }
"""

DARK_STYLE = """
    #autocomplete_popup {
        background-color: #2d2d2d;
        border: 1px solid #4d4d4d;
        border-radius: 6px;
    }
    QListWidget {
        background-color: transparent;
        border: none;
        outline: none;
        color: #e0e0e0;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-bottom: 1px solid #3d3d3d;
    }
    QListWidget::item:selected {
        background-color: #334d6e;
        color: #ffffff;
    }
    QListWidget::item:hover:!selected {
        background-color: #363636;
    }
"""


class AutocompletePopup(QFrame):
    """
    自动补全弹窗
    
    使用方法：
    1. 创建弹窗实例
    2. 调用 show_candidates(candidates, pos) 显示候选词
    3. 连接 candidate_selected 信号获取选中的候选词
    
    特性：
    - 输入时自动显示匹配的候选词
    - 不会阻止用户继续输入
    - 支持上下键选择、Enter/Tab确认、Esc取消
    - 支持浅色/深色主题切换
    """
    
    # 信号：选中候选词时发出 (candidate_text)
    candidate_selected = pyqtSignal(str)
    # 信号：弹窗关闭时发出
    popup_closed = pyqtSignal()
    
    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        # Tool 窗口：不抢焦点、不抢键盘，但能接收鼠标点击
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("autocomplete_popup")
        
        # 设置初始主题
        self._current_theme = theme
        self._apply_theme(theme)
        
        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # 候选词列表
        self.list_widget = QListWidget()
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setFont(QFont("Microsoft YaHei", 10))
        self.list_widget.setMinimumWidth(200)
        self.list_widget.setMaximumHeight(300)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)
        
        # 安装事件过滤器
        self.list_widget.installEventFilter(self)
    
    def _apply_theme(self, theme: str):
        """应用主题样式"""
        if theme == "dark":
            self.setStyleSheet(DARK_STYLE)
        else:
            self.setStyleSheet(LIGHT_STYLE)
        self._current_theme = theme
    
    def set_theme(self, theme: str):
        """切换主题"""
        if theme != self._current_theme:
            self._apply_theme(theme)
        
    def show_candidates(self, candidates: list, pos: QPoint = None):
        """
        显示候选词列表
        
        Args:
            candidates: 候选词列表
            pos: 弹窗显示位置（全局坐标）
        """
        self.list_widget.clear()
        
        if not candidates:
            self.hide()
            return
        
        for c in candidates:
            item = QListWidgetItem(c)
            self.list_widget.addItem(item)
        
        # 默认选中第一项
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        
        # 调整大小
        self.list_widget.setFixedWidth(max(200, self.list_widget.sizeHintForColumn(0) + 40))
        height = min(300, self.list_widget.sizeHintForRow(0) * min(10, len(candidates)) + 10)
        self.list_widget.setFixedHeight(height)
        self.adjustSize()
        
        # 显示在指定位置
        if pos:
            self.move(pos)
        
        self.show()
        # 不再让列表获取焦点，让编辑器保持焦点
        # self.list_widget.setFocus()
    
    def move_selection(self, direction: int):
        """
        移动选中项
        
        Args:
            direction: -1 上移, 1 下移
        """
        current_row = self.list_widget.currentRow()
        count = self.list_widget.count()
        
        if count == 0:
            return
        
        new_row = current_row + direction
        if new_row < 0:
            new_row = count - 1
        elif new_row >= count:
            new_row = 0
        
        self.list_widget.setCurrentRow(new_row)
    
    def confirm_selection(self):
        """确认选中当前项"""
        item = self.list_widget.currentItem()
        if item:
            self.candidate_selected.emit(item.text())
        self.hide()
        self.popup_closed.emit()
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """单击确认选择"""
        if item:
            self.candidate_selected.emit(item.text())
            self.hide()
            self.popup_closed.emit()
    
    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击确认"""
        self.candidate_selected.emit(item.text())
        self.hide()
        self.popup_closed.emit()
    
    def eventFilter(self, obj, event):
        """事件过滤器：处理键盘事件"""
        from PyQt5.QtCore import QEvent
        
        if obj == self.list_widget and event.type() == QEvent.KeyPress:
            key = event.key()
            
            if key == Qt.Key_Up:
                self.move_selection(-1)
                return True
            elif key == Qt.Key_Down:
                self.move_selection(1)
                return True
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                self.confirm_selection()
                return True
            elif key == Qt.Key_Escape:
                self.hide()
                self.popup_closed.emit()
                return True
            elif key == Qt.Key_Tab:
                # Tab 也确认选择
                self.confirm_selection()
                return True
        
        return super().eventFilter(obj, event)
    
    def hideEvent(self, event):
        """隐藏时发出信号"""
        super().hideEvent(event)
        self.popup_closed.emit()

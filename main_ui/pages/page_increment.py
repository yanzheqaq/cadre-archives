from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from .base_page import BasePage
from main_ui.config_pages import IncrementConfig

# 导入具体的子页面
from .increment_ui.archive_receive import ArchiveReceiveWidget

class IncrementPage(BasePage):
    def __init__(self):
        # 增量页面需要显示搜索栏，所以保持默认 True
        super().__init__(sub_menus=IncrementConfig.SUB_MENUS, show_search_bar=True)

    def init_content_pages(self):
        """
        重写父类方法，加载真实的业务页面
        顺序必须与 IncrementConfig.SUB_MENUS 中的顺序一致
        """
        # 1. 档案接收 (Index 0)
        self.content_area.addWidget(ArchiveReceiveWidget())
        
        # 2. 前处理 (Index 1)
        self.add_placeholder("前处理功能开发中...")
        
        # 3. 扫描 (Index 2)
        self.add_placeholder("扫描功能开发中...")
        
        # 4. 图像处理 (Index 3)
        self.add_placeholder("图像处理功能开发中...")
        
        # 5. 质检 (Index 4)
        self.add_placeholder("质检功能开发中...")
        
        # 6. 挂接 (Index 5)
        self.add_placeholder("挂接功能开发中...")

    def add_placeholder(self, text):
        """辅助方法：添加占位页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: #9ca3af; font-weight: bold;")
        layout.addWidget(label)
        self.content_area.addWidget(page)

    def update_theme(self, theme_name):
        """
        重写 update_theme 以通知所有子页面
        """
        super().update_theme(theme_name)
        
        # 遍历 content_area 中的所有页面，如果它们实现了 update_theme，则调用
        count = self.content_area.count()
        for i in range(count):
            widget = self.content_area.widget(i)
            if hasattr(widget, 'update_theme'):
                widget.update_theme(theme_name)

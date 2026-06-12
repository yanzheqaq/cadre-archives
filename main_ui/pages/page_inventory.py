from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from .base_page import BasePage
from main_ui.config_pages import InventoryConfig
from .inventory_ui.inventory_receive import InventoryReceiveWidget
from .inventory_ui.inventory_entry import InventoryEntryWidget
from .inventory_ui.inventory_catalog import InventoryCatalogWidget
from .inventory_ui.ai_retouch_widget import AIRetouchWidget


class InventoryPage(BasePage):
    def __init__(self):
        super().__init__(sub_menus=InventoryConfig.SUB_MENUS, show_search_bar=True)

    def init_content_pages(self):
        """重写父类方法：馆藏模块拥有独立的接收界面，其余为占位页"""
        self._entry_widget = None
        self._loaded_pages = {}
        self._page_factories = {
            0: InventoryReceiveWidget,
            1: InventoryEntryWidget,
            2: InventoryCatalogWidget,
            3: AIRetouchWidget,
        }

        placeholders = [
            "机构管理加载中...",
            "信息录入加载中...",
            "目录管理加载中...",
            "AI修图加载中...",
            "装订功能开发中...",
            "验收功能开发中...",
            "归档功能开发中...",
            "批次查询功能开发中...",
            "高级查询功能开发中..."
        ]

        for text in placeholders:
            self.content_area.addWidget(self._make_placeholder(text))

        self._ensure_page_loaded(0)

        self.search_bar_widget.btn_search.clicked.connect(self._on_search_clicked)
        self.search_bar_widget.btn_reset.clicked.connect(self._on_search_reset)

    def _ensure_page_loaded(self, index):
        if index in self._loaded_pages:
            return self._loaded_pages[index]
        factory = self._page_factories.get(index)
        if factory is None:
            return self.content_area.widget(index)
        old_widget = self.content_area.widget(index)
        widget = factory()
        if index == 1:
            self._entry_widget = widget
        self.content_area.removeWidget(old_widget)
        old_widget.deleteLater()
        self.content_area.insertWidget(index, widget)
        self._loaded_pages[index] = widget
        if hasattr(widget, 'update_theme'):
            widget.update_theme(self.current_theme)
        return widget

    def on_sub_nav_click(self):
        btn = self.sender()
        idx = self.nav_group.id(btn)
        self._ensure_page_loaded(idx)
        self.content_area.setCurrentIndex(idx)

    def _on_search_clicked(self):
        if self.content_area.currentIndex() != 1:
            return
        self._ensure_page_loaded(1)
        if self._entry_widget is None:
            return
        name = self.search_bar_widget.name_input.text().strip()
        item = self._entry_widget.org_tree.currentItem()
        self._entry_widget.load_personnel_for_org(item, name_filter=name)

    def _on_search_reset(self):
        if self.content_area.currentIndex() != 1:
            return
        self._ensure_page_loaded(1)
        if self._entry_widget is None:
            return
        item = self._entry_widget.org_tree.currentItem()
        self._entry_widget.load_personnel_for_org(item, name_filter="")

    def _make_placeholder(self, text):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: #9ca3af; font-weight: bold;")
        layout.addWidget(label)
        return page

    def add_placeholder(self, text):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: #9ca3af; font-weight: bold;")
        layout.addWidget(label)
        self.content_area.addWidget(page)

    def update_theme(self, theme_name):
        super().update_theme(theme_name)
        count = self.content_area.count()
        for i in range(count):
            widget = self.content_area.widget(i)
            if hasattr(widget, 'update_theme'):
                widget.update_theme(theme_name)


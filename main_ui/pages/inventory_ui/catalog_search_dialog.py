# -*- coding: utf-8 -*-

from typing import Any, Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .repo.inventory_entry_repo import search_entry_catalog_items, update_entry_catalog_item_by_id
from .styled_message_box import StyledMessageBox


class CatalogSearchItemDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            try:
                editor.setFont(option.font)
                editor.setStyleSheet(
                    "QLineEdit { padding: 0px 4px; border: 1px solid #93c5fd; "
                    "background-color: #ffffff; color: #111827; selection-background-color: #60a5fa; }"
                )
            except Exception:
                pass
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(1, 1, -1, -1))


class CatalogSearchDialog(QDialog):
    FIELD_COLUMNS = {
        "serial": 3,
        "name": 4,
        "year": 5,
        "month": 6,
        "day": 7,
        "pages": 8,
        "remark": 9,
    }

    def __init__(self, initial_keyword: str = "", parent=None, theme: str = "light"):
        super().__init__(parent)
        self.current_theme = theme or "light"
        self._rows: List[Dict[str, Any]] = []
        self.setWindowTitle("目录条目搜索")
        self.resize(1180, 680)
        self._init_ui(initial_keyword)
        self._apply_theme()
        if (initial_keyword or "").strip():
            self._search()

    def _init_ui(self, initial_keyword: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("目录条目搜索")
        title.setObjectName("catalog_search_title")
        layout.addWidget(title)

        search_layout = QHBoxLayout()
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("输入目录名称、编号、日期、页数或备注关键字")
        self.keyword_edit.setText(initial_keyword or "")
        self.keyword_edit.returnPressed.connect(self._search)
        search_layout.addWidget(self.keyword_edit, 1)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._search)
        search_layout.addWidget(self.search_btn)

        self.save_btn = QPushButton("保存当前行")
        self.save_btn.clicked.connect(self._save_current_row)
        search_layout.addWidget(self.save_btn)

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        search_layout.addWidget(self.close_btn)
        layout.addLayout(search_layout)

        self.info_label = QLabel("输入关键字后搜索；双击可编辑目录字段，修改后点击“保存当前行”。")
        self.info_label.setObjectName("catalog_search_info")
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "人员", "所属分类", "目录路径", "编号", "目录名称", "年", "月", "日", "页数", "备注"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setItemDelegate(CatalogSearchItemDelegate(self.table))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

    def _apply_theme(self):
        if self.current_theme == "dark":
            self.setStyleSheet("""
                QDialog { background-color: #111827; color: #d1d5db; }
                QLabel#catalog_search_title { font-size: 16px; font-weight: bold; color: #f3f4f6; }
                QLabel#catalog_search_info { color: #9ca3af; }
                QLineEdit { background-color: #1f2937; color: #f3f4f6; border: 1px solid #4b5563; border-radius: 4px; padding: 6px; }
                QPushButton { background-color: #334d6e; color: white; border: none; border-radius: 4px; padding: 7px 16px; }
                QPushButton:hover { background-color: #4a6a8a; }
                QTableWidget { background-color: #1f2937; color: #d1d5db; gridline-color: #374151; alternate-background-color: #273244; }
                QHeaderView::section { background-color: #111827; color: #d1d5db; padding: 7px; border: none; border-bottom: 1px solid #4b5563; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #ffffff; color: #374151; }
                QLabel#catalog_search_title { font-size: 16px; font-weight: bold; color: #1f2937; }
                QLabel#catalog_search_info { color: #6b7280; }
                QLineEdit { background-color: #ffffff; color: #1f2937; border: 1px solid #d1d5db; border-radius: 4px; padding: 6px; }
                QPushButton { background-color: #3498db; color: white; border: none; border-radius: 4px; padding: 7px 16px; }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget { background-color: #ffffff; color: #374151; gridline-color: #f3f4f6; alternate-background-color: #f9fafb; }
                QHeaderView::section { background-color: #f9fafb; color: #374151; padding: 7px; border: none; border-bottom: 1px solid #d1d5db; }
            """)

    def _search(self):
        keyword = self.keyword_edit.text().strip()
        if not keyword:
            StyledMessageBox.information(self, "提示", "请输入要搜索的目录关键字", self.current_theme)
            return
        try:
            rows = search_entry_catalog_items(keyword=keyword, limit=200)
        except Exception as e:
            StyledMessageBox.warning(self, "搜索失败", str(e), self.current_theme)
            return
        self._rows = rows
        self._fill_table(rows)
        self.info_label.setText(f"共找到 {len(rows)} 条结果。双击可编辑目录字段，修改后点击“保存当前行”。")

    def _fill_table(self, rows: List[Dict[str, Any]]):
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for record in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = [
                    record.get("person_name") or "",
                    record.get("org_path") or "未分类",
                    record.get("catalog_path") or "",
                    record.get("serial") or "",
                    record.get("name") or "",
                    record.get("year") or "",
                    record.get("month") or "",
                    record.get("day") or "",
                    record.get("pages") or "",
                    record.get("remark") or "",
                ]
                for col, value in enumerate(values):
                    editable = col in self.FIELD_COLUMNS.values()
                    if col == self.FIELD_COLUMNS["serial"] and record.get("serial_locked"):
                        editable = False
                    if col == self.FIELD_COLUMNS["name"] and record.get("name_locked"):
                        editable = False
                    item = self._make_item(value, editable=editable)
                    if col == 0:
                        item.setData(Qt.UserRole, dict(record))
                    if col in (1, 2, 9):
                        item.setToolTip(value)
                    if not editable:
                        item.setBackground(self._readonly_brush())
                    self.table.setItem(row, col, item)
        finally:
            self.table.blockSignals(False)

    def _make_item(self, value: Any, editable: bool) -> QTableWidgetItem:
        item = QTableWidgetItem("" if value is None else str(value))
        flags = item.flags()
        if editable:
            item.setFlags(flags | Qt.ItemIsEditable)
        else:
            item.setFlags(flags & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignCenter if item.text().strip() != item.text() or len(item.text()) <= 12 else Qt.AlignLeft | Qt.AlignVCenter)
        return item

    def _readonly_brush(self) -> QBrush:
        if self.current_theme == "dark":
            return QBrush(QColor("#263142"))
        return QBrush(QColor("#f3f4f6"))

    def _save_current_row(self):
        row = self.table.currentRow()
        if row < 0:
            StyledMessageBox.information(self, "提示", "请先选择要保存的结果行", self.current_theme)
            return
        first_item = self.table.item(row, 0)
        record = first_item.data(Qt.UserRole) if first_item else None
        if not record:
            StyledMessageBox.warning(self, "提示", "当前行缺少目录标识，无法保存", self.current_theme)
            return
        fields: Dict[str, Any] = {}
        for field, col in self.FIELD_COLUMNS.items():
            if field == "serial" and record.get("serial_locked"):
                continue
            if field == "name" and record.get("name_locked"):
                continue
            item = self.table.item(row, col)
            fields[field] = item.text() if item else ""
        try:
            updated = update_entry_catalog_item_by_id(
                entry_catalog_item_id=int(record.get("entry_catalog_item_id")),
                fields=fields,
            )
        except Exception as e:
            StyledMessageBox.warning(self, "保存失败", str(e), self.current_theme)
            return
        if updated:
            record.update(updated)
            first_item.setData(Qt.UserRole, dict(record))
            self._update_row_from_record(row, record)
        StyledMessageBox.information(self, "完成", "当前目录条目已保存", self.current_theme)

    def _update_row_from_record(self, row: int, record: Dict[str, Any]):
        self.table.blockSignals(True)
        try:
            for field, col in self.FIELD_COLUMNS.items():
                item = self.table.item(row, col)
                if item is not None:
                    item.setText(record.get(field) or "")
        finally:
            self.table.blockSignals(False)

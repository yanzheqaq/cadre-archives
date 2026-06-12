"""
打印预览对话框
- 所见即所得：预览与导出 XML 完全一致
- 支持在类别之间插入空行
- 支持边距、字体大小、加粗设置
- 支持打印（选择打印机、单双面、横纵向）
- 支持导出为 XML（Excel SpreadsheetML 格式）
- A4 纸张标准尺寸预览
"""
import math
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QCheckBox, QGroupBox, QFormLayout, QGridLayout, QHeaderView, QFileDialog,
    QScrollArea, QWidget, QComboBox, QDoubleSpinBox, QMessageBox, QStyle,
    QSplitter, QFrame, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QSizeF, QRectF
from PyQt5.QtGui import QFont, QTextDocument, QPageLayout, QPageSize, QPainter, QColor, QPen, QFontMetrics, QIcon
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrinterInfo

from common.config import AppConfig, AppSettings
from .styled_message_box import StyledMessageBox


class A4PreviewWidget(QWidget):
    """A4 纸张预览控件 - 支持分页"""
    
    # A4 尺寸 (mm)
    A4_W_MM = 210
    A4_H_MM = 297
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 566)  # A4 比例
        self._data = []
        self._font_family = "楷体_GB2312"
        self._font_size = 13
        self._bold = False
        self._margins = (20, 15, 20, 15)  # left, top, right, bottom (mm)
        self._scale = 1.0
        self._current_page = 0
        self._total_pages = 1
        self._rows_per_page = 30
        self._row_heights = []
        self._page_breaks = []
        self._row_h_mm = 6.0
        self._col_widths_fixed_mm = [10.0, 12.0, 9.0, 9.0, 12.0, 16.0]  # serial,year,month,day,pages,remark
        self._title_font_family = "黑体"
        self._title_font_size = 6.0
        self._header_font_family = "楷体_GB2312"
        self._header_font_size = 3.5
        self._header_bold = True
        self._data_font_family = "楷体_GB2312"
        self._data_font_size = 3.2
        self._data_bold = False
        self._category_font_family = "楷体_GB2312"
        self._category_font_size = 3.2
        self._category_bold = True
        self._table_scale = 1.0
    
    def set_data(self, data: List[dict], font_family: str, font_size: int,
                 bold: bool, margins: tuple, row_h_mm: float = 6.0,
                 col_widths_fixed_mm: list = None,
                 title_font_family: str = None, title_font_size: float = None,
                 header_font_family: str = None, header_font_size: float = None, header_bold: bool = None,
                 data_font_family: str = None, data_font_size: float = None, data_bold: bool = None,
                 category_font_family: str = None, category_font_size: float = None, category_bold: bool = None,
                 table_scale: float = 1.0):
        self._data = data
        self._font_family = font_family
        self._font_size = font_size
        self._bold = bold
        self._margins = margins
        self._row_h_mm = row_h_mm
        if col_widths_fixed_mm is not None:
            self._col_widths_fixed_mm = col_widths_fixed_mm
        if title_font_family    is not None: self._title_font_family    = title_font_family
        if title_font_size      is not None: self._title_font_size      = title_font_size
        if header_font_family   is not None: self._header_font_family   = header_font_family
        if header_font_size     is not None: self._header_font_size     = header_font_size
        if header_bold          is not None: self._header_bold          = header_bold
        if data_font_family     is not None: self._data_font_family     = data_font_family
        if data_font_size       is not None: self._data_font_size       = data_font_size
        if data_bold            is not None: self._data_bold            = data_bold
        if category_font_family is not None: self._category_font_family = category_font_family
        if category_font_size   is not None: self._category_font_size   = category_font_size
        if category_bold        is not None: self._category_bold        = category_bold
        self._table_scale = max(1.0, float(table_scale))
        self._calculate_pages()
        self.update()
    
    @staticmethod
    def _mm_to_pt(mm: float) -> float:
        """Convert millimetres to typographic points (1 pt = 25.4/72 mm ≈ 0.3528 mm)."""
        return float(mm) * (72.0 / 25.4)

    @staticmethod
    def _font_px_from_mm(mm: float) -> float:
        return max(1.0, float(mm))

    @staticmethod
    def _estimate_row_height_mm(name_text, col1_w_mm, base_row_h=6.0, font_size_mm=3.2):
        """Estimate row height in mm.
        
        Uses a fixed character width based on actual font size (not base_row_h),
        then returns max(base_row_h, required_height) so rows only grow when
        the text genuinely does not fit in the user-set row height.
        """
        if not name_text:
            return base_row_h
        # CJK: char width ≈ font_size_mm; line height adds ~20% leading
        char_w = max(0.5, font_size_mm)
        text_line_h = font_size_mm * 1.3
        chars_per_line = max(1, int(col1_w_mm / char_w))
        n_lines = math.ceil(len(name_text) / chars_per_line)
        required_h = n_lines * text_line_h
        return max(base_row_h, required_h)

    @staticmethod
    def _body_text_flags(col_idx: int):
        if col_idx == 1:
            return Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap
        return Qt.AlignCenter

    def _calculate_pages(self):
        """计算总页数（支持变高行）"""
        left, top, right, bottom = self._margins
        content_h = self.A4_H_MM - top - bottom - 12 - (14 * self._table_scale)
        content_w = self.A4_W_MM - left - right
        col1_w = max(10.0, content_w - sum(self._col_widths_fixed_mm))
        base_row_h = self._row_h_mm * self._table_scale

        self._row_heights = [
            self._estimate_row_height_mm(
                str(item.get("name", "")), col1_w, base_row_h,
                (self._category_font_size if item.get("is_template") else self._data_font_size) * self._table_scale
            )
            for item in self._data
        ]

        self._page_breaks = []
        _start, _cum = 0, 0.0
        for _i, _h in enumerate(self._row_heights):
            if _cum + _h > content_h and _i > _start:
                self._page_breaks.append((_start, _i))
                _start, _cum = _i, _h
            else:
                _cum += _h
        self._page_breaks.append((_start, len(self._row_heights)))

        self._total_pages = max(1, len(self._page_breaks))
        self._rows_per_page = max(1, int(content_h / base_row_h))
        if self._current_page >= self._total_pages:
            self._current_page = self._total_pages - 1
    
    def get_total_pages(self) -> int:
        return self._total_pages
    
    def get_current_page(self) -> int:
        return self._current_page
    
    def set_page(self, page: int):
        if 0 <= page < self._total_pages:
            self._current_page = page
            self.update()
    
    def next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self.update()
    
    def prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # 填充白色背景
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        
        # 计算缩放比例使 A4 适应控件
        w_ratio = self.width() / self.A4_W_MM
        h_ratio = self.height() / self.A4_H_MM
        self._scale = min(w_ratio, h_ratio) * 0.95
        
        # 居中偏移
        page_w = self.A4_W_MM * self._scale
        page_h = self.A4_H_MM * self._scale
        offset_x = (self.width() - page_w) / 2
        offset_y = (self.height() - page_h) / 2
        
        painter.translate(offset_x, offset_y)
        painter.scale(self._scale, self._scale)
        
        # 绘制页面背景（白色）
        painter.fillRect(QRectF(0, 0, self.A4_W_MM, self.A4_H_MM), QColor(255, 255, 255))
        
        # 绘制页面边框（浅灰色阴影效果）
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(QRectF(0, 0, self.A4_W_MM, self.A4_H_MM))
        
        # 内容区域
        left, top, right, bottom = self._margins
        content_x = left
        content_y = top
        content_w = self.A4_W_MM - left - right
        
        # 绘制标题
        title_font = QFont(self._title_font_family)
        title_font.setPixelSize(int(round(self._font_px_from_mm(self._title_font_size))))
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(Qt.black)
        
        title_rect = QRectF(content_x, content_y, content_w, 10)
        painter.drawText(title_rect, Qt.AlignCenter, "干部人事档案目录")
        
        # 表格起始位置
        table_y = content_y + 12
        
        # 列宽定义 (mm) - 与XML模板一致的比例
        col1_w = max(10.0, content_w - sum(self._col_widths_fixed_mm))
        col_widths = [self._col_widths_fixed_mm[0], col1_w, self._col_widths_fixed_mm[1], self._col_widths_fixed_mm[2], self._col_widths_fixed_mm[3], self._col_widths_fixed_mm[4], self._col_widths_fixed_mm[5]]
        row_height = self._row_h_mm * self._table_scale
        header_height = 7 * self._table_scale

        # 获取当前页数据（使用变高分页）
        if self._page_breaks and self._current_page < len(self._page_breaks):
            _s, _e = self._page_breaks[self._current_page]
            page_data = self._data[_s:_e]
            page_row_heights = self._row_heights[_s:_e]
        else:
            start_idx = self._current_page * self._rows_per_page
            end_idx = min(start_idx + self._rows_per_page, len(self._data))
            page_data = self._data[start_idx:end_idx]
            page_row_heights = [row_height] * len(page_data)

        # 绘制表格
        self._draw_table(painter, content_x, table_y, col_widths, page_row_heights, header_height, page_data)
        
        painter.end()
    
    def _draw_table(self, painter, x, y, col_widths, row_heights, header_h, page_data):
        """绘制表格（支持变高行和换行显示）"""
        # 表头字体
        header_font = QFont(self._header_font_family)
        header_font.setPixelSize(int(round(self._font_px_from_mm(self._header_font_size * self._table_scale))))
        header_font.setBold(self._header_bold)

        # 类别行字体
        category_font = QFont(self._category_font_family)
        category_font.setPixelSize(int(round(self._font_px_from_mm(self._category_font_size * self._table_scale))))
        category_font.setBold(self._category_bold)
        # 普通数据行字体
        data_font_normal = QFont(self._data_font_family)
        data_font_normal.setPixelSize(int(round(self._font_px_from_mm(self._data_font_size * self._table_scale))))
        data_font_normal.setBold(self._data_bold)
        
        # 表头第一行
        curr_y = y
        painter.setFont(header_font)
        painter.setPen(QPen(Qt.black, 0.3))
        
        # 序号（跨两行）
        curr_x = x
        rect = QRectF(curr_x, curr_y, col_widths[0], header_h * 2)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignCenter, "序号")
        curr_x += col_widths[0]
        
        # 材料名称（跨两行）
        rect = QRectF(curr_x, curr_y, col_widths[1], header_h * 2)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignCenter, "材料名称")
        curr_x += col_widths[1]
        
        # 材料形成时间（跨3列）
        date_width = col_widths[2] + col_widths[3] + col_widths[4]
        rect = QRectF(curr_x, curr_y, date_width, header_h)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignCenter, "材料形成时间")
        
        # 页数（跨两行）
        pages_x = curr_x + date_width
        rect = QRectF(pages_x, curr_y, col_widths[5], header_h * 2)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignCenter, "页数")
        
        # 备注（跨两行）
        remark_x = pages_x + col_widths[5]
        rect = QRectF(remark_x, curr_y, col_widths[6], header_h * 2)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignCenter, "备注")
        
        # 表头第二行（年月日）
        curr_y += header_h
        date_labels = ["年", "月", "日"]
        date_x = x + col_widths[0] + col_widths[1]
        for i, label in enumerate(date_labels):
            rect = QRectF(date_x, curr_y, col_widths[2 + i], header_h)
            painter.drawRect(rect)
            painter.drawText(rect, Qt.AlignCenter, label)
            date_x += col_widths[2 + i]
        
        # 数据行
        curr_y += header_h

        for item, row_h in zip(page_data, row_heights):
            # 根据is_template决定是否加粗
            is_template = item.get("is_template", False)
            if is_template:
                painter.setFont(category_font)
            else:
                painter.setFont(data_font_normal)

            values = [
                str(item.get("serial", "")),
                str(item.get("name", "")),
                str(item.get("year", "")),
                str(item.get("month", "")),
                str(item.get("day", "")),
                str(item.get("pages", "")),
                str(item.get("remark", ""))
            ]

            curr_x = x
            for i, (val, w) in enumerate(zip(values, col_widths)):
                rect = QRectF(curr_x, curr_y, w, row_h)
                painter.drawRect(rect)
                if i == 1:
                    pad = max(0.5, 0.8 * self._table_scale)
                    text_rect = rect.adjusted(pad, 0.5, -pad, -0.5)
                else:
                    text_rect = rect.adjusted(0.5, 0, -0.5, 0)
                painter.drawText(text_rect, self._body_text_flags(i), val)
                curr_x += w

            curr_y += row_h


class CustomPrintDialog(QDialog):
    """自定义打印对话框 - 与主界面样式一致"""
    
    LIGHT_STYLE = """
        QDialog {
            background-color: #ffffff;
            border: 1px solid #dcecf5;
            border-radius: 8px;
        }
        QLabel {
            color: #1e2732;
            font-size: 13px;
        }
        QLabel#title_label {
            color: #1e2732;
            font-size: 14px;
            font-weight: bold;
        }
        QComboBox {
            background-color: #f0f4f8;
            border: 1px solid #dcecf5;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 13px;
            color: #1e2732;
            min-width: 200px;
        }
        QComboBox:hover {
            border: 1px solid #3498db;
        }
        QComboBox:focus {
            border: 2px solid #3498db;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QRadioButton {
            color: #1e2732;
            font-size: 13px;
            spacing: 8px;
        }
        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #dcecf5;
            border-radius: 8px;
            background-color: #ffffff;
        }
        QRadioButton::indicator:hover {
            border: 2px solid #3498db;
        }
        QRadioButton::indicator:checked {
            border: 2px solid #3498db;
            background-color: #3498db;
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
    
    DARK_STYLE = """
        QDialog {
            background-color: #2d2d2d;
            border: 1px solid #4d4d4d;
            border-radius: 8px;
        }
        QLabel {
            color: #e0e0e0;
            font-size: 13px;
        }
        QLabel#title_label {
            color: #e0e0e0;
            font-size: 14px;
            font-weight: bold;
        }
        QComboBox {
            background-color: #4a4a4a;
            border: 1px solid #5a5a5a;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 13px;
            color: #e0e0e0;
            min-width: 200px;
        }
        QComboBox:hover {
            border: 1px solid #4a90d9;
        }
        QComboBox:focus {
            border: 2px solid #4a90d9;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QRadioButton {
            color: #e0e0e0;
            font-size: 13px;
            spacing: 8px;
        }
        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #5a5a5a;
            border-radius: 8px;
            background-color: #4a4a4a;
        }
        QRadioButton::indicator:hover {
            border: 2px solid #4a90d9;
        }
        QRadioButton::indicator:checked {
            border: 2px solid #4a90d9;
            background-color: #4a90d9;
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
    
    def __init__(self, parent=None, theme="light", total_pages: int = 1, current_page: int = 1):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self._theme = theme
        self._result = False
        self._printer = None
        self._is_duplex = False
        self._total_pages = max(1, int(total_pages))
        self._current_page = max(1, min(int(current_page), self._total_pages))
        # (start, end) 1-indexed inclusive; None 表示全部
        self._page_range = None
        self._apply_theme(theme)
        self._init_ui()
    
    def _apply_theme(self, theme):
        if theme == "dark":
            self.setStyleSheet(self.DARK_STYLE)
        else:
            self.setStyleSheet(self.LIGHT_STYLE)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        
        # 标题
        title_label = QLabel("打印设置")
        title_label.setObjectName("title_label")
        layout.addWidget(title_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #dcecf5;" if self._theme == "light" else "background-color: #4d4d4d;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
        # 打印机选择
        printer_layout = QHBoxLayout()
        printer_layout.setSpacing(12)
        printer_label = QLabel("打印机:")
        printer_label.setFixedWidth(80)
        printer_layout.addWidget(printer_label)
        
        self.printer_combo = QComboBox()
        self._load_printers()
        printer_layout.addWidget(self.printer_combo, 1)
        layout.addLayout(printer_layout)
        
        # 单双面打印
        duplex_layout = QHBoxLayout()
        duplex_layout.setSpacing(12)
        duplex_label = QLabel("打印方式:")
        duplex_label.setFixedWidth(80)
        duplex_layout.addWidget(duplex_label)
        
        self.duplex_group = QButtonGroup(self)
        self.single_radio = QRadioButton("单面打印")
        self.single_radio.setChecked(True)
        self.duplex_radio = QRadioButton("双面打印")
        self.duplex_group.addButton(self.single_radio, 0)
        self.duplex_group.addButton(self.duplex_radio, 1)
        duplex_layout.addWidget(self.single_radio)
        duplex_layout.addWidget(self.duplex_radio)
        duplex_layout.addStretch()
        layout.addLayout(duplex_layout)

        # 页面范围
        range_row1 = QHBoxLayout()
        range_row1.setSpacing(12)
        range_label = QLabel("页面范围:")
        range_label.setFixedWidth(80)
        range_row1.addWidget(range_label)

        self.range_group = QButtonGroup(self)
        self.range_all_radio     = QRadioButton(f"全部 (共 {self._total_pages} 页)")
        self.range_current_radio = QRadioButton(f"当前页 (第 {self._current_page} 页)")
        self.range_custom_radio  = QRadioButton("指定范围:")
        self.range_all_radio.setChecked(True)
        self.range_group.addButton(self.range_all_radio,     0)
        self.range_group.addButton(self.range_current_radio, 1)
        self.range_group.addButton(self.range_custom_radio,  2)
        range_row1.addWidget(self.range_all_radio)
        range_row1.addWidget(self.range_current_radio)
        range_row1.addStretch()
        layout.addLayout(range_row1)

        range_row2 = QHBoxLayout()
        range_row2.setSpacing(6)
        range_row2.addSpacing(80 + 12)  # 缩进对齐前面的标签
        range_row2.addWidget(self.range_custom_radio)
        range_row2.addSpacing(6)

        self.range_from_spin = QSpinBox()
        self.range_from_spin.setRange(1, self._total_pages)
        self.range_from_spin.setValue(1)
        self.range_from_spin.setFixedWidth(70)
        self.range_from_spin.setEnabled(False)
        range_row2.addWidget(QLabel("从"))
        range_row2.addWidget(self.range_from_spin)

        self.range_to_spin = QSpinBox()
        self.range_to_spin.setRange(1, self._total_pages)
        self.range_to_spin.setValue(self._total_pages)
        self.range_to_spin.setFixedWidth(70)
        self.range_to_spin.setEnabled(False)
        range_row2.addWidget(QLabel("到"))
        range_row2.addWidget(self.range_to_spin)
        range_row2.addWidget(QLabel("页"))
        range_row2.addStretch()
        layout.addLayout(range_row2)

        # 指定范围选中时才允许编辑从/到
        self.range_custom_radio.toggled.connect(self.range_from_spin.setEnabled)
        self.range_custom_radio.toggled.connect(self.range_to_spin.setEnabled)

        layout.addSpacing(8)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancel_btn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        print_btn = QPushButton("打印")
        print_btn.clicked.connect(self._on_print_clicked)
        btn_layout.addWidget(print_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_printers(self):
        """加载可用打印机"""
        printers = QPrinterInfo.availablePrinters()
        for printer_info in printers:
            self.printer_combo.addItem(printer_info.printerName(), printer_info)
        if self.printer_combo.count() == 0:
            self.printer_combo.addItem("无可用打印机", None)
    
    def _on_print_clicked(self):
        """确认打印"""
        if self.printer_combo.count() == 0 or self.printer_combo.currentData() is None:
            StyledMessageBox.warning(self, "提示", "没有可用的打印机", self._theme)
            return

        # 解析页面范围
        if self.range_all_radio.isChecked():
            self._page_range = None  # 全部
        elif self.range_current_radio.isChecked():
            self._page_range = (self._current_page, self._current_page)
        else:
            s = self.range_from_spin.value()
            e = self.range_to_spin.value()
            if s > e:
                StyledMessageBox.warning(self, "提示", "页面范围起始不能大于结束", self._theme)
                return
            self._page_range = (s, e)

        # 创建打印机对象
        printer_info = self.printer_combo.currentData()
        if printer_info:
            self._printer = QPrinter(printer_info, QPrinter.HighResolution)
        else:
            self._printer = QPrinter(QPrinter.HighResolution)
        
        # 设置单双面
        self._is_duplex = self.duplex_radio.isChecked()
        if self._is_duplex:
            self._printer.setDuplex(QPrinter.DuplexAuto)
        else:
            self._printer.setDuplex(QPrinter.DuplexNone)
        
        self._result = True
        self.accept()
    
    def get_printer(self):
        """获取打印机对象"""
        return self._printer
    
    def is_duplex(self):
        """是否双面打印"""
        return self._is_duplex

    def get_page_range(self):
        """返回 (start, end) 1-indexed inclusive；None 表示全部页。"""
        return self._page_range


def _set_combo(combo: QComboBox, text: str):
    """辅助：按文本设置 QComboBox 当前项，找不到则不变"""
    idx = combo.findText(text)
    if idx >= 0:
        combo.setCurrentIndex(idx)


class PrintPreviewDialog(QDialog):
    """打印预览对话框"""
    
    LIGHT_STYLE = """
        QDialog { background-color: #F5F5F5; }
        QGroupBox { font-weight: bold; border: 1px solid #D0D0D0; border-radius: 6px;
            margin-top: 12px; padding-top: 10px; background-color: #FFFFFF; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #333; }
        QLabel { color: #333333; }
        QSpinBox, QDoubleSpinBox, QComboBox { background-color: #FFFFFF; border: 1px solid #D0D0D0;
            border-radius: 4px; padding: 4px 8px; min-width: 100px; min-height: 24px; color: #333; }
        QPushButton { background-color: #4A90D9; color: white; border: none; border-radius: 4px;
            padding: 8px 16px; font-weight: bold; min-width: 80px; }
        QPushButton:hover { background-color: #3A7BC8; }
        QPushButton#cancelBtn { background-color: #E0E0E0; color: #333; }
        QScrollArea { border: 1px solid #D0D0D0; background-color: #E8E8E8; }
    """
    
    DARK_STYLE = """
        QDialog { background-color: #2D2D2D; }
        QGroupBox { font-weight: bold; border: 1px solid #4A4A4A; border-radius: 6px;
            margin-top: 12px; padding-top: 10px; background-color: #3A3A3A; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #E0E0E0; }
        QLabel { color: #E0E0E0; }
        QSpinBox, QDoubleSpinBox, QComboBox { background-color: #4A4A4A; border: 1px solid #5A5A5A;
            border-radius: 4px; padding: 4px 8px; min-width: 100px; min-height: 24px; color: #E0E0E0; }
        QPushButton { background-color: #4A90D9; color: white; border: none; border-radius: 4px;
            padding: 8px 16px; font-weight: bold; min-width: 80px; }
        QPushButton:hover { background-color: #3A7BC8; }
        QPushButton#cancelBtn { background-color: #4A4A4A; color: #E0E0E0; }
        QScrollArea { border: 1px solid #4A4A4A; background-color: #C0C0C0; }
    """
    
    def __init__(self, catalog_data: List[dict], person_name: str = "", parent=None, theme: str = "light"):
        super().__init__(parent)
        self.catalog_data = catalog_data
        self.person_name = person_name
        self.current_theme = theme
        
        # 找出每个模板类别下用户录入的最后一行索引
        self._last_entry_indices = self._find_last_entry_indices()
        # 空行数（统一设置，在每个模板类别的最后一行后插入）
        self._blank_rows_count = 1  # 默认值改为1
        
        self._init_ui()
        self._apply_theme()
        self._load_print_settings()
    
    def _find_last_entry_indices(self) -> List[int]:
        """找出每个模板类别下用户录入的最后一行的索引
        
        空行将在这些位置后插入
        """
        indices = []
        # 匹配 数字-数字 格式（如 9-1, 4-2）
        sub_pattern = re.compile(r'^\d+-\d+$')
        # 匹配中文数字一级类别
        cn_pattern = re.compile(r'^[一二三四五六七八九十]+$')
        
        i = 0
        while i < len(self.catalog_data):
            item = self.catalog_data[i]
            serial = str(item.get("serial", "")).strip()
            is_template = item.get("is_template", False)
            
            # 找到模板类别项（最小层级）
            is_min_level_template = False
            if is_template:
                if sub_pattern.match(serial):
                    is_min_level_template = True
                elif cn_pattern.match(serial):
                    # 检查该一级类别下是否有子级（数字-数字格式）
                    has_subcat = False
                    for j in range(i + 1, len(self.catalog_data)):
                        next_serial = str(self.catalog_data[j].get("serial", "")).strip()
                        next_is_template = self.catalog_data[j].get("is_template", False)
                        # 遇到下一个一级类别则停止搜索
                        if next_is_template and cn_pattern.match(next_serial):
                            break
                        # 发现子级分类
                        if next_is_template and sub_pattern.match(next_serial):
                            has_subcat = True
                            break
                    # 无论内层循环是否执行，只要没有子级就是最小层级
                    if not has_subcat:
                        is_min_level_template = True
            
            if is_min_level_template:
                # 找这个模板类别下用户录入的最后一行
                last_entry_idx = i  # 至少是类别本身
                for j in range(i + 1, len(self.catalog_data)):
                    next_item = self.catalog_data[j]
                    next_serial = str(next_item.get("serial", "")).strip()
                    next_is_template = next_item.get("is_template", False)
                    # 如果遇到下一个模板项，停止
                    if next_is_template:
                        break
                    if next_item.get("is_blank"):
                        continue
                    # 用户录入的行（非模板项）
                    last_entry_idx = j
                indices.append(last_entry_idx)
            i += 1
        return indices
    
    def _init_ui(self):
        self.setWindowTitle("打印预览")
        # 设置打印机图标
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        # 窗口最大化显示
        self.setWindowState(Qt.WindowMaximized)
        self.setMinimumSize(950, 700)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # 使用 QSplitter 实现可拖拽调整大小
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)  # 防止完全折叠
        splitter.setHandleWidth(8)  # 设置拖拽手柄宽度
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #C0C0C0;
                border: 1px solid #A0A0A0;
                border-radius: 2px;
                margin: 2px 0px;
            }
            QSplitter::handle:hover {
                background-color: #4A90D9;
            }
            QSplitter::handle:pressed {
                background-color: #3A7BC8;
            }
        """)
        
        # 左侧预览区域
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        
        # 预览滚动区域
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        
        self.preview_widget = A4PreviewWidget()
        self.preview_scroll.setWidget(self.preview_widget)
        preview_layout.addWidget(self.preview_scroll, 1)
        
        # 分页控制栏
        page_control = QHBoxLayout()
        page_control.setSpacing(10)
        
        self.prev_page_btn = QPushButton("◀ 上一页")
        self.prev_page_btn.setFixedWidth(100)
        self.prev_page_btn.clicked.connect(self._on_prev_page)
        page_control.addStretch()
        page_control.addWidget(self.prev_page_btn)
        
        self.page_label = QLabel("第 1 页 / 共 1 页")
        self.page_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        page_control.addWidget(self.page_label)
        
        self.next_page_btn = QPushButton("下一页 ▶")
        self.next_page_btn.setFixedWidth(100)
        self.next_page_btn.clicked.connect(self._on_next_page)
        page_control.addWidget(self.next_page_btn)
        page_control.addStretch()
        
        preview_layout.addLayout(page_control)
        
        # 左侧面板设置最小宽度，确保可以双向拖拽
        preview_panel.setMinimumWidth(400)
        splitter.addWidget(preview_panel)
        
        # 右侧操作面板
        right_panel = QWidget()
        right_panel.setMinimumWidth(320)  # 确保分辨率写无论如何 "行列设置" 里的 spinbox 都有足够空间显示数值+" mm"
        right_panel.setMaximumWidth(520)  # 最大宽度，允许拖拽扩大
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(0, 0, 6, 0)
        settings_layout.setSpacing(8)
        settings_scroll.setWidget(settings_container)
        
        # 页面设置
        page_group = QGroupBox("页面设置")
        page_form = QFormLayout(page_group)
        
        self.margin_top = QDoubleSpinBox()
        self.margin_top.setRange(5, 50)
        self.margin_top.setValue(12)
        self.margin_top.setSuffix(" mm")
        self.margin_top.valueChanged.connect(self._refresh_preview)
        page_form.addRow("上边距:", self.margin_top)
        
        self.margin_bottom = QDoubleSpinBox()
        self.margin_bottom.setRange(5, 50)
        self.margin_bottom.setValue(12)
        self.margin_bottom.setSuffix(" mm")
        self.margin_bottom.valueChanged.connect(self._refresh_preview)
        page_form.addRow("下边距:", self.margin_bottom)
        
        self.margin_left = QDoubleSpinBox()
        self.margin_left.setRange(5, 50)
        self.margin_left.setValue(10)
        self.margin_left.setSuffix(" mm")
        self.margin_left.valueChanged.connect(self._refresh_preview)
        page_form.addRow("左边距:", self.margin_left)
        
        self.margin_right = QDoubleSpinBox()
        self.margin_right.setRange(5, 50)
        self.margin_right.setValue(10)
        self.margin_right.setSuffix(" mm")
        self.margin_right.valueChanged.connect(self._refresh_preview)
        page_form.addRow("右边距:", self.margin_right)
        
        settings_layout.addWidget(page_group)
        
        # 字体设置（题名 / 标题 / 内容 分别设置）
        font_group = QGroupBox("字体设置")
        fg_layout = QVBoxLayout(font_group)
        fg_layout.setSpacing(6)
        font_grid = QGridLayout()
        font_grid.setSpacing(4)
        _FONTS = ["楷体_GB2312", "楷体", "仿宋", "宋体", "黑体", "微软雅黑"]

        # 列标题行
        for col, text in enumerate(["区域", "字体", "大小(mm)", "粗体"]):
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 11px; color: #888;")
            font_grid.addWidget(lbl, 0, col)

        # 题名
        font_grid.addWidget(QLabel("题名:"), 1, 0)
        self.title_font_fam = QComboBox(); self.title_font_fam.addItems(_FONTS)
        self.title_font_fam.setCurrentText("黑体")
        self.title_font_fam.currentTextChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.title_font_fam, 1, 1)
        self.title_font_sz = QDoubleSpinBox(); self.title_font_sz.setRange(2.0, 20.0)
        self.title_font_sz.setValue(6.0); self.title_font_sz.setSuffix(" mm"); self.title_font_sz.setSingleStep(0.5)
        self.title_font_sz.valueChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.title_font_sz, 1, 2)

        # 标题
        font_grid.addWidget(QLabel("标题:"), 2, 0)
        self.header_font_fam = QComboBox(); self.header_font_fam.addItems(_FONTS)
        self.header_font_fam.currentTextChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.header_font_fam, 2, 1)
        self.header_font_sz = QDoubleSpinBox(); self.header_font_sz.setRange(1.0, 15.0)
        self.header_font_sz.setValue(3.5); self.header_font_sz.setSuffix(" mm"); self.header_font_sz.setSingleStep(0.5)
        self.header_font_sz.valueChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.header_font_sz, 2, 2)
        self.header_bold_chk = QCheckBox(); self.header_bold_chk.setChecked(True)
        self.header_bold_chk.stateChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.header_bold_chk, 2, 3)

        # 内容
        font_grid.addWidget(QLabel("内容:"), 3, 0)
        self.data_font_fam = QComboBox(); self.data_font_fam.addItems(_FONTS)
        self.data_font_fam.currentTextChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.data_font_fam, 3, 1)
        self.data_font_sz = QDoubleSpinBox(); self.data_font_sz.setRange(1.0, 15.0)
        self.data_font_sz.setValue(3.2); self.data_font_sz.setSuffix(" mm"); self.data_font_sz.setSingleStep(0.5)
        self.data_font_sz.valueChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.data_font_sz, 3, 2)
        self.data_bold_chk = QCheckBox(); self.data_bold_chk.setChecked(False)
        self.data_bold_chk.stateChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.data_bold_chk, 3, 3)

        # 类别
        font_grid.addWidget(QLabel("类别:"), 4, 0)
        self.cat_font_fam = QComboBox(); self.cat_font_fam.addItems(_FONTS)
        self.cat_font_fam.currentTextChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.cat_font_fam, 4, 1)
        self.cat_font_sz = QDoubleSpinBox(); self.cat_font_sz.setRange(1.0, 15.0)
        self.cat_font_sz.setValue(3.2); self.cat_font_sz.setSuffix(" mm"); self.cat_font_sz.setSingleStep(0.5)
        self.cat_font_sz.valueChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.cat_font_sz, 4, 2)
        self.cat_bold_chk = QCheckBox(); self.cat_bold_chk.setChecked(True)
        self.cat_bold_chk.stateChanged.connect(self._refresh_preview)
        font_grid.addWidget(self.cat_bold_chk, 4, 3)

        font_grid.setColumnStretch(1, 1)
        fg_layout.addLayout(font_grid)
        settings_layout.addWidget(font_group)
        
        # 类别间空行（在模板最小层级类别后统一插入）
        blank_group = QGroupBox("类别间插入空行")
        blank_layout = QVBoxLayout(blank_group)
        blank_layout.setSpacing(8)
        
        # 说明标签
        desc_label = QLabel("在模板类别（如9-1、七等）\n后插入指定数量的空行")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 11px;")
        blank_layout.addWidget(desc_label)
        
        # 统一空行数输入
        row = QHBoxLayout()
        lbl = QLabel("空行数:")
        lbl.setFixedWidth(60)
        self.blank_spin = QSpinBox()
        self.blank_spin.setRange(0, 20)
        self.blank_spin.setValue(1)
        self.blank_spin.setFixedWidth(80)
        self.blank_spin.valueChanged.connect(self._on_blank_changed)
        row.addWidget(lbl)
        row.addWidget(self.blank_spin)
        row.addStretch()
        blank_layout.addLayout(row)
        
        # 显示将插入空行的类别数量
        cat_count = len(self._last_entry_indices)
        cat_info = QLabel(f"共 {cat_count} 个类别位置")
        cat_info.setStyleSheet("color: #888; font-size: 10px;")
        blank_layout.addWidget(cat_info)
        
        settings_layout.addWidget(blank_group)

        # 行列设置
        layout_group = QGroupBox("行列设置")
        layout_form = QFormLayout(layout_group)

        self.row_height_spin = QDoubleSpinBox()
        self.row_height_spin.setRange(4.0, 20.0)
        self.row_height_spin.setValue(6.0)
        self.row_height_spin.setSuffix(" mm")
        self.row_height_spin.setSingleStep(0.5)
        self.row_height_spin.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("行高:", self.row_height_spin)

        self.table_scale_spin = QSpinBox()
        self.table_scale_spin.setRange(100, 160)
        self.table_scale_spin.setValue(100)
        self.table_scale_spin.setSuffix(" %")
        self.table_scale_spin.setSingleStep(5)
        self.table_scale_spin.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("整体放大:", self.table_scale_spin)

        self.col_serial = QDoubleSpinBox()
        self.col_serial.setRange(5.0, 40.0)
        self.col_serial.setValue(10.0)
        self.col_serial.setSuffix(" mm")
        self.col_serial.setSingleStep(1.0)
        self.col_serial.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("序号列宽:", self.col_serial)

        self.col_year = QDoubleSpinBox()
        self.col_year.setRange(5.0, 30.0)
        self.col_year.setValue(12.0)
        self.col_year.setSuffix(" mm")
        self.col_year.setSingleStep(1.0)
        self.col_year.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("年列宽:", self.col_year)

        self.col_month = QDoubleSpinBox()
        self.col_month.setRange(5.0, 30.0)
        self.col_month.setValue(9.0)
        self.col_month.setSuffix(" mm")
        self.col_month.setSingleStep(1.0)
        self.col_month.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("月列宽:", self.col_month)

        self.col_day = QDoubleSpinBox()
        self.col_day.setRange(5.0, 30.0)
        self.col_day.setValue(9.0)
        self.col_day.setSuffix(" mm")
        self.col_day.setSingleStep(1.0)
        self.col_day.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("日列宽:", self.col_day)

        self.col_pages = QDoubleSpinBox()
        self.col_pages.setRange(5.0, 30.0)
        self.col_pages.setValue(12.0)
        self.col_pages.setSuffix(" mm")
        self.col_pages.setSingleStep(1.0)
        self.col_pages.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("页数列宽:", self.col_pages)

        self.col_remark = QDoubleSpinBox()
        self.col_remark.setRange(5.0, 60.0)
        self.col_remark.setValue(16.0)
        self.col_remark.setSuffix(" mm")
        self.col_remark.setSingleStep(1.0)
        self.col_remark.valueChanged.connect(self._refresh_preview)
        layout_form.addRow("备注列宽:", self.col_remark)

        settings_layout.addWidget(layout_group)

        # 统计
        info_group = QGroupBox("统计")
        info_form = QFormLayout(info_group)
        self.total_rows_label = QLabel(str(len(self.catalog_data)))
        info_form.addRow("数据行:", self.total_rows_label)
        self.blank_rows_label = QLabel("0")
        info_form.addRow("空行数:", self.blank_rows_label)
        self.final_rows_label = QLabel(str(len(self.catalog_data)))
        info_form.addRow("总行数:", self.final_rows_label)
        settings_layout.addWidget(info_group)
        
        settings_layout.addStretch()
        right_layout.addWidget(settings_scroll, 1)
        
        # 按钮
        self.print_btn = QPushButton("打印")
        self.print_btn.clicked.connect(self._on_print)
        right_layout.addWidget(self.print_btn)
        
        self.export_btn = QPushButton("导出 XML")
        self.export_btn.clicked.connect(self._on_export_xml)
        right_layout.addWidget(self.export_btn)
        
        self.cancel_btn = QPushButton("关闭")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.close)
        right_layout.addWidget(self.cancel_btn)
        
        splitter.addWidget(right_panel)
        
        # 设置初始比例（左侧占大部分）
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 340])
        
        main_layout.addWidget(splitter)
    
    def _apply_theme(self):
        self.setStyleSheet(self.DARK_STYLE if self.current_theme == "dark" else self.LIGHT_STYLE)
    
    def _load_print_settings(self):
        """从持久化存储加载打印设置并刷新预览"""
        s = AppSettings().get_print_settings()
        _widgets = [
            self.blank_spin,
            self.margin_top, self.margin_bottom, self.margin_left, self.margin_right,
            self.row_height_spin, self.table_scale_spin, self.col_serial, self.col_year, self.col_month,
            self.col_day, self.col_pages, self.col_remark,
            self.title_font_fam, self.title_font_sz,
            self.header_font_fam, self.header_font_sz, self.header_bold_chk,
            self.data_font_fam, self.data_font_sz, self.data_bold_chk,
            self.cat_font_fam, self.cat_font_sz, self.cat_bold_chk,
        ]
        for w in _widgets:
            w.blockSignals(True)
        self.blank_spin.setValue(s["blank_rows"])
        self._blank_rows_count = s["blank_rows"]
        self.margin_top.setValue(s["margin_top"])
        self.margin_bottom.setValue(s["margin_bottom"])
        self.margin_left.setValue(s["margin_left"])
        self.margin_right.setValue(s["margin_right"])
        self.row_height_spin.setValue(s["row_height"])
        self.table_scale_spin.setValue(s["table_scale"])
        self.col_serial.setValue(s["col_serial"])
        self.col_year.setValue(s["col_year"])
        self.col_month.setValue(s["col_month"])
        self.col_day.setValue(s["col_day"])
        self.col_pages.setValue(s["col_pages"])
        self.col_remark.setValue(s["col_remark"])
        _set_combo(self.title_font_fam,  s["title_font_family"])
        self.title_font_sz.setValue(s["title_font_size"])
        _set_combo(self.header_font_fam, s["header_font_family"])
        self.header_font_sz.setValue(s["header_font_size"])
        self.header_bold_chk.setChecked(s["header_bold"])
        _set_combo(self.data_font_fam,   s["data_font_family"])
        self.data_font_sz.setValue(s["data_font_size"])
        self.data_bold_chk.setChecked(s["data_bold"])
        _set_combo(self.cat_font_fam,    s["category_font_family"])
        self.cat_font_sz.setValue(s["category_font_size"])
        self.cat_bold_chk.setChecked(s["category_bold"])
        for w in _widgets:
            w.blockSignals(False)
        self._refresh_preview()

    def _save_print_settings(self):
        """保存当前打印设置到持久化存储"""
        AppSettings().set_print_settings({
            "blank_rows":         self.blank_spin.value(),
            "margin_top":         self.margin_top.value(),
            "margin_bottom":      self.margin_bottom.value(),
            "margin_left":        self.margin_left.value(),
            "margin_right":       self.margin_right.value(),
            "row_height":         self.row_height_spin.value(),
            "table_scale":        self.table_scale_spin.value(),
            "col_serial":         self.col_serial.value(),
            "col_year":           self.col_year.value(),
            "col_month":          self.col_month.value(),
            "col_day":            self.col_day.value(),
            "col_pages":          self.col_pages.value(),
            "col_remark":         self.col_remark.value(),
            "title_font_family":  self.title_font_fam.currentText(),
            "title_font_size":    self.title_font_sz.value(),
            "header_font_family": self.header_font_fam.currentText(),
            "header_font_size":   self.header_font_sz.value(),
            "header_bold":        self.header_bold_chk.isChecked(),
            "data_font_family":     self.data_font_fam.currentText(),
            "data_font_size":       self.data_font_sz.value(),
            "data_bold":            self.data_bold_chk.isChecked(),
            "category_font_family": self.cat_font_fam.currentText(),
            "category_font_size":   self.cat_font_sz.value(),
            "category_bold":        self.cat_bold_chk.isChecked(),
        })

    def closeEvent(self, event):
        self._save_print_settings()
        super().closeEvent(event)

    def _on_blank_changed(self, value: int):
        self._blank_rows_count = value
        self._refresh_preview()

    def _table_scale_factor(self) -> float:
        return self.table_scale_spin.value() / 100.0
    
    def _get_print_data(self) -> List[dict]:
        """获取带空行的打印数据"""
        result = []
        for i, item in enumerate(self.catalog_data):
            result.append(item)
            # 在模板类别下用户录入的最后一行后插入空行
            if i in self._last_entry_indices and self._blank_rows_count > 0:
                for _ in range(self._blank_rows_count):
                    result.append({"serial": "", "name": "", "year": "", "month": "",
                                   "day": "", "pages": "", "remark": "", "is_blank": True})
        return result
    
    def _refresh_preview(self):
        # 刷新最后一行索引（数据可能变化）
        self._last_entry_indices = self._find_last_entry_indices()
        print_data = self._get_print_data()
        total_blank = self._blank_rows_count * len(self._last_entry_indices)
        self.blank_rows_label.setText(str(total_blank))
        self.final_rows_label.setText(str(len(print_data)))
        
        self.preview_widget.set_data(
            print_data,
            self.data_font_fam.currentText(),
            int(self.data_font_sz.value() / 0.353),
            self.data_bold_chk.isChecked(),
            (self.margin_left.value(), self.margin_top.value(),
             self.margin_right.value(), self.margin_bottom.value()),
            row_h_mm=self.row_height_spin.value(),
            col_widths_fixed_mm=[
                self.col_serial.value(), self.col_year.value(),
                self.col_month.value(), self.col_day.value(),
                self.col_pages.value(), self.col_remark.value()
            ],
            title_font_family=self.title_font_fam.currentText(),
            title_font_size=self.title_font_sz.value(),
            header_font_family=self.header_font_fam.currentText(),
            header_font_size=self.header_font_sz.value(),
            header_bold=self.header_bold_chk.isChecked(),
            data_font_family=self.data_font_fam.currentText(),
            data_font_size=self.data_font_sz.value(),
            data_bold=self.data_bold_chk.isChecked(),
            category_font_family=self.cat_font_fam.currentText(),
            category_font_size=self.cat_font_sz.value(),
            category_bold=self.cat_bold_chk.isChecked(),
            table_scale=self._table_scale_factor(),
        )
        
        # 更新分页状态
        self._update_page_controls()
    
    def _update_page_controls(self):
        """更新分页控件状态"""
        total = self.preview_widget.get_total_pages()
        current = self.preview_widget.get_current_page() + 1  # 显示从1开始
        self.page_label.setText(f"第 {current} 页 / 共 {total} 页")
        self.prev_page_btn.setEnabled(current > 1)
        self.next_page_btn.setEnabled(current < total)
    
    def _on_prev_page(self):
        """上一页"""
        self.preview_widget.prev_page()
        self._update_page_controls()
    
    def _on_next_page(self):
        """下一页"""
        self.preview_widget.next_page()
        self._update_page_controls()
    
    @staticmethod
    def _compute_print_row_heights(data, col1_w_px, base_row_h_px, data_font, category_font, padding_px=20):
        """根据实际字体计算每行打印高度（支持长文本换行）"""
        heights = []
        for item in data:
            name = str(item.get("name", ""))
            if name:
                fm = QFontMetrics(category_font if item.get("is_template") else data_font)
                br = fm.boundingRect(0, 0, max(1, col1_w_px - (padding_px * 2)), 10000,
                                     A4PreviewWidget._body_text_flags(1), name)
                heights.append(max(base_row_h_px, br.height() + (padding_px * 2)))
            else:
                heights.append(base_row_h_px)
        return heights

    def _on_print(self):
        """打印 - 使用自定义打印对话框"""
        try:
            # 显示自定义打印对话框（带页数信息，用于页面范围选择）
            total_pages = self.preview_widget.get_total_pages()
            current_page = self.preview_widget.get_current_page() + 1  # 1-indexed
            print_dialog = CustomPrintDialog(
                self, self.current_theme,
                total_pages=total_pages, current_page=current_page,
            )
            if print_dialog.exec_() != QDialog.Accepted:
                return
            
            printer = print_dialog.get_printer()
            if not printer:
                StyledMessageBox.warning(self, "提示", "无法获取打印机", self.current_theme)
                return
            
            # 设置页面
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setPageOrientation(QPageLayout.Portrait)
            
            printer.setPageMargins(
                self.margin_left.value(),
                self.margin_top.value(),
                self.margin_right.value(),
                self.margin_bottom.value(),
                QPrinter.Millimeter,
            )
            
            # 执行打印
            is_duplex = print_dialog.is_duplex()
            page_range = print_dialog.get_page_range()  # None 或 (start, end) 1-indexed inclusive
            self._print_with_painter(printer, is_duplex, page_range=page_range)
        except Exception as e:
            StyledMessageBox.warning(self, "打印失败", f"打印时发生错误：{str(e)}", self.current_theme)
    
    def _print_with_painter(self, printer: QPrinter, is_duplex: bool = False, page_range=None):
        """使用QPainter直接绘制打印内容，支持单双面打印 + 页面范围过滤

        page_range: None 表示全部；(start, end) 为 1-indexed inclusive。
        """
        try:
            painter = QPainter()
            if not painter.begin(printer):
                StyledMessageBox.warning(self, "打印失败", "无法启动打印", self.current_theme)
                return
            
            # 获取页面尺寸
            page_rect = printer.pageRect()
            page_width = page_rect.width()
            page_height = page_rect.height()
            table_scale = self._table_scale_factor()

            # 字体：与预览完全一致——mm × scale → pt
            title_font = QFont(self.title_font_fam.currentText())
            title_font.setPointSizeF(A4PreviewWidget._mm_to_pt(self.title_font_sz.value()))
            title_font.setBold(True)
            header_font = QFont(self.header_font_fam.currentText())
            header_font.setPointSizeF(A4PreviewWidget._mm_to_pt(self.header_font_sz.value() * table_scale))
            header_font.setBold(self.header_bold_chk.isChecked())
            data_font = QFont(self.data_font_fam.currentText())
            data_font.setPointSizeF(A4PreviewWidget._mm_to_pt(self.data_font_sz.value() * table_scale))
            data_font.setBold(self.data_bold_chk.isChecked())
            category_font = QFont(self.cat_font_fam.currentText())
            category_font.setPointSizeF(A4PreviewWidget._mm_to_pt(self.cat_font_sz.value() * table_scale))
            category_font.setBold(self.cat_bold_chk.isChecked())

            # 获取打印数据
            data = self._get_print_data()

            # === 统一 mm→像素换算（与预览坐标系一致） ===
            page_rect_mm = printer.pageRect(QPrinter.Millimeter)
            _pmm_w = page_rect_mm.width()  if page_rect_mm.width()  > 0 else 170.0
            _pmm_h = page_rect_mm.height() if page_rect_mm.height() > 0 else 257.0
            pixels_per_mm_x = page_width  / _pmm_w
            pixels_per_mm_y = page_height / _pmm_h

            # 版面常量（mm）——与 A4PreviewWidget.paintEvent 保持一致
            TITLE_H_MM  = 10.0  # 预览 paintEvent 中 title_rect 高度
            TITLE_GAP_MM = 2.0  # 预览 table_y = content_y + 12 = 10 + 2
            HEADER_ROW_H_MM = 7.0 * table_scale   # 预览 header_height = 7 * table_scale
            FOOTER_H_MM = 0.0   # 页脚（不再显示页码，不预留空间）

            title_height     = int(TITLE_H_MM      * pixels_per_mm_y)
            title_gap        = int(TITLE_GAP_MM    * pixels_per_mm_y)
            header_row_height = int(HEADER_ROW_H_MM * pixels_per_mm_y)
            header_height    = header_row_height * 2
            footer_height    = int(FOOTER_H_MM     * pixels_per_mm_y)
            available_height = page_height - title_height - title_gap - header_height - footer_height

            # 行高（mm → 设备像素）
            row_height_mm = self.row_height_spin.value() * table_scale
            row_height = int(row_height_mm * pixels_per_mm_y)
            # 列宽（mm → 设备像素，名称列自动填充剩余）
            # setPageMargins 已把 pageRect 收缩到边距内，_pmm_w 就是打印区宽度
            # （即预览里的 content_w = A4_W - left - right），不能再减一次边距！
            content_w_mm = _pmm_w
            _cw_mm = [
                self.col_serial.value(), self.col_year.value(),
                self.col_month.value(), self.col_day.value(),
                self.col_pages.value(), self.col_remark.value()
            ]
            _name_mm = max(20.0, content_w_mm - sum(_cw_mm))
            _all_mm = [_cw_mm[0], _name_mm, _cw_mm[1], _cw_mm[2], _cw_mm[3], _cw_mm[4], _cw_mm[5]]
            col_widths = [int(w * pixels_per_mm_x) for w in _all_mm]
            # painter (0,0) 已经是可打印区左上角，表格起点就是 0（等同于预览 content_x）
            table_start_x = 0

            # 行高（mm 估算，与预览相同公式，与设备 DPI 无关，保证分页一致）
            name_col_mm = _all_mm[1]
            row_heights_mm = [
                A4PreviewWidget._estimate_row_height_mm(
                    str(item.get("name", "")), name_col_mm, row_height_mm,
                    (self.cat_font_sz.value() if item.get("is_template") else self.data_font_sz.value()) * table_scale,
                )
                for item in data
            ]
            row_heights = [int(h * pixels_per_mm_y) for h in row_heights_mm]

            # 传给 _draw_page 的像素量（与预览对齐）
            # margin_top 已经由 setPageMargins 生效，painter y=0 就是上边距内沿
            margin_top_px   = 0
            title_gap_px    = title_gap
            name_padding_px = max(1, int(max(0.5, 0.8 * table_scale) * pixels_per_mm_x))
            content_w_px    = int(content_w_mm * pixels_per_mm_x)

            # 根据实际行高计算分页
            _pp = []
            _ps, _ch = 0, 0
            for _pi, _ph in enumerate(row_heights):
                if _ch + _ph > available_height and _pi > _ps:
                    _pp.append((_ps, _pi))
                    _ps, _ch = _pi, _ph
                else:
                    _ch += _ph
            _pp.append((_ps, len(row_heights)))
            total_pages = max(1, len(_pp))

            # 按照 page_range 过滤要打印的页（page_range: None 或 (start, end) 1-indexed inclusive）
            if page_range is None:
                pages_to_print = list(range(total_pages))
            else:
                s1, e1 = page_range
                lo = max(0, int(s1) - 1)
                hi = min(total_pages - 1, int(e1) - 1)
                pages_to_print = list(range(lo, hi + 1)) if lo <= hi else []

            if not pages_to_print:
                painter.end()
                StyledMessageBox.warning(self, "提示", "所选页面范围在当前文档内无有效页", self.current_theme)
                return

            def _render(page_idx, order_in_job):
                """绘制第 page_idx 页；order_in_job 是它在本次打印作业里的顺序（0=首页）。"""
                if order_in_job > 0:
                    printer.newPage()
                _s, _e = _pp[page_idx]
                self._draw_page(painter, printer, page_idx, total_pages,
                               data[_s:_e], row_heights[_s:_e],
                               page_width, page_height, table_start_x, col_widths,
                               title_font, header_font, data_font, category_font,
                               title_height, header_row_height, footer_height, row_height,
                               margin_top_px=margin_top_px, title_gap_px=title_gap_px,
                               name_padding_px=name_padding_px, content_w_px=content_w_px)

            # 双面打印逻辑（针对过滤后列表里的位置奇偶，不是绝对页码）
            if is_duplex and len(pages_to_print) > 1:
                odd_positions  = [p for i, p in enumerate(pages_to_print) if i % 2 == 0]
                even_positions = [p for i, p in enumerate(pages_to_print) if i % 2 == 1]

                # 先打印奇数位（放在作业中的第 1、3、5… 个）
                for order, page_idx in enumerate(odd_positions):
                    _render(page_idx, order)

                painter.end()

                # 提示用户翻转纸张
                reply = StyledMessageBox.question(
                    self, "双面打印",
                    "奇数页已打印完成。\n\n请将纸张翻转后放回打印机，然后点击\"是\"继续打印偶数页。",
                    StyledMessageBox.Yes | StyledMessageBox.No,
                    StyledMessageBox.Yes,
                    self.current_theme
                )

                if reply != StyledMessageBox.Yes:
                    StyledMessageBox.information(self, "提示", "打印已取消", self.current_theme)
                    return

                if not even_positions:
                    return

                # 重新开始打印偶数位
                if not painter.begin(printer):
                    StyledMessageBox.warning(self, "打印失败", "无法重新启动打印", self.current_theme)
                    return

                for order, page_idx in enumerate(even_positions):
                    _render(page_idx, order)
            else:
                # 单面打印：按过滤后顺序打印
                for order, page_idx in enumerate(pages_to_print):
                    _render(page_idx, order)
            
            painter.end()
            StyledMessageBox.information(self, "成功", f"文档已发送到打印机", self.current_theme)
            
        except Exception as e:
            StyledMessageBox.warning(self, "打印失败", f"打印时发生错误：{str(e)}", self.current_theme)
    
    def _draw_page(self, painter, printer, page, total_pages, page_data, page_row_heights,
                   page_width, page_height, table_start_x, col_widths,
                   title_font, header_font, data_font, category_font,
                   title_height, header_row_height, footer_height, base_row_height=80,
                   margin_top_px: int = 0, title_gap_px: int = 0,
                   name_padding_px: int = 10, content_w_px: int = 0):
        """绘制单页内容（坐标系与预览完全一致）"""
        # 标题从上边距开始（与预览 content_y = top 一致）
        current_y = margin_top_px

        # 绘制标题
        painter.setFont(title_font)
        painter.setPen(Qt.black)
        # 标题绘制范围限定在左右边距之间，与预览的 title_rect 一致
        title_x = table_start_x
        title_w = content_w_px if content_w_px > 0 else int(page_width)
        painter.drawText(title_x, current_y, title_w, title_height,
                       Qt.AlignCenter, "干部人事档案目录")
        current_y += title_height + title_gap_px
        
        # 绘制表头第一行
        painter.setFont(header_font)
        x_pos = table_start_x
        
        # 序号列（跨两行）
        painter.setPen(QPen(Qt.black, 2))
        painter.drawRect(int(x_pos), int(current_y), int(col_widths[0]), int(header_row_height * 2))
        painter.drawText(int(x_pos), int(current_y), int(col_widths[0]), int(header_row_height * 2),
                       Qt.AlignCenter, "序号")
        x_pos += col_widths[0]
        
        # 材料名称列（跨两行）
        painter.drawRect(int(x_pos), int(current_y), int(col_widths[1]), int(header_row_height * 2))
        painter.drawText(int(x_pos), int(current_y), int(col_widths[1]), int(header_row_height * 2),
                       Qt.AlignCenter, "材料名称")
        x_pos += col_widths[1]
        
        # 材料形成时间（跨3列）
        date_width = col_widths[2] + col_widths[3] + col_widths[4]
        painter.drawRect(int(x_pos), int(current_y), int(date_width), int(header_row_height))
        painter.drawText(int(x_pos), int(current_y), int(date_width), int(header_row_height),
                       Qt.AlignCenter, "材料形成时间")
        
        # 页数列（跨两行）
        pages_x = x_pos + date_width
        painter.drawRect(int(pages_x), int(current_y), int(col_widths[5]), int(header_row_height * 2))
        painter.drawText(int(pages_x), int(current_y), int(col_widths[5]), int(header_row_height * 2),
                       Qt.AlignCenter, "页数")
        
        # 备注列（跨两行）
        remark_x = pages_x + col_widths[5]
        painter.drawRect(int(remark_x), int(current_y), int(col_widths[6]), int(header_row_height * 2))
        painter.drawText(int(remark_x), int(current_y), int(col_widths[6]), int(header_row_height * 2),
                       Qt.AlignCenter, "备注")
        
        current_y += header_row_height
        
        # 绘制表头第二行（年月日）
        for idx, label in enumerate(["年", "月", "日"]):
            col_x = table_start_x + col_widths[0] + col_widths[1] + sum(col_widths[2:2+idx])
            painter.drawRect(int(col_x), int(current_y), int(col_widths[2+idx]), int(header_row_height))
            painter.drawText(int(col_x), int(current_y), int(col_widths[2+idx]), int(header_row_height),
                           Qt.AlignCenter, label)
        
        current_y += header_row_height
        
        # 绘制数据行
        for item, row_h in zip(page_data, page_row_heights):
            is_template = item.get("is_template", False)
            painter.setFont(category_font if is_template else data_font)
            x_pos = table_start_x

            values = [
                str(item.get("serial", "")),
                str(item.get("name", "")),
                str(item.get("year", "")),
                str(item.get("month", "")),
                str(item.get("day", "")),
                str(item.get("pages", "")),
                str(item.get("remark", ""))
            ]

            for col_idx, value in enumerate(values):
                painter.setPen(QPen(Qt.black, 1))
                painter.drawRect(int(x_pos), int(current_y), int(col_widths[col_idx]), int(row_h))

                painter.setPen(Qt.black)
                if col_idx == 1:
                    padding = name_padding_px
                    painter.drawText(int(x_pos + padding), int(current_y),
                                   int(col_widths[col_idx] - (padding * 2)), int(row_h),
                                   A4PreviewWidget._body_text_flags(col_idx), value)
                else:
                    painter.drawText(int(x_pos), int(current_y),
                                   int(col_widths[col_idx]), int(row_h),
                                   A4PreviewWidget._body_text_flags(col_idx), value)
                x_pos += col_widths[col_idx]

            current_y += row_h
    
    def _generate_html(self) -> str:
        """生成打印 HTML"""
        t_font = self.title_font_fam.currentText()
        t_sz = max(1, int(self.title_font_sz.value() / 0.353))
        h_font = self.header_font_fam.currentText()
        h_sz = max(1, int(self.header_font_sz.value() / 0.353))
        h_bold = "bold" if self.header_bold_chk.isChecked() else "normal"
        d_font = self.data_font_fam.currentText()
        d_sz = max(1, int(self.data_font_sz.value() / 0.353))
        d_bold = "bold" if self.data_bold_chk.isChecked() else "normal"
        c_font = self.cat_font_fam.currentText()
        c_sz = max(1, int(self.cat_font_sz.value() / 0.353))
        c_bold = "bold" if self.cat_bold_chk.isChecked() else "normal"
        data = self._get_print_data()
        
        html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body {{ font-family:"{d_font}","SimSun"; font-size:{d_sz}pt; font-weight:{d_bold}; margin:0; }}
h1 {{ text-align:center; font-family:"{t_font}","SimHei"; font-size:{t_sz}pt; font-weight:bold; margin:10px 0 15px; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ border:1px solid #000; padding:4px 6px; text-align:center; vertical-align:middle; }}
th {{ font-family:"{h_font}"; font-size:{h_sz}pt; font-weight:{h_bold}; }}
td.name {{ text-align:left; }}
tr.category td {{ font-family:"{c_font}","SimSun"; font-size:{c_sz}pt; font-weight:{c_bold}; }}
</style></head><body>
<h1>干部人事档案目录</h1>
<table>
<thead>
<tr><th rowspan="2" style="width:40px">序号</th><th rowspan="2">材料名称</th>
<th colspan="3">材料形成时间</th><th rowspan="2" style="width:45px">页数</th>
<th rowspan="2" style="width:60px">备注</th></tr>
<tr><th style="width:45px">年</th><th style="width:35px">月</th><th style="width:35px">日</th></tr>
</thead><tbody>'''
        
        for item in data:
            s = self._esc(str(item.get("serial", "")))
            n = self._esc(str(item.get("name", "")))
            y = self._esc(str(item.get("year", "")))
            m = self._esc(str(item.get("month", "")))
            d = self._esc(str(item.get("day", "")))
            p = self._esc(str(item.get("pages", "")))
            r = self._esc(str(item.get("remark", "")))
            row_cls = ' class="category"' if item.get("is_template") else ""
            html += f'<tr{row_cls}><td>{s}</td><td class="name">{n}</td><td>{y}</td><td>{m}</td><td>{d}</td><td>{p}</td><td>{r}</td></tr>'
        
        html += '</tbody></table></body></html>'
        return html
    
    def _on_export_xml(self):
        """导出 XML"""
        # 如果人名为空，则使用"目录.xml"，否则使用"人名.xml"
        name = f"{self.person_name}.xml" if self.person_name else "目录.xml"
        path, _ = QFileDialog.getSaveFileName(self, "导出 XML", name, "XML Files (*.xml)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._generate_xml())
            QMessageBox.information(self, "成功", f"已导出到:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))
    
    def _generate_xml(self) -> str:
        """生成 Excel XML - 与模板格式完全一致"""
        font = self.data_font_fam.currentText()
        size = max(1, int(self.data_font_sz.value() / 0.353))
        bold = "1" if self.data_bold_chk.isChecked() else "0"
        c_font = self.cat_font_fam.currentText()
        c_size = max(1, int(self.cat_font_sz.value() / 0.353))
        c_bold = "1" if self.cat_bold_chk.isChecked() else "0"
        data = self._get_print_data()
        rows = 3 + len(data)
        
        _borders = '<Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/></Borders>'
        # 使用与模板一致的样式格式
        xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Styles>
<Style ss:ID="Default" ss:Name="Normal"><Alignment ss:Vertical="Bottom"/><Borders/><Font ss:FontName="Calibri" x:CharSet="134" x:Family="Swiss" ss:Size="11"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="sTitle"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:FontName="黑体" x:CharSet="134" ss:Size="18" ss:Bold="1"/></Style>
<Style ss:ID="CatalogIndex" ss:Name="CatalogIndex"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
{_borders}
<Font ss:FontName="{font}" x:CharSet="134" x:Family="Swiss" ss:Size="{size}" ss:Bold="{bold}"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="CatalogName" ss:Name="CatalogName"><Alignment ss:Horizontal="Left" ss:Vertical="Center"/>
{_borders}
<Font ss:FontName="{font}" x:CharSet="134" x:Family="Swiss" ss:Size="{size}" ss:Bold="{bold}"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="CatalogIndexCat" ss:Name="CatalogIndexCat"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
{_borders}
<Font ss:FontName="{c_font}" x:CharSet="134" x:Family="Swiss" ss:Size="{c_size}" ss:Bold="{c_bold}"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="CatalogNameCat" ss:Name="CatalogNameCat"><Alignment ss:Horizontal="Left" ss:Vertical="Center"/>
{_borders}
<Font ss:FontName="{c_font}" x:CharSet="134" x:Family="Swiss" ss:Size="{c_size}" ss:Bold="{c_bold}"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="DocCenter" ss:Name="DocCenter"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
{_borders}
<Font ss:FontName="{font}" x:CharSet="134" ss:Size="{size}" ss:Bold="{bold}"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="ZgHeader" ss:Name="ZgHeader"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
<Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/></Borders>
<Font ss:FontName="{font}" x:CharSet="134" x:Family="Swiss" ss:Size="{size}" ss:Bold="1"/><Interior/><NumberFormat/><Protection/></Style>
<Style ss:ID="ZgHeaderDate" ss:Name="ZgHeaderDate"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
<Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/><Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/></Borders>
<Font ss:FontName="{font}" x:CharSet="134" x:Family="Swiss" ss:Size="10" ss:Bold="1"/><Interior/><NumberFormat/><Protection/></Style>
</Styles>
<Worksheet ss:Name="目录">
<Table ss:ExpandedColumnCount="7" ss:ExpandedRowCount="{rows}" ss:DefaultRowHeight="24">
<Column ss:Width="40"/><Column ss:Width="280"/><Column ss:Width="45"/><Column ss:Width="35"/><Column ss:Width="35"/><Column ss:Width="45"/><Column ss:Width="60"/>
<Row ss:Height="40"><Cell ss:MergeAcross="6" ss:StyleID="sTitle"><Data ss:Type="String">干部人事档案目录</Data></Cell></Row>
<Row ss:Height="28">
<Cell ss:MergeDown="1" ss:StyleID="ZgHeader"><Data ss:Type="String">序号</Data></Cell>
<Cell ss:MergeDown="1" ss:StyleID="ZgHeader"><Data ss:Type="String">材料名称</Data></Cell>
<Cell ss:MergeAcross="2" ss:StyleID="ZgHeader"><Data ss:Type="String">材料形成时间</Data></Cell>
<Cell ss:MergeDown="1" ss:StyleID="ZgHeader"><Data ss:Type="String">页数</Data></Cell>
<Cell ss:MergeDown="1" ss:StyleID="ZgHeader"><Data ss:Type="String">备注</Data></Cell>
</Row>
<Row ss:Height="24">
<Cell ss:Index="3" ss:StyleID="ZgHeaderDate"><Data ss:Type="String">年</Data></Cell>
<Cell ss:StyleID="ZgHeaderDate"><Data ss:Type="String">月</Data></Cell>
<Cell ss:StyleID="ZgHeaderDate"><Data ss:Type="String">日</Data></Cell>
</Row>
'''
        for item in data:
            s = self._esc(str(item.get("serial", "")))
            n = self._esc(str(item.get("name", "")))
            y = self._esc(str(item.get("year", "")))
            m = self._esc(str(item.get("month", "")))
            d = self._esc(str(item.get("day", "")))
            p = self._esc(str(item.get("pages", "")))
            r = self._esc(str(item.get("remark", "")))
            # 类别行使用类别字体样式，普通行使用内容字体样式
            if item.get("is_template"):
                si = "CatalogIndexCat"
                sn = "CatalogNameCat"
            else:
                si = "CatalogIndex"
                sn = "CatalogName"
            xml += f'''<Row ss:Height="24">
<Cell ss:StyleID="{si}"><Data ss:Type="String">{s}</Data></Cell>
<Cell ss:StyleID="{sn}"><Data ss:Type="String">{n}</Data></Cell>
<Cell ss:StyleID="DocCenter"><Data ss:Type="String">{y}</Data></Cell>
<Cell ss:StyleID="DocCenter"><Data ss:Type="String">{m}</Data></Cell>
<Cell ss:StyleID="DocCenter"><Data ss:Type="String">{d}</Data></Cell>
<Cell ss:StyleID="DocCenter"><Data ss:Type="String">{p}</Data></Cell>
<Cell ss:StyleID="DocCenter"><Data ss:Type="String">{r}</Data></Cell>
</Row>
'''
        xml += '</Table></Worksheet></Workbook>'
        return xml
    
    def _esc(self, text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

from PyQt5.QtWidgets import QTreeWidget
from PyQt5.QtGui import QColor, QPalette


class OrgTreeWidget(QTreeWidget):
    """自绘树控件：统一行背景（含缩进区域），避免主题下出现色块。"""

    def __init__(self, theme: str = "light", parent=None, with_grid_lines: bool = False):
        super().__init__(parent)
        self.theme = theme
        self.with_grid_lines = bool(with_grid_lines)
        self.setMouseTracking(True)
        self.setRootIsDecorated(True)
        self.setIndentation(18)
        # 关闭交替色，由调色板统一控制
        self.setAlternatingRowColors(False)
        self._apply_theme_colors()

    def set_theme(self, theme: str):
        self.theme = theme
        self._apply_theme_colors()
        self.viewport().update()

    def _apply_theme_colors(self):
        if self.theme == "dark":
            self.bg_normal = "#1f2937"
            self.bg_hover = "#2b3544"
            self.bg_selected = "#1e3a8a"
            self.text_normal = "#d1d5db"
            self.text_selected = "#ffffff"
            self.line_color = "#3b4252"
        else:
            self.bg_normal = "#ffffff"
            self.bg_hover = "#f9fafb"
            self.bg_selected = "#e0e7ff"
            self.text_normal = "#374151"
            self.text_selected = "#1e3a8a"
            self.line_color = "#cbd5e1"

        # 应用到调色板，避免默认交替背景
        pal = self.palette()
        pal.setColor(QPalette.Base, QColor(self.bg_normal))
        pal.setColor(QPalette.AlternateBase, QColor(self.bg_normal))
        pal.setColor(QPalette.Text, QColor(self.text_normal))
        pal.setColor(QPalette.WindowText, QColor(self.text_normal))
        pal.setColor(QPalette.Highlight, QColor(self.bg_selected))
        pal.setColor(QPalette.HighlightedText, QColor(self.text_selected))
        self.setPalette(pal)

        # 可选：用样式在每行底部绘制横向分隔线（仅目录页需要）
        if self.with_grid_lines:
            self.setStyleSheet(
                f"""
                QTreeWidget#org_tree::item {{
                    border-bottom: 1px solid {self.line_color};
                }}
                """
            )
        else:
            self.setStyleSheet("")

    def drawRow(self, painter, option, index):
        # 使用默认绘制，但调色板已被我们统一设置
        super().drawRow(painter, option, index)



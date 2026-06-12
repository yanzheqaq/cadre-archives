from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QPushButton, QButtonGroup, QLabel, QStackedWidget,
                             QLineEdit, QDateEdit, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QFont, QWheelEvent
from PyQt5.QtGui import QFont, QWheelEvent

from common.config import AppSettings
from main_ui import style_pages
from main_ui.config_pages import PagesConfig

class NavButton(QPushButton):
    """
    自定义导航按钮，使用垂直布局包含两个 Label：
    - 上方显示图标 (Emoji)
    - 下方显示文字
    解决 QToolButton HTML 渲染不一致的问题
    """
    def __init__(self, text, icon_text, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("sub_nav_btn") # 继承原有样式（背景、边框等）
        
        # 内部布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(2)
        
        # 图标 Label
        self.icon_label = QLabel(icon_text)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setObjectName("icon_label") # 设置objectName方便样式控制
        # 设置透明背景，让鼠标事件透传给父控件(QPushButton)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        # 初始样式 (只有字体大小，颜色跟随父控件样式表可能比较难，建议直接透传或者在 update_style 中控制)
        self.icon_label.setStyleSheet(f"background: transparent; border: none; font-size: {PagesConfig.SUB_NAV_ICON_FONT_SIZE}px;")
        layout.addWidget(self.icon_label)
        
        # 文字 Label
        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setObjectName("text_label")
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text_label.setStyleSheet(f"background: transparent; border: none; font-size: {PagesConfig.SUB_NAV_FONT_SIZE}px; font-weight: normal;")
        layout.addWidget(self.text_label)
        
    # 重写 setText 以兼容部分旧逻辑（可选）
    def setText(self, text):
        pass # 禁用直接设置文本，防止覆盖布局


class SearchBar(QFrame):
    """
    自定义搜索栏组件
    包含：批次、案卷档号、案件号、接收日期（起始/终止）、查询按钮、重置按钮
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("search_bar")
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            PagesConfig.SEARCH_BAR_PADDING_X, 
            PagesConfig.SEARCH_BAR_PADDING_Y, 
            PagesConfig.SEARCH_BAR_PADDING_X, 
            PagesConfig.SEARCH_BAR_PADDING_Y
        )
        layout.setSpacing(PagesConfig.SEARCH_BAR_SPACING)

        # 通用 Label 样式 (字体大小从配置读取)
        label_style = f"QLabel {{ font-size: {PagesConfig.SEARCH_LABEL_FONT_SIZE}px; font-weight: 500; color: #555; }}"

        # --- 输入项工厂方法 ---
        def create_input_field(label_text, placeholder=""):
            container = QWidget()
            l = QHBoxLayout(container)
            l.setContentsMargins(0,0,0,0)
            l.setSpacing(8)
            
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            # 输入框样式在 style_pages.py 中定义，这里主要通过 layout 或 qss 设置字体
            # 实际上 QSS 已经覆盖了，这里只需要确保 objectName 或父类正确
            # 这里不硬编码样式，而是利用 style_pages.py 里的 class 选择器
            # 但为了字体大小动态化，如果这里写死 style 会覆盖 qss 里的
            # 最佳实践：仅设置最小宽度等布局属性，或通过 setStyleSheet 设置变量
            
            # 注意：为了让 style_pages.py 的 min-width 生效，这里最好不要 setFixedWidth
            # 或者我们在这里应用配置中的最小宽度
            # style_pages 里的 min-width 是兜底，这里可以直接设
            
            l.addWidget(lbl)
            l.addWidget(inp)
            return container, inp

        # 1. 批次
        self.batch_container, self.batch_input = create_input_field("接收批次:", "请输入批次")
        layout.addWidget(self.batch_container)

        # 2. 案卷档号
        self.vol_container, self.vol_input = create_input_field("案卷档号:", "请输入档号")
        layout.addWidget(self.vol_container)

        # 3. 案件号
        self.case_container, self.case_input = create_input_field("案件号:", "请输入案件号")
        layout.addWidget(self.case_container)

        # 4. 姓名
        self.name_container, self.name_input = create_input_field("姓名:", "请输入姓名")
        layout.addWidget(self.name_container)

        # 5. 接收日期 (起始 - 终止)
        date_container = QWidget()
        date_layout = QHBoxLayout(date_container)
        date_layout.setContentsMargins(0,0,0,0)
        date_layout.setSpacing(8)
        
        date_label = QLabel("接收日期:")
        date_label.setStyleSheet(label_style)
        
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addDays(-7)) # 默认一周前
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setFixedWidth(PagesConfig.SEARCH_DATE_WIDTH) # 使用配置宽度
        
        sep_label = QLabel("至")
        sep_label.setStyleSheet("color: #888;")
        
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setFixedWidth(PagesConfig.SEARCH_DATE_WIDTH) # 使用配置宽度

        # 下拉箭头样式等已在 style_pages.py 定义

        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_start)
        date_layout.addWidget(sep_label)
        date_layout.addWidget(self.date_end)
        
        layout.addWidget(date_container)

        # 5. 按钮组
        self.btn_search = QPushButton("查询")
        self.btn_search.setCursor(Qt.PointingHandCursor)
        self.btn_search.setFixedSize(PagesConfig.SEARCH_BTN_WIDTH, PagesConfig.SEARCH_BTN_HEIGHT) # 使用配置尺寸
        self.btn_search.setObjectName("btn_search") 

        self.btn_reset = QPushButton("重置")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFixedSize(PagesConfig.SEARCH_BTN_WIDTH, PagesConfig.SEARCH_BTN_HEIGHT) # 使用配置尺寸
        self.btn_reset.setObjectName("btn_reset")
        
        # 连接重置信号
        self.btn_reset.clicked.connect(self.reset_fields)

        layout.addWidget(self.btn_search)
        layout.addWidget(self.btn_reset)

        # 弹簧，将按钮推到左侧
        layout.addStretch(1)
        
    def reset_fields(self):
        self.batch_input.clear()
        self.vol_input.clear()
        self.case_input.clear()
        self.name_input.clear()
        self.date_start.setDate(QDate.currentDate().addDays(-7))
        self.date_end.setDate(QDate.currentDate())


class BasePage(QWidget):
    """
    所有功能页面的基类
    包含：
    1. 二级导航栏 (Sub Navigation)
    2. 搜索栏 (Search Bar) - [新增]
    3. 内容区域 (Content Area)
    4. 统一的主题切换响应
    """
    def __init__(self, sub_menus=None, show_search_bar=True):
        super().__init__()
        self.sub_menus = sub_menus or []
        self.show_search_bar = show_search_bar # 控制开关
        self.config_manager = AppSettings()
        self.current_theme = self.config_manager.load_theme_preference()
        # 字体缩放
        self._base_font: QFont = self.font()
        self._font_min = 9
        self._font_max = 20
        
        self.initBaseUI()
        self.apply_theme_style()

    def initBaseUI(self):
        # 页面整体布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # === 1. 二级导航栏 ===
        if self.sub_menus:
            self.nav_bar = QFrame()
            self.nav_bar.setObjectName("sub_nav_bar")
            self.nav_bar.setFixedHeight(PagesConfig.SUB_NAV_HEIGHT)
            
            self.nav_layout = QHBoxLayout(self.nav_bar)
            self.nav_layout.setContentsMargins(20, 0, 20, 0)
            self.nav_layout.setSpacing(PagesConfig.SUB_NAV_SPACING)
            
            self.nav_group = QButtonGroup(self)
            self.nav_group.setExclusive(True)
            
            for idx, item in enumerate(self.sub_menus):
                # 兼容旧配置（只传字符串）和新配置（元组）
                if isinstance(item, tuple):
                    name, icon_text = item
                else:
                    name = item
                    icon_text = "📄" # 默认图标

                # 使用自定义 NavButton
                btn = NavButton(name, icon_text)
                btn.setFixedSize(80, PagesConfig.SUB_NAV_HEIGHT - 10) # 固定大小
                
                if idx == 0:
                    btn.setChecked(True)
                    
                self.nav_group.addButton(btn, idx)
                self.nav_layout.addWidget(btn)
                
                btn.clicked.connect(self.on_sub_nav_click)
            
            self.nav_layout.addStretch()
            self.main_layout.addWidget(self.nav_bar)

        # === 2. 搜索栏 (根据开关决定是否添加) ===
        if self.show_search_bar:
            self.search_bar_widget = SearchBar() # 避免变量名冲突或为了清晰
            self.main_layout.addWidget(self.search_bar_widget)
            
        # === 3. 内容区域 (使用 StackedWidget 方便切换) ===
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("page_content")
        self.main_layout.addWidget(self.content_area)
        
        # 初始化内容页 (由子类实现具体的填充逻辑)
        self.init_content_pages()

    def init_content_pages(self):
        """
        子类重写此方法来填充 content_area
        """
        for item in self.sub_menus:
            name = item[0] if isinstance(item, tuple) else item
            
            page = QWidget()
            layout = QVBoxLayout(page)
            label = QLabel(f"当前功能: {name}")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 24px; color: #888;")
            layout.addWidget(label)
            self.content_area.addWidget(page)

    def on_sub_nav_click(self):
        btn = self.sender()
        idx = self.nav_group.id(btn)
        self.content_area.setCurrentIndex(idx)

    def apply_theme_style(self):
        """
        应用主题样式
        """
        if self.current_theme == "light":
            self.setStyleSheet(style_pages.LIGHT_PAGE_STYLE)
        else:
            self.setStyleSheet(style_pages.DARK_PAGE_STYLE)
        # 重新应用当前字体缩放（保持设置一致）
        self._apply_font_zoom(self.font().pointSizeF())
            
    def update_theme(self, theme_name):
        """
        主窗口通知主题切换
        """
        self.current_theme = theme_name
        self.apply_theme_style()

    # === 通用：Ctrl + 滚轮调整字体大小，所有页面可复用 ===
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 1 if delta > 0 else -1
            new_size = self.font().pointSizeF() + step
            new_size = max(self._font_min, min(self._font_max, new_size))
            self._apply_font_zoom(new_size)
            event.accept()
            return
        super().wheelEvent(event)

    def _apply_font_zoom(self, point_size: float):
        """应用字体缩放到当前页面及其子控件"""
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.setFont(f)

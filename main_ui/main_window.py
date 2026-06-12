from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QStackedWidget, QButtonGroup, QApplication,
                             QStyleOptionButton, QStyle)
from PyQt5.QtCore import Qt, QPoint, QEvent, pyqtProperty, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QRect
from PyQt5.QtGui import QMouseEvent, QPainter, QCursor

from . import style_main
from common.config import AppSettings, AppConfig, MainUIConfig

# 导入新创建的页面类
from main_ui.pages.page_inventory import InventoryPage
from main_ui.pages.page_custody import CustodyPage
from main_ui.pages.page_stats import StatsPage
from main_ui.pages.page_maintenance import MaintenancePage # [新增]
from main_ui.pages.page_users import UserPage
from main_ui.pages.page_settings import SettingsPage # [新增]
from main_ui.pages.page_system import SystemPage

class MenuButton(QPushButton):
    """
    自定义菜单按钮，支持选中状态的弹性放大动画 (苹果风格)
    """
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._zoom = 1.0
        self._anim = QPropertyAnimation(self, b"zoom", self)
        self._anim.setDuration(300) # 动画持续时间，稍快一点
        self._anim.setEasingCurve(QEasingCurve.OutBack) # 使用 OutBack 曲线，比 Elastic 更像现代UI
        
        self.toggled.connect(self.on_toggled)

    @pyqtProperty(float)
    def zoom(self):
        return self._zoom

    @zoom.setter
    def zoom(self, value):
        self._zoom = value
        self.update() # 触发重绘

    def on_toggled(self, checked):
        self._anim.stop()
        if checked:
            self._anim.setEndValue(1.2)  # 选中时放大到 1.2 倍并保持
            self.raise_() # 确保放大的按钮在最上层，不被遮挡
        else:
            self._anim.setEndValue(1.0)  # 未选中恢复原状
        self._anim.start()

    def setChecked(self, checked):
        # 重写 setChecked 以确保初始状态正确 (虽然 toggled 也会触发，但为了保险可以手动设置初始值)
        super().setChecked(checked)
        # 如果动画还没运行过（比如刚初始化），直接设置值避免动画
        if self._anim.state() == QAbstractAnimation.Stopped and self._zoom == 1.0 and checked:
             self._zoom = 1.2
             self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # --- 关键：设置缩放变换 ---
        # 1. 移动坐标原点到按钮中心
        painter.translate(self.width() / 2, self.height() / 2)
        # 2. 应用缩放
        painter.scale(self._zoom, self._zoom)
        # 3. 移回原点 (以便后续绘制逻辑基于左上角0,0)
        painter.translate(-self.width() / 2, -self.height() / 2)
        
        # --- 调用样式进行绘制 ---
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawControl(QStyle.CE_PushButton, opt, painter, self)

class TitleBar(QFrame):
    """
    自定义标题栏组件 (三栏结构)
    左侧：Logo (跨越两行高度)
    右侧：
        第一行：标题 (居中) + 窗口控制 (右侧)
        第二行：菜单 + 用户信息 + 主题切换
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("top_toolbar")
        self.setFixedHeight(MainUIConfig.HEADER_HEIGHT)
        self.initUI()
        
        # 拖动窗口相关变量
        self.m_flag = False
        self.m_Position = QPoint()

    def initUI(self):
        # 主布局改为水平布局：左侧Logo + 右侧容器
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # === 左侧：Logo ===
        self.logo_label = QLabel("LOGO") # 占位符
        self.logo_label.setFixedWidth(MainUIConfig.LOGO_WIDTH)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.1); 
            color: white; 
            font-weight: bold; 
            font-size: 20px;
        """)
        main_layout.addWidget(self.logo_label)
        
        # === 右侧容器：包含原来的 Top Row 和 Bottom Row ===
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # --- 原第一行：标题行 ---
        top_row = QWidget()
        top_row.setFixedHeight(MainUIConfig.TITLE_ROW_HEIGHT)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(MainUIConfig.TITLE_BAR_MARGINS[0], 0, MainUIConfig.TITLE_BAR_MARGINS[1], 0)
        top_layout.setSpacing(10)
        
        # 左侧占位
        top_layout.addStretch(1)
        
        # 中间标题
        app_title = QLabel(MainUIConfig.APP_TITLE)
        app_title.setAlignment(Qt.AlignCenter)
        app_title.setStyleSheet(f"color: white; font-weight: bold; font-size: {MainUIConfig.LOGO_FONT_SIZE}px;")
        top_layout.addWidget(app_title)
        
        # 右侧弹簧
        top_layout.addStretch(1)
        
        # 右侧：窗口控制按钮
        self.min_btn = self.create_control_btn("－", "min_btn")
        self.max_btn = self.create_control_btn("□", "max_btn")
        self.close_btn = self.create_control_btn("×", "close_btn")
        
        top_layout.addWidget(self.min_btn)
        top_layout.addWidget(self.max_btn)
        top_layout.addWidget(self.close_btn)
        
        right_layout.addWidget(top_row)
        
        # --- 原第二行：菜单行 ---
        bottom_row = QWidget()
        bottom_row.setFixedHeight(MainUIConfig.MENU_ROW_HEIGHT)
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(MainUIConfig.TITLE_BAR_MARGINS[0], 0, MainUIConfig.TITLE_BAR_MARGINS[1], 0)
        bottom_layout.setSpacing(MainUIConfig.TITLE_BAR_SPACING)
        
        # 菜单容器
        self.menu_container = QWidget()
        menu_layout = QHBoxLayout(self.menu_container)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(MainUIConfig.MENU_SPACING)
        bottom_layout.addWidget(self.menu_container)
        
        bottom_layout.addStretch()
        
        # 用户信息
        user_info = QLabel(f"👤 {AppConfig.ADMIN_USER}")
        user_info.setStyleSheet(f"color: rgba(255,255,255,0.7); margin-right: 10px; font-size: {MainUIConfig.INFO_FONT_SIZE}px;")
        bottom_layout.addWidget(user_info)
        
        # 项目地点和IP
        location_ip = QLabel(f"📍 {AppConfig.LOCATION} | 🌐 {AppConfig.IP_ADDR}")
        location_ip.setStyleSheet(f"color: rgba(255,255,255,0.7); margin-right: 10px; font-size: {MainUIConfig.INFO_FONT_SIZE}px;")
        bottom_layout.addWidget(location_ip)
        
        # 主题切换按钮
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("theme_btn")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFixedSize(MainUIConfig.THEME_BTN_SIZE, MainUIConfig.THEME_BTN_SIZE)
        bottom_layout.addWidget(self.theme_btn)
        
        right_layout.addWidget(bottom_row)
        
        # 将右侧容器添加到主布局
        main_layout.addWidget(right_container)
        
        # 连接窗口控制信号
        if self.parent:
            self.min_btn.clicked.connect(self.parent.showMinimized)
            self.max_btn.clicked.connect(self.toggle_max)
            self.close_btn.clicked.connect(self.parent.close)

    def create_control_btn(self, text, obj_name):
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setFixedSize(MainUIConfig.CONTROL_BTN_SIZE, MainUIConfig.CONTROL_BTN_SIZE)
        return btn

    def toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("□")
        else:
            self.parent.showMaximized()
            self.max_btn.setText("❐")

    # === 鼠标拖动事件重写 ===
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.parent:
            self.m_flag = True
            self.m_Position = event.globalPos() - self.parent.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if Qt.LeftButton and self.m_flag and self.parent:
            self.parent.move(event.globalPos() - self.m_Position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.m_flag = False

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.parent:
            # 由于现在 Header 包含 Logo，判断位置略复杂
            # 简化逻辑：只要在 Header 区域双击，且不在 Menu 区域 (y < TITLE_ROW_HEIGHT)，就最大化
            # 这里简单判断 Y 坐标
            if event.pos().y() <= MainUIConfig.TITLE_ROW_HEIGHT:
                self.toggle_max()


class MainWindow(QMainWindow):
    # 定义边缘检测距离
    MARGIN = 5

    def __init__(self):
        super().__init__()
        self.config = AppSettings()
        self.current_theme = self.config.load_theme_preference()
        
        # 无边框窗口设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint)
        
        # 调整大小相关的状态变量
        self._is_resizing = False
        self._resize_edge = None
        self._drag_pos = QPoint()
        
        self.initUI()
        self.apply_style()
        
        # 启用鼠标追踪，以便在不按下鼠标时也能检测边缘
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

    def initUI(self):
        self.setWindowTitle(AppConfig.TITLE_CN)
        self.resize(MainUIConfig.WINDOW_WIDTH, MainUIConfig.WINDOW_HEIGHT)
        
        # 中心部件
        central_widget = QWidget()
        central_widget.setObjectName("central_widget") # 方便样式控制
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # === 1. 自定义标题栏 ===
        self.title_bar = TitleBar(self)
        
        # 配置主题按钮
        self.title_bar.theme_btn.setText("🌙" if self.current_theme == "light" else "☀️")
        self.title_bar.theme_btn.clicked.connect(self.toggle_theme)
        
        # === 2. 注入菜单到标题栏 ===
        menu_layout = self.title_bar.menu_container.layout()
        
        self.menu_group = QButtonGroup(self)
        self.menu_group.setExclusive(True)
        
        for index, (name, icon) in enumerate(MainUIConfig.MENU_ITEMS):
            btn = MenuButton(f"{name}") # [修改] 使用自定义的 MenuButton
            btn.setCheckable(True)
            btn.setObjectName("menu_btn")
            btn.setCursor(Qt.PointingHandCursor)
            # 使用参数化高度 (基于 MENU_ROW_HEIGHT)
            btn.setFixedHeight(MainUIConfig.MENU_ROW_HEIGHT - MainUIConfig.MENU_HEIGHT_OFFSET)
            
            if index == 0:
                btn.setChecked(True)
            
            self.menu_group.addButton(btn, index)
            menu_layout.addWidget(btn)
            
            # 连接信号
            btn.clicked.connect(self.on_menu_click)
            
        main_layout.addWidget(self.title_bar)
        
        # === 3. 下方内容区 (加载实际页面) ===
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("main_content_area")
        
        # 实例化并添加所有页面
        self.pages = []
        self.pages.append(InventoryPage())   # index 0
        self.pages.append(CustodyPage())     # index 1
        self.pages.append(StatsPage())       # index 2
        self.pages.append(MaintenancePage()) # index 3 [新增]
        self.pages.append(UserPage())        # index 4
        self.pages.append(SettingsPage())    # index 5 [新增]
        self.pages.append(SystemPage())      # index 6
        
        for page in self.pages:
            self.stacked_widget.addWidget(page)
            
        main_layout.addWidget(self.stacked_widget)

        # 初始显示状态处理
        # 注意：在Frameless模式下，showMaximized可能需要特殊处理，这里先保持调用
        self.showMaximized()
        self.update_style_for_maximized() # 确保最大化时样式正确

    # === 窗口调整大小核心逻辑 ===
    def _get_resize_edge(self, pos):
        """根据鼠标位置判断处于哪个边缘"""
        r = self.rect()
        x, y, w, h = pos.x(), pos.y(), r.width(), r.height()
        edge = []
        
        # 判定上下左右
        if y < self.MARGIN: edge.append("top")
        if y > h - self.MARGIN: edge.append("bottom")
        if x < self.MARGIN: edge.append("left")
        if x > w - self.MARGIN: edge.append("right")
        
        return "-".join(edge) if edge else None

    def _update_cursor(self, edge):
        """根据边缘更新鼠标样式"""
        if edge == "top" or edge == "bottom":
            self.setCursor(Qt.SizeVerCursor)
        elif edge == "left" or edge == "right":
            self.setCursor(Qt.SizeHorCursor)
        elif edge in ["top-left", "bottom-right"]:
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in ["top-right", "bottom-left"]:
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._is_resizing = True
                self._resize_edge = edge
                self._drag_pos = event.globalPos()
                event.accept()
            else:
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 1. 如果正在调整大小
        if self._is_resizing:
            delta = event.globalPos() - self._drag_pos
            self._drag_pos = event.globalPos()
            geom = self.geometry()
            
            # 根据边缘调整 geometry
            if "left" in self._resize_edge:
                geom.setLeft(geom.left() + delta.x())
            if "right" in self._resize_edge:
                geom.setRight(geom.right() + delta.x())
            if "top" in self._resize_edge:
                geom.setTop(geom.top() + delta.y())
            if "bottom" in self._resize_edge:
                geom.setBottom(geom.bottom() + delta.y())
            
            self.setGeometry(geom)
            event.accept()
            
        # 2. 如果没在调整，且没有被最大化 -> 更新鼠标图标
        elif not self.isMaximized():
            edge = self._get_resize_edge(event.pos())
            self._update_cursor(edge)
            super().mouseMoveEvent(event)
        else:
            self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_resizing = False
            self._resize_edge = None
        super().mouseReleaseEvent(event)

    # === 覆盖 changeEvent 监听最大化变化 ===
    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMaximized():
                self.title_bar.max_btn.setText("❐")
                self.update_style_for_maximized()
            else:
                self.title_bar.max_btn.setText("□")
                self.update_style_for_normal()
        super().changeEvent(event)

    def update_style_for_maximized(self):
        """最大化时移除圆角"""
        self.centralWidget().setStyleSheet("QWidget#central_widget { border-radius: 0px; }")
        
    def update_style_for_normal(self):
        """正常模式下显示圆角"""
        # 这里的样式通常已经在 style_main.py 里定义了，不需要做太多操作
        # 除非我们在 style_main.py 里没有给 central_widget 定义样式
        self.centralWidget().setStyleSheet("") # 清除内联样式，恢复 class 样式

    def on_menu_click(self):
        btn = self.sender()
        index = self.menu_group.id(btn)
        self.stacked_widget.setCurrentIndex(index)

    def toggle_theme(self):
        if self.current_theme == "light":
            self.current_theme = "dark"
            self.title_bar.theme_btn.setText("☀️")
        else:
            self.current_theme = "light"
            self.title_bar.theme_btn.setText("🌙")
            
        self.apply_style()
        self.config.save_theme_preference(self.current_theme)
        
        # 通知所有子页面更新主题
        for page in self.pages:
            if hasattr(page, 'update_theme'):
                page.update_theme(self.current_theme)

    def apply_style(self):
        if self.current_theme == "light":
            self.setStyleSheet(style_main.LIGHT_THEME)
        else:
            self.setStyleSheet(style_main.DARK_THEME)

    def logout(self):
        self.close()

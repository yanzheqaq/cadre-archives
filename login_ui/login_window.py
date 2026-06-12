# -*- coding: utf-8 -*-
"""
登录窗口
使用新的服务层架构
"""

from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QHBoxLayout, 
                             QMessageBox, QFrame, QGraphicsDropShadowEffect, QCheckBox,
                             QApplication)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer
from PyQt5.QtGui import QColor

from . import style_login
from .db_config_dialog import DbConfigDialog
from common.config import AppSettings, AppConfig, LoginUIConfig
from common.config.db_config import DatabaseConfig
from common.db import test_connection, reset_engine, is_database_initialized, ensure_performance_indexes
from main_ui.main_window import MainWindow

# 使用新的服务层
from common.services import auth_service


class LoginWindow(QWidget):
    """登录窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化配置管理器
        self.config = AppSettings()
        
        # 加载主题（先加载主题，配置对话框需要）
        self.current_theme = self.config.load_theme_preference()
        
        # 加载数据库配置并检查连接
        self._db_connected = False
        self._db_initialized = False
        self._image_root_configured = False
        self._load_and_check_db()
        
        # 设置无边框和背景透明
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.initUI()
        self.initAnimation()
        self.load_settings()
        
        # 拖拽窗口相关变量
        self.oldPos = self.pos()
        
        # 如果数据库未连接，延迟弹出配置框（等窗口显示后）
        if not (self._db_connected and self._db_initialized and self._image_root_configured):
            QTimer.singleShot(300, self._show_db_config_on_start)
    
    def _load_and_check_db(self):
        """加载数据库配置并检查连接"""
        self._db_connected = False
        self._db_initialized = False

        # 先加载保存的配置
        if self.config.has_saved_db_connection():
            host, port, user, password, database = self.config.get_db_connection()
            DatabaseConfig.set_connection(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )
            # 重置引擎，使新配置生效
            reset_engine()
            # 测试连接
            success, _ = test_connection(host, port, user, password, database, timeout=3)
            self._db_connected = success
            if success:
                self._db_initialized = is_database_initialized()
                if self._db_initialized:
                    ensure_performance_indexes()
                self._image_root_configured = self.config.has_saved_image_root()
        else:
            # 没有保存的配置，尝试默认配置
            success, _ = test_connection(
                DatabaseConfig.DEFAULT_HOST,
                DatabaseConfig.DEFAULT_PORT,
                DatabaseConfig.DEFAULT_USER,
                DatabaseConfig.DEFAULT_PASSWORD,
                DatabaseConfig.DEFAULT_DATABASE,
                timeout=3
            )
            self._db_connected = success
            if success:
                self._db_initialized = is_database_initialized()
                if self._db_initialized:
                    ensure_performance_indexes()
                self._image_root_configured = self.config.has_saved_image_root()
    
    def _show_db_config_on_start(self):
        """启动时显示数据库配置对话框"""
        if self._db_connected and self._db_initialized and not self._image_root_configured:
            message = "数据库已连接，但图片共享目录尚未配置\n\n请在服务器配置窗口填写图片共享目录（局域网共享路径）。"
        elif self._db_connected and not self._db_initialized:
            message = "数据库已连接，但尚未初始化\n\n请在服务器配置窗口点击「主机初始化」完成首次部署。"
        else:
            message = "无法连接到数据库服务器\n\n请先配置数据库连接。\n如果这是主机首次部署，请在服务器配置窗口点击「主机初始化」。"
        QMessageBox.warning(self, "数据库连接", message)
        self.open_server_config()

    def initUI(self):
        """初始化界面"""
        self.setFixedSize(LoginUIConfig.WINDOW_WIDTH, LoginUIConfig.WINDOW_HEIGHT)
        
        # 主布局
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)
        
        # --- 背景容器 ---
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("bg_frame")
        
        # 窗口大阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.bg_frame.setGraphicsEffect(shadow)
        
        main_layout.addWidget(self.bg_frame)
        
        # 内部布局
        bg_layout = QHBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(0)
        
        # ================= 左侧：品牌展示区 =================
        self.left_frame = QFrame()
        self.left_frame.setObjectName("left_frame")
        left_layout = QVBoxLayout(self.left_frame)
        left_layout.setContentsMargins(*LoginUIConfig.MARGIN_LEFT_FRAME)
        
        # 系统名称
        sys_title = QLabel(AppConfig.TITLE_EN)
        sys_title.setObjectName("sys_title_en")
        left_layout.addWidget(sys_title)
        
        sys_title_cn = QLabel(AppConfig.TITLE_CN)
        sys_title_cn.setObjectName("sys_title_cn")
        left_layout.addWidget(sys_title_cn)
        
        left_layout.addSpacing(LoginUIConfig.SPACING_LEFT_ITEMS)
        
        # 装饰线
        line = QFrame()
        line.setObjectName("decor_line")
        line.setFixedWidth(60)
        left_layout.addWidget(line)
        
        left_layout.addSpacing(LoginUIConfig.SPACING_LEFT_ITEMS)
        
        # 介绍词
        intro_label = QLabel(LoginUIConfig.INTRO_TEXT)
        intro_label.setObjectName("intro_label")
        left_layout.addWidget(intro_label)
        
        left_layout.addStretch()
        
        # 版本号
        ver_label = QLabel(AppConfig.VERSION)
        ver_label.setObjectName("ver_label")
        left_layout.addWidget(ver_label)

        # 版权归属
        company_label = QLabel("厦门市洋翔技术开发有限公司所属")
        company_label.setObjectName("company_label")
        company_label.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 10px;
            background: transparent;
            border: none;
            margin-top: 2px;
        """)
        left_layout.addWidget(company_label)
        left_layout.addSpacing(4)

        bg_layout.addWidget(self.left_frame, LoginUIConfig.LAYOUT_LEFT_RATIO)
        
        # ================= 右侧：登录操作区 =================
        self.right_frame = QFrame()
        self.right_frame.setObjectName("right_frame")
        right_layout = QVBoxLayout(self.right_frame)
        right_layout.setContentsMargins(*LoginUIConfig.MARGIN_RIGHT_FRAME)
        
        # --- 窗口控制按钮 ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # 主题切换按钮
        self.theme_btn = QPushButton("🌙" if self.current_theme == "light" else "☀️")
        self.theme_btn.setObjectName("theme_btn")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("切换主题")
        self.theme_btn.clicked.connect(self.toggle_theme)
        btn_layout.addWidget(self.theme_btn)
        
        min_btn = QPushButton("－")
        min_btn.setObjectName("min_btn")
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        btn_layout.addWidget(min_btn)
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("close_btn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        right_layout.addLayout(btn_layout)
        right_layout.addStretch()
        
        # 欢迎标题
        login_title = QLabel(LoginUIConfig.LOGIN_TITLE)
        login_title.setObjectName("login_title")
        right_layout.addWidget(login_title)
        
        login_subtitle = QLabel(LoginUIConfig.LOGIN_SUBTITLE)
        login_subtitle.setObjectName("login_subtitle")
        right_layout.addWidget(login_subtitle)
        
        right_layout.addSpacing(LoginUIConfig.SPACING_RIGHT_ITEMS)
        
        # 输入框区域
        self.username = QLineEdit()
        self.username.setPlaceholderText(LoginUIConfig.PLACEHOLDER_USER)
        self.username.setObjectName("input_field")
        right_layout.addWidget(self.username)
        
        right_layout.addSpacing(LoginUIConfig.SPACING_INPUT_FIELDS)
        
        self.password = QLineEdit()
        self.password.setPlaceholderText(LoginUIConfig.PLACEHOLDER_PWD)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setObjectName("input_field")
        self.password.returnPressed.connect(self.handle_login)
        right_layout.addWidget(self.password)
        
        right_layout.addSpacing(LoginUIConfig.SPACING_BEFORE_LINKS)
        
        # 记住密码与忘记密码
        link_layout = QHBoxLayout()
        self.remember_cb = QCheckBox("记住密码")
        self.remember_cb.setObjectName("remember_cb")
        self.remember_cb.setCursor(Qt.PointingHandCursor)
        link_layout.addWidget(self.remember_cb)
        
        link_layout.addStretch()
        
        forgot_btn = QPushButton("忘记密码?")
        forgot_btn.setObjectName("forgot_btn")
        forgot_btn.setCursor(Qt.PointingHandCursor)
        link_layout.addWidget(forgot_btn)
        right_layout.addLayout(link_layout)
        
        right_layout.addSpacing(LoginUIConfig.SPACING_BEFORE_LOGIN_BTN)
        
        # 登录按钮
        self.login_btn = QPushButton("登  录")
        self.login_btn.setObjectName("login_btn")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.handle_login)
        
        # 按钮光晕阴影
        btn_shadow = QGraphicsDropShadowEffect()
        btn_shadow.setBlurRadius(15)
        btn_shadow.setColor(QColor(36, 59, 85, 100))
        btn_shadow.setOffset(0, 5)
        self.login_btn.setGraphicsEffect(btn_shadow)
        
        right_layout.addWidget(self.login_btn)
        
        right_layout.addSpacing(12)
        
        # 服务器配置链接
        server_layout = QHBoxLayout()
        server_layout.setContentsMargins(0, 0, 0, 0)
        
        # 当前服务器状态
        self.server_status = QLabel()
        self.server_status.setObjectName("server_status")
        self._update_server_status()
        server_layout.addWidget(self.server_status)
        
        server_layout.addStretch()
        
        # 配置按钮
        self.server_btn = QPushButton("⚙️ 服务器配置")
        self.server_btn.setObjectName("server_btn")
        self.server_btn.setCursor(Qt.PointingHandCursor)
        self.server_btn.clicked.connect(self.open_server_config)
        server_layout.addWidget(self.server_btn)
        
        right_layout.addLayout(server_layout)
        right_layout.addStretch()
        
        bg_layout.addWidget(self.right_frame, LoginUIConfig.LAYOUT_RIGHT_RATIO)

        # --- 设置 QSS 样式 ---
        self.apply_style()

    def apply_style(self):
        """应用主题样式"""
        if self.current_theme == "light":
            self.setStyleSheet(style_login.LIGHT_THEME)
            self.theme_btn.setText("🌙")
        else:
            self.setStyleSheet(style_login.DARK_THEME)
            self.theme_btn.setText("☀️")

    def toggle_theme(self):
        """切换主题"""
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"
            
        self.apply_style()
        self.config.save_theme_preference(self.current_theme)

    def initAnimation(self):
        """初始化窗口动画"""
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(800)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.opacity_anim.start()

    def mousePressEvent(self, event):
        """鼠标按下事件 - 用于拖拽窗口"""
        if event.button() == Qt.LeftButton:
            self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 用于拖拽窗口"""
        if event.buttons() == Qt.LeftButton:
            delta = QPoint(event.globalPos() - self.oldPos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

    def resizeEvent(self, event):
        """窗口大小变化事件"""
        super().resizeEvent(event)

    def _update_server_status(self):
        """更新服务器状态显示"""
        info = DatabaseConfig.get_display_info()
        if self._db_connected and self._db_initialized and self._image_root_configured:
            self.server_status.setText(f"🟢 {info}")
            self.server_status.setStyleSheet("color: #27ae60; font-size: 11px;")
        elif self._db_connected and self._db_initialized and not self._image_root_configured:
            self.server_status.setText(f"🟡 {info}（图片目录未配置）")
            self.server_status.setStyleSheet("color: #f39c12; font-size: 11px;")
        elif self._db_connected and not self._db_initialized:
            self.server_status.setText(f"🟡 {info}（未初始化）")
            self.server_status.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:
            self.server_status.setText(f"🔴 未连接")
            self.server_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
    
    def open_server_config(self):
        """打开服务器配置对话框"""
        dialog = DbConfigDialog(self, theme=self.current_theme)
        if dialog.exec_():
            # 重新检测数据库状态（可能是保存配置，也可能是主机初始化）
            self._load_and_check_db()
            self._update_server_status()

    def load_settings(self):
        """加载保存的登录设置"""
        remember, user, pwd = auth_service.load_login_info()
        if remember:
            self.username.setText(user)
            self.password.setText(pwd)
            self.remember_cb.setChecked(True)

    def save_settings(self):
        """保存登录设置"""
        auth_service.save_login_info(
            self.remember_cb.isChecked(),
            self.username.text(),
            self.password.text()
        )

    def handle_login(self):
        """处理登录"""
        # 检查数据库连接
        if not self._db_connected:
            reply = QMessageBox.warning(
                self, 
                "数据库未连接", 
                "请先配置数据库连接",
                QMessageBox.Ok
            )
            self.open_server_config()
            return

        if not self._db_initialized:
            QMessageBox.warning(
                self,
                "数据库未初始化",
                "数据库已连接，但尚未初始化。\n请在“服务器配置”中点击「主机初始化」。",
            )
            self.open_server_config()
            return

        if not self._image_root_configured:
            QMessageBox.warning(
                self,
                "图片共享目录未配置",
                "数据库已连接，但图片共享目录尚未配置。\n请在“服务器配置”中填写局域网共享图片目录。",
            )
            self.open_server_config()
            return
        
        username = self.username.text().strip()
        password = self.password.text().strip()
        
        # 使用认证服务进行验证
        success, error_msg = auth_service.authenticate(username, password)
        
        if success:
            self.save_settings()
            # 启动时回放本地 WAL 中残留的目录字段（上次异常退出/断电留下的 pending）。
            # 放在后台线程，避免阻塞主窗口显示。
            self._replay_catalog_wal_async()
            self.main_window = MainWindow()
            self.main_window.show()
            self.close()
        else:
            QMessageBox.critical(self, "错误", error_msg)

    def _replay_catalog_wal_async(self):
        """异步回放 catalog WAL。正常情况下 WAL 是空的，几乎零开销。"""
        try:
            from PyQt5.QtCore import QThreadPool
            from common.services.catalog_wal_service import replay_pending_saves
            from main_ui.pages.inventory_ui.widgets.qt_worker import Worker

            def _do_replay():
                return replay_pending_saves()

            def _on_done(result):
                if not result:
                    return
                ok, err = result
                if ok or err:
                    print(f"[startup] catalog WAL replay: {ok} ok, {err} errors")

            worker = Worker(_do_replay)
            worker.signals.finished.connect(_on_done)
            QThreadPool.globalInstance().start(worker)
        except Exception as e:
            print(f"[startup] WAL replay scheduling failed: {e}")

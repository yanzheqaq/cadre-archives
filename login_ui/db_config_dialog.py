# -*- coding: utf-8 -*-
"""
数据库连接配置对话框
允许用户配置局域网内的数据库服务器
"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel, QFrame,
    QWidget, QFileDialog,
    QGraphicsDropShadowEffect, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from common.config import AppSettings
from common.config.db_config import DatabaseConfig
from common.db import test_connection, reset_engine, bootstrap_host_database, is_database_initialized, migrate_existing_images_to_root


class DbConfigDialog(QDialog):
    """数据库连接配置对话框"""
    
    def __init__(self, parent=None, theme: str = "light"):
        super().__init__(parent)
        self.theme = theme
        self.config = AppSettings()
        self._connected = False
        self._initialized = False
        
        self.setWindowTitle("服务器配置")
        self.setFixedSize(520, 440)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.initUI()
        self.load_saved_config()
        
        # 拖拽窗口
        self.oldPos = self.pos()
    
    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 背景容器
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("db_config_frame")
        
        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.bg_frame.setGraphicsEffect(shadow)
        
        main_layout.addWidget(self.bg_frame)
        
        # 内部布局
        layout = QVBoxLayout(self.bg_frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        
        # 标题栏
        title_layout = QHBoxLayout()
        title = QLabel("🖥️ 服务器配置")
        title.setObjectName("db_config_title")
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("db_close_btn")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        layout.addLayout(title_layout)
        
        # 说明文字
        hint = QLabel("配置局域网数据库服务器连接和图片共享目录")
        hint.setObjectName("db_config_hint")
        layout.addWidget(hint)
        
        layout.addSpacing(8)
        
        # 表单
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # IP地址
        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("如：192.168.1.100")
        self.input_host.setObjectName("db_input")
        form_layout.addRow("服务器IP：", self.input_host)
        
        # 端口
        self.input_port = QSpinBox()
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(3306)
        self.input_port.setObjectName("db_input")
        form_layout.addRow("端口：", self.input_port)
        
        # 数据库名
        self.input_database = QLineEdit()
        self.input_database.setPlaceholderText("如：pfms")
        self.input_database.setObjectName("db_input")
        form_layout.addRow("数据库：", self.input_database)
        
        # 用户名
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("如：root")
        self.input_user.setObjectName("db_input")
        form_layout.addRow("用户名：", self.input_user)
        
        # 密码
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("数据库密码")
        self.input_password.setObjectName("db_input")
        form_layout.addRow("密码：", self.input_password)

        # 图片共享目录
        self.input_image_root = QLineEdit()
        self.input_image_root.setPlaceholderText(r"如：\\192.168.1.100\cadre_images 或 D:\cadre_images")
        self.input_image_root.setObjectName("db_input")
        self.btn_browse_image_root = QPushButton("浏览")
        self.btn_browse_image_root.setObjectName("db_browse_btn")
        self.btn_browse_image_root.setCursor(Qt.PointingHandCursor)
        self.btn_browse_image_root.clicked.connect(self.on_browse_image_root)

        image_root_row = QHBoxLayout()
        image_root_row.setContentsMargins(0, 0, 0, 0)
        image_root_row.setSpacing(8)
        image_root_row.addWidget(self.input_image_root, 1)
        image_root_row.addWidget(self.btn_browse_image_root)
        image_root_widget = QWidget()
        image_root_widget.setLayout(image_root_row)
        form_layout.addRow("图片共享目录：", image_root_widget)
        
        layout.addLayout(form_layout)
        
        layout.addSpacing(8)
        
        # 状态显示
        self.status_label = QLabel("● 未连接")
        self.status_label.setObjectName("db_status_disconnected")
        layout.addWidget(self.status_label)
        
        layout.addSpacing(8)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("db_test_btn")
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.clicked.connect(self.on_test_connection)
        btn_layout.addWidget(self.test_btn)

        self.init_btn = QPushButton("主机初始化")
        self.init_btn.setObjectName("db_init_btn")
        self.init_btn.setCursor(Qt.PointingHandCursor)
        self.init_btn.setToolTip("仅主机首次部署时使用：自动创建数据库、表结构和默认模板")
        self.init_btn.clicked.connect(self.on_init_host_database)
        btn_layout.addWidget(self.init_btn)
        
        self.save_btn = QPushButton("保存并使用")
        self.save_btn.setObjectName("db_save_btn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.on_save)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
        
        # 应用样式
        self.apply_style()
    
    def apply_style(self):
        """应用主题样式"""
        if self.theme == "dark":
            bg = "#2d2d2d"
            text = "#e0e0e0"
            text_sub = "#a0a0a0"
            input_bg = "#363636"
            input_border = "#4d4d4d"
            btn_bg = "#404040"
            btn_hover = "#505050"
            accent = "#5dade2"
        else:
            bg = "#ffffff"
            text = "#1e2732"
            text_sub = "#7f8c8d"
            input_bg = "#f5f7fa"
            input_border = "#e0e0e0"
            btn_bg = "#f0f0f0"
            btn_hover = "#e0e0e0"
            accent = "#3498db"
        
        self.setStyleSheet(f"""
            #db_config_frame {{
                background-color: {bg};
                border-radius: 12px;
            }}
            #db_config_title {{
                font-size: 16px;
                font-weight: bold;
                color: {text};
            }}
            #db_config_hint {{
                font-size: 12px;
                color: {text_sub};
            }}
            #db_close_btn {{
                background: transparent;
                border: none;
                font-size: 14px;
                color: {text_sub};
                border-radius: 14px;
            }}
            #db_close_btn:hover {{
                background-color: #ff5f57;
                color: white;
            }}
            QLabel {{
                color: {text};
                font-size: 13px;
            }}
            #db_input, QSpinBox {{
                background-color: {input_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {text};
                min-height: 18px;
            }}
            #db_input:focus, QSpinBox:focus {{
                border-color: {accent};
            }}
            #db_status_disconnected {{
                color: #e74c3c;
                font-size: 12px;
            }}
            #db_status_connected {{
                color: #27ae60;
                font-size: 12px;
            }}
            #db_status_testing {{
                color: #f39c12;
                font-size: 12px;
            }}
            #db_status_uninitialized {{
                color: #f39c12;
                font-size: 12px;
            }}
            #db_test_btn {{
                background-color: {btn_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                color: {text};
            }}
            #db_test_btn:hover {{
                background-color: {btn_hover};
            }}
            #db_browse_btn {{
                background-color: {btn_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 13px;
                color: {text};
                min-width: 72px;
            }}
            #db_browse_btn:hover {{
                background-color: {btn_hover};
            }}
            #db_init_btn {{
                background-color: {btn_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 13px;
                color: {text};
            }}
            #db_init_btn:hover {{
                background-color: {btn_hover};
            }}
            #db_save_btn {{
                background-color: {accent};
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                color: white;
                font-weight: bold;
            }}
            #db_save_btn:hover {{
                background-color: #2980b9;
            }}
            #db_save_btn:disabled {{
                background-color: #bdc3c7;
            }}
        """)
    
    def load_saved_config(self):
        """加载保存的配置"""
        host, port, user, password, database = self.config.get_db_connection()
        
        if host:
            self.input_host.setText(host)
        else:
            self.input_host.setText(DatabaseConfig.DEFAULT_HOST)
        
        if port > 0:
            self.input_port.setValue(port)
        else:
            self.input_port.setValue(DatabaseConfig.DEFAULT_PORT)
        
        if user:
            self.input_user.setText(user)
        else:
            self.input_user.setText(DatabaseConfig.DEFAULT_USER)
        
        if password:
            self.input_password.setText(password)
        else:
            self.input_password.setText(DatabaseConfig.DEFAULT_PASSWORD)
        
        if database:
            self.input_database.setText(database)
        else:
            self.input_database.setText(DatabaseConfig.DEFAULT_DATABASE)

        self.input_image_root.setText(self.config.get_image_root())
    
    def get_input_values(self):
        """获取当前输入值"""
        return (
            self.input_host.text().strip(),
            self.input_port.value(),
            self.input_user.text().strip(),
            self.input_password.text(),
            self.input_database.text().strip(),
        )

    def get_image_root_value(self) -> str:
        """获取图片共享目录"""
        return self.input_image_root.text().strip()

    def on_browse_image_root(self):
        """浏览选择图片共享目录"""
        current = self.get_image_root_value()
        start_dir = current if current and os.path.isdir(current) else os.getcwd()
        path = QFileDialog.getExistingDirectory(self, "选择图片共享目录", start_dir)
        if path:
            self.input_image_root.setText(path)

    def _set_status(self, text: str, object_name: str, color: str):
        self.status_label.setText(text)
        self.status_label.setObjectName(object_name)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
    
    def on_test_connection(self):
        """测试连接"""
        host, port, user, password, database = self.get_input_values()
        
        if not host:
            QMessageBox.warning(self, "提示", "请输入服务器IP地址")
            return
        if not database:
            QMessageBox.warning(self, "提示", "请输入数据库名称")
            return
        if not user:
            QMessageBox.warning(self, "提示", "请输入用户名")
            return
        
        # 更新状态
        self.status_label.setText("● 正在连接...")
        self.status_label.setObjectName("db_status_testing")
        self.status_label.setStyleSheet("color: #f39c12; font-size: 12px;")
        self.test_btn.setEnabled(False)
        self.test_btn.setText("连接中...")
        
        # 强制刷新UI
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        
        # 测试连接
        success, message = test_connection(host, port, user, password, database)
        
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        
        if success:
            self._connected = True
            self._initialized = is_database_initialized()
            if self._initialized:
                self._set_status(f"● 连接成功 - {host}:{port}/{database}", "db_status_connected", "#27ae60")
            else:
                self._set_status(f"● 连接成功，但数据库未初始化 - {host}:{port}/{database}", "db_status_uninitialized", "#f39c12")
        else:
            self._connected = False
            self._initialized = False
            self._set_status(f"● {message}", "db_status_disconnected", "#e74c3c")

    def on_init_host_database(self):
        """主机首次初始化：创建数据库、表结构和默认模板。"""
        host, port, user, password, database = self.get_input_values()
        image_root = self.get_image_root_value()

        if not host:
            QMessageBox.warning(self, "提示", "请输入服务器IP地址")
            return
        if not database:
            QMessageBox.warning(self, "提示", "请输入数据库名称")
            return
        if not user:
            QMessageBox.warning(self, "提示", "请输入用户名")
            return
        if not image_root:
            QMessageBox.warning(self, "提示", "请输入图片共享目录")
            return

        reply = QMessageBox.question(
            self,
            "确认初始化",
            "这将创建数据库、表结构并导入默认目录模板。\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.init_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self._set_status("● 正在初始化主机数据库...", "db_status_testing", "#f39c12")

        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            os.makedirs(image_root, exist_ok=True)
            bootstrap_host_database(host, port, user, password, database)

            migrate_stats = migrate_existing_images_to_root(image_root)

            # 保存到 QSettings
            self.config.set_db_connection(host, port, user, password, database)
            self.config.set_image_root(image_root)

            # 更新运行时配置
            DatabaseConfig.set_connection(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )

            # 重置引擎
            reset_engine()

            self._connected = True
            self._initialized = True
            self._set_status(f"● 主机初始化完成 - {host}:{port}/{database}", "db_status_connected", "#27ae60")
            migrate_msg = ""
            if migrate_stats.get("total", 0) > 0:
                migrate_msg = (
                    f"\n图片迁移：共 {migrate_stats.get('total', 0)} 张，"
                    f"已复制 {migrate_stats.get('copied', 0)} 张，"
                    f"已更新 {migrate_stats.get('updated', 0)} 条路径"
                )
                if migrate_stats.get("missing", 0):
                    migrate_msg += f"，缺失 {migrate_stats.get('missing', 0)} 张"
            QMessageBox.information(
                self,
                "成功",
                f"主机数据库初始化完成\n服务器：{host}:{port}/{database}{migrate_msg}",
            )
            self.accept()
        except Exception as e:
            self._connected = False
            self._initialized = False
            self._set_status(f"● 初始化失败：{e}", "db_status_disconnected", "#e74c3c")
            QMessageBox.warning(self, "初始化失败", f"主机初始化失败：{e}")
        finally:
            self.init_btn.setEnabled(True)
            self.test_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
    
    def on_save(self):
        """保存配置"""
        host, port, user, password, database = self.get_input_values()
        image_root = self.get_image_root_value()
        
        if not host:
            QMessageBox.warning(self, "提示", "请输入服务器IP地址")
            return
        if not database:
            QMessageBox.warning(self, "提示", "请输入数据库名称")
            return
        if not image_root:
            QMessageBox.warning(self, "提示", "请输入图片共享目录")
            return
        
        # 重新测试当前输入，避免复用上一次的连接状态
        success, message = test_connection(host, port, user, password, database)
        self._connected = success
        if not success:
            reply = QMessageBox.question(
                self, "连接失败",
                f"连接测试失败：{message}\n\n是否仍要保存配置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        try:
            os.makedirs(image_root, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "提示", f"图片共享目录不可用：{e}")
            return
        
        # 保存到 QSettings
        self.config.set_db_connection(host, port, user, password, database)
        self.config.set_image_root(image_root)
        
        # 更新运行时配置
        DatabaseConfig.set_connection(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        
        # 重置引擎
        reset_engine()

        self._initialized = is_database_initialized() if self._connected else False

        if self._connected and not self._initialized:
            QMessageBox.information(
                self,
                "成功",
                f"配置已保存\n服务器：{host}:{port}/{database}\n\n提示：数据库尚未初始化，主机首次部署请点击「主机初始化」。",
            )
        else:
            QMessageBox.information(self, "成功", f"配置已保存\n服务器：{host}:{port}/{database}")
        self.accept()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldPos = event.globalPos()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.oldPos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

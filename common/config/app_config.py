# -*- coding: utf-8 -*-
"""
应用程序配置
包含应用信息、默认账号等
"""

import os
from typing import Tuple, Optional


class AppConfig:
    """应用程序静态配置"""
    
    # 应用信息
    TITLE_EN = "ARCHIVE\nSYSTEM"
    TITLE_CN = "档案数字化加工系统"
    VERSION = "Ver 2.5.0 Pro"
    
    # 默认管理员账号（仅用于开发/演示）
    DEFAULT_ADMIN_USER = "admin"
    DEFAULT_ADMIN_PASS = "123456"
    
    # 向后兼容的别名
    ADMIN_USER = DEFAULT_ADMIN_USER
    ADMIN_PASS = DEFAULT_ADMIN_PASS
    
    # 项目地点和IP (示例)
    LOCATION = "北京总部"
    IP_ADDR = "192.168.1.100"
    
    # 字体配置
    FONT_FAMILY = (
        '"Microsoft YaHei", "Segoe UI", "Noto Sans", "Noto Sans CJK SC", '
        '"Roboto", "Arial", "DejaVu Sans", '
        '"Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji", "EmojiOne Color", sans-serif'
    )
    
    # =========================================
    # 向后兼容的颜色配置
    # 原来分散的颜色配置，现在集中到 theme_config.py
    # 这里保留别名以支持旧代码
    # =========================================
    
    # 通用高亮色
    ACCENT_COLOR = "#00d2ff"
    
    # === 浅色主题 ===
    LIGHT_BG_COLOR = "#ffffff"
    LIGHT_BG_SECONDARY = "#f5f5f5"
    LIGHT_TEXT_MAIN = "#1e2732"
    LIGHT_TEXT_SUB = "#7f8c8d"
    LIGHT_INPUT_BG = "#f0f4f8"
    LIGHT_INPUT_BORDER = "#dcecf5"
    LIGHT_BTN_GRADIENT_START = "#3498db"
    LIGHT_BTN_GRADIENT_END = "#5dade2"
    
    # === 深色主题 ===
    DARK_BG_COLOR = "#1a1a1a"
    DARK_BG_SECONDARY = "#2d2d2d"
    DARK_TEXT_MAIN = "#e0e0e0"
    DARK_TEXT_SUB = "#a0a0a0"
    DARK_INPUT_BG = "#363636"
    DARK_INPUT_BORDER = "#4d4d4d"
    DARK_BTN_GRADIENT_START = "#334d6e"
    DARK_BTN_GRADIENT_END = "#4a6a8a"


class AppSettings:
    """
    应用程序动态配置管理器
    使用 QSettings 持久化存储用户偏好
    """
    
    _instance = None
    _settings = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _ensure_settings(self):
        """延迟初始化 QSettings"""
        if self._settings is None:
            from PyQt5.QtCore import QSettings
            AppSettings._settings = QSettings("Company", "ArchiveSystem")
    
    @property
    def settings(self):
        self._ensure_settings()
        return self._settings
    
    # === 主题相关 ===
    def get_theme(self) -> str:
        """获取当前主题，默认 light"""
        self._ensure_settings()
        return self._settings.value("theme", "light", type=str)
    
    def set_theme(self, theme_name: str) -> None:
        """保存主题偏好"""
        self._ensure_settings()
        self._settings.setValue("theme", theme_name)
    
    # === 登录信息相关 ===
    def get_login_info(self) -> Tuple[bool, str, str]:
        """
        获取登录信息
        返回: (remember_password, username, password)
        """
        self._ensure_settings()
        remember = self._settings.value("remember_password", False, type=bool)
        username = ""
        password = ""
        
        if remember:
            username = self._settings.value("username", "")
            password = self._settings.value("password", "")
            
        return remember, username, password
    
    def set_login_info(self, remember: bool, username: str, password: str) -> None:
        """保存登录信息"""
        self._ensure_settings()
        if remember:
            self._settings.setValue("remember_password", True)
            self._settings.setValue("username", username)
            self._settings.setValue("password", password)
        else:
            self._settings.setValue("remember_password", False)
            self._settings.remove("username")
            self._settings.remove("password")
    
    # === 数据库连接配置 ===
    def get_db_connection(self) -> Tuple[str, int, str, str, str]:
        """
        获取保存的数据库连接配置
        返回: (host, port, user, password, database)
        """
        self._ensure_settings()
        host = self._settings.value("db_host", "", type=str)
        port = self._settings.value("db_port", 0, type=int)
        user = self._settings.value("db_user", "", type=str)
        password = self._settings.value("db_password", "", type=str)
        database = self._settings.value("db_database", "", type=str)
        return host, port, user, password, database
    
    def set_db_connection(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str
    ) -> None:
        """保存数据库连接配置"""
        self._ensure_settings()
        self._settings.setValue("db_host", host)
        self._settings.setValue("db_port", port)
        self._settings.setValue("db_user", user)
        self._settings.setValue("db_password", password)
        self._settings.setValue("db_database", database)
    
    def has_saved_db_connection(self) -> bool:
        """检查是否有保存的数据库连接配置"""
        self._ensure_settings()
        host = self._settings.value("db_host", "", type=str)
        return bool(host and host.strip())

    # === 图片共享目录相关 ===
    def get_image_root(self) -> str:
        """获取图片共享根目录，优先读取持久化配置，其次环境变量，最后回退到本地 data/images。"""
        self._ensure_settings()
        root = self._settings.value("image_root", "", type=str)
        if root and str(root).strip():
            return str(root).strip()
        env_root = os.getenv("IMAGE_ROOT", "").strip()
        if env_root:
            return env_root
        return os.path.join(os.getcwd(), "data", "images")

    def set_image_root(self, image_root: str) -> None:
        """保存图片共享根目录"""
        self._ensure_settings()
        root = (image_root or "").strip()
        if root:
            self._settings.setValue("image_root", root)
        else:
            self._settings.remove("image_root")

    def has_saved_image_root(self) -> bool:
        """检查是否已保存图片共享根目录"""
        self._ensure_settings()
        root = self._settings.value("image_root", "", type=str)
        if root and str(root).strip():
            return True
        return bool(os.getenv("IMAGE_ROOT", "").strip())
    
    # === 向后兼容的别名方法 ===
    def load_theme_preference(self) -> str:
        """向后兼容：加载主题偏好"""
        return self.get_theme()
    
    def save_theme_preference(self, theme_name: str) -> None:
        """向后兼容：保存主题偏好"""
        self.set_theme(theme_name)
    
    def load_login_info(self) -> Tuple[bool, str, str]:
        """向后兼容：加载登录信息"""
        return self.get_login_info()
    
    def save_login_info(self, remember: bool, username: str, password: str) -> None:
        """向后兼容：保存登录信息"""
        self.set_login_info(remember, username, password)

    def load_image_root(self) -> str:
        """向后兼容：加载图片共享根目录"""
        return self.get_image_root()

    def save_image_root(self, image_root: str) -> None:
        """向后兼容：保存图片共享根目录"""
        self.set_image_root(image_root)

    # === 打印设置 ===
    def get_print_settings(self) -> dict:
        """获取打印设置"""
        self._ensure_settings()
        return {
            "blank_rows":    self._settings.value("print/blank_rows",    1,           type=int),
            "font_size":     self._settings.value("print/font_size",     13,          type=int),
            "font_family":   self._settings.value("print/font_family",   "楷体_GB2312", type=str),
            "bold":          self._settings.value("print/bold",          False,       type=bool),
            "margin_top":    self._settings.value("print/margin_top",    12.0,        type=float),
            "margin_bottom": self._settings.value("print/margin_bottom", 12.0,        type=float),
            "margin_left":   self._settings.value("print/margin_left",   10.0,        type=float),
            "margin_right":  self._settings.value("print/margin_right",  10.0,        type=float),
            "row_height":    self._settings.value("print/row_height",    6.0,         type=float),
            "table_scale":   self._settings.value("print/table_scale",   100,         type=int),
            "col_serial":    self._settings.value("print/col_serial",    10.0,        type=float),
            "col_year":      self._settings.value("print/col_year",      12.0,        type=float),
            "col_month":     self._settings.value("print/col_month",     9.0,         type=float),
            "col_day":       self._settings.value("print/col_day",       9.0,         type=float),
            "col_pages":     self._settings.value("print/col_pages",     12.0,        type=float),
            "col_remark":        self._settings.value("print/col_remark",         16.0,         type=float),
            "title_font_family": self._settings.value("print/title_font_family",  "黑体",        type=str),
            "title_font_size":   self._settings.value("print/title_font_size",    6.0,           type=float),
            "header_font_family":self._settings.value("print/header_font_family", "楷体_GB2312", type=str),
            "header_font_size":  self._settings.value("print/header_font_size",   3.5,           type=float),
            "header_bold":       self._settings.value("print/header_bold",        True,          type=bool),
            "data_font_family":     self._settings.value("print/data_font_family",     "楷体_GB2312", type=str),
            "data_font_size":       self._settings.value("print/data_font_size",       3.2,           type=float),
            "data_bold":            self._settings.value("print/data_bold",            False,         type=bool),
            "category_font_family": self._settings.value("print/category_font_family", "楷体_GB2312", type=str),
            "category_font_size":   self._settings.value("print/category_font_size",   3.2,           type=float),
            "category_bold":        self._settings.value("print/category_bold",        True,          type=bool),
        }

    def set_print_settings(self, settings: dict) -> None:
        """保存打印设置"""
        self._ensure_settings()
        for key, value in settings.items():
            self._settings.setValue(f"print/{key}", value)

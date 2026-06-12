# -*- coding: utf-8 -*-
"""
主题服务
处理主题切换和管理
"""

from typing import Callable, List

from common.config import AppSettings


class ThemeService:
    """
    主题服务
    统一管理应用程序的主题切换
    """
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.settings = AppSettings()
        self._current_theme = None  # 延迟初始化
        self._listeners: List[Callable[[str], None]] = []
    
    def _ensure_theme_loaded(self):
        """延迟加载主题设置"""
        if self._current_theme is None:
            self._current_theme = self.settings.get_theme()
    
    @property
    def current_theme(self) -> str:
        """获取当前主题"""
        self._ensure_theme_loaded()
        return self._current_theme
    
    def toggle_theme(self) -> str:
        """
        切换主题
        
        Returns:
            切换后的主题名称
        """
        self._ensure_theme_loaded()
        if self._current_theme == "light":
            self._current_theme = "dark"
        else:
            self._current_theme = "light"
        
        # 保存偏好
        self.settings.set_theme(self._current_theme)
        
        # 通知所有监听器
        self._notify_listeners()
        
        return self._current_theme
    
    def set_theme(self, theme: str) -> None:
        """设置主题"""
        if theme not in ("light", "dark"):
            return
        
        self._current_theme = theme
        self.settings.set_theme(theme)
        self._notify_listeners()
    
    def add_listener(self, callback: Callable[[str], None]) -> None:
        """
        添加主题变化监听器
        
        Args:
            callback: 回调函数，接收新主题名称作为参数
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[str], None]) -> None:
        """移除主题变化监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def _notify_listeners(self) -> None:
        """通知所有监听器"""
        for listener in self._listeners:
            try:
                listener(self._current_theme)
            except Exception as e:
                print(f"[ThemeService] notify listener failed: {e}")
    
    def is_dark(self) -> bool:
        """是否为深色主题"""
        self._ensure_theme_loaded()
        return self._current_theme == "dark"
    
    def is_light(self) -> bool:
        """是否为浅色主题"""
        self._ensure_theme_loaded()
        return self._current_theme == "light"


# 单例实例
theme_service = ThemeService()

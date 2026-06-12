# -*- coding: utf-8 -*-
"""
主题配置
包含浅色和深色主题的颜色定义
"""


class ThemeConfig:
    """主题通用配置"""
    
    # 通用高亮色
    ACCENT_COLOR = "#00d2ff"


class LightTheme:
    """浅色主题配置"""
    
    # 背景色
    BG_COLOR = "#ffffff"
    BG_SECONDARY = "#f5f5f5"
    
    # 文字颜色
    TEXT_MAIN = "#1e2732"
    TEXT_SUB = "#7f8c8d"
    
    # 输入框
    INPUT_BG = "#f0f4f8"
    INPUT_BORDER = "#dcecf5"
    
    # 按钮渐变色
    BTN_GRADIENT_START = "#3498db"
    BTN_GRADIENT_END = "#5dade2"
    
    # 菜单颜色
    MENU_TEXT = "#ffffff"
    MENU_HOVER_BG = "rgba(255, 255, 255, 0.2)"
    MENU_CHECKED_BG = "rgba(255, 255, 255, 0.35)"
    MENU_CHECKED_TEXT = "#000000"
    
    # 控制按钮颜色
    CONTROL_TEXT = "#ffffff"
    CONTROL_HOVER_BG = "rgba(255, 255, 255, 0.2)"
    
    # 关闭按钮特殊颜色
    CLOSE_BTN_HOVER = "#e74c3c"


class DarkTheme:
    """深色主题配置"""
    
    # 背景色
    BG_COLOR = "#1a1a1a"
    BG_SECONDARY = "#2d2d2d"
    
    # 文字颜色
    TEXT_MAIN = "#e0e0e0"
    TEXT_SUB = "#a0a0a0"
    
    # 输入框
    INPUT_BG = "#363636"
    INPUT_BORDER = "#4d4d4d"
    
    # 按钮渐变色
    BTN_GRADIENT_START = "#334d6e"
    BTN_GRADIENT_END = "#4a6a8a"
    
    # 菜单颜色
    MENU_TEXT = "rgba(255, 255, 255, 0.6)"
    MENU_HOVER_BG = "rgba(255, 255, 255, 0.1)"
    MENU_CHECKED_BG = "rgba(255, 255, 255, 0.2)"
    MENU_CHECKED_TEXT = ThemeConfig.ACCENT_COLOR
    
    # 控制按钮颜色
    CONTROL_TEXT = "rgba(255, 255, 255, 0.6)"
    CONTROL_HOVER_BG = "rgba(255, 255, 255, 0.1)"
    
    # 关闭按钮特殊颜色
    CLOSE_BTN_HOVER = "#D32F2F"

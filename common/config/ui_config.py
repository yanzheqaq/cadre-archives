# -*- coding: utf-8 -*-
"""
UI 配置
包含登录窗口、主窗口、页面等所有 UI 相关配置
"""


class UIConfig:
    """UI 通用配置"""
    
    # 字体缩放范围
    FONT_MIN_SIZE = 9
    FONT_MAX_SIZE = 20


class LoginUIConfig:
    """登录窗口配置"""
    
    # 窗口尺寸
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 550
    
    # 介绍文案
    INTRO_TEXT = (
        "智慧档案 · 数据赋能\n\n"
        "INTELLIGENT ARCHIVING\n"
        "DIGITAL PROCESSING"
    )
    
    # 文本内容
    LOGIN_TITLE = "欢迎登录"
    LOGIN_SUBTITLE = "Please sign in to continue"
    PLACEHOLDER_USER = "请输入工号/账号"
    PLACEHOLDER_PWD = "请输入密码"
    
    # === 布局与样式参数 ===
    # 界面布局比例 (总和建议为 100)
    LAYOUT_LEFT_RATIO = 45
    LAYOUT_RIGHT_RATIO = 55

    # 字体大小设置 (单位: px)
    FONT_SIZE_TITLE_EN = 36       # 左侧英文大标题
    FONT_SIZE_TITLE_CN = 20       # 左侧中文标题
    FONT_SIZE_INTRO = 14          # 左侧介绍文案
    FONT_SIZE_VER = 12            # 左侧底部版本号
    
    FONT_SIZE_LOGIN_TITLE = 28    # 右侧"欢迎登录"标题
    FONT_SIZE_LOGIN_SUBTITLE = 14 # 右侧"Please sign in..."副标题
    FONT_SIZE_INPUT = 14          # 输入框内文字大小
    FONT_SIZE_BTN = 16            # 登录按钮文字大小
    FONT_SIZE_SMALL = 13          # 记住密码、忘记密码、右上角控制按钮

    # 间距和边距 (单位: px)
    MARGIN_LEFT_FRAME = (50, 60, 50, 60)  # (left, top, right, bottom)
    MARGIN_RIGHT_FRAME = (50, 40, 50, 40) # (left, top, right, bottom)
    
    SPACING_LEFT_ITEMS = 30       # 左侧垂直间距
    
    SPACING_RIGHT_ITEMS = 40      # 右侧主间距
    SPACING_INPUT_FIELDS = 15     # 输入框间距
    SPACING_BEFORE_LINKS = 10     # 链接前间距
    SPACING_BEFORE_LOGIN_BTN = 30 # 按钮前间距


class MainUIConfig:
    """主窗口配置"""
    
    # === 窗口尺寸参数 ===
    WINDOW_WIDTH = 1280
    WINDOW_HEIGHT = 800
    
    # === 标题 ===
    APP_TITLE = "档案数字化加工系统"

    # === 布局尺寸参数 ===
    HEADER_HEIGHT = 100
    TITLE_ROW_HEIGHT = 40
    MENU_ROW_HEIGHT = 60
    
    # === 标题栏内部布局参数 ===
    TITLE_BAR_MARGINS = (15, 10) 
    TITLE_BAR_SPACING = 10
    SEPARATOR_HEIGHT = 20
    LOGO_FONT_SIZE = 14
    INFO_FONT_SIZE = 12
    
    # === Logo 参数 ===
    LOGO_WIDTH = 120
    
    # === 按钮尺寸参数 ===
    CONTROL_BTN_SIZE = 28
    THEME_BTN_SIZE = 25
    
    # === 菜单相关参数 ===
    MENU_SPACING = 5
    MENU_FONT_SIZE = 15
    MENU_PADDING_X = 15
    MENU_HEIGHT_OFFSET = 10
    
    # === 侧边栏菜单定义 ===
    MENU_ITEMS = [
        ("馆藏", "🏢"),
        ("保管", "🔒"),
        ("统计", "📊"),
        ("维护", "🔧"),
        ("用户", "👥"),
        ("设置", "🛠️"),
        ("系统", "⚙️")
    ]

    # === 样式相关参数 ===
    BTN_RADIUS = 4
    BTN_FONT_WEIGHT = "bold"
    
    # === 浅色主题 - 菜单样式 ===
    LIGHT_MENU_TEXT = "#ffffff"
    LIGHT_MENU_HOVER_BG = "rgba(255, 255, 255, 0.2)"
    LIGHT_MENU_CHECKED_BG = "rgba(255, 255, 255, 0.35)"
    LIGHT_MENU_CHECKED_TEXT_COLOR = "#000000"
    
    # === 浅色主题 - 控制按钮样式 ===
    LIGHT_CONTROL_TEXT = "#ffffff"
    LIGHT_CONTROL_HOVER_BG = "rgba(255, 255, 255, 0.2)"
    CLOSE_BTN_HOVER_COLOR = "#e74c3c"
    
    # === 深色主题 - 菜单样式 ===
    DARK_MENU_TEXT = "rgba(255, 255, 255, 0.6)"
    DARK_MENU_HOVER_BG = "rgba(255, 255, 255, 0.1)"
    DARK_MENU_CHECKED_BG = "rgba(255, 255, 255, 0.2)"
    DARK_MENU_CHECKED_TEXT_COLOR = "#00d2ff"  # ACCENT_COLOR
    
    # === 深色主题 - 控制按钮样式 ===
    DARK_CONTROL_TEXT = "rgba(255, 255, 255, 0.6)"
    DARK_CONTROL_HOVER_BG = "rgba(255, 255, 255, 0.1)"
    CLOSE_BTN_HOVER_COLOR_DARK = "#D32F2F"


class PagesUIConfig:
    """页面通用配置"""
    
    # === 二级导航相关参数 ===
    SUB_NAV_HEIGHT = 70
    SUB_NAV_SPACING = 5
    SUB_NAV_ICON_FONT_SIZE = 18
    SUB_NAV_FONT_SIZE = 12

    # === 搜索栏相关参数 ===
    SEARCH_BAR_PADDING_X = 15
    SEARCH_BAR_PADDING_Y = 8
    SEARCH_BAR_SPACING = 15
    SEARCH_LABEL_FONT_SIZE = 13
    SEARCH_DATE_WIDTH = 130
    SEARCH_BTN_WIDTH = 80
    SEARCH_BTN_HEIGHT = 32

    # === 批次功能区图标 ===
    BATCH_FUNC_ICON_SIZE = 20
    BATCH_FUNC_ICON_SPACING = 8

    # === 馆藏模块子菜单 ===
    INVENTORY_SUB_MENUS = [
        ("机构管理", "🏢"),
        ("信息录入", "📝"),
        ("目录管理", "📋"),
        ("初验", "✓"),
        ("装订", "📕"),
        ("验收", "✅"),
        ("归档", "📁"),
        ("批次查询", "🔍"),
        ("高级查询", "🔎"),
    ]

    # === 保管模块子菜单 ===
    CUSTODY_SUB_MENUS = [
        ("卷宗一览", "📁"),
        ("借阅管理", "📚"),
        ("归还管理", "🔄"),
        ("销毁管理", "🗑️")
    ]

    # === 统计模块子菜单 ===
    STATS_SUB_MENUS = [
        ("数据概览", "📊"),
        ("业务统计", "📈"),
        ("报表导出", "📤")
    ]

    # === 维护模块子菜单 ===
    MAINTENANCE_SUB_MENUS = [
        ("数据备份", "💾"),
        ("数据恢复", "🔄"),
        ("日志管理", "📝")
    ]

    # === 用户模块子菜单 ===
    USER_SUB_MENUS = [
        ("用户列表", "👥"),
        ("角色管理", "🎭"),
        ("权限管理", "🔐")
    ]

    # === 设置模块子菜单 ===
    SETTINGS_SUB_MENUS = [
        ("系统设置", "⚙️"),
        ("个人设置", "👤"),
        ("通知设置", "🔔")
    ]

    # === 系统模块子菜单 ===
    SYSTEM_SUB_MENUS = [
        ("系统信息", "ℹ️"),
        ("更新检查", "🔄"),
        ("关于", "📖")
    ]

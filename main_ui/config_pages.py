# -*- coding: utf-8 -*-
"""
页面配置模块
定义各功能页面的子菜单配置
"""

from common.config import AppConfig


class PagesConfig:
    """
    页面通用配置
    """
    # 二级导航栏高度 (增加高度以容纳图标和文字)
    SUB_NAV_HEIGHT = 80
    
    # 二级导航栏字体大小 (文字部分)
    SUB_NAV_FONT_SIZE = 13

    # 二级导航栏图标字体大小 (控制Emoji图标大小)
    SUB_NAV_ICON_FONT_SIZE = 36
    
    # 二级导航栏按钮间距
    SUB_NAV_SPACING = 8
    
    # 内容区域内边距
    CONTENT_PADDING = 14
    
    # === 搜索栏配置 ===
    SEARCH_BAR_PADDING_X = 20
    SEARCH_BAR_PADDING_Y = 10
    SEARCH_BAR_SPACING = 15
    
    # 输入框最小宽度
    SEARCH_INPUT_MIN_WIDTH = 180
    # 日期输入框固定宽度
    SEARCH_DATE_WIDTH = 140
    # 输入框高度
    SEARCH_INPUT_HEIGHT = 28

    # === 档案接收功能按钮配置 ===
    BATCH_FUNC_ICON_SIZE = 22
    BATCH_FUNC_ICON_SPACING = 8
    
    # 查询/重置按钮宽度
    SEARCH_BTN_WIDTH = 70
    SEARCH_BTN_HEIGHT = 32
    
    # 标签文字大小
    SEARCH_LABEL_FONT_SIZE = 13
    SEARCH_INPUT_FONT_SIZE = 16


class IncrementConfig:
    """增量页面配置"""
    SUB_MENUS = [
        ("档案接收", "📥"), 
        ("前处理", "🛠️"), 
        ("扫描", "📷"), 
        ("图像处理", "🖼️"), 
        ("质检", "✅"), 
        ("挂接", "🔗")
    ]

class InventoryConfig:
    """馆藏页面配置"""
    SUB_MENUS = [
        ("机构管理", "📥"), 
        ("信息录入", "📝"), 
        ("目录管理", "📷"), 
        ("AI修图", "🎨"), 
        ("装订", "📚"), 
        ("验收", "✅"), 
        ("归档", "🗄️"), 
        ("批次查询", "📦"), 
        ("高级查询", "🔎")
    ]

class CustodyConfig:
    """保管页面配置"""
    SUB_MENUS = [
        ("借阅管理", "📖"), 
        ("温湿度记录", "🌡️"), 
        ("鉴定销毁", "🗑️")
    ]

class StatsConfig:
    """统计页面配置"""
    SUB_MENUS = [
        ("成果登记表", "📝"), 
        ("成果结算表", "💰"), 
        ("成果验收表", "✅"), 
        ("工作量统计", "📊"), 
        ("工作量周表", "📅"), 
        ("工作量月表", "🗓️"), 
        ("项目工资表", "💸"), 
        ("项目进度表", "📈")
    ]

class MaintenanceConfig:
    """维护页面配置"""
    SUB_MENUS = [
        ("批次维护", "📦"),
        ("案件维护", "📁")
    ]

class UserConfig:
    """用户页面配置"""
    SUB_MENUS = [
        ("用户管理", "👥"), 
        ("角色管理", "🏷️"), 
        ("菜单设定", "📋"), 
        ("菜单权限", "🔐"), 
        ("档案权限", "🗄️")
    ]

class SettingsConfig:
    """设置页面配置"""
    SUB_MENUS = [
        ("注册信息", "📝"),
        ("终端管理", "💻"),
        ("用户许可", "📜"),
        ("流程设置", "🔄"),
        ("服务器设置", "🖥️"),
        ("电子图片位置", "📂"),
        ("录入设置", "⌨️"),
        ("数据字典", "📚"),
        ("系统配置", "⚙️")
    ]

class SystemConfig:
    """系统页面配置"""
    SUB_MENUS = [
        ("系统日志", "📝"), 
        ("版本说明", "ℹ️"),
        ("用户手册", "📖"),
        ("修改密码", "🔑"),
        ("注销登陆", "🚪"),
        ("退出系统", "❌")
    ]

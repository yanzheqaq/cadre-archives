from common.config import AppConfig
from .config_pages import PagesConfig

# 页面通用样式 (浅色)
LIGHT_PAGE_STYLE = f"""
/* === 二级导航栏 === */
#sub_nav_bar {{
    background-color: #ffffff;
    border-bottom: 1px solid {AppConfig.LIGHT_INPUT_BORDER};
}}

/* 导航按钮容器 */
#sub_nav_btn {{
    color: {AppConfig.LIGHT_TEXT_MAIN}; /* 强制使用深色文字 */
    border: none;
    background: transparent;
    border-radius: 6px;
    padding: 2px;
}}

#sub_nav_btn:hover {{
    background-color: {AppConfig.LIGHT_INPUT_BG};
}}

#sub_nav_btn:checked {{
    background-color: {AppConfig.LIGHT_BTN_GRADIENT_START}; 
}}

/* 按钮内部 Label 样式适配 */
#sub_nav_btn QLabel {{
    background: transparent;
    color: {AppConfig.LIGHT_TEXT_MAIN};
}}

/* 专门指定 Emoji 图标的字体，优先使用彩色 Emoji 字体 */
#sub_nav_btn #icon_label {{
    font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "EmojiOne Color", sans-serif;
}}

#sub_nav_btn:hover QLabel {{
    color: {AppConfig.LIGHT_TEXT_MAIN};
}}

#sub_nav_btn:checked QLabel {{
    color: {AppConfig.LIGHT_TEXT_MAIN};
    font-weight: bold;
}}

/* === 搜索栏 === */
#search_bar {{
    background-color: #ffffff; /* 浅色背景 */
    border-bottom: 1px solid #e5e7eb; /* 浅灰分割线 */
}}

#search_bar QLabel {{
    color: #374151; /* 深灰文字 */
    font-weight: 500;
}}

#search_bar QLineEdit {{
    border: 1px solid #d1d5db;
    background-color: #ffffff;
    color: #111827;
    selection-background-color: {AppConfig.ACCENT_COLOR};
    min-width: {PagesConfig.SEARCH_INPUT_MIN_WIDTH}px; /* 使用配置参数 */
    font-size: {PagesConfig.SEARCH_INPUT_FONT_SIZE}px;
    height: {PagesConfig.SEARCH_INPUT_HEIGHT}px; /* [新增] 显式设置高度 */
}}

#search_bar QLineEdit:focus {{
    border: 1px solid {AppConfig.ACCENT_COLOR};
}}

#search_bar QDateEdit {{
    border: 1px solid #d1d5db;
    background-color: #ffffff;
    color: #111827;
    font-size: {PagesConfig.SEARCH_INPUT_FONT_SIZE}px;
    height: {PagesConfig.SEARCH_INPUT_HEIGHT}px; /* [新增] 显式设置高度 */
}}

#search_bar QDateEdit::drop-down {{
    border: none;
    background: transparent;
    width: 20px;
}}

#search_bar QDateEdit::down-arrow {{
    width: 0; 
    height: 0; 
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #555; /* 浅色模式下的箭头颜色 */
    margin-top: 2px;
    margin-right: 5px;
}}

/* 修复 QCalendarWidget 在浅色模式下的样式 */
QCalendarWidget QWidget {{
    background-color: #ffffff;
    color: #111827;
}}
QCalendarWidget QToolButton {{
    color: #111827;
    background-color: transparent;
}}
QCalendarWidget QMenu {{
    background-color: #ffffff;
    color: #111827;
}}
QCalendarWidget QSpinBox {{
    background-color: #ffffff;
    color: #111827;
    selection-background-color: {AppConfig.ACCENT_COLOR};
    selection-color: #ffffff;
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: #ffffff;
    color: #111827;
    selection-background-color: {AppConfig.ACCENT_COLOR};
    selection-color: #ffffff;
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: #9ca3af;
}}

/* === 搜索按钮 (浅色) === */
#btn_search {{
    background-color: {AppConfig.ACCENT_COLOR};
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: bold;
    font-size: {PagesConfig.SEARCH_LABEL_FONT_SIZE}px;
}}

#btn_search:hover {{
    background-color: #1d4ed8;
}}

#btn_search:pressed {{
    background-color: #1e40af;
}}

#btn_reset {{
    background-color: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    font-size: {PagesConfig.SEARCH_LABEL_FONT_SIZE}px;
}}

#btn_reset:hover {{
    background-color: #e5e7eb;
}}

#btn_reset:pressed {{
    background-color: #d1d5db;
}}

/* === 内容区域 === */
#page_content {{
    background-color: transparent;
}}
"""

# 页面通用样式 (深色)
DARK_PAGE_STYLE = f"""
/* === 二级导航栏 === */
#sub_nav_bar {{
    background-color: #252526;
    border-bottom: 1px solid #333;
}}

/* 导航按钮容器 */
#sub_nav_btn {{
    color: {AppConfig.DARK_TEXT_MAIN};
    border: none;
    background: transparent;
    border-radius: 6px;
    padding: 2px;
}}

#sub_nav_btn:hover {{
    background-color: {AppConfig.DARK_INPUT_BG};
}}

#sub_nav_btn:checked {{
    background-color: {AppConfig.DARK_BTN_GRADIENT_START};
}}

/* 按钮内部 Label 样式适配 */
#sub_nav_btn QLabel {{
    background: transparent;
    color: inherit;
}}

/* 专门指定 Emoji 图标的字体 */
#sub_nav_btn #icon_label {{
    font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "EmojiOne Color", sans-serif;
}}

#sub_nav_btn:hover QLabel {{
    color: {AppConfig.ACCENT_COLOR};
}}

#sub_nav_btn:checked QLabel {{
    color: #ffffff;
}}

/* === 搜索栏 (深色) === */
#search_bar {{
    background-color: #1e1e1e;
    border-bottom: 1px solid #333;
}}

#search_bar QLabel {{
    color: #d1d5db;
}}

#search_bar QLineEdit {{
    border: 1px solid #4b5563;
    background-color: #374151;
    color: #f3f4f6;
    selection-background-color: {AppConfig.ACCENT_COLOR};
    min-width: {PagesConfig.SEARCH_INPUT_MIN_WIDTH}px; /* 使用配置参数 */
    font-size: {PagesConfig.SEARCH_INPUT_FONT_SIZE}px;
    height: {PagesConfig.SEARCH_INPUT_HEIGHT}px; /* [新增] 显式设置高度 */
}}

#search_bar QLineEdit:focus {{
    border: 1px solid {AppConfig.ACCENT_COLOR};
}}

#search_bar QDateEdit {{
    border: 1px solid #4b5563;
    background-color: #374151;
    color: #f3f4f6; /* 确保文字颜色为浅灰色 */
    font-size: {PagesConfig.SEARCH_INPUT_FONT_SIZE}px;
    height: {PagesConfig.SEARCH_INPUT_HEIGHT}px; /* [新增] 显式设置高度 */
}}

/* 修复 QCalendarWidget 在深色模式下的样式 */
QCalendarWidget QWidget {{
    background-color: #374151;
    color: #f3f4f6;
}}
QCalendarWidget QToolButton {{
    color: #f3f4f6;
    background-color: transparent;
}}
QCalendarWidget QMenu {{
    background-color: #374151;
    color: #f3f4f6;
}}
QCalendarWidget QSpinBox {{
    background-color: #374151;
    color: #f3f4f6;
    selection-background-color: #1e3a8a;
    selection-color: #ffffff;
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: #374151;
    color: #f3f4f6;
    selection-background-color: #1e3a8a;
    selection-color: #ffffff;
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: #6b7280;
}}

#search_bar QDateEdit::drop-down {{
    border: none;
    background: transparent;
    width: 20px;
}}

#search_bar QDateEdit::down-arrow {{
    width: 0; 
    height: 0; 
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #ccc; /* 深色模式下的箭头颜色 */
    margin-top: 2px;
    margin-right: 5px;
}}

/* === 搜索按钮 (深色) === */
#btn_search {{
    background-color: #1e3a8a; /* 使用更深沉的藏蓝色 (Blue 900)，大幅降低亮度 */
    color: #e2e8f0; /* 文字稍微灰一点点，不那么刺眼 */
    border: 1px solid #1e40af; /* 加一个稍微亮一点的边框增加层次感 */
    border-radius: 4px;
    font-weight: bold;
    font-size: {PagesConfig.SEARCH_LABEL_FONT_SIZE}px;
}}

#btn_search:hover {{
    background-color: #1e40af; /* 悬停时稍微亮一点 (Blue 800) */
}}

#btn_search:pressed {{
    background-color: #1d4ed8;
}}

#btn_reset {{
    background-color: #374151;
    color: #d1d5db;
    border: 1px solid #4b5563;
    border-radius: 4px;
    font-size: {PagesConfig.SEARCH_LABEL_FONT_SIZE}px;
}}

#btn_reset:hover {{
    background-color: #4b5563;
}}

#btn_reset:pressed {{
    background-color: #374151;
}}

/* === 内容区域 === */
#page_content {{
    background-color: transparent;
}}
"""

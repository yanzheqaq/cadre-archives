from common.config import AppConfig, MainUIConfig

# 浅色主题 (主窗口)
LIGHT_THEME = f"""
/* === 全局设置 === */
QWidget {{
    font-family: {AppConfig.FONT_FAMILY};
    border-radius: 4px;
}}

/* === 自定义标题栏 (浅色) === */
#top_toolbar {{
    background-color: {AppConfig.LIGHT_BTN_GRADIENT_START};
    border-bottom: 1px solid {AppConfig.LIGHT_INPUT_BORDER};
}}

#menu_btn {{
    text-align: center;
    padding: 0 {MainUIConfig.MENU_PADDING_X}px;
    color: {MainUIConfig.LIGHT_MENU_TEXT};
    border: none;
    font-size: {MainUIConfig.MENU_FONT_SIZE}px;
    background-color: transparent;
    border-radius: {MainUIConfig.BTN_RADIUS}px;
    margin: 2px;
    font-weight: {MainUIConfig.BTN_FONT_WEIGHT};
}}

#menu_btn:hover {{
    background-color: {MainUIConfig.LIGHT_MENU_HOVER_BG};
    color: #ffffff;
}}

#menu_btn:checked {{
    background-color: {MainUIConfig.LIGHT_MENU_CHECKED_BG};
    color: {MainUIConfig.LIGHT_MENU_CHECKED_TEXT_COLOR};
}}

/* 窗口控制按钮 */
#min_btn, #max_btn, #close_btn, #theme_btn {{
    border: none;
    color: {MainUIConfig.LIGHT_CONTROL_TEXT};
    background: transparent;
    font-size: 14px;
}}

#min_btn:hover, #max_btn:hover, #theme_btn:hover {{
    background-color: {MainUIConfig.LIGHT_CONTROL_HOVER_BG};
    color: white;
}}

#close_btn:hover {{
    background-color: {MainUIConfig.CLOSE_BTN_HOVER_COLOR};
    color: white;
}}

#main_content_area {{
    background-color: {AppConfig.LIGHT_INPUT_BG};
}}
"""

# 深色主题 (主窗口)
DARK_THEME = f"""
/* === 全局设置 === */
QWidget {{
    font-family: {AppConfig.FONT_FAMILY};
    border-radius: 4px;
}}

/* === 自定义标题栏 (深色) === */
#top_toolbar {{
    background-color: #0f0f0f;
    border-bottom: 1px solid #333;
}}

#menu_btn {{
    text-align: center;
    padding: 0 {MainUIConfig.MENU_PADDING_X}px;
    color: {MainUIConfig.DARK_MENU_TEXT};
    border: none;
    font-size: {MainUIConfig.MENU_FONT_SIZE}px;
    background-color: transparent;
    border-radius: {MainUIConfig.BTN_RADIUS}px;
    margin: 2px;
    font-weight: {MainUIConfig.BTN_FONT_WEIGHT};
}}

#menu_btn:hover {{
    background-color: {MainUIConfig.DARK_MENU_HOVER_BG};
    color: #ffffff;
}}

#menu_btn:checked {{
    background-color: {MainUIConfig.DARK_MENU_CHECKED_BG};
    color: {MainUIConfig.DARK_MENU_CHECKED_TEXT_COLOR};
}}

/* 窗口控制按钮 */
#min_btn, #max_btn, #close_btn, #theme_btn {{
    border: none;
    color: {MainUIConfig.DARK_CONTROL_TEXT};
    background: transparent;
    font-size: 14px;
}}

#min_btn:hover, #max_btn:hover, #theme_btn:hover {{
    background-color: {MainUIConfig.DARK_CONTROL_HOVER_BG};
    color: white;
}}

#close_btn:hover {{
    background-color: {MainUIConfig.CLOSE_BTN_HOVER_COLOR_DARK};
    color: white;
}}

#main_content_area {{
    background-color: #121212;
}}
"""

from common.config import AppConfig, LoginUIConfig

# 浅色主题 (登录)
LIGHT_THEME = f"""
/* === 全局设置 === */
QWidget {{
    font-family: {AppConfig.FONT_FAMILY};
}}

#bg_frame {{
    background-color: {AppConfig.LIGHT_BG_COLOR};
    border-radius: 20px;
}}

/* === 左侧美化 === */
#left_frame {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #141E30, stop:1 #243B55);
    border-top-left-radius: 20px;
    border-bottom-left-radius: 20px;
}}

#sys_title_en {{
    font-family: "Segoe UI Black", "Arial Black";
    font-size: {LoginUIConfig.FONT_SIZE_TITLE_EN}px;
    font-weight: bold;
    color: rgba(255, 255, 255, 0.9);
    line-height: 40px;
}}

#sys_title_cn {{
    font-size: {LoginUIConfig.FONT_SIZE_TITLE_CN}px;
    font-weight: bold;
    color: rgba(255, 255, 255, 0.8);
    margin-top: 10px;
}}

#decor_line {{
    background-color: {AppConfig.ACCENT_COLOR};
    border: none;
    height: 4px;
    border-radius: 2px;
}}

#intro_label {{
    color: rgba(255, 255, 255, 0.6);
    font-size: {LoginUIConfig.FONT_SIZE_INTRO}px;
    line-height: 24px;
    letter-spacing: 1px;
}}

#ver_label {{
    color: rgba(255, 255, 255, 0.3);
    font-size: {LoginUIConfig.FONT_SIZE_VER}px;
}}

/* === 右侧美化 === */
#right_frame {{
    background-color: {AppConfig.LIGHT_BG_COLOR};
    border-top-right-radius: 20px;
    border-bottom-right-radius: 20px;
}}

#login_title {{
    font-size: {LoginUIConfig.FONT_SIZE_LOGIN_TITLE}px;
    font-weight: bold;
    color: {AppConfig.LIGHT_TEXT_MAIN};
}}

#login_subtitle {{
    font-size: {LoginUIConfig.FONT_SIZE_LOGIN_SUBTITLE}px;
    color: {AppConfig.LIGHT_TEXT_SUB};
    margin-top: 5px;
}}

/* 输入框样式 */
#input_field {{
    background-color: {AppConfig.LIGHT_INPUT_BG};
    border: 1px solid {AppConfig.LIGHT_INPUT_BORDER};
    border-radius: 8px;
    padding: 14px;
    font-size: {LoginUIConfig.FONT_SIZE_INPUT}px;
    color: #333;
}}

#input_field:hover {{
    background-color: #FFFFFF;
    border: 1px solid #C0C4CC;
}}

#input_field:focus {{
    background-color: #FFFFFF;
    border: 1px solid #243B55;
}}

/* 登录按钮 */
#login_btn {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 {AppConfig.LIGHT_BTN_GRADIENT_START}, stop:1 {AppConfig.LIGHT_BTN_GRADIENT_END});
    color: white;
    font-size: {LoginUIConfig.FONT_SIZE_BTN}px;
    font-weight: bold;
    border-radius: 8px;
    padding: 14px;
    border: none;
}}

#login_btn:hover {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #1c2b42, stop:1 #2d4b6b);
}}

#login_btn:pressed {{
    background-color: #0f1724;
    padding-top: 15px;
}}

/* 杂项 */
#remember_cb {{
    color: {AppConfig.LIGHT_TEXT_SUB};
    font-size: {LoginUIConfig.FONT_SIZE_SMALL}px;
    spacing: 5px;
}}

#forgot_btn {{
    background-color: transparent;
    color: {AppConfig.LIGHT_TEXT_SUB};
    border: none;
    font-size: {LoginUIConfig.FONT_SIZE_SMALL}px;
}}

#forgot_btn:hover {{
    color: {AppConfig.LIGHT_BTN_GRADIENT_END};
    text-decoration: underline;
}}

#close_btn, #min_btn, #theme_btn {{
    border: none;
    background: transparent;
    font-size: 18px;
    color: {AppConfig.LIGHT_TEXT_SUB};
    padding: 5px;
}}

#close_btn:hover {{
    color: #F56C6C;
    background-color: rgba(245, 108, 108, 0.1);
    border-radius: 4px;
}}

#min_btn:hover {{
    color: #409EFF;
    background-color: rgba(64, 158, 255, 0.1);
    border-radius: 4px;
}}

#theme_btn:hover {{
    color: {AppConfig.LIGHT_BTN_GRADIENT_END};
    background-color: rgba(36, 59, 85, 0.1);
    border-radius: 4px;
}}

/* 服务器配置 */
#server_status {{
    color: {AppConfig.LIGHT_TEXT_SUB};
    font-size: 11px;
}}

#server_btn {{
    background-color: transparent;
    color: {AppConfig.LIGHT_TEXT_SUB};
    border: none;
    font-size: 11px;
    padding: 4px 8px;
}}

#server_btn:hover {{
    color: {AppConfig.LIGHT_BTN_GRADIENT_END};
    text-decoration: underline;
}}
"""

# 深色主题 (登录)
DARK_THEME = f"""
/* === 全局设置 === */
QWidget {{
    font-family: {AppConfig.FONT_FAMILY};
}}

#bg_frame {{
    background-color: {AppConfig.DARK_BG_COLOR};
    border-radius: 20px;
    border: 1px solid #333;
}}

/* === 左侧美化 === */
#left_frame {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #0f0f0f, stop:1 #2c2c2c);
    border-top-left-radius: 20px;
    border-bottom-left-radius: 20px;
}}

#sys_title_en {{
    font-family: "Segoe UI Black", "Arial Black";
    font-size: {LoginUIConfig.FONT_SIZE_TITLE_EN}px;
    font-weight: bold;
    color: rgba(255, 255, 255, 0.9);
    line-height: 40px;
}}

#sys_title_cn {{
    font-size: {LoginUIConfig.FONT_SIZE_TITLE_CN}px;
    font-weight: bold;
    color: rgba(255, 255, 255, 0.8);
    margin-top: 10px;
}}

#decor_line {{
    background-color: {AppConfig.ACCENT_COLOR};
    border: none;
    height: 4px;
    border-radius: 2px;
}}

#intro_label {{
    color: rgba(255, 255, 255, 0.6);
    font-size: {LoginUIConfig.FONT_SIZE_INTRO}px;
    line-height: 24px;
    letter-spacing: 1px;
}}

#ver_label {{
    color: rgba(255, 255, 255, 0.3);
    font-size: {LoginUIConfig.FONT_SIZE_VER}px;
}}

/* === 右侧美化 === */
#right_frame {{
    background-color: #2b2b2b;
    border-top-right-radius: 20px;
    border-bottom-right-radius: 20px;
}}

#login_title {{
    font-size: {LoginUIConfig.FONT_SIZE_LOGIN_TITLE}px;
    font-weight: bold;
    color: {AppConfig.DARK_TEXT_MAIN};
}}

#login_subtitle {{
    font-size: {LoginUIConfig.FONT_SIZE_LOGIN_SUBTITLE}px;
    color: {AppConfig.DARK_TEXT_SUB};
    margin-top: 5px;
}}

/* 输入框样式 */
#input_field {{
    background-color: {AppConfig.DARK_INPUT_BG};
    border: 1px solid {AppConfig.DARK_INPUT_BORDER};
    border-radius: 8px;
    padding: 14px;
    font-size: {LoginUIConfig.FONT_SIZE_INPUT}px;
    color: {AppConfig.DARK_TEXT_MAIN};
}}

#input_field:hover {{
    background-color: #404040;
    border: 1px solid #666;
}}

#input_field:focus {{
    background-color: #404040;
    border: 1px solid {AppConfig.ACCENT_COLOR};
}}

/* 登录按钮 */
#login_btn {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 {AppConfig.DARK_BTN_GRADIENT_START}, stop:1 {AppConfig.DARK_BTN_GRADIENT_END});
    color: white;
    font-size: {LoginUIConfig.FONT_SIZE_BTN}px;
    font-weight: bold;
    border-radius: 8px;
    padding: 14px;
    border: none;
}}

#login_btn:hover {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #3d5a80, stop:1 #557da0);
}}

#login_btn:pressed {{
    background-color: #2a3e58;
    padding-top: 15px;
}}

/* 杂项 */
#remember_cb {{
    color: {AppConfig.DARK_TEXT_SUB};
    font-size: {LoginUIConfig.FONT_SIZE_SMALL}px;
    spacing: 5px;
}}

#forgot_btn {{
    background-color: transparent;
    color: {AppConfig.DARK_TEXT_SUB};
    border: none;
    font-size: {LoginUIConfig.FONT_SIZE_SMALL}px;
}}

#forgot_btn:hover {{
    color: {AppConfig.ACCENT_COLOR};
    text-decoration: underline;
}}

#close_btn, #min_btn, #theme_btn {{
    border: none;
    background: transparent;
    font-size: 18px;
    color: {AppConfig.DARK_TEXT_SUB};
    padding: 5px;
}}

#close_btn:hover {{
    color: #ff6b6b;
    background-color: rgba(255, 107, 107, 0.1);
    border-radius: 4px;
}}

#min_btn:hover {{
    color: #4facfe;
    background-color: rgba(79, 172, 254, 0.1);
    border-radius: 4px;
}}

#theme_btn:hover {{
    color: {AppConfig.DARK_TEXT_MAIN};
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
}}

/* 服务器配置 */
#server_status {{
    color: {AppConfig.DARK_TEXT_SUB};
    font-size: 11px;
}}

#server_btn {{
    background-color: transparent;
    color: {AppConfig.DARK_TEXT_SUB};
    border: none;
    font-size: 11px;
    padding: 4px 8px;
}}

#server_btn:hover {{
    color: {AppConfig.ACCENT_COLOR};
    text-decoration: underline;
}}
"""

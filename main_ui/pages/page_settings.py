from .base_page import BasePage
from main_ui.config_pages import SettingsConfig

class SettingsPage(BasePage):
    def __init__(self):
        # 设置页面不需要搜索栏
        super().__init__(sub_menus=SettingsConfig.SUB_MENUS, show_search_bar=False)

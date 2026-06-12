from .base_page import BasePage
from main_ui.config_pages import SystemConfig

class SystemPage(BasePage):
    def __init__(self):
        # 系统页面通常不需要搜索栏
        super().__init__(sub_menus=SystemConfig.SUB_MENUS, show_search_bar=False)

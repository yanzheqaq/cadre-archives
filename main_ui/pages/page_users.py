from .base_page import BasePage
from main_ui.config_pages import UserConfig

class UserPage(BasePage):
    def __init__(self):
        super().__init__(sub_menus=UserConfig.SUB_MENUS, show_search_bar=False)


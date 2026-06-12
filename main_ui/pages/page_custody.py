from .base_page import BasePage
from main_ui.config_pages import CustodyConfig

class CustodyPage(BasePage):
    def __init__(self):
        super().__init__(sub_menus=CustodyConfig.SUB_MENUS)


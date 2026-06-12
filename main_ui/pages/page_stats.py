from .base_page import BasePage
from main_ui.config_pages import StatsConfig

class StatsPage(BasePage):
    def __init__(self):
        super().__init__(sub_menus=StatsConfig.SUB_MENUS)


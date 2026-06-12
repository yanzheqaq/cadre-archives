from .base_page import BasePage
from main_ui.config_pages import MaintenanceConfig

class MaintenancePage(BasePage):
    def __init__(self):
        super().__init__(sub_menus=MaintenanceConfig.SUB_MENUS)


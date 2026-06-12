# 向后兼容：从拆分后的文件导入类
from .inventory_entry_widget import InventoryEntryWidget
from .inventory_entry_dialog import InventoryEntryDialog

# 导出类以保持向后兼容
__all__ = ['InventoryEntryWidget', 'InventoryEntryDialog']

# -*- coding: utf-8 -*-
"""
机构服务
处理机构管理相关业务逻辑
"""

from typing import Any, Dict, List, Optional, Tuple

from common.repositories import OrgRepository


class OrgService:
    """机构服务"""
    
    def __init__(self):
        self.org_repo = OrgRepository()
    
    def get_root_units(self) -> List[Dict[str, Any]]:
        """获取所有顶级机构"""
        return self.org_repo.list_root_units()
    
    def get_all_units(self) -> List[Dict[str, Any]]:
        """获取所有机构"""
        return self.org_repo.list_all_units()
    
    def create_unit(
        self,
        name: str,
        code: str = "",
        contact: str = "",
        parent_id: Optional[int] = None
    ) -> Tuple[Optional[int], str]:
        """
        创建机构
        
        Returns:
            (机构ID, 错误消息)
        """
        if not name or not name.strip():
            return None, "机构名称不能为空"
        
        new_id = self.org_repo.create_unit(name, code, contact, parent_id)
        if not new_id:
            return None, "创建机构失败"
        
        return new_id, ""
    
    def update_unit(
        self,
        org_id: int,
        name: str,
        code: str = "",
        contact: str = ""
    ) -> Tuple[bool, str]:
        """
        更新机构信息
        
        Returns:
            (成功与否, 错误消息)
        """
        if not name or not name.strip():
            return False, "机构名称不能为空"
        
        ok = self.org_repo.update_unit(org_id, name, code, contact)
        if not ok:
            return False, "保存失败（记录不存在）"
        
        return True, ""
    
    def delete_unit(self, org_id: int) -> Tuple[bool, str]:
        """
        删除机构
        
        Returns:
            (成功与否, 错误消息)
        """
        # 检查是否有人员
        entry_count = self.org_repo.count_entries_in_subtree(org_id)
        if entry_count > 0:
            return False, f"该机构（含子机构）下有 {entry_count} 名人员，请先删除或移动人员后再删除机构"
        
        deleted = self.org_repo.delete_subtree(org_id)
        if deleted <= 0:
            return False, "删除失败"
        
        return True, ""
    
    def get_tree_for_root(self, root_id: int) -> List[Dict[str, Any]]:
        """获取某个根节点的树结构"""
        return self.org_repo.build_tree_for_root(root_id)


# 单例实例
org_service = OrgService()

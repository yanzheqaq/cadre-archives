# -*- coding: utf-8 -*-
"""
档案条目服务
处理档案条目相关业务逻辑
"""

from typing import Any, Dict, List, Optional, Tuple

from common.repositories import EntryRepository, ImageRepository


class EntryService:
    """档案条目服务"""
    
    def __init__(self):
        self.entry_repo = EntryRepository()
        self.image_repo = ImageRepository()
    
    def create_person(
        self,
        owner_id: int,
        name: str = "",
        emp_no: str = "",
        role_title: str = "",
        phone: str = "",
        status: str = "",
        id_card: str = "",
        org_unit_id: Optional[int] = None,
    ) -> Tuple[Optional[int], str]:
        """
        创建人员档案
        
        Returns:
            (条目ID, 错误消息)
        """
        # 获取默认模板
        template_id = self.entry_repo.get_default_template_id()
        if not template_id:
            return None, "没有可用的目录模板"
        
        entry_id = self.entry_repo.create_person(
            owner_id=owner_id,
            template_id=template_id,
            name=name,
            emp_no=emp_no,
            role_title=role_title,
            phone=phone,
            status=status,
            id_card=id_card,
            org_unit_id=org_unit_id,
        )
        
        if not entry_id:
            return None, "创建失败"
        
        return entry_id, ""
    
    def delete_entry(self, entry_id: int) -> Tuple[bool, str]:
        """
        删除档案条目
        
        Returns:
            (成功与否, 错误消息)
        """
        ok = self.entry_repo.delete_entry(entry_id)
        if not ok:
            return False, "删除失败"
        return True, ""
    
    def get_entries_by_org(
        self,
        org_unit_id: Optional[int],
        sort_field: str = "name",
        sort_asc: bool = True
    ) -> List[Dict[str, Any]]:
        """按机构获取档案条目列表"""
        return self.entry_repo.list_by_org_unit_id(org_unit_id, sort_field, sort_asc)
    
    def get_entry_detail(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """获取档案条目详情"""
        info = self.entry_repo.get_entry_info(entry_id)
        if info:
            # 添加图片数量
            info['image_count'] = self.image_repo.count_entry_images(entry_id)
        return info
    
    def update_person_fields(
        self,
        entry_id: int,
        name: str = "",
        emp_no: str = "",
        role_title: str = "",
        phone: str = "",
        status: str = "",
        id_card: str = "",
    ) -> None:
        """更新人员基础字段"""
        self.entry_repo.update_person_fields(
            entry_id, name, emp_no, role_title, phone, status, id_card
        )
    
    def get_catalog_items_for_export(self, entry_id: int) -> List[Dict[str, Any]]:
        """获取导出用的目录项列表"""
        return self.entry_repo.list_catalog_items_for_export(entry_id)


# 单例实例
entry_service = EntryService()

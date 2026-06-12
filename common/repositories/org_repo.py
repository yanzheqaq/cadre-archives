# -*- coding: utf-8 -*-
"""
机构数据仓库
"""

from typing import Any, Dict, List, Optional

from common.db import get_session, OrgUnit, Entry
from .base_repo import BaseRepository


class OrgRepository(BaseRepository[OrgUnit]):
    """机构数据仓库"""
    
    model = OrgUnit
    
    def list_root_units(self) -> List[Dict[str, Any]]:
        """获取所有顶级机构"""
        with get_session() as session:
            rows = (
                session.query(OrgUnit.id, OrgUnit.name, OrgUnit.code, OrgUnit.contact)
                .filter(OrgUnit.parent_id == None)
                .order_by(OrgUnit.id)
                .all()
            )
            return [
                {
                    "id": int(r.id),
                    "name": r.name or "",
                    "code": r.code or "",
                    "contact": r.contact or "",
                }
                for r in rows
            ]
    
    def list_all_units(self) -> List[Dict[str, Any]]:
        """获取所有机构"""
        with get_session() as session:
            rows = (
                session.query(OrgUnit.id, OrgUnit.parent_id, OrgUnit.name, OrgUnit.code, OrgUnit.contact)
                .order_by(OrgUnit.id)
                .all()
            )
            return [
                {
                    "id": int(r.id),
                    "parent_id": int(r.parent_id) if r.parent_id is not None else None,
                    "name": r.name or "",
                    "code": r.code or "",
                    "contact": r.contact or "",
                }
                for r in rows
            ]
    
    def create_unit(
        self,
        name: str,
        code: str = "",
        contact: str = "",
        parent_id: Optional[int] = None
    ) -> Optional[int]:
        """创建机构"""
        name = (name or "").strip()
        if not name:
            return None
        return self.create(
            name=name,
            code=(code or "").strip(),
            contact=(contact or "").strip(),
            parent_id=parent_id,
        )
    
    def update_unit(
        self,
        org_id: int,
        name: str,
        code: str = "",
        contact: str = ""
    ) -> bool:
        """更新机构信息"""
        name = (name or "").strip()
        if not name:
            return False
        with get_session() as session:
            obj = session.query(OrgUnit).filter(OrgUnit.id == org_id).first()
            if not obj:
                return False
            obj.name = name
            obj.code = (code or "").strip()
            obj.contact = (contact or "").strip()
            session.commit()
            return True
    
    def count_entries_in_subtree(self, org_id: int) -> int:
        """统计机构及子机构下的人员数量"""
        with get_session() as session:
            rows = session.query(OrgUnit.id, OrgUnit.parent_id).all()
            children_by_parent: Dict[Optional[int], List[int]] = {}
            for _id, _pid in rows:
                pid = int(_pid) if _pid is not None else None
                children_by_parent.setdefault(pid, []).append(int(_id))

            org_ids: List[int] = []
            stack = [int(org_id)]
            seen = set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                org_ids.append(cur)
                for ch in children_by_parent.get(cur, []):
                    stack.append(ch)

            if not org_ids:
                return 0
            
            return session.query(Entry).filter(Entry.org_unit_id.in_(org_ids)).count()
    
    def count_entries_grouped_by_org(self) -> Dict[Optional[int], int]:
        """
        一次查询返回所有机构的直属人数
        
        Returns:
            {org_unit_id: 人数}，None 键表示未分类人员
        """
        from sqlalchemy import func
        with get_session() as session:
            rows = session.query(
                Entry.org_unit_id,
                func.count(Entry.id)
            ).group_by(Entry.org_unit_id).all()
            
            result: Dict[Optional[int], int] = {}
            for org_id, cnt in rows:
                key = int(org_id) if org_id is not None else None
                result[key] = int(cnt)
            return result
    
    def delete_subtree(self, org_id: int) -> int:
        """删除机构及所有子机构，返回删除数量"""
        with get_session() as session:
            rows = session.query(OrgUnit.id, OrgUnit.parent_id).all()
            children_by_parent: Dict[Optional[int], List[int]] = {}
            for _id, _pid in rows:
                pid = int(_pid) if _pid is not None else None
                children_by_parent.setdefault(pid, []).append(int(_id))

            to_delete: List[int] = []
            stack = [int(org_id)]
            seen = set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                to_delete.append(cur)
                for ch in children_by_parent.get(cur, []):
                    stack.append(ch)

            if not to_delete:
                return 0

            session.query(OrgUnit).filter(OrgUnit.id.in_(to_delete)).delete(synchronize_session=False)
            session.commit()
            return len(to_delete)
    
    def build_tree_for_root(self, root_id: int) -> List[Dict[str, Any]]:
        """构建某个根节点的树结构"""
        all_nodes = self.list_all_units()
        by_id: Dict[int, Dict[str, Any]] = {int(n["id"]): n for n in all_nodes}
        children_by_parent: Dict[Optional[int], List[Dict[str, Any]]] = {}
        for n in all_nodes:
            children_by_parent.setdefault(n.get("parent_id"), []).append(n)

        def pack(node: Dict[str, Any]) -> Dict[str, Any]:
            pid = node.get("parent_id")
            parent_name = ""
            if pid is not None:
                parent_name = (by_id.get(int(pid)) or {}).get("name") or ""
            return {
                "id": int(node["id"]),
                "name": node.get("name") or "",
                "code": node.get("code") or "",
                "contact": node.get("contact") or "",
                "parent_name": parent_name,
                "children": [pack(ch) for ch in (children_by_parent.get(int(node["id"]), []) or [])],
            }

        root = by_id.get(int(root_id))
        if not root:
            return []
        return [pack(ch) for ch in (children_by_parent.get(int(root_id), []) or [])]


# 单例实例
org_repo = OrgRepository()


# 向后兼容的函数接口
def list_root_org_units() -> List[Dict[str, Any]]:
    return org_repo.list_root_units()

def list_all_org_units() -> List[Dict[str, Any]]:
    return org_repo.list_all_units()

def create_org_unit(*, name: str, code: str = "", contact: str = "", parent_id: Optional[int] = None) -> Optional[int]:
    return org_repo.create_unit(name, code, contact, parent_id)

def update_org_unit(*, org_id: int, name: str, code: str = "", contact: str = "") -> bool:
    return org_repo.update_unit(org_id, name, code, contact)

def count_entries_in_org_subtree(*, org_id: int) -> int:
    return org_repo.count_entries_in_subtree(org_id)

def count_entries_grouped_by_org() -> Dict[Optional[int], int]:
    """批量查询所有机构的直属人数"""
    return org_repo.count_entries_grouped_by_org()

def delete_org_unit_subtree(*, org_id: int) -> int:
    return org_repo.delete_subtree(org_id)

def build_org_tree_for_root(root_id: int) -> List[Dict[str, Any]]:
    return org_repo.build_tree_for_root(root_id)

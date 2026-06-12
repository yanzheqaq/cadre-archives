# -*- coding: utf-8 -*-
"""
档案条目数据仓库
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import String as SAString, cast, or_

from common.db import get_session, Entry, EntryCatalogItem, EntryItemImage, OrgUnit, CatalogTemplate, CatalogTemplateItem
from .base_repo import BaseRepository


class EntryRepository(BaseRepository[Entry]):
    """档案条目数据仓库"""
    
    model = Entry
    
    def get_default_template_id(self) -> Optional[int]:
        """获取默认目录模板 ID"""
        with get_session() as session:
            tpl = (
                session.query(CatalogTemplate)
                .order_by(CatalogTemplate.is_default.desc(), CatalogTemplate.id)
                .first()
            )
            return int(tpl.id) if tpl else None
    
    def create_person(
        self,
        owner_id: int,
        template_id: int,
        name: str = "",
        emp_no: str = "",
        role_title: str = "",
        phone: str = "",
        status: str = "",
        id_card: str = "",
        org_unit_id: Optional[int] = None,
    ) -> Optional[int]:
        """创建人员记录"""
        with get_session() as session:
            e = Entry(
                owner_id=int(owner_id),
                template_id=int(template_id),
                name=(name or "").strip() or None,
                emp_no=(emp_no or "").strip() or None,
                role_title=(role_title or "").strip() or None,
                phone=(phone or "").strip() or None,
                status=(status or "").strip() or None,
                id_card=(id_card or "").strip() or None,
                org_unit_id=int(org_unit_id) if org_unit_id is not None else None,
            )
            session.add(e)
            session.commit()
            return int(e.id)
    
    def delete_entry(self, entry_id: int) -> bool:
        """删除档案条目及其关联数据"""
        with get_session() as session:
            entry = session.query(Entry).filter(Entry.id == int(entry_id)).first()
            if not entry:
                return False
            
            # 获取所有目录项ID
            catalog_item_ids = [
                row[0] for row in 
                session.query(EntryCatalogItem.id).filter(EntryCatalogItem.entry_id == int(entry_id)).all()
            ]
            
            # 删除关联图片（先清除自引用外键 original_id，再删除）
            if catalog_item_ids:
                session.query(EntryItemImage).filter(
                    EntryItemImage.entry_catalog_item_id.in_(catalog_item_ids)
                ).update({EntryItemImage.original_id: None}, synchronize_session=False)
                session.query(EntryItemImage).filter(
                    EntryItemImage.entry_catalog_item_id.in_(catalog_item_ids)
                ).delete(synchronize_session=False)
            
            # 删除目录项（带审计：删前快照本 entry 所有 EC 行）
            from common.services.ec_delete_audit import snapshot_and_log_before_delete
            audit_q = session.query(EntryCatalogItem).filter(EntryCatalogItem.entry_id == int(entry_id))
            snapshot_and_log_before_delete(session, caller="entry_delete", query=audit_q)
            session.query(EntryCatalogItem).filter(EntryCatalogItem.entry_id == int(entry_id)).delete(synchronize_session=False)
            
            # 删除条目
            session.delete(entry)
            session.commit()
            return True
    
    def list_by_org_unit_id(
        self,
        org_unit_id: Optional[int],
        sort_field: str = "name",
        sort_asc: bool = True,
        name_filter: str = "",
    ) -> List[Dict[str, Any]]:
        """按机构ID列出档案条目"""
        with get_session() as session:
            query = session.query(
                Entry.id,
                Entry.name,
                Entry.emp_no,
                Entry.role_title,
                Entry.phone,
                Entry.status,
                Entry.id_card,
                Entry.template_id,
                Entry.org_unit_id,
            )
            if org_unit_id is None:
                query = query.filter(Entry.org_unit_id == None)
            else:
                query = query.filter(Entry.org_unit_id == int(org_unit_id))
            
            if name_filter:
                query = query.filter(Entry.name.like(f"%{name_filter}%"))

            allowed_sort_fields = {"name", "emp_no", "role_title", "phone", "status", "id_card", "id"}
            sort_column = getattr(Entry, sort_field, Entry.name) if sort_field in allowed_sort_fields else Entry.name
            if sort_asc:
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())
            
            rows = query.all()
            return [
                {
                    "id": r.id,
                    "name": r.name or "",
                    "emp_no": r.emp_no or "",
                    "role_title": r.role_title or "",
                    "phone": r.phone or "",
                    "status": r.status or "",
                    "id_card": r.id_card or "",
                    "template_id": r.template_id,
                    "org_unit_id": r.org_unit_id,
                }
                for r in rows
            ]

    def move_entries_to_org_unit(self, entry_ids: List[int], target_org_unit_id: Optional[int]) -> int:
        ids = []
        for raw_id in entry_ids or []:
            try:
                entry_id = int(raw_id)
            except Exception:
                continue
            if entry_id > 0 and entry_id not in ids:
                ids.append(entry_id)
        if not ids:
            return 0
        target_id = int(target_org_unit_id) if target_org_unit_id is not None else None
        with get_session() as session:
            target_path = ""
            if target_id is not None:
                rows = session.query(OrgUnit.id, OrgUnit.parent_id, OrgUnit.name).all()
                by_id = {int(row.id): row for row in rows}
                if target_id not in by_id:
                    raise ValueError("目标类别不存在或已被删除")
                parts = []
                current_id = target_id
                seen = set()
                while current_id is not None and current_id not in seen:
                    seen.add(current_id)
                    row = by_id.get(int(current_id))
                    if not row:
                        break
                    name = (row.name or "").strip()
                    if name:
                        parts.append(name)
                    current_id = int(row.parent_id) if row.parent_id is not None else None
                target_path = "/".join(reversed(parts))
            count = (
                session.query(Entry)
                .filter(Entry.id.in_(ids))
                .update(
                    {
                        Entry.org_unit_id: target_id,
                        Entry.org_path: target_path,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return int(count or 0)
    
    def get_entry_info(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """获取档案条目完整信息"""
        with get_session() as session:
            e = session.query(Entry).filter(Entry.id == int(entry_id)).first()
            if not e:
                return None
            org_name = ""
            try:
                if e.org_unit_id:
                    ou = session.query(OrgUnit).filter(OrgUnit.id == int(e.org_unit_id)).first()
                    org_name = (ou.name or "") if ou else ""
            except Exception:
                org_name = ""
            return {
                "id": int(e.id),
                "owner_id": int(e.owner_id),
                "template_id": int(e.template_id),
                "name": e.name or "",
                "emp_no": e.emp_no or "",
                "role_title": e.role_title or "",
                "phone": e.phone or "",
                "status": e.status or "",
                "id_card": e.id_card or "",
                "custom_fields": e.custom_fields or "",
                "org_path": e.org_path or "",
                "org_unit_id": int(e.org_unit_id) if e.org_unit_id is not None else None,
                "org_unit_name": org_name,
                "created_at": str(e.created_at) if getattr(e, "created_at", None) else "",
                "updated_at": str(e.updated_at) if getattr(e, "updated_at", None) else "",
            }
    
    def update_person_fields(
        self,
        entry_id: int,
        name: str = "",
        emp_no: str = "",
        role_title: str = "",
        phone: str = "",
        status: str = "",
        id_card: str = "",
        custom_fields: str = "",
    ) -> None:
        """更新人员基础字段"""
        with get_session() as session:
            updates = {
                    Entry.name: (name or "").strip() or None,
                    Entry.emp_no: (emp_no or "").strip() or None,
                    Entry.role_title: (role_title or "").strip() or None,
                    Entry.phone: (phone or "").strip() or None,
                    Entry.status: (status or "").strip() or None,
                    Entry.id_card: (id_card or "").strip() or None,
            }
            if custom_fields is not None:
                updates[Entry.custom_fields] = custom_fields or None
            session.query(Entry).filter(Entry.id == int(entry_id)).update(updates)
            session.commit()
    
    def list_catalog_items_for_export(self, entry_id: int) -> List[Dict[str, Any]]:
        """列出导出用的目录项"""
        with get_session() as session:
            rows = (
                session.query(EntryCatalogItem, CatalogTemplateItem)
                .join(CatalogTemplateItem, CatalogTemplateItem.id == EntryCatalogItem.template_item_id)
                .filter(EntryCatalogItem.entry_id == int(entry_id))
                .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id, EntryCatalogItem.id)
                .all()
            )
            out: List[Dict[str, Any]] = []
            for ec, tpl in rows:
                serial = (ec.serial or "").strip() or (tpl.serial or "").strip()
                name = (ec.name or "").strip() or (tpl.name or "").strip()
                out.append(
                    {
                        "entry_catalog_item_id": int(ec.id),
                        "template_item_id": int(ec.template_item_id),
                        "serial": serial,
                        "name": name,
                        "year": ec.year,
                        "month": ec.month,
                        "day": ec.day,
                        "pages": ec.pages,
                        "remark": ec.remark or "",
                        "attachment_path": ec.attachment_path or "",
                        "tpl_parent_id": int(tpl.parent_id) if tpl.parent_id is not None else None,
                        "tpl_sort_order": int(tpl.sort_order or 0),
                    }
                )
            return out

    def search_catalog_items(self, keyword: str, limit: int = 200) -> List[Dict[str, Any]]:
        kw = (keyword or "").strip()
        if not kw:
            return []
        try:
            max_rows = int(limit or 200)
        except Exception:
            max_rows = 200
        max_rows = max(1, min(500, max_rows))
        pattern = f"%{kw}%"
        with get_session() as session:
            rows = (
                session.query(EntryCatalogItem, Entry, CatalogTemplateItem)
                .join(Entry, Entry.id == EntryCatalogItem.entry_id)
                .join(CatalogTemplateItem, CatalogTemplateItem.id == EntryCatalogItem.template_item_id)
                .filter(
                    or_(
                        EntryCatalogItem.serial.like(pattern),
                        EntryCatalogItem.name.like(pattern),
                        EntryCatalogItem.year.like(pattern),
                        EntryCatalogItem.month.like(pattern),
                        EntryCatalogItem.day.like(pattern),
                        cast(EntryCatalogItem.pages, SAString).like(pattern),
                        EntryCatalogItem.remark.like(pattern),
                        CatalogTemplateItem.serial.like(pattern),
                        CatalogTemplateItem.name.like(pattern),
                        CatalogTemplateItem.remark.like(pattern),
                    )
                )
                .order_by(Entry.name.asc(), CatalogTemplateItem.sort_order.asc(), EntryCatalogItem.id.asc())
                .limit(max_rows)
                .all()
            )
            if not rows:
                return []

            template_ids = sorted({int(tpl.template_id) for _, _, tpl in rows if tpl.template_id is not None})
            tpl_nodes = {}
            if template_ids:
                for t in (
                    session.query(CatalogTemplateItem)
                    .filter(CatalogTemplateItem.template_id.in_(template_ids))
                    .all()
                ):
                    tpl_nodes[int(t.id)] = {
                        "parent_id": int(t.parent_id) if t.parent_id is not None else None,
                        "name": t.name or "",
                        "serial": t.serial or "",
                    }

            org_nodes = {}
            for org in session.query(OrgUnit).all():
                org_nodes[int(org.id)] = {
                    "parent_id": int(org.parent_id) if org.parent_id is not None else None,
                    "name": org.name or "",
                }

            catalog_path_cache: Dict[int, str] = {}
            org_path_cache: Dict[Optional[int], str] = {}

            def catalog_path(template_item_id: int) -> str:
                tid = int(template_item_id)
                if tid in catalog_path_cache:
                    return catalog_path_cache[tid]
                parts = []
                current_id = tid
                seen = set()
                while current_id is not None and current_id not in seen:
                    seen.add(current_id)
                    node = tpl_nodes.get(int(current_id))
                    if not node:
                        break
                    text = (node.get("name") or node.get("serial") or "").strip()
                    if text:
                        parts.append(text)
                    current_id = node.get("parent_id")
                value = " / ".join(reversed(parts))
                catalog_path_cache[tid] = value
                return value

            def org_path(org_unit_id: Optional[int]) -> str:
                oid = int(org_unit_id) if org_unit_id is not None else None
                if oid in org_path_cache:
                    return org_path_cache[oid]
                if oid is None:
                    org_path_cache[oid] = "未分类"
                    return org_path_cache[oid]
                parts = []
                current_id = oid
                seen = set()
                while current_id is not None and current_id not in seen:
                    seen.add(current_id)
                    node = org_nodes.get(int(current_id))
                    if not node:
                        break
                    name = (node.get("name") or "").strip()
                    if name:
                        parts.append(name)
                    current_id = node.get("parent_id")
                value = " / ".join(reversed(parts)) or "未分类"
                org_path_cache[oid] = value
                return value

            out: List[Dict[str, Any]] = []
            for ec, entry, tpl in rows:
                serial_locked = bool((tpl.serial or "").strip())
                name_locked = bool((tpl.name or "").strip())
                out.append(
                    {
                        "entry_catalog_item_id": int(ec.id),
                        "entry_id": int(entry.id),
                        "template_item_id": int(ec.template_item_id),
                        "person_name": entry.name or "",
                        "emp_no": entry.emp_no or "",
                        "id_card": entry.id_card or "",
                        "org_path": (entry.org_path or "").strip() or org_path(entry.org_unit_id),
                        "catalog_path": catalog_path(int(ec.template_item_id)),
                        "serial": (ec.serial if ec.serial is not None else tpl.serial) or "",
                        "name": (ec.name if ec.name is not None else tpl.name) or "",
                        "year": ec.year or "",
                        "month": ec.month or "",
                        "day": ec.day or "",
                        "pages": "" if ec.pages is None else str(ec.pages),
                        "remark": ec.remark or "",
                        "serial_locked": serial_locked,
                        "name_locked": name_locked,
                        "updated_at": str(ec.updated_at) if getattr(ec, "updated_at", None) else "",
                    }
                )
            return out

    def update_catalog_item_by_id(self, entry_catalog_item_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"serial", "name", "year", "month", "day", "pages", "remark"}
        clean: Dict[str, Any] = {}
        for key, value in (fields or {}).items():
            if key not in allowed:
                continue
            if key == "pages":
                text = "" if value is None else str(value).strip()
                if text == "":
                    clean[key] = None
                else:
                    try:
                        number = int(text)
                    except Exception:
                        raise ValueError("页数必须是整数")
                    if number < 0:
                        raise ValueError("页数不能小于 0")
                    clean[key] = number
            else:
                clean[key] = "" if value is None else str(value).strip()
        if not clean:
            return {}
        with get_session() as session:
            ec = session.query(EntryCatalogItem).filter(EntryCatalogItem.id == int(entry_catalog_item_id)).first()
            if not ec:
                raise ValueError("目录条目不存在或已被删除")
            tpl = session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == int(ec.template_item_id)).first()
            if not tpl:
                raise ValueError("目录模板条目不存在或已被删除")
            if "serial" in clean and (tpl.serial or "").strip():
                raise ValueError("模板预设编号不能在搜索结果中修改")
            if "name" in clean and (tpl.name or "").strip():
                raise ValueError("模板预设目录名称不能在搜索结果中修改")
            session.query(EntryCatalogItem).filter(EntryCatalogItem.id == int(entry_catalog_item_id)).update(clean)
            session.commit()
            updated = session.query(EntryCatalogItem).filter(EntryCatalogItem.id == int(entry_catalog_item_id)).first()
            return {
                "entry_catalog_item_id": int(updated.id),
                "serial": (updated.serial if updated.serial is not None else tpl.serial) or "",
                "name": (updated.name if updated.name is not None else tpl.name) or "",
                "year": updated.year or "",
                "month": updated.month or "",
                "day": updated.day or "",
                "pages": "" if updated.pages is None else str(updated.pages),
                "remark": updated.remark or "",
                "updated_at": str(updated.updated_at) if getattr(updated, "updated_at", None) else "",
            }


# 单例实例
entry_repo = EntryRepository()


# 向后兼容的函数接口
def get_default_template_id() -> Optional[int]:
    return entry_repo.get_default_template_id()

def create_entry_person(
    *,
    owner_id: int,
    template_id: int,
    name: str,
    emp_no: str,
    role_title: str,
    phone: str,
    status: str,
    id_card: str,
    org_unit_id: Optional[int],
) -> Optional[int]:
    return entry_repo.create_person(owner_id, template_id, name, emp_no, role_title, phone, status, id_card, org_unit_id)

def delete_entry(entry_id: int) -> bool:
    return entry_repo.delete_entry(entry_id)

def list_entries_by_org_unit_id(org_unit_id: Optional[int], sort_field: str = "name", sort_asc: bool = True, name_filter: str = "") -> List[Dict[str, Any]]:
    return entry_repo.list_by_org_unit_id(org_unit_id, sort_field, sort_asc, name_filter=name_filter)

def move_entries_to_org_unit(*, entry_ids: List[int], target_org_unit_id: Optional[int]) -> int:
    return entry_repo.move_entries_to_org_unit(entry_ids, target_org_unit_id)

def get_entry_info(*, entry_id: int) -> Optional[Dict[str, Any]]:
    return entry_repo.get_entry_info(entry_id)

def update_entry_person_fields(
    *,
    entry_id: int,
    name: str,
    emp_no: str,
    role_title: str,
    phone: str,
    status: str,
    id_card: str,
    custom_fields: str = "",
) -> None:
    return entry_repo.update_person_fields(entry_id, name, emp_no, role_title, phone, status, id_card, custom_fields)

def list_entry_catalog_items_for_export(*, entry_id: int) -> List[Dict[str, Any]]:
    return entry_repo.list_catalog_items_for_export(entry_id)

def search_entry_catalog_items(*, keyword: str, limit: int = 200) -> List[Dict[str, Any]]:
    return entry_repo.search_catalog_items(keyword, limit=limit)

def update_entry_catalog_item_by_id(*, entry_catalog_item_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    return entry_repo.update_catalog_item_by_id(entry_catalog_item_id, fields)

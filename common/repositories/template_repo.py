# -*- coding: utf-8 -*-
"""
目录模板数据仓库
"""

from typing import Any, Dict, List, Optional, Iterable

from common.db import get_session, CatalogTemplate, CatalogTemplateItem, EntryCatalogItem, EntryItemImage
from .base_repo import BaseRepository


class TemplateRepository(BaseRepository[CatalogTemplate]):
    """目录模板数据仓库"""
    
    model = CatalogTemplate
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板"""
        with get_session() as session:
            tpls = (
                session.query(CatalogTemplate.id, CatalogTemplate.name, CatalogTemplate.is_default)
                .order_by(CatalogTemplate.is_default.desc(), CatalogTemplate.id)
                .all()
            )
            return [{"id": t.id, "name": t.name, "is_default": t.is_default} for t in tpls]
    
    def list_template_items(self, template_id: int) -> List[Dict[str, Any]]:
        """列出模板的所有项"""
        with get_session() as session:
            rows = (
                session.query(
                    CatalogTemplateItem.id,
                    CatalogTemplateItem.template_id,
                    CatalogTemplateItem.parent_id,
                    CatalogTemplateItem.sort_order,
                    CatalogTemplateItem.serial,
                    CatalogTemplateItem.name,
                    CatalogTemplateItem.year,
                    CatalogTemplateItem.month,
                    CatalogTemplateItem.day,
                    CatalogTemplateItem.pages,
                    CatalogTemplateItem.remark,
                )
                .filter(CatalogTemplateItem.template_id == template_id)
                .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "template_id": r.template_id,
                    "parent_id": r.parent_id or None,
                    "sort_order": r.sort_order,
                    "serial": r.serial or "",
                    "name": r.name or "",
                    "year": r.year,
                    "month": r.month,
                    "day": r.day,
                    "pages": r.pages,
                    "remark": r.remark or "",
                }
                for r in rows
            ]
    
    def _same_parent_query(self, session, template_id: int, parent_id: Optional[int]):
        query = session.query(CatalogTemplateItem).filter(
            CatalogTemplateItem.template_id == int(template_id),
        )
        if parent_id is None:
            query = query.filter(CatalogTemplateItem.parent_id.is_(None))
        else:
            query = query.filter(CatalogTemplateItem.parent_id == int(parent_id))
        return query

    def _reorder_siblings_for_insert(
        self,
        session,
        *,
        template_id: int,
        parent_id: Optional[int],
        new_item_id: int,
        sibling_order_ids: Optional[List[int]],
        insert_index: Optional[int],
    ) -> None:
        rows = (
            self._same_parent_query(session, template_id, parent_id)
            .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
            .all()
        )
        valid_ids = {int(r.id) for r in rows}
        new_item_id = int(new_item_id)
        ordered_ids: List[int] = []
        seen = set()
        for raw_id in sibling_order_ids or []:
            try:
                item_id = int(raw_id)
            except Exception:
                continue
            if item_id <= 0 or item_id == new_item_id or item_id not in valid_ids or item_id in seen:
                continue
            ordered_ids.append(item_id)
            seen.add(item_id)

        try:
            idx = int(insert_index)
        except Exception:
            idx = len(ordered_ids)
        idx = max(0, min(idx, len(ordered_ids)))
        ordered_ids.insert(idx, new_item_id)
        seen.add(new_item_id)

        for row in rows:
            item_id = int(row.id)
            if item_id not in seen:
                ordered_ids.append(item_id)
                seen.add(item_id)

        for pos, item_id in enumerate(ordered_ids, start=1):
            session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id).update(
                {"sort_order": pos},
                synchronize_session=False,
            )

    def create_template_item(
        self,
        template_id: int,
        parent_id: Optional[int] = None,
        sort_order: int = 0,
        sibling_order_ids: Optional[List[int]] = None,
        insert_index: Optional[int] = None,
    ) -> int:
        """创建模板项"""
        with get_session() as session:
            insert_sort = max(1, int(sort_order or 1))
            obj = CatalogTemplateItem(template_id=template_id, parent_id=parent_id, sort_order=insert_sort)
            session.add(obj)
            session.flush()
            if sibling_order_ids is not None and insert_index is not None:
                self._reorder_siblings_for_insert(
                    session,
                    template_id=int(template_id),
                    parent_id=parent_id,
                    new_item_id=int(obj.id),
                    sibling_order_ids=sibling_order_ids,
                    insert_index=insert_index,
                )
            else:
                (
                    self._same_parent_query(session, int(template_id), parent_id)
                    .filter(CatalogTemplateItem.id != int(obj.id))
                    .filter(CatalogTemplateItem.sort_order >= insert_sort)
                    .update(
                        {CatalogTemplateItem.sort_order: CatalogTemplateItem.sort_order + 1},
                        synchronize_session=False,
                    )
                )
            session.commit()
            return obj.id
    
    def delete_template_items(self, template_item_ids: Iterable[int]) -> None:
        """【管理员用】删除模板项及其关联的所有 entry 目录项。

        ⚠️ 注意：此方法会删掉 **所有 entry** 下引用这些 template_item 的 EC 行，
        属于模板级 schema 变更。**用户从录入对话框删自己的一行时不要调用本方法**，
        否则会导致所有用户该 template_item 下的数据一起丢失（历史 bug）。
        普通删行请调用 ``delete_entry_catalog_rows_only``。
        """
        ids = [int(x) for x in template_item_ids if x is not None]
        if not ids:
            return
        with get_session() as session:
            ids = self._collect_template_item_subtree_ids(session, ids)
            if not ids:
                return
            # 审计：此路径死过人，删前完整快照，方便事后追溯
            from common.services.ec_delete_audit import snapshot_and_log_before_delete
            ec_query = session.query(EntryCatalogItem).filter(EntryCatalogItem.template_item_id.in_(ids))
            snapshot_and_log_before_delete(session, caller="admin_cascade_delete", query=ec_query)
            ec_ids = [
                int(row[0])
                for row in session.query(EntryCatalogItem.id)
                .filter(EntryCatalogItem.template_item_id.in_(ids))
                .all()
            ]
            if ec_ids:
                session.query(EntryItemImage).filter(
                    EntryItemImage.entry_catalog_item_id.in_(ec_ids)
                ).update({EntryItemImage.original_id: None}, synchronize_session=False)
                session.query(EntryItemImage).filter(
                    EntryItemImage.entry_catalog_item_id.in_(ec_ids)
                ).delete(synchronize_session=False)
                session.query(EntryCatalogItem).filter(EntryCatalogItem.id.in_(ec_ids)).delete(synchronize_session=False)
            for item_id in self._template_item_delete_order(session, ids):
                session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id).delete(synchronize_session=False)
            session.commit()

    def _collect_template_item_subtree_ids(self, session, template_item_ids: Iterable[int]) -> List[int]:
        roots = [int(x) for x in template_item_ids if x is not None and int(x) > 0]
        if not roots:
            return []
        rows = session.query(CatalogTemplateItem.id, CatalogTemplateItem.parent_id).all()
        children_by_parent: Dict[Optional[int], List[int]] = {}
        for row in rows:
            item_id = int(row.id)
            parent_id = int(row.parent_id) if row.parent_id is not None else None
            children_by_parent.setdefault(parent_id, []).append(item_id)
        result: List[int] = []
        seen = set()
        stack = list(roots)
        while stack:
            cur = int(stack.pop())
            if cur in seen:
                continue
            seen.add(cur)
            result.append(cur)
            stack.extend(children_by_parent.get(cur, []))
        return result

    def _template_item_delete_order(self, session, template_item_ids: Iterable[int]) -> List[int]:
        ids = {int(x) for x in template_item_ids if x is not None and int(x) > 0}
        if not ids:
            return []
        rows = (
            session.query(CatalogTemplateItem.id, CatalogTemplateItem.parent_id)
            .filter(CatalogTemplateItem.id.in_(ids))
            .all()
        )
        parent_by_id = {
            int(row.id): int(row.parent_id) if row.parent_id is not None else None
            for row in rows
        }

        def depth(item_id: int) -> int:
            d = 0
            cur = int(item_id)
            seen = set()
            while cur in parent_by_id:
                parent_id = parent_by_id.get(cur)
                if parent_id not in ids or parent_id in seen or parent_id == cur:
                    break
                seen.add(cur)
                cur = int(parent_id)
                d += 1
            return d

        return sorted(ids, key=lambda item_id: (depth(item_id), item_id), reverse=True)

    def delete_entry_catalog_rows_only(self, entry_id: int, template_item_ids: Iterable[int]) -> int:
        """【用户录入删行用】仅删除 **指定 entry** 下对应 template_item 的 EC 行。

        模板条目 ``catalog_template_items`` 一律保留（方案A，最保守）：
        - 避免因一个用户的删除操作级联丢掉其他 entry 的同槽位数据
        - 长期累积的孤儿 tpl_item 留给管理员侧清理脚本处理，对用户透明
          （UI 中 is_structural=False + has_data=False 的孤儿会被自动隐藏）

        返回实际删除的 EC 行数。
        """
        ids = [int(x) for x in template_item_ids if x is not None and int(x) > 0]
        if not ids or not entry_id:
            return 0
        with get_session() as session:
            ec_ids = [
                int(row[0])
                for row in session.query(EntryCatalogItem.id)
                .filter(
                    EntryCatalogItem.entry_id == int(entry_id),
                    EntryCatalogItem.template_item_id.in_(ids),
                )
                .all()
            ]
            if not ec_ids:
                return 0
            # 审计：删前快照本次将被删的 EC 行
            from common.services.ec_delete_audit import snapshot_and_log_before_delete
            ec_query = session.query(EntryCatalogItem).filter(
                EntryCatalogItem.id.in_(ec_ids),
            )
            snapshot_and_log_before_delete(session, caller="user_row_delete", query=ec_query)
            session.query(EntryItemImage).filter(
                EntryItemImage.entry_catalog_item_id.in_(ec_ids)
            ).update({EntryItemImage.original_id: None}, synchronize_session=False)
            session.query(EntryItemImage).filter(
                EntryItemImage.entry_catalog_item_id.in_(ec_ids)
            ).delete(synchronize_session=False)
            n = (
                session.query(EntryCatalogItem)
                .filter(EntryCatalogItem.id.in_(ec_ids))
                .delete(synchronize_session=False)
            )
            session.commit()
            return int(n or 0)

    def swap_item_sort_order(self, item_id_a: int, item_id_b: int) -> bool:
        """交换两个模板项的排序（影响所有档案，仅管理员目录管理页使用）。"""
        with get_session() as session:
            item_a = session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id_a).first()
            item_b = session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id_b).first()
            if not item_a or not item_b:
                return False
            sort_a = item_a.sort_order
            sort_b = item_b.sort_order
            item_a.sort_order = sort_b
            item_b.sort_order = sort_a
            session.commit()
            return True

    def swap_entry_catalog_item_order(
        self, entry_id: int, template_item_id_a: int, template_item_id_b: int,
    ) -> bool:
        """【录入对话框用】仅交换当前 entry 两个 EC 行的显示顺序，不影响其他档案。

        原理
        ----
        不修改共享模板的 ``sort_order``，而是交换当前 entry 两条 EC 行的
        ``template_item_id`` 引用。由于显示顺序由 ``CatalogTemplateItem.sort_order``
        决定，交换引用后，两条 EC 行的内容（名称/页数/日期）会出现在对方的
        位置上，等效于"上移/下移"，但只影响当前人。

        如果其中一个模板项没有当前 entry 的 EC 行（空槽位），则将 EC 行
        的引用直接移到目标模板项，实现"移入空位"的效果。
        """
        with get_session() as session:
            ec_a = (
                session.query(EntryCatalogItem)
                .filter(
                    EntryCatalogItem.entry_id == int(entry_id),
                    EntryCatalogItem.template_item_id == int(template_item_id_a),
                )
                .first()
            )
            ec_b = (
                session.query(EntryCatalogItem)
                .filter(
                    EntryCatalogItem.entry_id == int(entry_id),
                    EntryCatalogItem.template_item_id == int(template_item_id_b),
                )
                .first()
            )
            if ec_a and ec_b:
                # 两条都有 EC 行：交换 template_item_id
                ec_a.template_item_id = int(template_item_id_b)
                ec_b.template_item_id = int(template_item_id_a)
            elif ec_a and not ec_b:
                # 只有 A 有 EC 行：移到 B 的位置
                ec_a.template_item_id = int(template_item_id_b)
            elif ec_b and not ec_a:
                # 只有 B 有 EC 行：移到 A 的位置
                ec_b.template_item_id = int(template_item_id_a)
            else:
                # 两条都没有 EC 行：无需操作
                return True
            session.commit()
            return True

    def delete_orphan_template_item_safely(self, template_item_id: int) -> bool:
        """【孤儿清理用】仅当没有任何 EntryCatalogItem 引用此模板条目时才删除模板。

        使用场景
        --------
        录入对话框中：用户通过右键"插入一行"创建了新模板条目（异步），
        在 worker 返回 ``real_tpl_id`` 之前关闭了对话框。回调发现
        ``tree_item`` 已 detached，需要清理这个"无主"模板条目。

        历史 bug（必须避免）
        --------------------
        旧代码在这种场景下直接调用 ``delete_template_items``（级联删 EC），
        但 CatalogTemplate 是**全局共享**的：用户 A 异步创建模板期间，
        用户 B 可能已经为这个新槽位填入了数据。盲目级联删会跨 entry
        把 B 的数据一起删掉 —— 这就是用户反馈"每类第一条都没了"的成因。

        本方法的安全语义
        ----------------
        - 检查是否有 **任何** EC 行引用该 ``template_item_id``。
        - 有：保留模板条目（极其保守，宁可留孤儿也绝不跨 entry 删数据）。
        - 无：仅删模板条目本身。

        Returns
        -------
        bool
            ``True``  → 模板已删除（确认无引用）。
            ``False`` → 因仍有 EC 引用而保留。
        """
        tpl_id = int(template_item_id) if template_item_id else 0
        if tpl_id <= 0:
            return False
        with get_session() as session:
            tpl_ids = self._collect_template_item_subtree_ids(session, [tpl_id])
            if not tpl_ids:
                return False
            still_referenced = (
                session.query(EntryCatalogItem.id)
                .filter(EntryCatalogItem.template_item_id.in_(tpl_ids))
                .first()
                is not None
            )
            if still_referenced:
                return False
            for item_id in self._template_item_delete_order(session, tpl_ids):
                session.query(CatalogTemplateItem).filter(
                    CatalogTemplateItem.id == item_id
                ).delete(synchronize_session=False)
            session.commit()
            return True

    def move_catalog_template_items_to_parent(
        self,
        template_item_ids: List[int],
        new_parent_id: int,
    ) -> int:
        """将一组模板条目迁移到新的父节点下。

        ⚠️ 此方法修改共享模板结构，影响所有使用该模板的档案。
        录入对话框的跨类别迁移应使用 ``migrate_entry_catalog_items_to_parent``。

        迁移后的条目附加到目标父节点的末尾（sort_order 从当前最大值+1 开始）。
        返回实际更新的条目数。
        """
        ids = [int(x) for x in template_item_ids if x is not None and int(x) > 0]
        if not ids or not new_parent_id:
            return 0
        with get_session() as session:
            from sqlalchemy import func

            target = (
                session.query(CatalogTemplateItem)
                .filter(CatalogTemplateItem.id == int(new_parent_id))
                .first()
            )
            if not target:
                raise ValueError("目标类别不存在或已被删除")
            target_id = int(target.id)
            template_id = int(target.template_id)
            parent_rows = (
                session.query(CatalogTemplateItem.id, CatalogTemplateItem.parent_id)
                .filter(CatalogTemplateItem.template_id == template_id)
                .all()
            )
            parent_by_id = {
                int(row.id): int(row.parent_id) if row.parent_id is not None else None
                for row in parent_rows
            }

            def target_is_descendant_of(item_id: int) -> bool:
                current = parent_by_id.get(target_id)
                seen = set()
                while current is not None and current not in seen:
                    if current == int(item_id):
                        return True
                    seen.add(current)
                    current = parent_by_id.get(current)
                return False

            # 获取当前目标父节点下的最大 sort_order
            max_sort = (
                session.query(func.coalesce(func.max(CatalogTemplateItem.sort_order), 0))
                .filter(CatalogTemplateItem.parent_id == target_id)
                .scalar()
            ) or 0

            items = (
                session.query(CatalogTemplateItem)
                .filter(
                    CatalogTemplateItem.id.in_(ids),
                    CatalogTemplateItem.template_id == template_id,
                    CatalogTemplateItem.parent_id.isnot(None),
                )
                .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
                .all()
            )
            items = [
                item for item in items
                if int(item.id) != target_id and not target_is_descendant_of(int(item.id))
            ]

            for idx, item in enumerate(items, start=1):
                item.parent_id = target_id
                item.sort_order = int(max_sort) + idx

            session.commit()
            return len(items)

    def migrate_entry_catalog_items_to_parent(
        self,
        entry_id: int,
        source_template_item_ids: List[int],
        target_parent_id: int,
    ) -> int:
        """【录入对话框用】仅迁移指定 entry 的目录数据到目标类别，不影响其他档案。

        原理
        ----
        不修改共享模板结构（``CatalogTemplateItem.parent_id``），
        而是在目标父类别下创建新的模板槽位，然后将当前 entry 的
        ``EntryCatalogItem`` 从旧槽位迁移到新槽位。旧槽位如果变成
        孤儿（无 EC 引用）则自动清理。

        这样一个人迁移目录内容，其他人的目录结构完全不受影响。

        参数
        ----
        entry_id : int
            当前操作的档案 ID
        source_template_item_ids : List[int]
            要迁移的源模板项 ID 列表
        target_parent_id : int
            目标父类别模板项 ID

        返回
        ----
        int : 实际迁移的条目数
        """
        src_ids = [int(x) for x in source_template_item_ids if x is not None and int(x) > 0]
        if not src_ids or not target_parent_id or not entry_id:
            return 0
        with get_session() as session:
            from sqlalchemy import func

            target = (
                session.query(CatalogTemplateItem)
                .filter(CatalogTemplateItem.id == int(target_parent_id))
                .first()
            )
            if not target:
                raise ValueError("目标类别不存在或已被删除")
            target_tpl_id = int(target.template_id)

            # 获取目标父节点下的最大 sort_order
            max_sort = (
                session.query(func.coalesce(func.max(CatalogTemplateItem.sort_order), 0))
                .filter(CatalogTemplateItem.parent_id == int(target_parent_id))
                .scalar()
            ) or 0

            migrated = 0
            orphan_ids = []
            for src_id in src_ids:
                src_item = (
                    session.query(CatalogTemplateItem)
                    .filter(CatalogTemplateItem.id == src_id)
                    .first()
                )
                if not src_item or src_item.parent_id is None:
                    continue
                if int(src_item.template_id) != target_tpl_id:
                    continue

                # 在目标父类别下创建新模板槽位
                max_sort += 1
                new_item = CatalogTemplateItem(
                    template_id=target_tpl_id,
                    parent_id=int(target_parent_id),
                    sort_order=int(max_sort),
                )
                session.add(new_item)
                session.flush()  # 获取 new_item.id

                # 将当前 entry 的 EC 数据从旧模板项迁移到新模板项
                ec_rows = (
                    session.query(EntryCatalogItem)
                    .filter(
                        EntryCatalogItem.entry_id == int(entry_id),
                        EntryCatalogItem.template_item_id == src_id,
                    )
                    .all()
                )
                for ec in ec_rows:
                    ec.template_item_id = int(new_item.id)

                # 同时迁移关联的图片
                for ec in ec_rows:
                    session.query(EntryItemImage).filter(
                        EntryItemImage.entry_catalog_item_id == int(ec.id)
                    ).update(
                        {"entry_catalog_item_id": int(ec.id)},
                        synchronize_session=False,
                    )

                orphan_ids.append(src_id)
                migrated += 1

            session.commit()

            # 清理孤儿旧模板项（无 EC 引用时才删除）
            for old_id in orphan_ids:
                try:
                    self.delete_orphan_template_item_safely(old_id)
                except Exception:
                    pass

            return migrated


# 单例实例
template_repo = TemplateRepository()


# 向后兼容的函数接口
def list_catalog_templates() -> List[Dict[str, Any]]:
    return template_repo.list_templates()

def list_catalog_template_items(template_id: int) -> List[Dict[str, Any]]:
    return template_repo.list_template_items(template_id)

def create_catalog_template_item(
    *,
    template_id: int,
    parent_id: Optional[int],
    sort_order: int,
    sibling_order_ids: Optional[List[int]] = None,
    insert_index: Optional[int] = None,
) -> int:
    return template_repo.create_template_item(
        template_id,
        parent_id,
        sort_order,
        sibling_order_ids=sibling_order_ids,
        insert_index=insert_index,
    )

def delete_catalog_template_items_and_entry_catalog_items(template_item_ids: Iterable[int]) -> None:
    return template_repo.delete_template_items(template_item_ids)

def delete_entry_catalog_rows_only(*, entry_id: int, template_item_ids: Iterable[int]) -> int:
    """用户从录入对话框删行时调用，只删本 entry 的 EC 行，不触碰模板条目。"""
    return template_repo.delete_entry_catalog_rows_only(entry_id, template_item_ids)

def delete_orphan_template_item_safely(template_item_id: int) -> bool:
    """录入对话框孤儿清理用：无 EC 引用时删模板，有引用时保留（杜绝跨 entry 数据丢失）。"""
    return template_repo.delete_orphan_template_item_safely(template_item_id)

def swap_catalog_template_item_sort_order(*, item_id_a: int, item_id_b: int) -> bool:
    """交换共享模板项排序（影响所有档案，仅目录管理页使用）。"""
    return template_repo.swap_item_sort_order(item_id_a, item_id_b)

def swap_entry_catalog_item_order(*, entry_id: int, template_item_id_a: int, template_item_id_b: int) -> bool:
    """录入对话框用：仅交换当前 entry 两个 EC 行的显示顺序，不影响其他档案。"""
    return template_repo.swap_entry_catalog_item_order(
        entry_id=entry_id,
        template_item_id_a=template_item_id_a,
        template_item_id_b=template_item_id_b,
    )

def move_catalog_template_items_to_parent(
    *,
    template_item_ids: Iterable[int],
    new_parent_id: int,
) -> int:
    """向后兼容函数接口：跨类别迁移模板条目（影响所有档案）。"""
    return template_repo.move_catalog_template_items_to_parent(
        template_item_ids=list(template_item_ids),
        new_parent_id=new_parent_id,
    )

def migrate_entry_catalog_items_to_parent(
    *,
    entry_id: int,
    source_template_item_ids: Iterable[int],
    target_parent_id: int,
) -> int:
    """录入对话框用：仅迁移指定 entry 的目录数据，不影响其他档案。"""
    return template_repo.migrate_entry_catalog_items_to_parent(
        entry_id=entry_id,
        source_template_item_ids=list(source_template_item_ids),
        target_parent_id=target_parent_id,
    )

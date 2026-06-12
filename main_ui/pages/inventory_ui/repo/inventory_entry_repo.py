# -*- coding: utf-8 -*-
"""
向后兼容模块
请使用 common.repositories 代替
"""

# 从新模块导入，保持向后兼容
from common.repositories.entry_repo import (
    entry_repo,
    get_default_template_id,
    create_entry_person,
    delete_entry,
    list_entries_by_org_unit_id,
    move_entries_to_org_unit,
    get_entry_info,
    update_entry_person_fields,
    list_entry_catalog_items_for_export,
    search_entry_catalog_items,
    update_entry_catalog_item_by_id,
)

from common.repositories.template_repo import (
    template_repo,
    list_catalog_templates,
    list_catalog_template_items,
    delete_catalog_template_items_and_entry_catalog_items,
    delete_entry_catalog_rows_only,
    delete_orphan_template_item_safely,
    swap_catalog_template_item_sort_order,
    swap_entry_catalog_item_order,
    move_catalog_template_items_to_parent,
    migrate_entry_catalog_items_to_parent,
)

from common.repositories.image_repo import (
    image_repo,
    count_entry_total_images,
    count_entries_total_images,
    list_entry_item_images,
    get_next_image_sort_base,
    upsert_original_images,
    delete_entry_item_image,
    set_cover_image,
    swap_image_sort_order,
    resolve_original_image_info,
)

# 从原始的 inventory_entry_repo 中可能还需要的其他函数
# 这里添加一些可能被使用的额外函数

from typing import Any, Dict, List, Optional
from common.db.session import get_session
from common.db.models import Entry, EntryCatalogItem, EntryItemImage, CatalogTemplateItem


def _ec_data_completeness_score(obj) -> int:
    """给一条 EntryCatalogItem 打"数据完整度"分。

    历史 schema **没有** ``UNIQUE(entry_id, template_item_id)`` 约束，
    并发 upsert / WAL 回放有概率在同一槽位下产生多条 EC 行，
    其中可能既有"用户填了数据的行"，也有"刚被自动建出但还没填的空行"。
    选取顺序若按 id desc / updated_at desc，可能让空行盖住数据行
    —— 这就是用户反馈"每类第一条都没了"的另一种潜在成因。

    本函数按字段重要性给每条行打分：分高的视作"更值得保留的代表行"。
    ``name`` 是档案目录的核心字段，权重最大；其次是 ``pages``、``attachment`` 等。
    """
    score = 0
    if (getattr(obj, "name", "") or "").strip():
        score += 100
    if getattr(obj, "pages", None) is not None:
        score += 30
    if (getattr(obj, "attachment_path", "") or "").strip():
        score += 25
    if (getattr(obj, "remark", "") or "").strip():
        score += 15
    if (getattr(obj, "serial", "") or "").strip():
        score += 12
    if (getattr(obj, "year", "") or "").strip():
        score += 8
    if (getattr(obj, "month", "") or "").strip():
        score += 4
    if (getattr(obj, "day", "") or "").strip():
        score += 2
    return score


def _pick_most_complete_ec(session, entry_id: int, template_item_id: int):
    """在 (entry_id, template_item_id) 下挑选"最有数据"的 EC 行。

    返回 SQLAlchemy 对象，无匹配时返回 ``None``。

    选择规则：
    - 完整度评分最高
    - 同分时 ``id`` 最小（最早创建，避免被后到的空行替身覆盖）

    ⚠️ 所有"按 (entry_id, template_item_id) 找已有 EC 行"的查询都必须用本函数，
    禁止再使用 ``order_by(updated_at.desc(), id.desc()).first()`` 那种容易选错
    空行的方式。这是杜绝"每类第一条都没了"的统一拦截点。
    """
    rows = (
        session.query(EntryCatalogItem)
        .filter(
            EntryCatalogItem.entry_id == int(entry_id),
            EntryCatalogItem.template_item_id == int(template_item_id),
        )
        .order_by(EntryCatalogItem.id.asc())
        .all()
    )
    if not rows:
        return None
    return max(
        rows,
        key=lambda o: (_ec_data_completeness_score(o), -int(o.id)),
    )


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


def list_distinct_entry_org_paths() -> List[str]:
    """返回 entries 表中出现过的 org_path"""
    with get_session() as session:
        rows = session.query(Entry.org_path).distinct().all()
        return [r[0] or "" for r in rows]


def list_entries_by_org_path(org_path: str) -> List[Dict[str, Any]]:
    """向后兼容：按 org_path 列出条目"""
    with get_session() as session:
        if org_path == "":
            persons = session.query(Entry).filter((Entry.org_path == None) | (Entry.org_path == "")).all()
        else:
            persons = session.query(Entry).filter(Entry.org_path == org_path).all()
        return [
            {
                "id": p.id,
                "name": p.name or "",
                "emp_no": p.emp_no or "",
                "role_title": p.role_title or "",
                "phone": p.phone or "",
                "status": p.status or "",
                "id_card": p.id_card or "",
                "template_id": p.template_id,
                "org_unit_id": p.org_unit_id,
            }
            for p in persons
        ]


def find_entry_for_autoselect(passed_entry_id: Optional[int], emp_no: str) -> Optional[Dict[str, Any]]:
    """给目录录入对话框"自动选模板"用"""
    with get_session() as session:
        entry = None
        if passed_entry_id:
            entry = session.query(Entry).filter(Entry.id == passed_entry_id).first()
        elif emp_no:
            entry = session.query(Entry).filter(Entry.emp_no == emp_no).first()
        if not entry:
            return None
        return {"id": entry.id, "template_id": entry.template_id}


def ensure_entry_record(
    *,
    passed_entry_id: Optional[int],
    owner_id: int,
    template_id: int,
    emp_no: str,
    name: str,
    role_title: str,
    phone: str,
    status: str,
) -> Optional[int]:
    """确保当前录入对象有对应的 Entry 记录"""
    with get_session() as session:
        if passed_entry_id:
            entry = session.query(Entry).filter(Entry.id == passed_entry_id).first()
            if entry:
                return entry.id

        entry = (
            session.query(Entry)
            .filter(Entry.emp_no == emp_no, Entry.template_id == template_id)
            .first()
        )
        if not entry:
            entry = Entry(
                owner_id=owner_id,
                template_id=template_id,
                name=name,
                emp_no=emp_no,
                role_title=role_title,
                phone=phone,
                status=status,
            )
            session.add(entry)
            session.commit()
        return entry.id


def get_entry_catalog_item_readonly(*, entry_id: int, template_item_id: int) -> Dict[str, Any]:
    """只读获取 entry_catalog_item（重复时按完整度选最有数据的那条）。"""
    with get_session() as session:
        obj = _pick_most_complete_ec(session, entry_id, template_item_id)
        if not obj:
            return {
                "id": None,
                "serial": "",
                "name": "",
                "year": None,
                "month": None,
                "day": None,
                "pages": None,
                "remark": "",
            }
        is_empty_payload = (
            not (obj.serial or "").strip()
            and not (obj.name or "").strip()
            and not (obj.year or "").strip()
            and not (obj.month or "").strip()
            and not (obj.day or "").strip()
            and obj.pages is None
            and not (obj.remark or "").strip()
            and not (obj.attachment_path or "").strip()
        )
        if is_empty_payload:
            has_image = (
                session.query(EntryItemImage.id)
                .filter(EntryItemImage.entry_catalog_item_id == obj.id)
                .first()
                is not None
            )
            if not has_image:
                return {
                    "id": obj.id,
                    "serial": "",
                    "name": "",
                    "year": None,
                    "month": None,
                    "day": None,
                    "pages": None,
                    "remark": "",
                }
        return {
            "id": obj.id,
            "serial": obj.serial or "",
            "name": obj.name or "",
            "year": obj.year,
            "month": obj.month,
            "day": obj.day,
            "pages": obj.pages,
            "remark": obj.remark,
        }


def ensure_entry_catalog_item(*, entry_id: int, template_item_id: int) -> int:
    """确保 entry_catalog_item 存在（重复时返回最有数据的那条 id，杜绝再分裂）。"""
    with get_session() as session:
        obj = _pick_most_complete_ec(session, entry_id, template_item_id)
        if obj:
            return obj.id

        obj = EntryCatalogItem(entry_id=entry_id, template_item_id=template_item_id)
        session.add(obj)
        session.commit()
        return obj.id


def upsert_entry_catalog_item_field(
    *,
    entry_id: int,
    template_item_id: int,
    entry_catalog_item_id: Optional[int],
    field: str,
    value: Any,
) -> int:
    """确保 entry_catalog_item 存在并更新一个字段（重复时按完整度挑写入目标）。"""
    # 空串归一化：pages 是 Integer 列，写 "" 会触发 DataError。
    if field == "pages" and isinstance(value, str) and value == "":
        value = None
    with get_session() as session:
        ec_id = entry_catalog_item_id
        if not ec_id:
            ec_item = _pick_most_complete_ec(session, entry_id, template_item_id)
            if ec_item:
                ec_id = ec_item.id
            else:
                ec_item = EntryCatalogItem(entry_id=entry_id, template_item_id=template_item_id)
                session.add(ec_item)
                session.flush()
                ec_id = ec_item.id
        session.query(EntryCatalogItem).filter(EntryCatalogItem.id == ec_id).update({field: value})
        session.commit()
        return int(ec_id)


def batch_get_entry_catalog_items(*, entry_id: int) -> dict:
    """一次性加载 entry 下所有目录项，返回 {template_item_id: item_dict}。

    重复行处理（数据安全严格保护）
    ------------------------------
    历史并发 upsert 可能在同一 ``(entry_id, template_item_id)`` 下产生多条 EC 行，
    其中"刚自动建出的空行"如果按 id/updated_at 排序排在用户填了数据的行后面，
    用 ``result[template_item_id] = ...`` 直接覆盖会让 UI 看不到用户的数据。
    这正是用户反馈"每类第一条都没了"的另一种潜在成因。

    本函数改为按"数据完整度"挑代表行：
    - 同 ``template_item_id`` 出现多条 → 选 ``_ec_data_completeness_score``
      最高的那条作为 UI 展示行；分数相同时取 ``id`` 最小（最早创建）的，
      这样"先填了数据 → 之后又自动建空行"的常见场景一定会保留数据行。
    - 输出诊断日志，方便管理员定位 DB 中的重复并人工合并。
    """
    with get_session() as session:
        rows = (
            session.query(EntryCatalogItem)
            .filter(EntryCatalogItem.entry_id == entry_id)
            .order_by(EntryCatalogItem.id.asc())
            .all()
        )
        result: dict = {}
        scores: dict = {}
        shadowed: list = []  # 被遮蔽的重复行 id（仅诊断用）
        for obj in rows:
            tpl_id = obj.template_item_id
            score = _ec_data_completeness_score(obj)
            payload = {
                "id": obj.id,
                "serial": obj.serial or "",
                "name": obj.name or "",
                "year": obj.year,
                "month": obj.month,
                "day": obj.day,
                "pages": obj.pages,
                "remark": obj.remark or "",
                # 乐观锁基线：调用者（UI）把它传回 upsert_entry_catalog_item_fields 时检测冲突
                "updated_at": str(obj.updated_at) if obj.updated_at else None,
            }
            if tpl_id not in result:
                result[tpl_id] = payload
                scores[tpl_id] = score
                continue
            # 同 tpl_id 已经有候选 → 比较完整度
            if score > scores[tpl_id]:
                shadowed.append((tpl_id, result[tpl_id]["id"], obj.id, "kept_new"))
                result[tpl_id] = payload
                scores[tpl_id] = score
            else:
                # 已有候选更完整或同分（此时已有的 id 更小，优先保留），
                # 把当前 obj 记为被遮蔽的重复行
                shadowed.append((tpl_id, obj.id, result[tpl_id]["id"], "kept_existing"))
        if shadowed:
            print(
                f"[catalog-entry] entry_id={entry_id} found {len(shadowed)} "
                f"duplicate EC row(s); UI displays the most complete one. "
                f"Run merge_duplicate_entry_catalog_items() to consolidate."
            )
            for tpl_id, hidden_id, kept_id, _why in shadowed:
                print(f"  tpl_item={tpl_id}: hidden_id={hidden_id} (kept={kept_id})")
        return result


def upsert_entry_catalog_item_fields(
    *,
    entry_id: int,
    template_item_id: int,
    entry_catalog_item_id: Optional[int],
    fields: dict,
    base_updated_at: Optional[str] = None,
):
    """在一次事务中更新多个字段（比逐字段调用 upsert_entry_catalog_item_field 快得多）。

    并发保护（2026-04 新增）
    -----------------------
    可选参数 ``base_updated_at`` 实现**字段级冲突日志**：
    - 调用者传入它加载该行时观察到的 ``updated_at``（ISO8601 或 datetime 字符串）。
    - 如果当前 DB 的 ``updated_at`` 比这个更新，且我们正在写的字段远端值与本地不同，
      记录一条 ``[catalog-conflict]`` 日志方便事后审计。
    - **字段仍按"最后写者胜"落盘**：档案录入场景下，保留用户最新意图比保护旧值更重要。
    - 日志包含 ec_id / field / 本地值 / 远端值 / 两边时间戳，管理员可事后合并。

    返回
    ----
    ``(ec_id, new_updated_at_str)`` —— 便于调用者刷新本地乐观锁基线。
    """
    if not fields:
        return (entry_catalog_item_id or 0, None)

    # 空串归一化：DB Integer 列（pages）不接受 ""，会触发 DataError。
    # 用户清空"页数"输入时，fields={"pages": ""}，这里转为 None（= SQL NULL）。
    # 字符串列（name/serial/year/month/day/remark）写 "" 是合法的，保留不动。
    _integer_cols = {"pages"}
    fields = {
        k: (None if (k in _integer_cols and isinstance(v, str) and v == "") else v)
        for k, v in fields.items()
    }

    with get_session() as session:
        ec_id = entry_catalog_item_id
        current_row = None

        if not ec_id:
            # 同 (entry_id, template_item_id) 在历史并发下可能存在多条 EC 行。
            # 用 _pick_most_complete_ec 统一选行，避免把新数据写到空行上让数据继续分裂
            # （历史 bug "每类第一条都没了"）。同时检测是否有未合并的重复，输出诊断日志。
            all_candidates = (
                session.query(EntryCatalogItem)
                .filter(
                    EntryCatalogItem.entry_id == entry_id,
                    EntryCatalogItem.template_item_id == template_item_id,
                )
                .order_by(EntryCatalogItem.id.asc())
                .all()
            )
            if all_candidates:
                ec_item = max(
                    all_candidates,
                    key=lambda o: (_ec_data_completeness_score(o), -int(o.id)),
                )
                ec_id = ec_item.id
                current_row = ec_item
                if len(all_candidates) > 1:
                    other_ids = [int(c.id) for c in all_candidates if int(c.id) != int(ec_id)]
                    print(
                        f"[catalog-entry] upsert detected {len(all_candidates)} duplicate "
                        f"EC rows for entry={entry_id} tpl={template_item_id}; "
                        f"writing to id={ec_id} (most-complete), shadow ids={other_ids}"
                    )
            else:
                ec_item = EntryCatalogItem(entry_id=entry_id, template_item_id=template_item_id)
                session.add(ec_item)
                session.flush()
                ec_id = ec_item.id
                # 新建行，无冲突可能
                current_row = None

        # 冲突检测（只记录日志，不阻止写入——按最后写者胜）
        if base_updated_at and current_row is None:
            current_row = (
                session.query(EntryCatalogItem)
                .filter(EntryCatalogItem.id == ec_id)
                .first()
            )
        if base_updated_at and current_row is not None:
            remote_updated_at = current_row.updated_at
            if remote_updated_at is not None and str(remote_updated_at) > str(base_updated_at):
                for f, v in fields.items():
                    remote_v = getattr(current_row, f, None)
                    # 两边都有值但不相同 → 真正的冲突
                    if remote_v is not None and str(remote_v) != str(v):
                        print(
                            f"[catalog-conflict] ec_id={ec_id} field={f} "
                            f"base_ts={base_updated_at} remote_ts={remote_updated_at} "
                            f"remote={remote_v!r} local={v!r} -> overwrite (last-writer-wins)"
                        )

        session.query(EntryCatalogItem).filter(EntryCatalogItem.id == ec_id).update(fields)
        session.commit()

        # 取提交后的最新 updated_at，作为调用者新的乐观锁基线
        new_ts = (
            session.query(EntryCatalogItem.updated_at)
            .filter(EntryCatalogItem.id == ec_id)
            .scalar()
        )
        return (int(ec_id), str(new_ts) if new_ts else None)


def merge_duplicate_entry_catalog_items(*, entry_id: int) -> int:
    """合并 ``entry_id`` 下同 ``template_item_id`` 的多条 EC 行（自愈）。

    背景
    ----
    历史 schema 没有给 ``entry_catalog_items`` 加 ``UNIQUE(entry_id, template_item_id)``。
    并发 upsert / WAL 回放 / 多客户端写入有概率在同一槽位下产生多条 EC 行。
    UI 加载时若空行排在数据行后面，会让用户的数据"看不见" —— 这就是反馈
    "每类第一条都没了" 的另一种潜在成因。

    本函数在 **一个事务** 内做以下事情：
    1. 找出同 ``(entry_id, template_item_id)`` 的所有重复行；
    2. 按 ``_ec_data_completeness_score`` 选最完整的一条作为"代表行"，
       同分则取 ``id`` 最小（最早创建的）；
    3. **把每个被淘汰行的非空字段 merge 到代表行**——只填充代表行中
       原本为 None / 空串的字段，**绝不覆盖**代表行已有数据；
    4. 把 ``entry_item_images.entry_catalog_item_id`` 从淘汰行重定向到代表行，
       保证图片资产不丢；
    5. 删除被淘汰的重复行。

    Returns
    -------
    int
        被合并（删除）的重复行总数。
    """
    eid = int(entry_id) if entry_id else 0
    if eid <= 0:
        return 0

    # 用于"非空判定"的小工具
    def _is_empty_str(v) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    merged_total = 0
    with get_session() as session:
        rows = (
            session.query(EntryCatalogItem)
            .filter(EntryCatalogItem.entry_id == eid)
            .order_by(EntryCatalogItem.id.asc())
            .all()
        )
        # 按 tpl_id 分组
        groups: Dict[int, list] = {}
        for r in rows:
            groups.setdefault(int(r.template_item_id), []).append(r)

        ids_to_delete: list = []
        for tpl_id, group in groups.items():
            if len(group) < 2:
                continue

            # 选最完整的代表行；同分时取 id 最小（最早创建）
            keeper = max(
                group,
                key=lambda o: (_ec_data_completeness_score(o), -int(o.id)),
            )
            losers = [o for o in group if int(o.id) != int(keeper.id)]
            if not losers:
                continue

            # 1) 字段 merge：仅填充 keeper 的空字段，绝不覆盖
            keeper_changes: dict = {}
            for loser in losers:
                if _is_empty_str(keeper.serial) and not _is_empty_str(loser.serial):
                    keeper.serial = loser.serial
                    keeper_changes["serial"] = loser.serial
                if _is_empty_str(keeper.name) and not _is_empty_str(loser.name):
                    keeper.name = loser.name
                    keeper_changes["name"] = loser.name
                if _is_empty_str(keeper.year) and not _is_empty_str(loser.year):
                    keeper.year = loser.year
                    keeper_changes["year"] = loser.year
                if _is_empty_str(keeper.month) and not _is_empty_str(loser.month):
                    keeper.month = loser.month
                    keeper_changes["month"] = loser.month
                if _is_empty_str(keeper.day) and not _is_empty_str(loser.day):
                    keeper.day = loser.day
                    keeper_changes["day"] = loser.day
                if keeper.pages is None and loser.pages is not None:
                    keeper.pages = loser.pages
                    keeper_changes["pages"] = loser.pages
                if _is_empty_str(keeper.remark) and not _is_empty_str(loser.remark):
                    keeper.remark = loser.remark
                    keeper_changes["remark"] = loser.remark
                if (
                    _is_empty_str(keeper.attachment_path)
                    and not _is_empty_str(loser.attachment_path)
                ):
                    keeper.attachment_path = loser.attachment_path
                    keeper_changes["attachment_path"] = loser.attachment_path

            # 2) 把图片重定向到 keeper（保证图片资产不丢）
            loser_ids = [int(o.id) for o in losers]
            session.query(EntryItemImage).filter(
                EntryItemImage.entry_catalog_item_id.in_(loser_ids)
            ).update(
                {EntryItemImage.entry_catalog_item_id: int(keeper.id)},
                synchronize_session=False,
            )

            # 3) 把淘汰行加入待删列表
            ids_to_delete.extend(loser_ids)
            print(
                f"[catalog-entry] merge_duplicates entry={eid} tpl={tpl_id}: "
                f"kept id={keeper.id}, merged from ids={loser_ids}, "
                f"backfilled fields={list(keeper_changes.keys())}"
            )

        if ids_to_delete:
            # 审计：删前快照（与 purge_empty 一致）
            from common.services.ec_delete_audit import snapshot_and_log_before_delete
            audit_q = session.query(EntryCatalogItem).filter(
                EntryCatalogItem.id.in_(ids_to_delete)
            )
            snapshot_and_log_before_delete(session, caller="merge_duplicates", query=audit_q)

            session.query(EntryCatalogItem).filter(
                EntryCatalogItem.id.in_(ids_to_delete)
            ).delete(synchronize_session=False)
            merged_total = len(ids_to_delete)

        session.commit()
        return merged_total


def delete_empty_entry_catalog_items(*, entry_id: int, min_age_seconds: int = 3600) -> int:
    """删除当前 entry 下没有任何实际内容且没有图片的目录项。

    保守策略（2026-04 新增）
    -----------------------
    只删除 ``created_at`` 早于 ``min_age_seconds`` 秒前的空行。
    这样可以保护**其他机器刚创建但字段还没到达**的行：
    - 另一台客户端的异步 worker 还没完成字段写入；
    - 另一台客户端因异常退出 / 断电还没触发 WAL 回放；
    - 本机 WAL 回放尚未运行到这条。

    默认窗口 3600 秒（1 小时），对绝大多数在途写入都足够保守。
    """
    from datetime import datetime, timedelta
    threshold = datetime.now() - timedelta(seconds=max(0, int(min_age_seconds)))
    with get_session() as session:
        rows = (
            session.query(EntryCatalogItem)
            .filter(EntryCatalogItem.entry_id == entry_id)
            .order_by(EntryCatalogItem.id.asc())
            .all()
        )
        ids = []
        for obj in rows:
            # 跳过太新的行——可能是别的机器刚插入还没来得及填字段
            if obj.created_at and obj.created_at > threshold:
                continue

            has_image = (
                session.query(EntryItemImage.id)
                .filter(EntryItemImage.entry_catalog_item_id == obj.id)
                .first()
                is not None
            )
            if has_image:
                continue
            is_empty_payload = (
                not (obj.serial or "").strip()
                and not (obj.name or "").strip()
                and not (obj.year or "").strip()
                and not (obj.month or "").strip()
                and not (obj.day or "").strip()
                and obj.pages is None
                and not (obj.remark or "").strip()
                and not (obj.attachment_path or "").strip()
            )
            if is_empty_payload:
                ids.append(int(obj.id))

        if not ids:
            return 0

        # 审计：删前快照
        from common.services.ec_delete_audit import snapshot_and_log_before_delete
        audit_q = session.query(EntryCatalogItem).filter(EntryCatalogItem.id.in_(ids))
        snapshot_and_log_before_delete(session, caller="purge_empty", query=audit_q)

        session.query(EntryCatalogItem).filter(EntryCatalogItem.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
        return len(ids)


import os

def resolve_edit_base_image_info(*, image_id: int, fallback_path: str = "") -> Optional[Dict[str, Any]]:
    """解析修图基线信息"""
    with get_session() as session:
        cur = session.query(EntryItemImage).filter(EntryItemImage.id == image_id).first()
        if not cur:
            return None

        orig_id = int(cur.original_id or cur.id)
        orig = session.query(EntryItemImage).filter(EntryItemImage.id == orig_id).first() or cur

        base = (
            session.query(EntryItemImage)
            .filter(
                EntryItemImage.original_id == orig_id,
                EntryItemImage.image_type == "retouched",
            )
            .order_by(EntryItemImage.id.desc())
            .first()
        ) or orig

        orig_path = (orig.file_path or "").strip()
        if (not orig_path) and fallback_path:
            orig_path = fallback_path

        base_path = (base.file_path or "").strip()
        if (not base_path) and orig_path:
            base_path = orig_path
        if (not base_path) and fallback_path:
            base_path = fallback_path

        return {
            "orig_id": orig_id,
            "orig_file_path": orig_path,
            "orig_entry_catalog_item_id": orig.entry_catalog_item_id,
            "orig_sort_order": orig.sort_order,
            "base_id": int(base.id),
            "base_file_path": base_path,
            "cur_id": int(cur.id),
            "cur_file_path": (cur.file_path or "").strip(),
        }


def upsert_single_retouched(
    *,
    orig_id: int,
    entry_catalog_item_id: Optional[int],
    orig_sort_order: Optional[int],
    out_path: str,
    out_name: str,
    mime_type: str,
    file_size: Any,
) -> None:
    """写库保证同一 original_id + image_type='retouched' 仅保留 1 条记录"""
    with get_session() as session:
        rows = (
            session.query(EntryItemImage)
            .filter(
                EntryItemImage.original_id == orig_id,
                EntryItemImage.image_type == "retouched",
            )
            .order_by(EntryItemImage.id.asc())
            .all()
        )
        keep = rows[0] if rows else None
        extra = rows[1:] if rows else []

        if keep:
            old_path = keep.file_path or ""
            if entry_catalog_item_id is not None:
                keep.entry_catalog_item_id = entry_catalog_item_id
            keep.file_path = out_path
            keep.file_name = out_name
            keep.file_size = file_size
            keep.mime_type = mime_type or ""
            keep.original_id = orig_id
            keep.sort_order = orig_sort_order or keep.sort_order
            if old_path and old_path != out_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
        else:
            keep = EntryItemImage(
                entry_catalog_item_id=entry_catalog_item_id,
                image_type="retouched",
                file_path=out_path,
                file_name=out_name,
                file_size=file_size,
                mime_type=mime_type or "",
                original_id=orig_id,
                sort_order=orig_sort_order,
            )
            session.add(keep)

        for r in extra:
            old = r.file_path or ""
            try:
                session.delete(r)
            except Exception:
                pass
            if old and old != out_path and os.path.exists(old):
                try:
                    os.remove(old)
                except Exception:
                    pass

        session.commit()


def upsert_retouched_batch(updates: List[Dict[str, Any]]) -> None:
    """批量 upsert retouched 图片"""
    if not updates:
        return
    with get_session() as session:
        for u in updates:
            orig_id = int(u.get("orig_id"))
            out_path = u.get("out_path") or ""
            out_name = u.get("out_name") or os.path.basename(out_path)
            mime_type = u.get("mime_type") or ""
            file_size = u.get("file_size")
            entry_catalog_item_id = u.get("entry_catalog_item_id")
            orig_sort_order = u.get("orig_sort_order")

            rows = (
                session.query(EntryItemImage)
                .filter(
                    EntryItemImage.original_id == orig_id,
                    EntryItemImage.image_type == "retouched",
                )
                .order_by(EntryItemImage.id.asc())
                .all()
            )
            keep = rows[0] if rows else None
            extra = rows[1:] if rows else []

            if keep:
                old_path = keep.file_path or ""
                if entry_catalog_item_id is not None:
                    keep.entry_catalog_item_id = entry_catalog_item_id
                keep.file_path = out_path
                keep.file_name = out_name
                keep.file_size = file_size
                keep.mime_type = mime_type or ""
                keep.original_id = orig_id
                keep.sort_order = orig_sort_order or keep.sort_order
                if old_path and old_path != out_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            else:
                keep = EntryItemImage(
                    entry_catalog_item_id=entry_catalog_item_id,
                    image_type="retouched",
                    file_path=out_path,
                    file_name=out_name,
                    file_size=file_size,
                    mime_type=mime_type or "",
                    original_id=orig_id,
                    sort_order=orig_sort_order,
                )
                session.add(keep)

            for r in extra:
                old = r.file_path or ""
                try:
                    session.delete(r)
                except Exception:
                    pass
                if old and old != out_path and os.path.exists(old):
                    try:
                        os.remove(old)
                    except Exception:
                        pass

        session.commit()


__all__ = [
    'entry_repo',
    'template_repo',
    'image_repo',
    'get_default_template_id',
    'create_entry_person',
    'delete_entry',
    'list_entries_by_org_unit_id',
    'move_entries_to_org_unit',
    'get_entry_info',
    'update_entry_person_fields',
    'list_entry_catalog_items_for_export',
    'search_entry_catalog_items',
    'update_entry_catalog_item_by_id',
    'list_catalog_templates',
    'list_catalog_template_items',
    'create_catalog_template_item',
    'delete_catalog_template_items_and_entry_catalog_items',
    'delete_entry_catalog_rows_only',
    'delete_orphan_template_item_safely',
    'swap_catalog_template_item_sort_order',
    'swap_entry_catalog_item_order',
    'count_entry_total_images',
    'count_entries_total_images',
    'list_entry_item_images',
    'get_next_image_sort_base',
    'upsert_original_images',
    'delete_entry_item_image',
    'set_cover_image',
    'swap_image_sort_order',
    'resolve_original_image_info',
    'list_distinct_entry_org_paths',
    'list_entries_by_org_path',
    'find_entry_for_autoselect',
    'ensure_entry_record',
    'get_entry_catalog_item_readonly',
    'ensure_entry_catalog_item',
    'upsert_entry_catalog_item_field',
    'batch_get_entry_catalog_items',
    'upsert_entry_catalog_item_fields',
    'merge_duplicate_entry_catalog_items',
    'resolve_edit_base_image_info',
    'upsert_single_retouched',
    'upsert_retouched_batch',
]
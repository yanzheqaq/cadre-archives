# -*- coding: utf-8 -*-
"""
回归测试：移动顺序持久化 + 跨人隔离

覆盖两个核心契约：

1. 【顺序持久化】模拟修复后的 UI 移动逻辑（每次 swap 后同步交换两节点
   携带的模板项 id），连续多次上移/下移后按 DB 重建顺序，必须与 UI
   最终顺序完全一致（即"退出再进顺序不变"）。
   同时验证：若不同步交换 id（修复前的行为），连续移动会产生错位——
   证明修复确实针对了根因。

2. 【跨人隔离】对张三(entry 1)做移动/字段修改/新增/删除/孤儿清理的全套
   操作，李四(entry 2)的全部 EC 行逐列对比必须前后完全一致。

运行：
    python tests/test_move_order_persistence_and_isolation.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _bootstrap():
    from sqlalchemy.dialects.sqlite import base as _sqlite_base
    if not getattr(_sqlite_base.SQLiteTypeCompiler, "_patched_bigint_for_test", False):
        def _bigint_as_int(self, type_, **kw):  # noqa: ARG001
            return "INTEGER"
        _sqlite_base.SQLiteTypeCompiler.visit_BIGINT = _bigint_as_int  # type: ignore[attr-defined]
        _sqlite_base.SQLiteTypeCompiler._patched_bigint_for_test = True

    from common.db.engine import Base
    from common.db import models as _m  # noqa: F401

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    import common.db.session as s
    s._SessionLocal = Session
    return engine, Session


N_SLOTS = 6


def _seed(Session):
    """1 个模板 + 1 个大类 + N_SLOTS 个叶子槽位；张三/李四各有完整 EC 行。"""
    from common.db.models import (
        CatalogTemplate, CatalogTemplateItem, Entry, EntryCatalogItem, User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="t", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="模板", is_default=True))
        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三", template_id=1, org_path=""))
        sess.add(Entry(id=2, owner_id=1, emp_no="A002", name="李四", template_id=1, org_path=""))
        sess.add(CatalogTemplateItem(id=100, template_id=1, parent_id=None,
                                     serial="一", name="大类", sort_order=0))
        sess.add(CatalogTemplateItem(id=200, template_id=1, parent_id=None,
                                     serial="二", name="第二类", sort_order=1))
        for k in range(N_SLOTS):
            sess.add(CatalogTemplateItem(id=1000 + k, template_id=1, parent_id=100,
                                         serial="", name="", sort_order=k))
            for entry_id, tag in ((1, "张"), (2, "李")):
                sess.add(EntryCatalogItem(
                    id=entry_id * 10000 + k, entry_id=entry_id,
                    template_item_id=1000 + k,
                    serial=str(k + 1), name=f"{tag}-材料{k}",
                    year="2024", month="3", day=str(k + 1),
                    pages=k + 1, remark=f"{tag}备注{k}",
                ))
        sess.commit()


def _db_order(Session, entry_id: int):
    """按 DB 重建显示顺序：槽位按 sort_order,id 排，取该 entry 的内容名。"""
    from common.db.models import CatalogTemplateItem, EntryCatalogItem
    with Session() as sess:
        slots = (sess.query(CatalogTemplateItem)
                 .filter(CatalogTemplateItem.parent_id == 100)
                 .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
                 .all())
        out = []
        for slot in slots:
            ec = (sess.query(EntryCatalogItem)
                  .filter(EntryCatalogItem.entry_id == entry_id,
                          EntryCatalogItem.template_item_id == slot.id)
                  .first())
            if ec is not None:
                out.append(ec.name)
        return out


def _dump_entry_rows(Session, entry_id: int):
    from common.db.models import EntryCatalogItem
    with Session() as sess:
        rows = (sess.query(EntryCatalogItem)
                .filter(EntryCatalogItem.entry_id == entry_id)
                .order_by(EntryCatalogItem.id).all())
        return [
            (r.id, r.template_item_id, r.serial, r.name, r.year, r.month,
             r.day, r.pages, r.remark)
            for r in rows
        ]


class FixedUiModel:
    """模拟修复后的 UI：节点列表按显示顺序，move 后交换两节点的 tpl id。"""

    def __init__(self, Session, entry_id: int):
        self.entry_id = entry_id
        self.nodes = [{"name": n, "tpl": t} for n, t in zip(
            _db_order(Session, entry_id), range(1000, 1000 + N_SLOTS))]

    def move(self, swap_fn, index: int, direction: int) -> bool:
        target = index + direction
        if target < 0 or target >= len(self.nodes):
            return False
        a, b = self.nodes[index], self.nodes[target]
        ok = swap_fn(entry_id=self.entry_id,
                     template_item_id_a=int(a["tpl"]),
                     template_item_id_b=int(b["tpl"]))
        assert ok, "swap 应当成功"
        # 修复核心：DB 交换后同步交换 UI 节点携带的槽位 id
        a["tpl"], b["tpl"] = b["tpl"], a["tpl"]
        # UI 中交换显示位置
        self.nodes[index], self.nodes[target] = self.nodes[target], self.nodes[index]
        return True

    def names(self):
        return [n["name"] for n in self.nodes]


def test_order_persists_after_many_moves(Session):
    from common.repositories.template_repo import swap_entry_catalog_item_order

    ui = FixedUiModel(Session, entry_id=1)
    # 连续多次、混合方向的移动（覆盖相邻互换、同一节点连续移动、来回移动）
    moves = [(0, 1), (1, 1), (2, 1), (5, -1), (4, -1), (0, 1), (3, -1), (3, -1), (1, 1)]
    for idx, direction in moves:
        ui.move(swap_entry_catalog_item_order, idx, direction)
        # 每一步都验证：按 DB 重建的顺序 == UI 当前顺序（= 重进后看到的顺序）
        assert _db_order(Session, 1) == ui.names(), (
            f"移动({idx},{direction})后 DB 顺序与 UI 不一致: "
            f"DB={_db_order(Session, 1)} UI={ui.names()}")
    print("  [PASS] 连续 %d 次移动后，重新加载顺序与界面一致" % len(moves))


def test_stale_id_reproduces_old_bug(Session):
    """对照组：不同步交换 tpl id（修复前的行为）→ 第二次移动后必然错位。"""
    from common.repositories.template_repo import swap_entry_catalog_item_order

    from common.db.models import EntryCatalogItem
    ui = FixedUiModel(Session, entry_id=1)
    base = ui.names()
    with Session() as sess:
        tpl_backup = {r.id: r.template_item_id
                      for r in sess.query(EntryCatalogItem)
                      .filter(EntryCatalogItem.entry_id == 1).all()}

    # 第一次移动：DB 交换 + UI 挪位置，但**不**交换 tpl id（旧行为）
    a, b = ui.nodes[0], ui.nodes[1]
    swap_entry_catalog_item_order(entry_id=1, template_item_id_a=a["tpl"],
                                  template_item_id_b=b["tpl"])
    ui.nodes[0], ui.nodes[1] = ui.nodes[1], ui.nodes[0]
    assert _db_order(Session, 1) == ui.names(), "第一次移动后应当还一致"

    # 第二次移动同一节点：拿着已经错位的 tpl id 去交换 → DB 换错行
    a2, b2 = ui.nodes[1], ui.nodes[2]
    swap_entry_catalog_item_order(entry_id=1, template_item_id_a=a2["tpl"],
                                  template_item_id_b=b2["tpl"])
    ui.nodes[1], ui.nodes[2] = ui.nodes[2], ui.nodes[1]
    assert _db_order(Session, 1) != ui.names(), (
        "旧行为下第二次移动后 DB 顺序应当与 UI 错位（复现原 bug）")
    print("  [PASS] 旧行为（不同步 id）确实在第二次移动后产生错位，证明根因定位正确")

    # 还原数据，避免影响后续用例
    with Session() as sess:
        for row_id, tpl_id in tpl_backup.items():
            sess.get(EntryCatalogItem, row_id).template_item_id = tpl_id
        sess.commit()
    assert _db_order(Session, 1) == base


def test_zhangsan_ops_do_not_touch_lisi(Session):
    from common.repositories.template_repo import (
        swap_entry_catalog_item_order,
        delete_entry_catalog_rows_only,
        delete_orphan_template_item_safely,
        create_catalog_template_item,
        migrate_entry_catalog_items_to_parent,
    )
    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        ensure_entry_catalog_item,
        upsert_entry_catalog_item_fields,
        merge_duplicate_entry_catalog_items,
        delete_empty_entry_catalog_items,
    )
    from common.db.models import EntryCatalogItem

    lisi_before = _dump_entry_rows(Session, 2)
    lisi_order_before = _db_order(Session, 2)

    # 1) 张三：连续移动
    ui = FixedUiModel(Session, entry_id=1)
    for idx, direction in [(0, 1), (1, 1), (4, -1), (2, 1)]:
        ui.move(swap_entry_catalog_item_order, idx, direction)

    # 2) 张三：字段修改（含序号重编）
    with __import__("common.db.session", fromlist=["get_session"]).get_session() as sess:
        ec_ids = [r.id for r in sess.query(EntryCatalogItem)
                  .filter(EntryCatalogItem.entry_id == 1).all()]
    with Session() as sess:
        ec_tpl = {r.id: r.template_item_id for r in sess.query(EntryCatalogItem)
                  .filter(EntryCatalogItem.entry_id == 1).all()}
    for i, ec_id in enumerate(ec_ids):
        upsert_entry_catalog_item_fields(
            entry_id=1, template_item_id=int(ec_tpl[ec_id]),
            entry_catalog_item_id=int(ec_id),
            fields={"serial": str(i + 1), "remark": "张三改"})

    # 3) 张三：新增一条（新建共享槽位 + EC 行）
    new_tpl = create_catalog_template_item(template_id=1, parent_id=100,
                                           sort_order=N_SLOTS)
    ensure_entry_catalog_item(entry_id=1, template_item_id=int(new_tpl))
    upsert_entry_catalog_item_fields(entry_id=1, template_item_id=int(new_tpl),
                                     entry_catalog_item_id=None,
                                     fields={"name": "张三新增"})

    # 4) 张三：删除两条 + 孤儿清理（李四仍引用这些槽位 → 槽位必须保留）
    delete_entry_catalog_rows_only(
        entry_id=1, template_item_ids=[int(ec_tpl[ec_ids[0]]), int(ec_tpl[ec_ids[1]])])
    for tpl in (1000, 1001, 1002, 1003, 1004, 1005):
        delete_orphan_template_item_safely(tpl)

    # 5) 张三：跨类别迁移一条到第二类
    migrate_entry_catalog_items_to_parent(
        entry_id=1, source_template_item_ids=[int(ec_tpl[ec_ids[2]])],
        target_parent_id=200)

    # 6) 张三：合并重复 + 清理空行
    merge_duplicate_entry_catalog_items(entry_id=1)
    delete_empty_entry_catalog_items(entry_id=1, min_age_seconds=0)

    # 李四的数据必须一个字节都没变
    lisi_after = _dump_entry_rows(Session, 2)
    assert lisi_after == lisi_before, (
        "李四的 EC 行发生了变化！\nbefore=%r\nafter=%r" % (lisi_before, lisi_after))
    assert _db_order(Session, 2) == lisi_order_before, "李四的显示顺序发生了变化！"
    # 李四的 6 条记录一条不少
    assert len(lisi_after) == N_SLOTS
    print("  [PASS] 张三全套操作（移动/改字段/新增/删除/孤儿清理/跨类迁移/合并清理）后，"
          "李四 %d 条数据逐列对比完全不变" % N_SLOTS)


def main():
    print("\n=== 移动顺序持久化 + 跨人隔离 回归测试 ===\n")
    engine, Session = _bootstrap()
    _seed(Session)
    test_order_persists_after_many_moves(Session)
    test_stale_id_reproduces_old_bug(Session)
    test_zhangsan_ops_do_not_touch_lisi(Session)
    print("\nAll tests passed")


if __name__ == "__main__":
    main()

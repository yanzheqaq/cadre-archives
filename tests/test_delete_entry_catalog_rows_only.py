# -*- coding: utf-8 -*-
"""
回归测试：验证用户从录入对话框删行时，绝不会跨 entry 级联删除。

这个测试对应的 bug：
- 用户 A 在自己的 entry_A 里删除一行 → 旧代码用 `delete_catalog_template_items_and_entry_catalog_items`
  这个函数没加 entry_id 过滤，导致 **所有 entry** 中引用同一 template_item 的 EC 行被一起删光；
  加上模板条目本身也被级联删掉，其他所有用户对该"槽位"补齐的数据瞬间蒸发。
- 用户反馈的"每一类的第一条都没了"就是这个 bug 在多人场景下的直接表现。

修复：新增 `delete_entry_catalog_rows_only(entry_id, tpl_item_ids)`，只删本 entry 的 EC 行，
模板条目一律保留。本测试用 SQLite 内存库验证行为，可脱离 MySQL 独立运行。

运行方式（在仓库根目录）：
    python tests/test_delete_entry_catalog_rows_only.py
"""
from __future__ import annotations

import os
import sys

# 允许直接 python tests/xxx.py 执行
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _bootstrap_in_memory_db():
    """构造一个内存 SQLite，并注入所有 models；返回 Session 工厂。"""
    # 先 import Base 和所有 model，让 metadata 知道需要建哪些表
    from common.db.engine import Base
    from common.db import models as _models  # noqa: F401  确保所有 model 被注册

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, Session


def _patch_get_session(Session):
    """把 common.db.session.get_session 替换成我们内存库的工厂。"""
    import common.db.session as s

    s._SessionLocal = Session  # 绕过延迟初始化
    # _SessionLocalProxy 会调用 _get_session_factory() -> 返回 _SessionLocal
    # 所以只要把 _SessionLocal 设好即可


def _seed(Session):
    """造一个典型场景：
    - 1 个 template + 3 个 template_item（1: 顶层, 2: 第一槽位, 3: 第二槽位）
    - 2 个 entry，A 和 B，都在 tpl=2 这个"第一槽位"里填了数据
    """
    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        User,
    )

    # SQLite 对 BigInteger 主键不会自增，显式分配 id；owner_id 是 FK NOT NULL，先建 User
    with Session() as sess:
        user = User(id=1, username="tester", password_hash="x")
        sess.add(user)

        tpl = CatalogTemplate(id=1, owner_id=1, name="干部人事档案目录模板", is_default=True)
        sess.add(tpl)

        top = CatalogTemplateItem(id=1, template_id=1, parent_id=None, serial="一", name="履历材料", sort_order=1)
        slot1 = CatalogTemplateItem(id=2, template_id=1, parent_id=1, serial="", name="", sort_order=1)
        slot2 = CatalogTemplateItem(id=3, template_id=1, parent_id=1, serial="", name="", sort_order=2)
        sess.add_all([top, slot1, slot2])

        entry_a = Entry(id=1, owner_id=1, emp_no="A001", name="张三", template_id=1, org_path="")
        entry_b = Entry(id=2, owner_id=1, emp_no="B001", name="李四", template_id=1, org_path="")
        sess.add_all([entry_a, entry_b])

        # 两个 entry 都在 slot1（第一槽位）和 slot2 里填了数据
        sess.add_all([
            EntryCatalogItem(id=1, entry_id=1, template_item_id=2, serial="1", name="张三履历", year="2024"),
            EntryCatalogItem(id=2, entry_id=1, template_item_id=3, serial="2", name="张三简历", year="2024"),
            EntryCatalogItem(id=3, entry_id=2, template_item_id=2, serial="1", name="李四履历", year="2025"),
            EntryCatalogItem(id=4, entry_id=2, template_item_id=3, serial="2", name="李四简历", year="2025"),
        ])
        sess.commit()

        return {
            "tpl_id": 1,
            "top_id": 1,
            "slot1_id": 2,
            "slot2_id": 3,
            "entry_a_id": 1,
            "entry_b_id": 2,
        }


def _count_rows(Session):
    from common.db.models import CatalogTemplateItem, EntryCatalogItem

    with Session() as sess:
        return {
            "tpl_items": sess.query(CatalogTemplateItem).count(),
            "ec_rows": sess.query(EntryCatalogItem).count(),
        }


def test_new_function_only_deletes_current_entry():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed(Session)

    from common.repositories.template_repo import delete_entry_catalog_rows_only
    from common.db.models import EntryCatalogItem, CatalogTemplateItem

    # 用户 A 删掉了自己的 slot1 行
    removed = delete_entry_catalog_rows_only(
        entry_id=ctx["entry_a_id"],
        template_item_ids=[ctx["slot1_id"]],
    )
    assert removed == 1, f"expected 1 row removed, got {removed}"

    # 断言 1：A 的 slot1 EC 行已删
    with Session() as sess:
        a_slot1 = (
            sess.query(EntryCatalogItem)
            .filter(
                EntryCatalogItem.entry_id == ctx["entry_a_id"],
                EntryCatalogItem.template_item_id == ctx["slot1_id"],
            )
            .first()
        )
        assert a_slot1 is None, "A's slot1 row should be deleted"

        # 断言 2：B 的 slot1 EC 行必须完整保留（这是老 bug 的核心表现）
        b_slot1 = (
            sess.query(EntryCatalogItem)
            .filter(
                EntryCatalogItem.entry_id == ctx["entry_b_id"],
                EntryCatalogItem.template_item_id == ctx["slot1_id"],
            )
            .first()
        )
        assert b_slot1 is not None, "B's slot1 row must NOT be affected by A's deletion"
        assert b_slot1.name == "李四履历", "B's data content must be unchanged"

        # 断言 3：模板条目本身必须全部保留
        tpl_items = sess.query(CatalogTemplateItem).count()
        assert tpl_items == 3, f"template items should remain untouched (3), got {tpl_items}"

        # 断言 4：A 的 slot2 和 B 的 slot2 都不受影响
        a_slot2 = (
            sess.query(EntryCatalogItem)
            .filter(
                EntryCatalogItem.entry_id == ctx["entry_a_id"],
                EntryCatalogItem.template_item_id == ctx["slot2_id"],
            )
            .first()
        )
        assert a_slot2 is not None, "A's slot2 should remain"
        b_slot2 = (
            sess.query(EntryCatalogItem)
            .filter(
                EntryCatalogItem.entry_id == ctx["entry_b_id"],
                EntryCatalogItem.template_item_id == ctx["slot2_id"],
            )
            .first()
        )
        assert b_slot2 is not None, "B's slot2 should remain"


def test_old_function_still_cascades_for_admin_use():
    """旧的 delete_catalog_template_items_and_entry_catalog_items 保留给管理员模板维护用，
    语义仍然是"跨 entry 级联删"。这里仅确认没有被无意改坏。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed(Session)

    from common.repositories.template_repo import delete_catalog_template_items_and_entry_catalog_items
    from common.db.models import CatalogTemplateItem, EntryCatalogItem

    delete_catalog_template_items_and_entry_catalog_items([ctx["slot1_id"]])

    with Session() as sess:
        tpl_remaining = sess.query(CatalogTemplateItem).count()
        assert tpl_remaining == 2, f"admin cascade deletes the tpl item; expected 2, got {tpl_remaining}"
        # 所有 entry 的 slot1 EC 行都没了（管理员语义）
        any_slot1 = (
            sess.query(EntryCatalogItem)
            .filter(EntryCatalogItem.template_item_id == ctx["slot1_id"])
            .first()
        )
        assert any_slot1 is None, "admin cascade removes every entry's slot1 row"


def test_entry_id_is_required():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    _seed(Session)

    from common.repositories.template_repo import delete_entry_catalog_rows_only

    # 忘传 entry_id 不应误伤任何数据
    removed = delete_entry_catalog_rows_only(entry_id=0, template_item_ids=[1, 2, 3])
    assert removed == 0, "missing entry_id must be a no-op, never cascade delete"


def test_placeholder_ids_are_ignored():
    """占位 id（负数或 0）不会被传给数据库，避免误扫全表。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed(Session)

    from common.repositories.template_repo import delete_entry_catalog_rows_only

    removed = delete_entry_catalog_rows_only(
        entry_id=ctx["entry_a_id"],
        template_item_ids=[-1, -2, 0, None],
    )
    assert removed == 0, "negative/zero/None ids must be filtered before SQL"


def _run_all():
    tests = [
        test_new_function_only_deletes_current_entry,
        test_old_function_still_cascades_for_admin_use,
        test_entry_id_is_required,
        test_placeholder_ids_are_ignored,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    print("\nAll tests passed")


if __name__ == "__main__":
    _run_all()

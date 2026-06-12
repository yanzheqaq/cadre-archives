# -*- coding: utf-8 -*-
"""
回归测试：录入对话框"孤儿模板清理"路径必须是数据安全的。

复现的历史 bug
--------------
"每一类的第一条都没了" —— 用户在录入对话框中通过右键"插入一行"创建了一个
新模板条目，后台异步 worker 还没返回 real_tpl_id 时用户就关闭了对话框，
回调发现 tree_item 已 detached，触发"孤儿清理"。

旧实现直接调 ``delete_catalog_template_items_and_entry_catalog_items``
（跨 entry 级联删 EC + 删模板）。但 CatalogTemplate 是**全局共享**的：
异步窗口期内别的客户端可能已经为该新槽位创建了 EC 行（甚至填了数据），
被这次盲目级联一并清光 —— 这就是"每类第一条都没了"在多人协作场景下的成因。

修复后的语义（本测试验证）
--------------------------
- 仅当**确认无任何 EC 行引用**该模板条目时，才删除模板。
- 一旦有引用 → 保留模板（宁可留孤儿槽位，也绝不跨 entry 误删）。

运行方式：
    python tests/test_orphan_template_cleanup.py
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


def _bootstrap_in_memory_db():
    """构造内存 SQLite，并把 BigInteger 主键映射成 INTEGER 让 autoincrement 工作。"""
    # SQLite 对 BigInteger 主键不会 autoincrement，全部当 INTEGER 处理
    from sqlalchemy.dialects.sqlite import base as _sqlite_base
    if not getattr(_sqlite_base.SQLiteTypeCompiler, "_patched_bigint_for_test", False):
        def _bigint_as_int(self, type_, **kw):  # noqa: ARG001
            return "INTEGER"

        _sqlite_base.SQLiteTypeCompiler.visit_BIGINT = _bigint_as_int  # type: ignore[attr-defined]
        _sqlite_base.SQLiteTypeCompiler._patched_bigint_for_test = True

    from common.db.engine import Base
    from common.db import models as _models  # noqa: F401  注册所有 model

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, Session


def _patch_get_session(Session):
    import common.db.session as s

    s._SessionLocal = Session


def _seed_two_users_competing_on_new_slot(Session):
    """模拟并发场景：
    - 用户 A 通过录入对话框异步创建了 ``slot_new``（新模板条目，id=99）
    - worker 返回 real_tpl_id=99 的瞬间，用户 A 关闭了对话框 → tree_item detached
    - **但**用户 B 的客户端已经在自己的 entry_b 下为这个 slot_new 填了一行数据
    - 此时若孤儿清理走旧的级联删 → 用户 B 的数据会被无声清掉
    """
    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        User,
    )

    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="共享模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="一", name="履历材料", sort_order=1))
        # 用户 A 异步创建的新模板条目（"插入一行"产生的）
        sess.add(CatalogTemplateItem(id=99, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=99))

        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))
        sess.add(Entry(id=2, owner_id=1, emp_no="B001", name="李四",
                       template_id=1, org_path=""))

        # 用户 A 自己的录入对话框还没来得及给 slot_new(99) 创建 EC 行就关闭了
        # 但用户 B 的客户端已经看到了新槽位 99，并填进了**重要数据**
        sess.add(EntryCatalogItem(
            id=1001, entry_id=2, template_item_id=99,
            serial="1", name="李四的关键档案", year="2025", month="3",
            pages=10, remark="不能丢的内容",
        ))
        sess.commit()
        return {"new_tpl_id": 99, "entry_a_id": 1, "entry_b_id": 2}


def _seed_truly_orphan_slot(Session):
    """没有任何 entry 引用的真孤儿槽位 —— 应当被清理掉。"""
    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        User,
    )

    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="共享模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="一", name="履历材料", sort_order=1))
        sess.add(CatalogTemplateItem(id=99, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=99))
        sess.commit()
        return {"orphan_tpl_id": 99}


def test_orphan_cleanup_keeps_template_when_other_entry_uses_it():
    """核心回归：用户 B 已有 EC 行引用此 tpl，孤儿清理必须保留模板与 B 的数据。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed_two_users_competing_on_new_slot(Session)

    from common.repositories.template_repo import delete_orphan_template_item_safely
    from common.db.models import CatalogTemplateItem, EntryCatalogItem

    deleted = delete_orphan_template_item_safely(ctx["new_tpl_id"])
    assert deleted is False, "有 EC 引用时绝不能删模板"

    with Session() as sess:
        # 模板必须保留
        tpl = sess.query(CatalogTemplateItem).filter(
            CatalogTemplateItem.id == ctx["new_tpl_id"]
        ).first()
        assert tpl is not None, "模板被错误地删除了"

        # 用户 B 的数据必须完整保留（这就是历史 bug "每类第一条都没了" 的关键资产）
        ec_b = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.entry_id == ctx["entry_b_id"],
            EntryCatalogItem.template_item_id == ctx["new_tpl_id"],
        ).first()
        assert ec_b is not None, "用户 B 的 EC 行被跨 entry 误删（历史 bug 复现）"
        assert ec_b.name == "李四的关键档案"
        assert ec_b.remark == "不能丢的内容"


def test_orphan_cleanup_removes_template_when_truly_unreferenced():
    """对照组：确实无人引用的孤儿模板 → 应当被清理掉。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed_truly_orphan_slot(Session)

    from common.repositories.template_repo import delete_orphan_template_item_safely
    from common.db.models import CatalogTemplateItem

    deleted = delete_orphan_template_item_safely(ctx["orphan_tpl_id"])
    assert deleted is True, "无引用的孤儿模板应被清理"

    with Session() as sess:
        remaining = sess.query(CatalogTemplateItem).filter(
            CatalogTemplateItem.id == ctx["orphan_tpl_id"]
        ).first()
        assert remaining is None, "孤儿模板未被清理"


def test_orphan_cleanup_rejects_invalid_ids():
    """0/负数/None 都是占位 id，不应该触及数据库。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    _seed_two_users_competing_on_new_slot(Session)

    from common.repositories.template_repo import delete_orphan_template_item_safely

    for bad in [0, -1, -999, None]:
        assert delete_orphan_template_item_safely(bad) is False, (
            f"占位 id {bad} 不应触发删除"
        )


def test_orphan_cleanup_does_not_affect_sibling_template_items():
    """清理某个孤儿 tpl 时，同模板下其他 tpl 必须不受影响。"""
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)

    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="共享模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="一", name="履历", sort_order=1))
        sess.add(CatalogTemplateItem(id=10, template_id=1, parent_id=1,
                                     serial="1", name="兄弟槽位 1", sort_order=1))
        sess.add(CatalogTemplateItem(id=11, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=2))  # 这个是孤儿
        sess.add(CatalogTemplateItem(id=12, template_id=1, parent_id=1,
                                     serial="3", name="兄弟槽位 3", sort_order=3))
        sess.commit()

    from common.repositories.template_repo import delete_orphan_template_item_safely
    deleted = delete_orphan_template_item_safely(11)
    assert deleted is True

    from common.db.models import CatalogTemplateItem as TplItem
    with Session() as sess:
        ids = sorted(r.id for r in sess.query(TplItem).all())
        assert ids == [1, 10, 12], f"兄弟模板被误删，剩余 ids={ids}"


def _run_all():
    tests = [
        test_orphan_cleanup_keeps_template_when_other_entry_uses_it,
        test_orphan_cleanup_removes_template_when_truly_unreferenced,
        test_orphan_cleanup_rejects_invalid_ids,
        test_orphan_cleanup_does_not_affect_sibling_template_items,
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

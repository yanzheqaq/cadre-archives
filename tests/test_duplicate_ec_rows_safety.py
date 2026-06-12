# -*- coding: utf-8 -*-
"""
回归测试：同 (entry_id, template_item_id) 多条 EC 行场景下，**绝对不能丢用户数据**。

复现的历史 bug
--------------
"每类第一条都没了" 的另一种潜在成因：

- ``entry_catalog_items`` 表历史 schema **没有** ``UNIQUE(entry_id, template_item_id)``。
- 并发 upsert / WAL 回放 / 多客户端写入有概率产生多条同槽位 EC 行：
  其中一条带数据，另一条是后被自动建出的空行。
- 加载层旧实现 ``result[obj.template_item_id] = ...`` 直接覆盖，
  按 id 升序排序后**保留最后一条**，可能是空行 → 用户的数据"看不见"。
- upsert 旧实现"按 updated_at desc 取一条"也可能选到空行作为更新目标，
  让数据继续分裂。

修复后必须保证（本测试覆盖）
----------------------------
1. ``batch_get_entry_catalog_items`` 在重复存在时返回**最有数据**的行。
2. ``upsert_entry_catalog_item_fields`` 在重复存在时把字段写到最有数据的行上。
3. ``merge_duplicate_entry_catalog_items`` 把重复行合并到代表行：
   - 字段 merge 时只填空字段，**绝不覆盖**已有数据
   - 图片资产 ``entry_item_images`` 重定向到代表行，不丢失
   - 淘汰行被删除

运行方式：
    python tests/test_duplicate_ec_rows_safety.py
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
    from sqlalchemy.dialects.sqlite import base as _sqlite_base
    if not getattr(_sqlite_base.SQLiteTypeCompiler, "_patched_bigint_for_test", False):
        def _bigint_as_int(self, type_, **kw):  # noqa: ARG001
            return "INTEGER"

        _sqlite_base.SQLiteTypeCompiler.visit_BIGINT = _bigint_as_int  # type: ignore[attr-defined]
        _sqlite_base.SQLiteTypeCompiler._patched_bigint_for_test = True

    from common.db.engine import Base
    from common.db import models as _models  # noqa: F401

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, Session


def _patch_get_session(Session):
    import common.db.session as s

    s._SessionLocal = Session


def _seed_with_duplicate_rows(Session):
    """种数据：模拟 entry=1 在 tpl_item=2 这个槽位下出现了两条 EC 行：
    - id=10：用户填的 "出生证明" 等关键数据（早创建 → id 较小）
    - id=20：后来某次并发 upsert 自动建出的空行（晚创建 → id 较大）

    旧 batch_get_entry_catalog_items 用 dict 覆盖时会保留 id=20 那条空行，
    用户的关键数据被遮蔽 —— 这就是"每类第一条都没了"的复现条件。
    """
    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        EntryItemImage,
        User,
    )

    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="共享模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="二", name="自传材料", sort_order=1))
        sess.add(CatalogTemplateItem(id=2, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))

        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))

        # 关键数据行（早创建）
        sess.add(EntryCatalogItem(
            id=10, entry_id=1, template_item_id=2,
            serial="1", name="出生证明", year="2024", month="3", day="5",
            pages=2, remark="重要凭证",
        ))
        # 后来并发产生的空行（晚创建）
        sess.add(EntryCatalogItem(
            id=20, entry_id=1, template_item_id=2,
        ))
        # 关键数据行下挂了一张图片
        sess.add(EntryItemImage(
            id=100, entry_catalog_item_id=10, image_type="original",
            file_path="/tmp/cert.jpg", file_name="cert.jpg",
        ))
        sess.commit()
        return {
            "entry_id": 1,
            "tpl_item_id": 2,
            "data_row_id": 10,
            "empty_row_id": 20,
            "image_id": 100,
        }


# ----------------------------------------------------------------------
# Test 1: 加载层 —— 空行不能遮蔽数据行
# ----------------------------------------------------------------------
def test_batch_load_returns_most_complete_row_when_duplicates_exist():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed_with_duplicate_rows(Session)

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        batch_get_entry_catalog_items,
    )
    items = batch_get_entry_catalog_items(entry_id=ctx["entry_id"])

    # tpl=2 必须返回那条带数据的行（id=10），而不是空行（id=20）
    assert ctx["tpl_item_id"] in items, "目标槽位的 EC 行没被加载"
    payload = items[ctx["tpl_item_id"]]
    assert payload["id"] == ctx["data_row_id"], (
        f"加载层选错了行：返回 id={payload['id']}（应为 {ctx['data_row_id']}）"
        f" → 用户数据被空行遮蔽（历史 bug 复现）"
    )
    assert payload["name"] == "出生证明", "用户的关键数据丢失"
    assert payload["pages"] == 2
    assert payload["remark"] == "重要凭证"


# ----------------------------------------------------------------------
# Test 2: 写入层 —— upsert 选最有数据的行更新，不让数据进一步分裂
# ----------------------------------------------------------------------
def test_upsert_targets_most_complete_row_when_duplicates_exist():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed_with_duplicate_rows(Session)

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        upsert_entry_catalog_item_fields,
    )
    # 不传 ec_id（模拟刚加载的 UI 不知道选哪条），让 upsert 自己挑
    new_ec_id, _ = upsert_entry_catalog_item_fields(
        entry_id=ctx["entry_id"],
        template_item_id=ctx["tpl_item_id"],
        entry_catalog_item_id=None,
        fields={"remark": "已核对"},
    )
    assert new_ec_id == ctx["data_row_id"], (
        f"upsert 选错了行：写到了 id={new_ec_id}（应写到 {ctx['data_row_id']}）"
        f" → 数据继续分裂在多条 EC 上"
    )

    from common.db.models import EntryCatalogItem
    with Session() as sess:
        data_row = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == ctx["data_row_id"]
        ).first()
        empty_row = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == ctx["empty_row_id"]
        ).first()
        assert data_row.remark == "已核对", "新字段没写到数据行"
        assert data_row.name == "出生证明", "原数据被覆盖"
        assert empty_row is not None, "空行不应被 upsert 顺手删除"


# ----------------------------------------------------------------------
# Test 3: 合并函数 —— 字段填空、图片迁移、删除淘汰行
# ----------------------------------------------------------------------
def test_merge_duplicates_consolidates_into_keeper():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)
    ctx = _seed_with_duplicate_rows(Session)

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        merge_duplicate_entry_catalog_items,
    )
    merged = merge_duplicate_entry_catalog_items(entry_id=ctx["entry_id"])
    assert merged == 1, f"应合并 1 条重复行，实际 {merged}"

    from common.db.models import EntryCatalogItem, EntryItemImage
    with Session() as sess:
        # 数据行保留，且数据完整无误
        keeper = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == ctx["data_row_id"]
        ).first()
        assert keeper is not None, "数据行被错误删除"
        assert keeper.name == "出生证明"
        assert keeper.pages == 2
        assert keeper.remark == "重要凭证"

        # 空行被删除
        loser = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == ctx["empty_row_id"]
        ).first()
        assert loser is None, "淘汰行没被删除"

        # 图片仍挂在 keeper 上（资产不丢）
        img = sess.query(EntryItemImage).filter(
            EntryItemImage.id == ctx["image_id"]
        ).first()
        assert img is not None, "图片记录丢失"
        assert img.entry_catalog_item_id == ctx["data_row_id"], (
            "图片没正确指向 keeper"
        )


# ----------------------------------------------------------------------
# Test 4: 合并 —— 反向场景，空行先创建，数据行后到，仍然以数据行为 keeper
# ----------------------------------------------------------------------
def test_merge_keeper_chosen_by_data_completeness_not_id_order():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)

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
                                     serial="一", name="履历", sort_order=1))
        sess.add(CatalogTemplateItem(id=2, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))
        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))
        # 反向：id=10 是空行，id=20 才有数据
        sess.add(EntryCatalogItem(id=10, entry_id=1, template_item_id=2))
        sess.add(EntryCatalogItem(
            id=20, entry_id=1, template_item_id=2,
            name="履历表", pages=3, remark="正本",
        ))
        sess.commit()

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        merge_duplicate_entry_catalog_items,
    )
    merged = merge_duplicate_entry_catalog_items(entry_id=1)
    assert merged == 1

    from common.db.models import EntryCatalogItem
    with Session() as sess:
        # 数据行（id=20）应该被保留
        keeper = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == 20
        ).first()
        loser = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == 10
        ).first()
        assert keeper is not None and keeper.name == "履历表"
        assert loser is None


# ----------------------------------------------------------------------
# Test 5: 合并 —— 多条都带不同字段时，字段 merge 但不覆盖 keeper 已有数据
# ----------------------------------------------------------------------
def test_merge_fills_empty_fields_without_overwriting_existing():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)

    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="一", name="履历", sort_order=1))
        sess.add(CatalogTemplateItem(id=2, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))
        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))

        # keeper 候选：name 满分（100），但 year 为空
        sess.add(EntryCatalogItem(
            id=10, entry_id=1, template_item_id=2,
            name="重要文档",  # 100
        ))
        # 备选：仅有 year 字段（8 分）
        sess.add(EntryCatalogItem(
            id=20, entry_id=1, template_item_id=2,
            year="2024",
        ))
        sess.commit()

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        merge_duplicate_entry_catalog_items,
    )
    merged = merge_duplicate_entry_catalog_items(entry_id=1)
    assert merged == 1

    from common.db.models import EntryCatalogItem
    with Session() as sess:
        keeper = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.id == 10
        ).first()
        assert keeper.name == "重要文档", "keeper 已有数据被错误覆盖"
        assert keeper.year == "2024", "loser 的 year 没被回填到 keeper"


# ----------------------------------------------------------------------
# Test 6: 没有重复行时 merge 是 no-op
# ----------------------------------------------------------------------
def test_merge_is_noop_when_no_duplicates():
    engine, Session = _bootstrap_in_memory_db()
    _patch_get_session(Session)

    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="一", name="履历", sort_order=1))
        sess.add(CatalogTemplateItem(id=2, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))
        sess.add(CatalogTemplateItem(id=3, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=2))
        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))
        sess.add(EntryCatalogItem(id=10, entry_id=1, template_item_id=2, name="A"))
        sess.add(EntryCatalogItem(id=11, entry_id=1, template_item_id=3, name="B"))
        sess.commit()

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        merge_duplicate_entry_catalog_items,
    )
    merged = merge_duplicate_entry_catalog_items(entry_id=1)
    assert merged == 0

    from common.db.models import EntryCatalogItem
    with Session() as sess:
        rows = sess.query(EntryCatalogItem).all()
        assert len(rows) == 2, "无重复时 merge 不应改动数据"


def _run_all():
    tests = [
        test_batch_load_returns_most_complete_row_when_duplicates_exist,
        test_upsert_targets_most_complete_row_when_duplicates_exist,
        test_merge_duplicates_consolidates_into_keeper,
        test_merge_keeper_chosen_by_data_completeness_not_id_order,
        test_merge_fills_empty_fields_without_overwriting_existing,
        test_merge_is_noop_when_no_duplicates,
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

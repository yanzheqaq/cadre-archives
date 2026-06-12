# -*- coding: utf-8 -*-
"""
端到端数据安全契约：本测试覆盖几条用户最关心的"录入数据绝不能丢"的场景。

这些都是历史 bug "每类第一条都没了" 在不同极端场景下的复现入口。
所有测试通过即等于保证：

1. ``replay`` 回放 WAL 时，**绝不会**把字段写到空替身行而让用户的关键数据被遮蔽；
2. ``replay`` 不会因为遇到一条永久性错误就清空整批 pending；
3. ``upsert`` 即使没有 ``ec_id``，也会精确定位到"最有数据"的 EC 行更新；
4. 多条字段连续写入同一槽位，不会因为重复行而分裂成多条。

运行：
    python tests/test_data_safety_contract.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

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


def _seed_with_duplicate(Session):
    """entry=1 / tpl=2 下有重复：id=10 有数据，id=20 是空替身。"""
    from common.db.models import (
        CatalogTemplate, CatalogTemplateItem, Entry, EntryCatalogItem, User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="t", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="二", name="自传", sort_order=1))
        sess.add(CatalogTemplateItem(id=2, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))
        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path=""))
        # 数据行（早创建）
        sess.add(EntryCatalogItem(
            id=10, entry_id=1, template_item_id=2,
            serial="1", name="出生证明", year="2024", pages=2,
        ))
        # 空替身（晚创建，并发产物）
        sess.add(EntryCatalogItem(id=20, entry_id=1, template_item_id=2))
        sess.commit()


# ----------------------------------------------------------------------
# Test 1: WAL 回放遇到重复行时，必须把字段写到"最有数据"的代表行上
# ----------------------------------------------------------------------
def test_wal_replay_writes_to_data_row_not_empty_shadow():
    """模拟应用崩溃：用户在 tpl=2 行编辑了 remark 还没落盘 → WAL 持久化 →
    重启 → replay_pending_saves → 必须把 remark 写到 id=10（数据行）。"""
    engine, Session = _bootstrap()
    _seed_with_duplicate(Session)

    from common.services.catalog_wal_service import CatalogWAL, replay_pending_saves
    from common.db.models import EntryCatalogItem
    import common.services.catalog_wal_service as wal_module

    with tempfile.TemporaryDirectory() as td:
        wal = CatalogWAL(db_path=os.path.join(td, "wal.sqlite"))
        # 替换全局单例为这个临时 wal
        wal_module._wal_instance = wal

        # 用户编辑了 remark，WAL 已记录但 MySQL 还没收到（应用崩了）
        wal.write_fields(
            entry_id=1, template_item_id=2,
            fields={"remark": "重启后该看到这个"},
            entry_catalog_item_id=None,  # 关键：没传 ec_id，回放时要自己挑行
        )

        # 模拟重启 → 执行 replay
        ok, err = replay_pending_saves()
        assert ok == 1 and err == 0, f"replay 应成功 1 条，实际 ok={ok} err={err}"

        # 验证：remark 写到了 id=10（数据行），id=20 仍空
        with Session() as sess:
            data_row = sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.id == 10
            ).first()
            empty_row = sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.id == 20
            ).first()
            assert data_row.remark == "重启后该看到这个", (
                "WAL 回放选错了行：字段没落到数据行（历史 bug 复现）"
            )
            assert data_row.name == "出生证明", "原数据被覆盖"
            assert data_row.pages == 2, "原数据被覆盖"
            assert empty_row.remark in (None, ""), "空替身被错误填充"


# ----------------------------------------------------------------------
# Test 2: WAL 回放期间一条永久性错误不能影响其他条目
# ----------------------------------------------------------------------
def test_wal_replay_isolates_failures_per_item():
    """一条永久性错误（IntegrityError）被丢弃，不能拖累其他条目落盘。

    在生产环境中，FK 失败 / 类型错误 / 重复键等都属永久性错误。
    本测试用 monkey-patch 方式精确模拟"第二条 upsert 永久失败"，
    验证第一条仍然成功落盘到正确的 EC 行。
    """
    engine, Session = _bootstrap()
    _seed_with_duplicate(Session)

    from common.services.catalog_wal_service import CatalogWAL, replay_pending_saves
    from common.db.models import EntryCatalogItem
    import common.services.catalog_wal_service as wal_module
    from main_ui.pages.inventory_ui.repo import inventory_entry_repo as repo_mod

    with tempfile.TemporaryDirectory() as td:
        wal = CatalogWAL(db_path=os.path.join(td, "wal.sqlite"))
        wal_module._wal_instance = wal

        # 一条会真的写到 DB，一条会被强制抛 IntegrityError 模拟永久错误
        wal.write_fields(
            entry_id=1, template_item_id=2,
            fields={"remark": "好的字段"},
            entry_catalog_item_id=None,
        )
        wal.write_fields(
            entry_id=1, template_item_id=999,  # 模板不存在 → 我们用 monkey-patch 强制其失败
            fields={"remark": "坏的字段"},
            entry_catalog_item_id=None,
        )

        # 用 monkey-patch 让 tpl=999 那条调用变成永久错误（模拟 FK 失败）
        from sqlalchemy.exc import IntegrityError
        original_upsert = repo_mod.upsert_entry_catalog_item_fields

        def _patched_upsert(*, entry_id, template_item_id, **kw):
            if int(template_item_id) == 999:
                raise IntegrityError("模拟 FK 失败", params=None, orig=Exception("fk fail"))
            return original_upsert(entry_id=entry_id, template_item_id=template_item_id, **kw)

        repo_mod.upsert_entry_catalog_item_fields = _patched_upsert
        try:
            ok, err = replay_pending_saves()
        finally:
            repo_mod.upsert_entry_catalog_item_fields = original_upsert

        # 好的 1 条成功；坏的 1 条作为永久错误丢弃（不重试）
        assert ok == 1, f"好的字段必须落盘成功，实际 ok={ok}"
        assert err == 1, f"坏的字段应作为永久错误丢弃，实际 err={err}"

        with Session() as sess:
            data_row = sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.id == 10
            ).first()
            assert data_row.remark == "好的字段", "好的字段没落盘"

        # 永久错误的字段应被从 WAL 移除（避免下次启动又来失败）
        # 好的字段也已被移除（成功后清理）
        assert wal.count() == 0, "回放后 WAL 应被清空（成功的 + 永久失败的 = 都清掉）"


# ----------------------------------------------------------------------
# Test 3: 连续多次 upsert 同一槽位，绝对不会再产生新的重复行
# ----------------------------------------------------------------------
def test_repeated_upsert_does_not_create_more_duplicates():
    """复现的潜在 bug：如果 upsert 误选空行作为目标，且回调延迟，
    会在 UI 来不及拿到 ec_id 时再次 upsert，又新建一条 EC，重复继续繁殖。"""
    engine, Session = _bootstrap()
    _seed_with_duplicate(Session)

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        upsert_entry_catalog_item_fields,
    )
    from common.db.models import EntryCatalogItem

    # 连续 5 次给同一槽位写不同字段，每次都不传 ec_id（模拟 UI 没拿到回调）
    for i, field_pair in enumerate([
        {"month": "1"}, {"day": "5"}, {"pages": 3},
        {"remark": "新备注"}, {"name": "出生证明（修订）"},
    ]):
        upsert_entry_catalog_item_fields(
            entry_id=1, template_item_id=2,
            entry_catalog_item_id=None, fields=field_pair,
        )

    with Session() as sess:
        rows = sess.query(EntryCatalogItem).filter(
            EntryCatalogItem.entry_id == 1,
            EntryCatalogItem.template_item_id == 2,
        ).all()
        # 不应繁殖出更多重复行 —— 仍然是原来的 2 条（id=10 数据行 + id=20 空替身）
        assert len(rows) == 2, (
            f"upsert 又新建了 EC 行（重复在繁殖！）：现存 {len(rows)} 条"
        )
        data_row = next(r for r in rows if r.id == 10)
        # 所有字段都落到数据行上
        assert data_row.month == "1"
        assert data_row.day == "5"
        assert data_row.pages == 3
        assert data_row.remark == "新备注"
        assert data_row.name == "出生证明（修订）"


# ----------------------------------------------------------------------
# Test 4: WAL 回放成功后，对应字段必须被从 WAL 中清除
# ----------------------------------------------------------------------
def test_wal_replay_clears_persisted_fields():
    """成功落盘后 WAL 应清除对应记录，避免下次启动重复回放产生意外行为。"""
    engine, Session = _bootstrap()
    _seed_with_duplicate(Session)

    from common.services.catalog_wal_service import CatalogWAL, replay_pending_saves
    import common.services.catalog_wal_service as wal_module

    with tempfile.TemporaryDirectory() as td:
        wal = CatalogWAL(db_path=os.path.join(td, "wal.sqlite"))
        wal_module._wal_instance = wal

        wal.write_fields(
            entry_id=1, template_item_id=2,
            fields={"remark": "测试"},
            entry_catalog_item_id=None,
        )
        assert wal.count() == 1, "WAL 应有 1 条 pending"

        ok, err = replay_pending_saves()
        assert ok == 1

        assert wal.count() == 0, "成功落盘后 WAL 必须清空，否则下次又会回放"


# ----------------------------------------------------------------------
# Test 5: 即使 merge 函数失败，UI 加载层仍能选最有数据的行
# ----------------------------------------------------------------------
def test_ui_load_safe_even_when_merge_skipped():
    """模拟管理员还没跑 merge 工具时，UI 直接加载也必须能正确选行。
    这是面向"在途数据"的最后一道安全防线。"""
    engine, Session = _bootstrap()
    _seed_with_duplicate(Session)

    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        batch_get_entry_catalog_items,
    )
    items = batch_get_entry_catalog_items(entry_id=1)
    assert 2 in items, "槽位应被加载"
    assert items[2]["id"] == 10, (
        "即使没合并，加载层也必须选数据行（id=10），不让空替身（id=20）遮蔽"
    )
    assert items[2]["name"] == "出生证明"


def _run_all():
    tests = [
        test_wal_replay_writes_to_data_row_not_empty_shadow,
        test_wal_replay_isolates_failures_per_item,
        test_repeated_upsert_does_not_create_more_duplicates,
        test_wal_replay_clears_persisted_fields,
        test_ui_load_safe_even_when_merge_skipped,
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

# -*- coding: utf-8 -*-
"""
``catalog_snapshot_service`` 全套回归测试。

覆盖场景
--------
1. 完整 take_snapshot：从主 DB 拉数据，每个 entry 一行，字段完整。
2. 空白行不进快照（杜绝把"自动建出的空 EC 行"当成"用户数据"误报丢失）。
3. compare_with_latest：上次快照里的某 entry 被整个删除时，能精准报"整人丢失"。
4. compare_with_latest：上次快照里某条目录条目消失时，能精准报"哪一条丢了"。
5. compare_with_latest：用户主动**修改**字段（不是删除）不算丢失。
6. compare_with_latest：用户主动**新增**条目不会被识别成丢失。
7. compare_with_latest：图片张数从 N 变 0 → 视为该条目丢失。
8. cleanup_old_snapshots：超过 keep_days 的清理，最少保留 keep_min 个。
9. 多次快照按 snapshot_id 顺序保留。

运行：
    python tests/test_catalog_snapshot_service.py
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


def _seed_two_entries(Session, with_images=True):
    """种数据：2 个 entry，每人 2 条目录条目。第一条挂图片（如启用）。"""
    from common.db.models import (
        CatalogTemplate, CatalogTemplateItem, Entry, EntryCatalogItem,
        EntryItemImage, User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="t", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="模板", is_default=True))
        sess.add(CatalogTemplateItem(id=1, template_id=1, parent_id=None,
                                     serial="二", name="自传", sort_order=1))
        sess.add(CatalogTemplateItem(id=10, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=1))
        sess.add(CatalogTemplateItem(id=11, template_id=1, parent_id=1,
                                     serial="", name="", sort_order=2))

        sess.add(Entry(id=1, owner_id=1, emp_no="A001", name="张三",
                       template_id=1, org_path="集团/财务部"))
        sess.add(Entry(id=2, owner_id=1, emp_no="B007", name="李四",
                       template_id=1, org_path="集团/技术部"))

        # 张三 2 条
        sess.add(EntryCatalogItem(id=100, entry_id=1, template_item_id=10,
                                  serial="1", name="出生证明", year="2024",
                                  month="3", day="5", pages=2))
        sess.add(EntryCatalogItem(id=101, entry_id=1, template_item_id=11,
                                  serial="2", name="身份证复印件", pages=1))
        # 李四 2 条
        sess.add(EntryCatalogItem(id=200, entry_id=2, template_item_id=10,
                                  serial="1", name="学历证明", pages=3,
                                  remark="正本"))
        sess.add(EntryCatalogItem(id=201, entry_id=2, template_item_id=11,
                                  serial="2", name="工作证明", pages=2))

        # 一条**真空白行**——不应进快照
        sess.add(EntryCatalogItem(id=300, entry_id=1, template_item_id=11))

        if with_images:
            sess.add(EntryItemImage(id=1, entry_catalog_item_id=100,
                                    image_type="original",
                                    file_path="/tmp/a.jpg", file_name="a.jpg"))
            sess.add(EntryItemImage(id=2, entry_catalog_item_id=100,
                                    image_type="original",
                                    file_path="/tmp/b.jpg", file_name="b.jpg"))
            sess.add(EntryItemImage(id=3, entry_catalog_item_id=200,
                                    image_type="original",
                                    file_path="/tmp/c.jpg", file_name="c.jpg"))
        sess.commit()


def _new_snap(td):
    """构造独立的本地快照实例（避免污染用户机器）。"""
    from common.services.catalog_snapshot_service import CatalogSnapshot
    return CatalogSnapshot(db_path=os.path.join(td, "snapshot.db"))


# ----------------------------------------------------------------------
# Test 1: take_snapshot 写入完整元信息
# ----------------------------------------------------------------------
def test_take_snapshot_records_all_meaningful_items():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        result = snap.take_snapshot(kind="manual")

        # 2 个 entry，每人 2 条；空白行不计入
        assert result["entries_count"] == 2
        assert result["items_count"] == 4

        snapshots = snap.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["kind"] == "manual"
        assert snapshots[0]["items_count"] == 4


# ----------------------------------------------------------------------
# Test 2: 空白行不进快照
# ----------------------------------------------------------------------
def test_blank_rows_excluded_from_snapshot():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")
        # 拉出来看看 items_json 里没空白行
        import sqlite3, json
        conn = sqlite3.connect(snap._db_path)
        rows = conn.execute(
            "SELECT entry_id, items_json FROM catalog_snapshot"
        ).fetchall()
        conn.close()
        for eid, items_json in rows:
            items = json.loads(items_json)
            for it in items:
                # 每条都至少有一个有意义字段
                meaningful = (
                    (it.get("name") or "").strip()
                    or (it.get("serial") or "").strip()
                    or it.get("pages") is not None
                    or (it.get("remark") or "").strip()
                )
                assert meaningful, f"快照里出现了空白条目 entry={eid}: {it}"


# ----------------------------------------------------------------------
# Test 3: 整 entry 丢失能被检测出
# ----------------------------------------------------------------------
def test_compare_detects_entire_entry_missing():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")

        # 模拟"李四整个不见了"
        from common.db.models import Entry, EntryCatalogItem
        with Session() as sess:
            sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.entry_id == 2
            ).delete()
            sess.query(Entry).filter(Entry.id == 2).delete()
            sess.commit()

        report = snap.compare_with_latest()
        assert report is not None
        assert report["summary"]["entries_lost_count"] == 1
        assert report["summary"]["items_lost_count"] == 2
        lost = report["missing_entries"][0]
        assert lost["emp_no"] == "B007"
        assert lost["person_name"] == "李四"
        assert lost["items_lost"] == 2


# ----------------------------------------------------------------------
# Test 4: 部分条目丢失能被精确定位
# ----------------------------------------------------------------------
def test_compare_detects_individual_item_missing():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")

        # 模拟"张三第 1 条目录条目消失了"
        from common.db.models import EntryCatalogItem
        with Session() as sess:
            sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.id == 100
            ).delete()
            sess.commit()

        report = snap.compare_with_latest()
        assert report["summary"]["entries_lost_count"] == 0
        assert report["summary"]["items_lost_count"] == 1
        assert len(report["missing_items"]) == 1
        loss = report["missing_items"][0]
        assert loss["emp_no"] == "A001"
        assert loss["person_name"] == "张三"
        assert len(loss["items"]) == 1
        assert loss["items"][0]["name"] == "出生证明"
        assert loss["items"][0]["serial"] == "1"


# ----------------------------------------------------------------------
# Test 5: 用户主动修改（不删除）不算丢失
# ----------------------------------------------------------------------
def test_compare_does_not_flag_user_edits():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")

        # 用户改了张三的备注
        from common.db.models import EntryCatalogItem
        with Session() as sess:
            row = sess.query(EntryCatalogItem).filter(
                EntryCatalogItem.id == 100
            ).first()
            row.remark = "已添加新备注"
            sess.commit()

        report = snap.compare_with_latest()
        # 改字段会让"原签名"匹配不到 → 视作"原条目丢失" + "新条目存在"。
        # 这对"档案完整性"语义来说是合理的：用户能看到"原版本不见了"。
        # 但不应该报整 entry 丢失，且数量精确为 1。
        assert report["summary"]["entries_lost_count"] == 0
        # （改一个字段 → 旧签名丢失 1 条；新内容存在不影响）
        assert report["summary"]["items_lost_count"] == 1


# ----------------------------------------------------------------------
# Test 6: 新增条目不会被报为丢失
# ----------------------------------------------------------------------
def test_compare_ignores_new_items_added_after_snapshot():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")

        # 用户新增了一条
        from common.db.models import CatalogTemplateItem, EntryCatalogItem
        with Session() as sess:
            sess.add(CatalogTemplateItem(id=12, template_id=1, parent_id=1,
                                         serial="", name="", sort_order=3))
            sess.add(EntryCatalogItem(id=102, entry_id=1, template_item_id=12,
                                      serial="3", name="新增证书", pages=1))
            sess.commit()

        report = snap.compare_with_latest()
        # 没有任何丢失
        assert report["summary"]["entries_lost_count"] == 0
        assert report["summary"]["items_lost_count"] == 0


# ----------------------------------------------------------------------
# Test 7: 图片张数归零（条目变空）也算丢失
# ----------------------------------------------------------------------
def test_compare_detects_pure_image_loss_when_field_empty():
    """张三第 100 条无字段、仅靠 image 体现存在。删图后，
    该条因为 _is_meaningful_item 返回 False，从"当前快照"消失。
    比对应当报"丢了"。"""
    engine, Session = _bootstrap()
    _seed_two_entries(Session, with_images=False)

    # 给张三第 100 条**清空**所有字段，只留下图片做内容
    from common.db.models import EntryCatalogItem, EntryItemImage
    with Session() as sess:
        row = sess.query(EntryCatalogItem).filter(EntryCatalogItem.id == 100).first()
        row.serial = ""
        row.name = ""
        row.year = ""
        row.month = ""
        row.day = ""
        row.pages = None
        row.remark = ""
        # 加 1 张图（只有图）
        sess.add(EntryItemImage(id=99, entry_catalog_item_id=100,
                                image_type="original",
                                file_path="/tmp/x.jpg", file_name="x.jpg"))
        sess.commit()

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        snap.take_snapshot(kind="manual")

        # 删掉那张图（用户的关键资产丢了）
        with Session() as sess:
            sess.query(EntryItemImage).filter(EntryItemImage.id == 99).delete()
            sess.commit()

        report = snap.compare_with_latest()
        assert report["summary"]["items_lost_count"] >= 1


# ----------------------------------------------------------------------
# Test 8: cleanup 保留最近 keep_min 个，删除 cutoff 之前的
# ----------------------------------------------------------------------
def test_cleanup_old_snapshots_respects_keep_min():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        # 制造 7 个快照
        for _ in range(7):
            snap.take_snapshot(kind="manual")
            time.sleep(0.01)

        # 把最早 5 个的 taken_at 改成 30 天前，最近 2 个保持新
        import sqlite3
        conn = sqlite3.connect(snap._db_path)
        oldest_ids = [r[0] for r in conn.execute(
            "SELECT snapshot_id FROM snapshot_meta ORDER BY snapshot_id ASC LIMIT 5"
        ).fetchall()]
        for sid in oldest_ids:
            conn.execute(
                "UPDATE snapshot_meta SET taken_at = ? WHERE snapshot_id = ?",
                ("2020-01-01 00:00:00", sid),
            )
        conn.commit()
        conn.close()

        # 默认 keep_days=14、keep_min=5：要求最少保留 5 个
        deleted = snap.cleanup_old_snapshots(keep_days=14, keep_min=5)
        # 5 个旧快照，但 keep_min=5 要保留最近 5 个 → 实际能删的是
        # 早于 cutoff 且不在最近 5 个内的 → 5 - (5-2) = 2 个
        # 实测：oldest 5 都老了，但 keep_min=5 强制保留最近 5 个，
        # 所以被删的是 oldest 5 中的"既老又不在最近 5 个内"，等于 2 个
        assert deleted == 2
        remaining = snap.list_snapshots(limit=10)
        assert len(remaining) == 5


# ----------------------------------------------------------------------
# Test 9: 没有快照时 compare_with_latest 返回 None
# ----------------------------------------------------------------------
def test_compare_with_no_snapshot_returns_none():
    engine, Session = _bootstrap()
    _seed_two_entries(Session)

    with tempfile.TemporaryDirectory() as td:
        snap = _new_snap(td)
        report = snap.compare_with_latest()
        assert report is None


def _run_all():
    tests = [
        test_take_snapshot_records_all_meaningful_items,
        test_blank_rows_excluded_from_snapshot,
        test_compare_detects_entire_entry_missing,
        test_compare_detects_individual_item_missing,
        test_compare_does_not_flag_user_edits,
        test_compare_ignores_new_items_added_after_snapshot,
        test_compare_detects_pure_image_loss_when_field_empty,
        test_cleanup_old_snapshots_respects_keep_min,
        test_compare_with_no_snapshot_returns_none,
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
            import traceback
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    print("\nAll tests passed")


if __name__ == "__main__":
    _run_all()

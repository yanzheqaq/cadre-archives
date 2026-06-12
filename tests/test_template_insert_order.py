# -*- coding: utf-8 -*-
"""
回归测试：目录录入右键“在上方/下方插入一行”后，关闭重开顺序必须保持。

核心要求：
1. 插入时同父节点下 catalog_template_items.sort_order 必须整体重排，不能产生重复 sort_order。
2. 只更新模板项排序，不删除、不改写 entry_catalog_items 中已有录入内容。
3. 重新按 list_catalog_template_items 加载时，新行仍在用户选择的位置。
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
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles
    from common.db.engine import Base
    from common.db import models as _models  # noqa: F401

    @compiles(BigInteger, "sqlite")
    def _compile_big_integer_sqlite(type_, compiler, **kw):
        return "INTEGER"

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    import common.db.session as s
    s._SessionLocal = Session
    return engine, Session


def _seed(Session):
    from common.db.models import CatalogTemplate, CatalogTemplateItem, Entry, EntryCatalogItem, User

    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="T", is_default=True))
        sess.add(CatalogTemplateItem(id=10, template_id=1, parent_id=None, serial="二", name="自传材料", sort_order=1))
        sess.add_all([
            CatalogTemplateItem(id=101, template_id=1, parent_id=10, serial="", name="", sort_order=1),
            CatalogTemplateItem(id=102, template_id=1, parent_id=10, serial="", name="", sort_order=2),
            CatalogTemplateItem(id=103, template_id=1, parent_id=10, serial="", name="", sort_order=3),
            CatalogTemplateItem(id=104, template_id=1, parent_id=10, serial="", name="", sort_order=4),
        ])
        sess.add(Entry(id=201, owner_id=1, template_id=1, emp_no="A001", name="张三"))
        sess.add_all([
            EntryCatalogItem(id=301, entry_id=201, template_item_id=101, serial="1", name="测试上移1", year="2020"),
            EntryCatalogItem(id=302, entry_id=201, template_item_id=102, serial="2", name="测试上移2", year="2021"),
            EntryCatalogItem(id=303, entry_id=201, template_item_id=103, serial="3", name="测试上移3", year="2022"),
            EntryCatalogItem(id=304, entry_id=201, template_item_id=104, serial="4", name="测试上移4", year="2023"),
        ])
        sess.commit()


def _child_order_from_repo():
    from common.repositories.template_repo import list_catalog_template_items
    rows = list_catalog_template_items(1)
    return [r["id"] for r in rows if r.get("parent_id") == 10]


def _ec_snapshot(Session):
    from common.db.models import EntryCatalogItem
    with Session() as sess:
        rows = sess.query(EntryCatalogItem).order_by(EntryCatalogItem.id).all()
        return [(r.id, r.entry_id, r.template_item_id, r.serial, r.name, r.year, r.month, r.day, r.pages, r.remark) for r in rows]


def test_insert_above_first_keeps_first_after_reload():
    engine, Session = _bootstrap_in_memory_db()
    _seed(Session)
    before_ec = _ec_snapshot(Session)

    from common.repositories.template_repo import create_catalog_template_item

    new_id = create_catalog_template_item(
        template_id=1,
        parent_id=10,
        sort_order=1,
        sibling_order_ids=[101, 102, 103, 104],
        insert_index=0,
    )

    assert _child_order_from_repo() == [new_id, 101, 102, 103, 104]
    assert _ec_snapshot(Session) == before_ec, "existing entry_catalog_items must not be changed"


def test_insert_below_first_keeps_second_after_reload():
    engine, Session = _bootstrap_in_memory_db()
    _seed(Session)
    before_ec = _ec_snapshot(Session)

    from common.repositories.template_repo import create_catalog_template_item

    new_id = create_catalog_template_item(
        template_id=1,
        parent_id=10,
        sort_order=2,
        sibling_order_ids=[101, 102, 103, 104],
        insert_index=1,
    )

    assert _child_order_from_repo() == [101, new_id, 102, 103, 104]
    assert _ec_snapshot(Session) == before_ec, "existing entry_catalog_items must not be changed"


def test_insert_below_last_keeps_last_after_reload():
    engine, Session = _bootstrap_in_memory_db()
    _seed(Session)

    from common.repositories.template_repo import create_catalog_template_item

    new_id = create_catalog_template_item(
        template_id=1,
        parent_id=10,
        sort_order=5,
        sibling_order_ids=[101, 102, 103, 104],
        insert_index=4,
    )

    assert _child_order_from_repo() == [101, 102, 103, 104, new_id]


def test_duplicate_old_sort_orders_are_normalized():
    engine, Session = _bootstrap_in_memory_db()
    _seed(Session)

    from common.db.models import CatalogTemplateItem
    from common.repositories.template_repo import create_catalog_template_item

    with Session() as sess:
        sess.query(CatalogTemplateItem).filter(CatalogTemplateItem.id.in_([101, 102, 103, 104])).update(
            {CatalogTemplateItem.sort_order: 1},
            synchronize_session=False,
        )
        sess.commit()

    new_id = create_catalog_template_item(
        template_id=1,
        parent_id=10,
        sort_order=3,
        sibling_order_ids=[101, 102, 103, 104],
        insert_index=2,
    )

    assert _child_order_from_repo() == [101, 102, new_id, 103, 104]
    with Session() as sess:
        orders = [
            r.sort_order
            for r in sess.query(CatalogTemplateItem)
            .filter(CatalogTemplateItem.parent_id == 10)
            .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
            .all()
        ]
    assert orders == [1, 2, 3, 4, 5], f"sort_order must be contiguous, got {orders}"


def _run_all():
    tests = [
        test_insert_above_first_keeps_first_after_reload,
        test_insert_below_first_keeps_second_after_reload,
        test_insert_below_last_keeps_last_after_reload,
        test_duplicate_old_sort_orders_are_normalized,
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

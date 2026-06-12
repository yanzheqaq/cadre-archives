# -*- coding: utf-8 -*-
"""
回归测试：用户清空页数列时（fields={"pages": ""}），upsert 必须把 "" 归一化为 None，
否则 MySQL Integer 列会抛 DataError，pending 队列会反复重试。

用 SQLite 内存库模拟，SQLite 对 "" → Integer 比 MySQL 宽松，所以这里主要验证
归一化逻辑正确执行（pages 最终为 None），而不是 DB 层面的 DataError。
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _bootstrap():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from common.db.engine import Base
    from common.db import models as _m  # noqa: F401

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    import common.db.session as ds
    ds._SessionLocal = Session
    return Session


def _seed(Session):
    from common.db.models import (
        CatalogTemplate, CatalogTemplateItem, Entry, EntryCatalogItem, User,
    )
    with Session() as s:
        s.add_all([
            User(id=1, username="tester", password_hash="x"),
            CatalogTemplate(id=1, owner_id=1, name="T", is_default=True),
            CatalogTemplateItem(id=10, template_id=1, parent_id=None, serial="", name="", sort_order=1),
            Entry(id=100, owner_id=1, template_id=1, name="A"),
            EntryCatalogItem(id=900, entry_id=100, template_item_id=10, pages=5),
        ])
        s.commit()


class EmptyPagesUpsertTests(unittest.TestCase):
    def setUp(self):
        self.Session = _bootstrap()
        _seed(self.Session)

    def _fetch_pages(self, ec_id):
        from common.db.models import EntryCatalogItem
        with self.Session() as s:
            return s.query(EntryCatalogItem.pages).filter_by(id=ec_id).scalar()

    def test_batch_upsert_empty_string_becomes_null(self):
        from main_ui.pages.inventory_ui.repo.inventory_entry_repo import upsert_entry_catalog_item_fields
        self.assertEqual(self._fetch_pages(900), 5)
        upsert_entry_catalog_item_fields(
            entry_id=100, template_item_id=10,
            entry_catalog_item_id=900,
            fields={"pages": ""},
        )
        self.assertIsNone(self._fetch_pages(900), "empty pages should be stored as NULL")

    def test_batch_upsert_normal_integer_string(self):
        from main_ui.pages.inventory_ui.repo.inventory_entry_repo import upsert_entry_catalog_item_fields
        upsert_entry_catalog_item_fields(
            entry_id=100, template_item_id=10,
            entry_catalog_item_id=900,
            fields={"pages": "8"},
        )
        self.assertEqual(self._fetch_pages(900), 8)

    def test_single_field_upsert_empty_string_becomes_null(self):
        from main_ui.pages.inventory_ui.repo.inventory_entry_repo import upsert_entry_catalog_item_field
        self.assertEqual(self._fetch_pages(900), 5)
        upsert_entry_catalog_item_field(
            entry_id=100, template_item_id=10,
            entry_catalog_item_id=900,
            field="pages", value="",
        )
        self.assertIsNone(self._fetch_pages(900))

    def test_string_columns_keep_empty_string(self):
        """name/remark 是 String 列，"" 是合法值，不应被归一化为 None"""
        from main_ui.pages.inventory_ui.repo.inventory_entry_repo import upsert_entry_catalog_item_fields
        from common.db.models import EntryCatalogItem
        upsert_entry_catalog_item_fields(
            entry_id=100, template_item_id=10,
            entry_catalog_item_id=900,
            fields={"name": "", "remark": ""},
        )
        with self.Session() as s:
            row = s.query(EntryCatalogItem).filter_by(id=900).first()
            self.assertEqual(row.name, "")
            self.assertEqual(row.remark, "")


def _run():
    tests = unittest.TestLoader().loadTestsFromTestCase(EmptyPagesUpsertTests)
    failed = []
    for t in tests:
        name = t._testMethodName
        suite = unittest.TestSuite([t])
        res = unittest.TestResult()
        suite.run(res)
        if res.wasSuccessful():
            print(f"[PASS] {name}")
        else:
            failed.append(name)
            for err_src in (res.errors, res.failures):
                for _case, err in err_src:
                    last = err.strip().splitlines()[-1]
                    print(f"[FAIL] {name}: {last}")
    print()
    if failed:
        print(f"{len(failed)} test(s) failed")
        sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    _run()

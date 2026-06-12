# -*- coding: utf-8 -*-
"""
EC 行删除审计日志回归测试

验证：
- 用户删行（scoped）会留审计记录
- 管理员级联删（所有 entry）会留审计记录
- 每条删除记录都包含 entry_id / template_item_id / 原始字段 / 调用栈
- 即便业务 DELETE 走"方案A"只删 EC 不删 tpl，审计内容仍完整
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import unittest

# 把项目根目录加入 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _make_sqlite_engine():
    """用内存 SQLite 搭测试库，隔离业务 MySQL。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from common.db.engine import Base

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session


def _seed(Session):
    from common.db.models import (
        CatalogTemplate,
        CatalogTemplateItem,
        Entry,
        EntryCatalogItem,
        User,
    )
    with Session() as sess:
        sess.add(User(id=1, username="tester", password_hash="x"))
        sess.add(CatalogTemplate(id=1, owner_id=1, name="干部人事档案目录模板", is_default=True))
        sess.add_all([
            CatalogTemplateItem(id=1, template_id=1, parent_id=None, serial="一", name="履历材料", sort_order=1),
            CatalogTemplateItem(id=2, template_id=1, parent_id=1, serial="", name="", sort_order=1),
        ])
        sess.add_all([
            Entry(id=100, owner_id=1, template_id=1, name="A", emp_no="A001"),
            Entry(id=200, owner_id=1, template_id=1, name="B", emp_no="B002"),
        ])
        sess.add_all([
            EntryCatalogItem(id=1, entry_id=100, template_item_id=2, serial="1-1", name="A履历", year="2026", pages=5),
            EntryCatalogItem(id=2, entry_id=200, template_item_id=2, serial="1-1", name="B履历", year="2025", pages=8),
        ])
        sess.commit()


def _patch_audit_to_tempfile():
    """把审计单例指向临时文件，测试完删掉，避免污染用户 LOCALAPPDATA。"""
    import common.services.ec_delete_audit as mod
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    mod._instance = mod._ECDeleteAudit(db_path=tmp.name)
    return tmp.name


def _cleanup_tempfile(path):
    try:
        os.remove(path)
    except Exception:
        pass


class ECDeleteAuditTests(unittest.TestCase):
    def setUp(self):
        self._engine, self._Session = _make_sqlite_engine()
        _seed(self._Session)
        # 内存 Session 工厂装到 common.db.session._SessionLocal（_SessionLocalProxy 会读它）
        import common.db.session as db_session
        self._orig_session_local = getattr(db_session, "_SessionLocal", None)
        db_session._SessionLocal = self._Session

        self._audit_db = _patch_audit_to_tempfile()

    def tearDown(self):
        import common.db.session as db_session
        db_session._SessionLocal = self._orig_session_local
        _cleanup_tempfile(self._audit_db)

    def _audit_rows(self):
        from common.services.ec_delete_audit import get_audit
        return get_audit().recent(limit=100)

    def test_user_row_delete_writes_audit(self):
        """用户删自己 entry 的一行 → 审计表有 1 条 caller=user_row_delete 记录"""
        from common.repositories.template_repo import delete_entry_catalog_rows_only

        removed = delete_entry_catalog_rows_only(entry_id=100, template_item_ids=[2])
        self.assertEqual(removed, 1)

        rows = self._audit_rows()
        self.assertEqual(len(rows), 1, f"expected 1 audit row, got {len(rows)}")
        r = rows[0]
        self.assertEqual(r["caller"], "user_row_delete")
        self.assertEqual(r["entry_id"], 100)
        self.assertEqual(r["template_item_id"], 2)
        self.assertEqual(r["ec_id"], 1)
        self.assertEqual(r["name"], "A履历")
        self.assertEqual(r["year"], "2026")
        self.assertEqual(r["pages"], 5)
        self.assertTrue(r["stack_trace"], "stack trace should be recorded")

    def test_admin_cascade_writes_audit_for_all_entries(self):
        """管理员级联删 → 审计记录里 entry=100 和 entry=200 两行都在"""
        from common.repositories.template_repo import delete_catalog_template_items_and_entry_catalog_items

        delete_catalog_template_items_and_entry_catalog_items([2])

        rows = self._audit_rows()
        self.assertEqual(len(rows), 2, f"expected 2 audit rows, got {len(rows)}")
        callers = {r["caller"] for r in rows}
        self.assertEqual(callers, {"admin_cascade_delete"})
        entry_ids = sorted(r["entry_id"] for r in rows)
        self.assertEqual(entry_ids, [100, 200])

    def test_admin_cascade_parent_deletes_subtree(self):
        from common.repositories.template_repo import delete_catalog_template_items_and_entry_catalog_items
        from common.db.models import CatalogTemplateItem, EntryCatalogItem

        delete_catalog_template_items_and_entry_catalog_items([1])

        with self._Session() as sess:
            self.assertEqual(sess.query(CatalogTemplateItem).count(), 0)
            self.assertEqual(sess.query(EntryCatalogItem).count(), 0)

        rows = self._audit_rows()
        self.assertEqual(len(rows), 2, f"expected 2 audit rows, got {len(rows)}")
        self.assertEqual({r["template_item_id"] for r in rows}, {2})

    def test_purge_empty_writes_audit(self):
        """purge 空行 → 审计里有 caller=purge_empty 记录"""
        from common.db.models import EntryCatalogItem
        # 再加一条全空的 EC 行，时间戳改成 2 小时前（越过 1h 窗口）
        import datetime
        with self._Session() as sess:
            obj = EntryCatalogItem(
                id=99, entry_id=100, template_item_id=2,
                serial=None, name=None, year=None, month=None, day=None,
                pages=None, remark=None, attachment_path=None,
            )
            sess.add(obj)
            sess.commit()
            sess.query(EntryCatalogItem).filter_by(id=99).update(
                {"created_at": datetime.datetime.now() - datetime.timedelta(hours=2)}
            )
            sess.commit()

        from main_ui.pages.inventory_ui.repo.inventory_entry_repo import delete_empty_entry_catalog_items
        removed = delete_empty_entry_catalog_items(entry_id=100)
        self.assertGreaterEqual(removed, 1)

        rows = self._audit_rows()
        self.assertTrue(any(r["caller"] == "purge_empty" for r in rows))

    def test_entry_delete_writes_audit(self):
        """删除整个人员 → 审计里有 caller=entry_delete，且包含该 entry 所有 EC 行"""
        from common.repositories.entry_repo import delete_entry

        ok = delete_entry(100)
        self.assertTrue(ok)

        rows = self._audit_rows()
        entry_delete_rows = [r for r in rows if r["caller"] == "entry_delete"]
        self.assertEqual(len(entry_delete_rows), 1, "entry_delete should log entry 100's 1 EC row")
        self.assertEqual(entry_delete_rows[0]["entry_id"], 100)


def _run():
    tests = unittest.TestLoader().loadTestsFromTestCase(ECDeleteAuditTests)
    failed = []
    passed = []
    for t in tests:
        name = t._testMethodName
        suite = unittest.TestSuite([t])
        res = unittest.TestResult()
        suite.run(res)
        if res.wasSuccessful():
            passed.append(name)
            print(f"[PASS] {name}")
        else:
            failed.append(name)
            for err_src in (res.errors, res.failures):
                for _case, err in err_src:
                    first_line = err.strip().splitlines()[-1]
                    print(f"[FAIL] {name}: {first_line}")
    print()
    if failed:
        print(f"{len(failed)} test(s) failed")
        sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    _run()

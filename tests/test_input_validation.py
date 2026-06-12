# -*- coding: utf-8 -*-
"""
UI 输入校验回归测试：确保 year/month/day/pages 四列不接受非法输入。

特别关注全角数字 '１２３' / 其他 Unicode 数字字符的陷阱：
Python 的 .isdigit() 对它们返回 True，但 MySQL Integer 列可能拒绝。
因此必须用 ASCII-only 校验。
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load_validators():
    """不实例化整个 Dialog，直接把 4 个校验函数提取出来单测。
    这样无需启动 QApplication，也不会受其他构造路径影响。"""
    # 使用 importlib 加载源码，再用 ast 提取我们需要的函数
    import types
    from main_ui.pages.inventory_ui import inventory_entry_dialog as mod
    Dialog = mod.InventoryEntryDialog
    # 构造一个最小的 stub 实例，只挂静态方法 _is_ascii_digits 和 4 个校验
    # 我们直接通过 unbound-call 调用实例方法
    class _Stub:
        _is_ascii_digits = staticmethod(Dialog._is_ascii_digits)
        _validate_year = Dialog._validate_year
        _validate_month = Dialog._validate_month
        _validate_day = Dialog._validate_day
        _validate_pages = Dialog._validate_pages
    return _Stub()


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self.v = _load_validators()

    # ---- year ----
    def test_year_accepts_valid(self):
        ok, _ = self.v._validate_year("2024")
        self.assertTrue(ok)

    def test_year_rejects_fullwidth_digits(self):
        """全角 '２０２４' 必须被拒绝，否则会导致后续排序/升序校验混乱"""
        ok, msg = self.v._validate_year("２０２４")
        self.assertFalse(ok, f"fullwidth '２０２４' should be rejected, msg={msg}")

    def test_year_rejects_chinese(self):
        ok, _ = self.v._validate_year("二零二四")
        self.assertFalse(ok)

    def test_year_rejects_too_short(self):
        ok, _ = self.v._validate_year("202")
        self.assertFalse(ok)

    # ---- month ----
    def test_month_accepts_valid(self):
        self.assertTrue(self.v._validate_month("12")[0])
        self.assertTrue(self.v._validate_month("1")[0])
        self.assertTrue(self.v._validate_month("")[0])

    def test_month_rejects_fullwidth(self):
        self.assertFalse(self.v._validate_month("１２")[0])

    def test_month_rejects_out_of_range(self):
        self.assertFalse(self.v._validate_month("13")[0])
        self.assertFalse(self.v._validate_month("0")[0])

    # ---- day ----
    def test_day_accepts_valid(self):
        self.assertTrue(self.v._validate_day("31")[0])
        self.assertTrue(self.v._validate_day("01")[0])

    def test_day_rejects_fullwidth(self):
        self.assertFalse(self.v._validate_day("３１")[0])

    def test_day_rejects_out_of_range(self):
        self.assertFalse(self.v._validate_day("32")[0])

    # ---- pages ----（最关键：这列 DB 是 Integer，严格拦截）
    def test_pages_accepts_valid(self):
        self.assertTrue(self.v._validate_pages("5")[0])
        self.assertTrue(self.v._validate_pages("12345")[0])
        self.assertTrue(self.v._validate_pages("")[0])

    def test_pages_rejects_chinese(self):
        """用户报告的 bug：把 '测试卡吗...' 写到页数列，导致 WAL 反复回放失败"""
        ok, msg = self.v._validate_pages("测试卡吗测试卡吗测试")
        self.assertFalse(ok, f"chinese string must be rejected, msg={msg}")

    def test_pages_rejects_fullwidth_digits(self):
        ok, msg = self.v._validate_pages("１２３")
        self.assertFalse(ok, f"fullwidth '１２３' must be rejected, msg={msg}")

    def test_pages_rejects_bengali_digits(self):
        ok, _ = self.v._validate_pages("১২৩")
        self.assertFalse(ok)

    def test_pages_rejects_letters(self):
        self.assertFalse(self.v._validate_pages("abc")[0])
        self.assertFalse(self.v._validate_pages("12a")[0])

    def test_pages_rejects_too_large(self):
        self.assertFalse(self.v._validate_pages("100000")[0])

    def test_pages_rejects_negative(self):
        # '-5' 不是全数字，会被 _is_ascii_digits 拒绝
        self.assertFalse(self.v._validate_pages("-5")[0])


def _run():
    from PyQt5.QtWidgets import QApplication
    import sys as _sys
    # 有些 UI 模块在 import 时会 touch Qt 类型，提前构造 QApplication 避免告警
    if not QApplication.instance():
        QApplication(_sys.argv)
    tests = unittest.TestLoader().loadTestsFromTestCase(InputValidationTests)
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
        _sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    _run()

# -*- coding: utf-8 -*-
"""
管理员工具：扫描 ``entry_catalog_items`` 表，合并所有 entry 下的同槽位重复行。

背景
----
历史 schema 没有给 ``entry_catalog_items`` 加 ``UNIQUE(entry_id, template_item_id)``，
并发 upsert / WAL 回放可能在同一槽位下产生多条重复 EC 行。UI 在加载时虽然
已经会自动选最完整的那条显示（应用层防护），但 DB 层的重复仍然存在，
长期会让维护变得困难，也让管理员无法直接给表加唯一约束。

本脚本：

1. 列出当前所有 entry 中存在 ``(entry_id, template_item_id)`` 重复的情况；
2. 调用 ``merge_duplicate_entry_catalog_items`` 把每个 entry 的重复合并掉
   （字段填空 + 图片重定向 + 淘汰行删除，事务内完成，绝不丢用户数据）；
3. 打印合并前后的统计，方便管理员核对。

⚠️ 用法
-------
**强烈建议先备份数据库再运行**。然后在仓库根目录执行：

    python tools/merge_duplicate_ec_rows.py --dry-run    # 仅扫描不合并
    python tools/merge_duplicate_ec_rows.py              # 实际合并

合并完成后，可视情况手动为旧库加上唯一约束：

    ALTER TABLE entry_catalog_items
        ADD CONSTRAINT uq_entry_tpl UNIQUE (entry_id, template_item_id);

加约束之前必须先把所有重复合并干净，否则 ALTER 会失败。
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _scan_duplicates() -> dict:
    """扫描整库，返回 {entry_id: [(tpl_id, [ec_id...]), ...]} 形式的报告。"""
    from common.db.session import get_session
    from common.db.models import EntryCatalogItem

    grouped: dict = defaultdict(lambda: defaultdict(list))
    with get_session() as session:
        rows = (
            session.query(EntryCatalogItem.id, EntryCatalogItem.entry_id,
                          EntryCatalogItem.template_item_id)
            .order_by(EntryCatalogItem.id.asc())
            .all()
        )
        for ec_id, entry_id, tpl_id in rows:
            grouped[int(entry_id)][int(tpl_id)].append(int(ec_id))

    report: dict = {}
    for entry_id, slots in grouped.items():
        dup_slots = {tpl_id: ids for tpl_id, ids in slots.items() if len(ids) > 1}
        if dup_slots:
            report[entry_id] = dup_slots
    return report


def _print_report(report: dict) -> None:
    if not report:
        print("[scan] 未发现 (entry_id, template_item_id) 重复的 EC 行。")
        return
    total_dup_rows = 0
    print(f"[scan] 共发现 {len(report)} 个 entry 存在重复 EC 行：\n")
    for entry_id in sorted(report.keys()):
        slots = report[entry_id]
        slot_dup_rows = sum(len(ids) - 1 for ids in slots.values())
        total_dup_rows += slot_dup_rows
        print(f"  entry_id={entry_id}: {len(slots)} 个槽位重复，"
              f"将合并 {slot_dup_rows} 条多余行")
        for tpl_id in sorted(slots.keys()):
            ids = slots[tpl_id]
            print(f"    tpl_item_id={tpl_id}: ec_ids={ids}")
    print(f"\n[scan] 全库累计需要合并的多余行：{total_dup_rows} 条。\n")


def _merge_all(report: dict) -> None:
    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        merge_duplicate_entry_catalog_items,
    )

    total_merged = 0
    for entry_id in sorted(report.keys()):
        try:
            merged = merge_duplicate_entry_catalog_items(entry_id=int(entry_id))
            print(f"[merge] entry_id={entry_id}: 合并 {merged} 条")
            total_merged += int(merged or 0)
        except Exception as e:
            print(f"[merge] entry_id={entry_id}: FAILED ({type(e).__name__}: {e})")
    print(f"\n[merge] 全库合并完成：累计删除 {total_merged} 条多余 EC 行。")


def main():
    parser = argparse.ArgumentParser(description="合并 entry_catalog_items 同槽位重复行")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描不合并")
    args = parser.parse_args()

    print("[step 1] 扫描整库，定位重复 EC 行 ...\n")
    report = _scan_duplicates()
    _print_report(report)

    if args.dry_run:
        print("[done] dry-run 模式，未执行合并。")
        return

    if not report:
        print("[done] 无重复行可合并。")
        return

    print("[step 2] 开始合并（已包含审计快照）...\n")
    _merge_all(report)

    print("\n[step 3] 重新扫描以核对合并结果 ...\n")
    report_after = _scan_duplicates()
    _print_report(report_after)

    if not report_after:
        print("[done] 全库已干净，可考虑为表加上 UNIQUE(entry_id, template_item_id) 约束。")
    else:
        print("[warn] 仍有未合并的重复，请检查日志。")


if __name__ == "__main__":
    main()

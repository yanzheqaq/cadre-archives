# -*- coding: utf-8 -*-
"""
数据完整性自检对话框

功能
----
- 上方摘要：上次快照时间 / 当前对比时间 / 检查的 entry 数量 / 检测到的丢失数
- 主区域：树状列出"整人丢失"和"目录条目丢失"详情，让用户清楚"是谁的、哪一条丢了"
- 底部按钮：
  - **重新检查**：对最近一次快照重新对比一次（不创建新快照）
  - **立即创建新快照**：手动 ``take_snapshot(kind='manual')``，把当前 DB 状态留作新基线
  - **导出报告**：把丢失列表导出 CSV / TXT，供用户存档/上报
  - **关闭**

无丢失时显示绿色"全部数据完整"提示。
无快照时引导用户先创建第一份基线。
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QFrame, QApplication, QStyle,
)

from common.services.catalog_snapshot_service import get_catalog_snapshot


def _fmt_item_summary(item: Dict[str, Any]) -> str:
    """把单条目录条目格式化为人类可读字符串。"""
    parts = []
    if item.get("serial"):
        parts.append(f"第{item['serial']}条")
    if item.get("name"):
        parts.append(str(item["name"]))
    date_parts = [item.get("year"), item.get("month"), item.get("day")]
    date_parts = [str(p).strip() for p in date_parts if p and str(p).strip()]
    if date_parts:
        parts.append("-".join(date_parts))
    if item.get("pages") is not None:
        parts.append(f"{item['pages']}页")
    if item.get("remark"):
        parts.append(f"备注: {item['remark']}")
    if item.get("image_count"):
        parts.append(f"图片{item['image_count']}张")
    return " · ".join(parts) if parts else "(空白条目)"


class DataIntegrityDialog(QDialog):
    """数据完整性自检报告对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据完整性自检")
        self.resize(900, 600)
        self._report: Optional[Dict[str, Any]] = None
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # 顶部摘要
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        font = self.summary_label.font()
        font.setPointSize(font.pointSize() + 1)
        self.summary_label.setFont(font)
        self.summary_label.setMinimumHeight(56)
        self.summary_label.setStyleSheet(
            "QLabel { padding: 10px 12px; border-radius: 6px; "
            "background-color: #f0f4f8; color: #1e2732; }"
        )
        layout.addWidget(self.summary_label)

        # 主区域：丢失明细
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["人员 / 目录类别 / 丢失明细", "工号 / 所属机构"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_refresh = QPushButton("重新检查")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setToolTip("对最近一次快照重新对比，不创建新快照")
        self.btn_refresh.clicked.connect(self._refresh)
        btn_row.addWidget(self.btn_refresh)

        self.btn_take = QPushButton("立即创建新快照")
        self.btn_take.setCursor(Qt.PointingHandCursor)
        self.btn_take.setToolTip("把当前 DB 状态保存为新的对比基线")
        self.btn_take.clicked.connect(self._on_take_snapshot)
        btn_row.addWidget(self.btn_take)

        self.btn_export = QPushButton("导出报告")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setToolTip("把丢失明细导出为 CSV，便于存档/上报")
        self.btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(self.btn_export)

        btn_row.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # 加载 & 渲染
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        """重新对比 latest snapshot 并刷新 UI。"""
        snap = get_catalog_snapshot()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = snap.compare_with_latest()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "自检失败", f"读取快照失败：\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._report = report
        self._render()

    def _render(self) -> None:
        self.tree.clear()
        report = self._report

        if not report:
            self.summary_label.setText(
                "还没有任何快照可供对比。\n"
                "请点击下方「立即创建新快照」按钮，把当前数据库状态留作第一份基线。\n"
                "（之后软件每次正常关闭时，会自动追加一份新快照）"
            )
            self.summary_label.setStyleSheet(
                "QLabel { padding: 10px 12px; border-radius: 6px; "
                "background-color: #fff7e0; color: #6b5400; }"
            )
            self.btn_export.setEnabled(False)
            return

        summary = report["summary"]
        entries_lost = summary["entries_lost_count"]
        items_lost = summary["items_lost_count"]
        checked = summary["entries_checked"]

        if entries_lost == 0 and items_lost == 0:
            self.summary_label.setText(
                f"[ 数据完整 ]\n"
                f"对比基准：{report['taken_at']}（快照）\n"
                f"当前时刻：{report['current_at']}\n"
                f"检查了 {checked} 个档案，未发现任何丢失。"
            )
            self.summary_label.setStyleSheet(
                "QLabel { padding: 10px 12px; border-radius: 6px; "
                "background-color: #e6f7ec; color: #0a6e2e; font-weight: bold; }"
            )
            self.btn_export.setEnabled(False)
            return

        # 检测到丢失
        single_lost = items_lost - sum(e['items_lost'] for e in report['missing_entries'])
        self.summary_label.setText(
            f"[ 检测到数据丢失 ]\n"
            f"对比基准：{report['taken_at']}（快照）  →  当前：{report['current_at']}\n"
            f"共检查 {checked} 个档案，丢失 {entries_lost} 个整档案、"
            f"{single_lost} 条单独目录条目。"
        )
        self.summary_label.setStyleSheet(
            "QLabel { padding: 10px 12px; border-radius: 6px; "
            "background-color: #fdecec; color: #8b1a1a; font-weight: bold; }"
        )
        self.btn_export.setEnabled(True)

        # 整 entry 丢失分组
        if report["missing_entries"]:
            top = QTreeWidgetItem(["【整个档案丢失，最严重】", ""])
            top.setExpanded(True)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, Qt.red)
            self.tree.addTopLevelItem(top)
            for e in report["missing_entries"]:
                node = QTreeWidgetItem([
                    f"{e['person_name'] or '(无姓名)'} - 共 {e['items_lost']} 条数据",
                    f"{e['emp_no'] or '-'}  |  {e['org_path'] or '-'}",
                ])
                top.addChild(node)
                for it in e["items"]:
                    leaf = QTreeWidgetItem([f"  ↳ {_fmt_item_summary(it)}", ""])
                    node.addChild(leaf)
                node.setExpanded(False)
            top.setExpanded(True)

        # 部分目录条目丢失分组
        if report["missing_items"]:
            top = QTreeWidgetItem(["【部分目录条目丢失】", ""])
            top.setExpanded(True)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, Qt.darkYellow)
            self.tree.addTopLevelItem(top)
            for m in report["missing_items"]:
                node = QTreeWidgetItem([
                    f"{m['person_name'] or '(无姓名)'} - 丢失 {len(m['items'])} 条",
                    f"{m['emp_no'] or '-'}  |  {m['org_path'] or '-'}",
                ])
                top.addChild(node)
                for it in m["items"]:
                    leaf = QTreeWidgetItem([f"  ↳ {_fmt_item_summary(it)}", ""])
                    node.addChild(leaf)
                node.setExpanded(True)
            top.setExpanded(True)

    # ------------------------------------------------------------------
    # 事件：手动新建快照
    # ------------------------------------------------------------------
    def _on_take_snapshot(self) -> None:
        snap = get_catalog_snapshot()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = snap.take_snapshot(kind="manual")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "快照失败", f"创建快照时出错：\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        QMessageBox.information(
            self, "快照已创建",
            f"已成功创建新快照（编号 {res['snapshot_id']}）。\n"
            f"包含 {res['entries_count']} 个档案，{res['items_count']} 条目录条目。\n"
            f"以后再点「重新检查」会以这份快照为基准对比。"
        )
        # 刚创建的快照与当前 DB 状态完全一致，刷新会显示"全部完整"
        self._refresh()

    # ------------------------------------------------------------------
    # 事件：导出报告
    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        if not self._report:
            return
        default_name = (
            f"data_integrity_report_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", default_name,
            "CSV 文件 (*.csv);;文本文件 (*.txt)"
        )
        if not path:
            return

        try:
            self._write_report_file(path)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"写文件失败：\n{e}")
            return

        QMessageBox.information(
            self, "导出成功",
            f"报告已保存到：\n{path}"
        )

    def _write_report_file(self, path: str) -> None:
        report = self._report or {}
        rows: List[List[str]] = [[
            "类型", "姓名", "工号", "所属机构",
            "目录条目编号", "目录条目名称", "年", "月", "日",
            "页数", "备注", "图片张数", "附件路径",
        ]]
        for e in report.get("missing_entries", []):
            for it in e.get("items", []):
                rows.append([
                    "整档案丢失", e.get("person_name", ""), e.get("emp_no", ""),
                    e.get("org_path", ""),
                    str(it.get("serial") or ""), str(it.get("name") or ""),
                    str(it.get("year") or ""), str(it.get("month") or ""),
                    str(it.get("day") or ""),
                    str(it.get("pages") if it.get("pages") is not None else ""),
                    str(it.get("remark") or ""),
                    str(it.get("image_count") or 0),
                    str(it.get("attachment_path") or ""),
                ])
        for m in report.get("missing_items", []):
            for it in m.get("items", []):
                rows.append([
                    "目录条目丢失", m.get("person_name", ""), m.get("emp_no", ""),
                    m.get("org_path", ""),
                    str(it.get("serial") or ""), str(it.get("name") or ""),
                    str(it.get("year") or ""), str(it.get("month") or ""),
                    str(it.get("day") or ""),
                    str(it.get("pages") if it.get("pages") is not None else ""),
                    str(it.get("remark") or ""),
                    str(it.get("image_count") or 0),
                    str(it.get("attachment_path") or ""),
                ])

        if path.lower().endswith(".txt"):
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    f"数据完整性自检报告\n"
                    f"对比基准: {report.get('taken_at', '-')}\n"
                    f"当前时刻: {report.get('current_at', '-')}\n"
                    f"概要: 整档案丢失 {report['summary']['entries_lost_count']} 个，"
                    f"目录条目丢失合计 {report['summary']['items_lost_count']} 条\n"
                    f"{'=' * 80}\n"
                )
                for r in rows[1:]:
                    f.write(" | ".join(r) + "\n")
        else:
            # CSV：utf-8-sig 兼容 Excel 中文
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow([
                    f"数据完整性自检报告 - 对比基准 {report.get('taken_at', '-')}"
                    f" - 当前 {report.get('current_at', '-')}"
                ])
                w.writerows(rows)

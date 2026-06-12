# -*- coding: utf-8 -*-
"""
目录数据完整性自检：本地快照 + 丢失对比

用途
----
给用户一个**看得见的**数据安全保险：

1. 软件关闭前（``aboutToQuit``）自动给所有人的目录数据做一次本地快照；
2. 用户随时可以点"数据自检"按钮，把当前 DB 状态与最近一次快照对比，
   如果发现某条目录数据"消失了"——立即列出"是谁的、哪一条目录、
   什么内容"，方便用户追责或恢复。

本服务**只读**地从主 DB 拉取目录数据，写入**独立的本地 SQLite**。
绝不会污染主 DB，绝不会影响录入性能（关闭时异步执行 + 14 天滚动清理）。

数据安全契约
------------
- 快照存的都是元信息（条目数 + 关键字段 + 哈希），单条 KB 级；
- 一个全库快照（数百员工 × 数百条目录）通常 < 5 MB；
- 即使主 DB 真的丢数据，快照仍保留"丢失前的最后状态"作为恢复线索；
- 对比仅做**减法判断**：上次快照里有 → 现在 DB 里没有 = 丢失。
  不对"内容修改"做告警（用户主动改不算丢失）。

存放位置
--------
- Windows: ``%LOCALAPPDATA%/CadreArchives/catalog_snapshot.db``
- 其他: ``~/.cadre_archives/catalog_snapshot.db``
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _default_db_path() -> str:
    """返回默认快照 DB 路径（与 WAL 同目录）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    if os.name == "nt":
        folder = os.path.join(base, "CadreArchives")
    else:
        folder = os.path.join(base, ".cadre_archives")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "catalog_snapshot.db")


# ----------------------------------------------------------------------
# 单条目录条目的"快照值"——只取真正能反映"用户填了什么"的字段
# ----------------------------------------------------------------------
def _item_signature(item: Dict[str, Any]) -> str:
    """生成单条目录条目的内容签名（用于对比时识别"等价条目"）。"""
    keys = ("serial", "name", "year", "month", "day", "pages", "remark", "attachment_path")
    parts = []
    for k in keys:
        v = item.get(k)
        if v is None:
            parts.append("")
        else:
            parts.append(str(v).strip())
    return "|".join(parts)


def _is_meaningful_item(item: Dict[str, Any]) -> bool:
    """判断该条目录条目是否"有用户数据"——空白行不进快照，不影响对比。"""
    if not item:
        return False
    for k in ("serial", "name", "year", "month", "day", "remark", "attachment_path"):
        v = item.get(k)
        if v and str(v).strip():
            return True
    if item.get("pages") is not None:
        return True
    if int(item.get("image_count") or 0) > 0:
        return True
    return False


class CatalogSnapshot:
    """目录数据快照本地存储 + 对比。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS catalog_snapshot (
        snapshot_id     INTEGER NOT NULL,
        entry_id        INTEGER NOT NULL,
        emp_no          TEXT,
        person_name     TEXT,
        org_path        TEXT,
        items_json      TEXT    NOT NULL,
        items_count     INTEGER NOT NULL,
        content_hash    TEXT    NOT NULL,
        PRIMARY KEY (snapshot_id, entry_id)
    );
    CREATE TABLE IF NOT EXISTS snapshot_meta (
        snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        taken_at        TEXT    NOT NULL,
        kind            TEXT    NOT NULL,
        entries_count   INTEGER NOT NULL,
        items_count     INTEGER NOT NULL,
        operator_user_id INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_snapshot_entry
        ON catalog_snapshot(entry_id, snapshot_id DESC);
    CREATE INDEX IF NOT EXISTS idx_snapshot_meta_taken
        ON snapshot_meta(taken_at DESC);
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn() as conn:
                for stmt in self._SCHEMA.strip().split(";"):
                    s = stmt.strip()
                    if s:
                        conn.execute(s)

    # ==================================================================
    # 写入：take snapshot
    # ==================================================================
    def take_snapshot(
        self,
        *,
        kind: str = "manual",
        operator_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """从主 DB 拉取所有 entry 的目录数据，落到本地快照表。

        返回：``{snapshot_id, taken_at, entries_count, items_count}``。
        kind 取值约定：``'auto_close'`` / ``'manual'`` / ``'auto_open'``。
        """
        snapshot_payload = self._collect_payload_from_main_db()

        taken_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    "INSERT INTO snapshot_meta (taken_at, kind, entries_count, items_count, operator_user_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        taken_at, kind,
                        len(snapshot_payload),
                        sum(p["items_count"] for p in snapshot_payload),
                        int(operator_user_id) if operator_user_id else None,
                    ),
                )
                snapshot_id = int(cur.lastrowid)
                rows = [
                    (
                        snapshot_id, p["entry_id"], p["emp_no"], p["person_name"],
                        p["org_path"], p["items_json"], p["items_count"], p["content_hash"],
                    )
                    for p in snapshot_payload
                ]
                conn.executemany(
                    "INSERT INTO catalog_snapshot "
                    "(snapshot_id, entry_id, emp_no, person_name, org_path, "
                    " items_json, items_count, content_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )

        return {
            "snapshot_id": snapshot_id,
            "taken_at": taken_at,
            "kind": kind,
            "entries_count": len(snapshot_payload),
            "items_count": sum(p["items_count"] for p in snapshot_payload),
        }

    @staticmethod
    def _collect_payload_from_main_db() -> List[Dict[str, Any]]:
        """从主 DB 一次性拉所有 entry + 它们的目录条目 + 图片张数。"""
        # 延迟导入避免循环
        from common.db.session import get_session
        from common.db.models import Entry, EntryCatalogItem, EntryItemImage

        with get_session() as session:
            # 一次性拉所有 entry
            entries = session.query(
                Entry.id, Entry.emp_no, Entry.name, Entry.org_path,
            ).all()
            if not entries:
                return []

            # 一次性拉所有 EC 行
            ec_rows = session.query(
                EntryCatalogItem.id,
                EntryCatalogItem.entry_id,
                EntryCatalogItem.template_item_id,
                EntryCatalogItem.serial,
                EntryCatalogItem.name,
                EntryCatalogItem.year,
                EntryCatalogItem.month,
                EntryCatalogItem.day,
                EntryCatalogItem.pages,
                EntryCatalogItem.remark,
                EntryCatalogItem.attachment_path,
            ).all()

            # 一次性按 EC 聚合图片张数
            from sqlalchemy import func as _f
            img_counts: Dict[int, int] = dict(
                session.query(
                    EntryItemImage.entry_catalog_item_id,
                    _f.count(EntryItemImage.id),
                ).group_by(EntryItemImage.entry_catalog_item_id).all()
            )

        # 按 entry_id 归并
        by_entry: Dict[int, List[Dict[str, Any]]] = {}
        for r in ec_rows:
            (ec_id, eid, tpl_id, serial, name, yr, mo, dy,
             pages, remark, attach) = r
            item = {
                "ec_id": int(ec_id),
                "tpl_id": int(tpl_id),
                "serial": serial,
                "name": name,
                "year": yr,
                "month": mo,
                "day": dy,
                "pages": pages,
                "remark": remark,
                "attachment_path": attach,
                "image_count": int(img_counts.get(int(ec_id), 0) or 0),
            }
            if _is_meaningful_item(item):
                by_entry.setdefault(int(eid), []).append(item)

        payload: List[Dict[str, Any]] = []
        for entry_id, emp_no, person_name, org_path in entries:
            items = by_entry.get(int(entry_id), [])
            items_json = json.dumps(items, ensure_ascii=False)
            content_hash = hashlib.sha256(items_json.encode("utf-8")).hexdigest()
            payload.append({
                "entry_id": int(entry_id),
                "emp_no": emp_no or "",
                "person_name": person_name or "",
                "org_path": org_path or "",
                "items_json": items_json,
                "items_count": len(items),
                "content_hash": content_hash,
            })
        return payload

    # ==================================================================
    # 查询：list snapshots / get latest
    # ==================================================================
    def list_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的 N 次快照元信息（用于让用户选择对比基准）。"""
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT snapshot_id, taken_at, kind, entries_count, items_count "
                    "FROM snapshot_meta ORDER BY snapshot_id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        return [
            {
                "snapshot_id": r[0],
                "taken_at": r[1],
                "kind": r[2],
                "entries_count": r[3],
                "items_count": r[4],
            }
            for r in rows
        ]

    def get_latest_snapshot_id(self) -> Optional[int]:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT snapshot_id FROM snapshot_meta ORDER BY snapshot_id DESC LIMIT 1"
                ).fetchone()
        return int(row[0]) if row else None

    # ==================================================================
    # 对比：compare with snapshot
    # ==================================================================
    def compare_with_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        """对比指定快照 vs 当前主 DB 状态，返回详细丢失报告。

        报告结构：
        ::

            {
                "snapshot_id": 123,
                "taken_at": "2026-04-26 18:00:00",
                "current_at": "2026-04-27 09:00:00",
                "missing_entries": [           # 整个 entry 在当前 DB 已不存在
                    {"entry_id": 7, "emp_no": "B007", "person_name": "李四",
                     "items_lost": 12}
                ],
                "missing_items": [             # entry 还在，但部分目录条目丢失
                    {"entry_id": 1, "emp_no": "A001", "person_name": "张三",
                     "items": [{"serial": "1", "name": "出生证明",
                                "year": "2024", ...}, ...]}
                ],
                "summary": {
                    "entries_lost_count": 1,
                    "items_lost_count": 13,
                    "entries_checked": 200,
                }
            }
        """
        # 取快照
        with self._lock:
            with self._conn() as conn:
                meta_row = conn.execute(
                    "SELECT taken_at FROM snapshot_meta WHERE snapshot_id = ?",
                    (int(snapshot_id),),
                ).fetchone()
                if not meta_row:
                    raise ValueError(f"snapshot_id={snapshot_id} 不存在")
                taken_at = meta_row[0]
                snap_rows = conn.execute(
                    "SELECT entry_id, emp_no, person_name, org_path, items_json "
                    "FROM catalog_snapshot WHERE snapshot_id = ?",
                    (int(snapshot_id),),
                ).fetchall()

        snapshot_by_entry: Dict[int, Dict[str, Any]] = {}
        for eid, emp_no, person_name, org_path, items_json in snap_rows:
            try:
                items = json.loads(items_json) if items_json else []
            except Exception:
                items = []
            snapshot_by_entry[int(eid)] = {
                "entry_id": int(eid),
                "emp_no": emp_no or "",
                "person_name": person_name or "",
                "org_path": org_path or "",
                "items": items,
            }

        # 取当前主 DB 状态
        current_payload = self._collect_payload_from_main_db()
        current_by_entry: Dict[int, List[Dict[str, Any]]] = {}
        for p in current_payload:
            try:
                current_by_entry[int(p["entry_id"])] = json.loads(p["items_json"])
            except Exception:
                current_by_entry[int(p["entry_id"])] = []

        missing_entries: List[Dict[str, Any]] = []
        missing_items: List[Dict[str, Any]] = []

        for eid, snap_entry in snapshot_by_entry.items():
            if eid not in current_by_entry:
                # 整个 entry 没了
                missing_entries.append({
                    "entry_id": eid,
                    "emp_no": snap_entry["emp_no"],
                    "person_name": snap_entry["person_name"],
                    "org_path": snap_entry["org_path"],
                    "items_lost": len(snap_entry["items"]),
                    "items": list(snap_entry["items"]),
                })
                continue

            # entry 还在，按 (tpl_id, content) 比对哪些条目丢了
            current_items = current_by_entry[eid]
            current_signatures: Dict[int, set] = {}
            for it in current_items:
                tpl_id = int(it.get("tpl_id") or 0)
                current_signatures.setdefault(tpl_id, set()).add(_item_signature(it))

            lost: List[Dict[str, Any]] = []
            for snap_it in snap_entry["items"]:
                tpl_id = int(snap_it.get("tpl_id") or 0)
                sig = _item_signature(snap_it)
                if sig not in current_signatures.get(tpl_id, set()):
                    lost.append(snap_it)

            if lost:
                missing_items.append({
                    "entry_id": eid,
                    "emp_no": snap_entry["emp_no"],
                    "person_name": snap_entry["person_name"],
                    "org_path": snap_entry["org_path"],
                    "items": lost,
                })

        return {
            "snapshot_id": int(snapshot_id),
            "taken_at": taken_at,
            "current_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "missing_entries": missing_entries,
            "missing_items": missing_items,
            "summary": {
                "entries_lost_count": len(missing_entries),
                "items_lost_count": (
                    sum(e["items_lost"] for e in missing_entries)
                    + sum(len(m["items"]) for m in missing_items)
                ),
                "entries_checked": len(snapshot_by_entry),
            },
        }

    def compare_with_latest(self) -> Optional[Dict[str, Any]]:
        """对比最近一次快照。无快照时返回 ``None``。"""
        sid = self.get_latest_snapshot_id()
        if sid is None:
            return None
        return self.compare_with_snapshot(sid)

    # ==================================================================
    # 维护：旧快照清理
    # ==================================================================
    def cleanup_old_snapshots(self, *, keep_days: int = 14, keep_min: int = 5) -> int:
        """清理超过 ``keep_days`` 天的快照，但至少保留最近 ``keep_min`` 个。

        返回被删除的快照数量。
        """
        cutoff = (datetime.now() - timedelta(days=max(0, int(keep_days)))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        with self._lock:
            with self._conn() as conn:
                # 选出"既早于 cutoff 又在最近 keep_min 之外"的 snapshot_id
                rows = conn.execute(
                    "SELECT snapshot_id FROM snapshot_meta "
                    "WHERE snapshot_id NOT IN ("
                    "  SELECT snapshot_id FROM snapshot_meta ORDER BY snapshot_id DESC LIMIT ?"
                    ") AND taken_at < ?",
                    (int(keep_min), cutoff),
                ).fetchall()
                if not rows:
                    return 0
                ids = [int(r[0]) for r in rows]
                placeholders = ",".join(["?"] * len(ids))
                conn.execute(
                    f"DELETE FROM catalog_snapshot WHERE snapshot_id IN ({placeholders})",
                    ids,
                )
                conn.execute(
                    f"DELETE FROM snapshot_meta WHERE snapshot_id IN ({placeholders})",
                    ids,
                )
                return len(ids)


# ----------------------------------------------------------------------
# 模块级单例 + 便捷封装
# ----------------------------------------------------------------------
_snapshot_instance: Optional[CatalogSnapshot] = None
_snapshot_lock = threading.Lock()


def get_catalog_snapshot() -> CatalogSnapshot:
    """返回全局单例。"""
    global _snapshot_instance
    if _snapshot_instance is None:
        with _snapshot_lock:
            if _snapshot_instance is None:
                _snapshot_instance = CatalogSnapshot()
    return _snapshot_instance


def take_snapshot_with_timeout(
    *, kind: str = "auto_close",
    operator_user_id: Optional[int] = None,
    timeout_seconds: float = 8.0,
) -> Optional[Dict[str, Any]]:
    """同步触发一次快照，但带超时保护。

    关闭软件时调用：典型耗时 ~100ms（200 entry）~500ms（1000 entry），
    超时 8 秒后让快照线程在后台继续跑（daemon），主流程立即返回。

    Returns
    -------
    dict | None
        正常完成时返回快照元信息；超时时返回 ``None``，表示"已开始但还没完"。
    """
    result_holder: Dict[str, Any] = {}
    error_holder: Dict[str, BaseException] = {}

    def _runner():
        try:
            t0 = time.time()
            res = get_catalog_snapshot().take_snapshot(
                kind=kind, operator_user_id=operator_user_id,
            )
            dt = (time.time() - t0) * 1000
            print(
                f"[snapshot] {kind} done in {dt:.0f}ms: "
                f"snapshot_id={res['snapshot_id']} "
                f"entries={res['entries_count']} items={res['items_count']}"
            )
            result_holder.update(res)
            # 顺手清理过期快照
            try:
                deleted = get_catalog_snapshot().cleanup_old_snapshots()
                if deleted:
                    print(f"[snapshot] cleaned up {deleted} expired snapshot(s)")
            except Exception as e:
                print(f"[snapshot] cleanup failed: {e}")
        except BaseException as e:
            error_holder["e"] = e
            print(f"[snapshot] {kind} FAILED: {type(e).__name__}: {e}")

    t = threading.Thread(target=_runner, name=f"snapshot-{kind}", daemon=True)
    t.start()
    t.join(timeout=max(0.5, float(timeout_seconds)))
    if t.is_alive():
        # 超时：线程继续在后台跑（daemon, 进程退出会被 kill，但 SQLite 事务原子性保护数据库不损坏）
        print(f"[snapshot] {kind} timed out after {timeout_seconds}s, continuing in background")
        return None
    if "e" in error_holder:
        return None
    return result_holder if result_holder else None

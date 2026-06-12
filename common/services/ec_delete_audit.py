# -*- coding: utf-8 -*-
"""
EntryCatalogItem 删除审计日志

目的
----
任何 ``entry_catalog_items`` 行被删除时，先把完整字段快照写进本地 SQLite 审计表，
再执行真正的删除。这样一旦再发生"数据离奇消失"，可以定位到：
- 哪个代码路径删的（caller 标签）
- 什么时间删的（deleted_at）
- 删前的完整字段内容（可用于还原）
- 调用栈（pinpoint 源码行）

本模块**只**提供记录能力，不替代 SQL 删除本身——调用方应先调用
``snapshot_and_log_before_delete(...)`` 再执行实际 DELETE。

存放位置
--------
Windows: ``%LOCALAPPDATA%/CadreArchives/ec_delete_audit.db``
其他系统: ``~/.cadre_archives/ec_delete_audit.db``

线程安全
--------
所有公开方法通过 ``self._lock`` 串行化。SQLite 使用 WAL 模式，读写不阻塞。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import traceback
from typing import Any, Dict, Iterable, List, Optional


def _default_db_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    if os.name == "nt":
        folder = os.path.join(base, "CadreArchives")
    else:
        folder = os.path.join(base, ".cadre_archives")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "ec_delete_audit.db")


class _ECDeleteAudit:
    """EC 行删除审计单例。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS ec_deletions (
        audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        deleted_at       REAL    NOT NULL,
        caller           TEXT    NOT NULL,
        entry_id         INTEGER,
        template_item_id INTEGER,
        ec_id            INTEGER,
        serial           TEXT,
        name             TEXT,
        year             TEXT,
        month            TEXT,
        day              TEXT,
        pages            INTEGER,
        remark           TEXT,
        attachment_path  TEXT,
        updated_at_snap  TEXT,
        stack_trace      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_entry ON ec_deletions(entry_id);
    CREATE INDEX IF NOT EXISTS idx_audit_tpl   ON ec_deletions(template_item_id);
    CREATE INDEX IF NOT EXISTS idx_audit_when  ON ec_deletions(deleted_at);
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

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def log_rows(
        self,
        *,
        caller: str,
        rows: Iterable[Dict[str, Any]],
        include_stack: bool = True,
    ) -> int:
        """把即将被删除的 EC 行快照写入审计表。

        参数
        ----
        caller
            调用方标签，如 ``"user_row_delete"`` / ``"admin_cascade"`` / ``"purge"``
            / ``"entry_delete"`` / ``"orphan_cleanup"``。
        rows
            每个元素是一个 dict，含 ``id, entry_id, template_item_id, serial,
            name, year, month, day, pages, remark, attachment_path, updated_at``。
        include_stack
            是否记录 Python 调用栈（定位触发删除的源码位置，开销很小）。

        返回
        ----
        实际写入的审计条数。
        """
        rows_list = list(rows or [])
        if not rows_list:
            return 0

        now = time.time()
        stack = ""
        if include_stack:
            try:
                # 跳过 log_rows 自己的栈帧，保留调用方上下文
                stack = "".join(traceback.format_stack(limit=12)[:-1])
            except Exception:
                stack = ""

        payload = [
            (
                now,
                str(caller or "unknown"),
                r.get("entry_id"),
                r.get("template_item_id"),
                r.get("id"),
                r.get("serial"),
                r.get("name"),
                r.get("year"),
                r.get("month"),
                r.get("day"),
                r.get("pages"),
                r.get("remark"),
                r.get("attachment_path"),
                str(r.get("updated_at")) if r.get("updated_at") is not None else None,
                stack,
            )
            for r in rows_list
        ]

        with self._lock:
            with self._conn() as conn:
                conn.executemany(
                    """INSERT INTO ec_deletions
                       (deleted_at, caller, entry_id, template_item_id, ec_id,
                        serial, name, year, month, day, pages, remark,
                        attachment_path, updated_at_snap, stack_trace)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    payload,
                )
        return len(payload)

    def recent(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        """查看最近 N 条删除记录（便于 diag）。"""
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    """SELECT audit_id, deleted_at, caller, entry_id, template_item_id,
                              ec_id, serial, name, year, month, day, pages, remark,
                              attachment_path, updated_at_snap, stack_trace
                       FROM ec_deletions
                       ORDER BY deleted_at DESC
                       LIMIT ?""",
                    (int(limit),),
                )
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count(self) -> int:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM ec_deletions")
                return int(cur.fetchone()[0])

    def db_path(self) -> str:
        return self._db_path


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------

_instance: Optional[_ECDeleteAudit] = None
_instance_lock = threading.Lock()


def get_audit() -> _ECDeleteAudit:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = _ECDeleteAudit()
        return _instance


def snapshot_and_log_before_delete(
    session,
    *,
    caller: str,
    query,
) -> int:
    """在执行 DELETE 前，把 query 命中的 EntryCatalogItem 行快照写入审计表。

    使用方式
    --------
    >>> q = session.query(EntryCatalogItem).filter(...)
    >>> snapshot_and_log_before_delete(session, caller="user_row_delete", query=q)
    >>> q.delete(synchronize_session=False)
    >>> session.commit()

    注意审计写入的是**另一个 SQLite 文件**，和业务 MySQL 事务完全解耦：
    即便业务事务最终回滚，审计记录仍会保留（"行曾被尝试删除"），这对排查有帮助。
    """
    try:
        objs = query.all()
    except Exception as e:
        print(f"[ec-audit] snapshot query failed caller={caller}: {e}")
        return 0

    rows = []
    for obj in objs:
        try:
            rows.append({
                "id": getattr(obj, "id", None),
                "entry_id": getattr(obj, "entry_id", None),
                "template_item_id": getattr(obj, "template_item_id", None),
                "serial": getattr(obj, "serial", None),
                "name": getattr(obj, "name", None),
                "year": getattr(obj, "year", None),
                "month": getattr(obj, "month", None),
                "day": getattr(obj, "day", None),
                "pages": getattr(obj, "pages", None),
                "remark": getattr(obj, "remark", None),
                "attachment_path": getattr(obj, "attachment_path", None),
                "updated_at": getattr(obj, "updated_at", None),
            })
        except Exception:
            continue

    if not rows:
        return 0

    try:
        return get_audit().log_rows(caller=caller, rows=rows)
    except Exception as e:
        # 审计写失败不能阻断业务删除（否则比 bug 本身更糟）
        print(f"[ec-audit] log failed caller={caller}: {e}")
        return 0


__all__ = [
    "get_audit",
    "snapshot_and_log_before_delete",
]

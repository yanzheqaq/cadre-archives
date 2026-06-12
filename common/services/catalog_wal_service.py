# -*- coding: utf-8 -*-
"""
目录录入持久化 WAL（Write-Ahead Log）

用途
----
用户在录入目录字段（题名 / 年月日 / 页数 / 备注等）时，现有的防抖队列 `_pending_catalog_saves`
只存在于内存。如果 app 被强杀或断电，那些还没来得及写入服务器 DB 的字段就会丢失。

本服务用**本地 SQLite 文件**把 pending 写入镜像一份，保证：
1. 进程退出（包括异常退出）后，下次启动可以重放未落盘的字段。
2. WAL 记录只有在服务器 DB 写入成功之后才被移除。
3. 多写同一字段时 `INSERT OR REPLACE` 自动覆盖，保留最新值。

存放位置
--------
Windows: ``%LOCALAPPDATA%/CadreArchives/catalog_wal.db``
其他系统: ``~/.cadre_archives/catalog_wal.db``

线程安全
--------
所有公开方法都通过 ``self._lock`` 串行化，允许从 UI 线程和 Worker 线程并发调用。
内部使用 SQLite 的 WAL 模式（PRAGMA journal_mode=WAL），读写不阻塞。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _default_db_path() -> str:
    """返回默认 WAL 文件路径。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    if os.name == "nt":
        folder = os.path.join(base, "CadreArchives")
    else:
        folder = os.path.join(base, ".cadre_archives")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "catalog_wal.db")


class CatalogWAL:
    """目录字段保存的本地 WAL。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS pending_field_saves (
        entry_id              INTEGER NOT NULL,
        template_item_id      INTEGER NOT NULL,
        field                 TEXT    NOT NULL,
        value                 TEXT,
        entry_catalog_item_id INTEGER,
        base_updated_at       TEXT,
        staged_at             REAL    NOT NULL,
        PRIMARY KEY (entry_id, template_item_id, field)
    );
    CREATE INDEX IF NOT EXISTS idx_pending_entry ON pending_field_saves(entry_id);
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._init_schema()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
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

    @staticmethod
    def _encode(value: Any) -> str:
        """把任意标量（通常是字符串 / int / None）编码为可存储字符串。"""
        if value is None:
            return ""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _decode(text: Optional[str]) -> Any:
        if text is None or text == "":
            return None
        try:
            return json.loads(text)
        except Exception:
            return text  # 兼容早期非 JSON 存储

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def write_fields(
        self,
        *,
        entry_id: int,
        template_item_id: int,
        fields: Dict[str, Any],
        entry_catalog_item_id: Optional[int] = None,
        base_updated_at: Optional[str] = None,
    ) -> None:
        """批量写入/更新字段。已存在的字段会被新值覆盖。"""
        if not fields:
            return
        now = time.time()
        rows = [
            (
                int(entry_id),
                int(template_item_id),
                str(field),
                self._encode(value),
                int(entry_catalog_item_id) if entry_catalog_item_id else None,
                base_updated_at,
                now,
            )
            for field, value in fields.items()
        ]
        with self._lock:
            with self._conn() as conn:
                conn.executemany(
                    """INSERT OR REPLACE INTO pending_field_saves
                       (entry_id, template_item_id, field, value,
                        entry_catalog_item_id, base_updated_at, staged_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )

    def remove_fields(
        self,
        *,
        entry_id: int,
        template_item_id: int,
        fields: Iterable[str],
    ) -> None:
        """从 WAL 中删除指定字段。仅在服务器 DB 写入确认成功后调用。"""
        fields_list = [f for f in fields if f]
        if not fields_list:
            return
        with self._lock:
            with self._conn() as conn:
                placeholders = ",".join(["?"] * len(fields_list))
                conn.execute(
                    f"""DELETE FROM pending_field_saves
                        WHERE entry_id=? AND template_item_id=? AND field IN ({placeholders})""",
                    [int(entry_id), int(template_item_id), *fields_list],
                )

    def clear_item(self, *, entry_id: int, template_item_id: int) -> None:
        """清除某个目录项的所有 pending。"""
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    "DELETE FROM pending_field_saves WHERE entry_id=? AND template_item_id=?",
                    (int(entry_id), int(template_item_id)),
                )

    def list_by_entry(self, *, entry_id: int) -> List[Dict[str, Any]]:
        """列出某 entry 下所有 pending 字段。返回按 template_item_id 分组的字段字典。"""
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    """SELECT template_item_id, entry_catalog_item_id, field, value, base_updated_at, staged_at
                       FROM pending_field_saves WHERE entry_id=?""",
                    (int(entry_id),),
                )
                rows = cur.fetchall()
        grouped: Dict[int, Dict[str, Any]] = {}
        for tpl_id, ec_id, field, value, base_ts, staged_at in rows:
            item = grouped.setdefault(
                int(tpl_id),
                {"entry_catalog_item_id": ec_id, "fields": {}, "base_updated_at": base_ts, "staged_at": staged_at},
            )
            item["fields"][field] = self._decode(value)
            if ec_id is not None:
                item["entry_catalog_item_id"] = ec_id
        return [
            {
                "template_item_id": tpl_id,
                "entry_catalog_item_id": info["entry_catalog_item_id"],
                "fields": info["fields"],
                "base_updated_at": info["base_updated_at"],
                "staged_at": info["staged_at"],
            }
            for tpl_id, info in grouped.items()
        ]

    def list_all(self) -> List[Dict[str, Any]]:
        """列出 WAL 里所有 pending（按 entry 分组，再按 template_item 分组）。"""
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    """SELECT entry_id, template_item_id, entry_catalog_item_id,
                              field, value, base_updated_at, staged_at
                       FROM pending_field_saves
                       ORDER BY entry_id, template_item_id, staged_at"""
                )
                rows = cur.fetchall()
        grouped: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for entry_id, tpl_id, ec_id, field, value, base_ts, staged_at in rows:
            key = (int(entry_id), int(tpl_id))
            info = grouped.setdefault(
                key,
                {
                    "entry_id": int(entry_id),
                    "template_item_id": int(tpl_id),
                    "entry_catalog_item_id": ec_id,
                    "fields": {},
                    "base_updated_at": base_ts,
                    "staged_at": staged_at,
                },
            )
            info["fields"][field] = self._decode(value)
            if ec_id is not None:
                info["entry_catalog_item_id"] = ec_id
        return list(grouped.values())

    def count(self) -> int:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM pending_field_saves")
                return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# 单例 & 回放
# ---------------------------------------------------------------------------

_wal_instance: Optional[CatalogWAL] = None
_wal_lock = threading.Lock()


def get_catalog_wal() -> CatalogWAL:
    """获取全局单例 WAL。"""
    global _wal_instance
    with _wal_lock:
        if _wal_instance is None:
            _wal_instance = CatalogWAL()
        return _wal_instance


def replay_pending_saves(max_age_seconds: int = 7 * 24 * 3600) -> Tuple[int, int]:
    """启动时回放 WAL 中所有未落盘的字段，尝试把它们写到服务器 DB。

    参数
    ----
    max_age_seconds
        回放窗口。超过该窗口的老 pending 一律丢弃，不再写回 DB——避免
        "crash 时的老值在多日后回放时把别的客户端写入的新值覆盖"。
        默认 7 天。

    返回
    ----
    ``(成功条目数, 跳过+失败条目数)``"""
    # 延迟 import 避免循环依赖：repositories 可能反向引用 services
    from main_ui.pages.inventory_ui.repo.inventory_entry_repo import (
        upsert_entry_catalog_item_fields,
    )

    wal = get_catalog_wal()
    items = wal.list_all()
    if not items:
        return 0, 0

    now = time.time()
    ok_count = 0
    err_count = 0
    stale_count = 0
    for info in items:
        entry_id = info["entry_id"]
        tpl_id = info["template_item_id"]
        ec_id = info["entry_catalog_item_id"]
        fields = info["fields"]
        staged_at = info.get("staged_at") or 0
        if not fields:
            continue

        # 老于阈值的条目：直接从 WAL 清除，不回放（避免用旧值覆盖新值）
        if staged_at and (now - float(staged_at)) > max_age_seconds:
            try:
                wal.remove_fields(entry_id=entry_id, template_item_id=tpl_id, fields=list(fields.keys()))
            except Exception:
                pass
            stale_count += 1
            print(
                f"[catalog-wal] discard stale entry={entry_id} tpl={tpl_id} "
                f"age={int(now - float(staged_at))}s > {max_age_seconds}s"
            )
            continue

        try:
            # 回放时不传 base_updated_at：上次异常退出后无法再确认基线，
            # 而 WAL 只保留的是用户"已经想保存"的值，按最后写者胜即可。
            upsert_entry_catalog_item_fields(
                entry_id=entry_id,
                template_item_id=tpl_id,
                entry_catalog_item_id=int(ec_id) if ec_id else None,
                fields=fields,
            )
            wal.remove_fields(entry_id=entry_id, template_item_id=tpl_id, fields=list(fields.keys()))
            ok_count += 1
        except Exception as e:
            # 数据类型冲突/唯一键冲突/外键缺失 —— 都是永久性错误，retry 也写不进去。
            # 留在 WAL 里只会每次启动都喷日志，直接丢弃。
            msg = str(e)
            is_permanent = (
                "DataError" in type(e).__name__
                or "IntegrityError" in type(e).__name__
                or "1366" in msg  # Incorrect integer value
                or "1264" in msg  # Out of range value
                or "1292" in msg  # Incorrect datetime value
                or "1062" in msg  # Duplicate entry
                or "1452" in msg  # Cannot add or update a child row: a foreign key constraint fails
            )
            if is_permanent:
                print(f"[catalog-wal] permanent error, discarding entry={entry_id} tpl={tpl_id}: {e}")
                try:
                    wal.remove_fields(entry_id=entry_id, template_item_id=tpl_id, fields=list(fields.keys()))
                except Exception:
                    pass
                err_count += 1
            else:
                print(f"[catalog-wal] replay failed (retryable) entry={entry_id} tpl={tpl_id}: {e}")
                err_count += 1

    if stale_count:
        print(f"[catalog-wal] discarded {stale_count} stale pending entries")
    return ok_count, err_count


__all__ = ["CatalogWAL", "get_catalog_wal", "replay_pending_saves"]

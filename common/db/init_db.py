# -*- coding: utf-8 -*-
"""
数据库初始化和迁移
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import create_engine, inspect, text

from common.config.app_config import AppConfig
from common.config.db_config import DatabaseConfig

from .engine import Base, get_engine, reset_engine


_PERFORMANCE_INDEXES_ENSURED = False


def create_all():
    """创建所有数据库表"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_entries_org_unit_id()
    _ensure_performance_indexes()
    _seed_field_options()


def ensure_database_exists(host: str, port: int, user: str, password: str, database: str) -> None:
    """确保 MySQL 数据库本身存在（不创建表，仅创建库）。"""
    db_name = (database or "").strip()
    if not db_name:
        raise ValueError("数据库名称不能为空")

    server_url = (
        f"mysql+pymysql://{user}:{password}"
        f"@{host}:{port}/"
        f"?charset={DatabaseConfig.DEFAULT_CHARSET}"
    )
    engine = create_engine(
        server_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    try:
        safe_db_name = db_name.replace("`", "``")
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{safe_db_name}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                )
            )
    finally:
        try:
            engine.dispose()
        except Exception:
            pass


def is_database_initialized(required_tables: Optional[Iterable[str]] = None) -> bool:
    """检查数据库是否完成基础初始化（表结构 + 基础种子数据）。"""
    try:
        inspector = inspect(get_engine())
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(required_tables or Base.metadata.tables.keys())
        if not expected_tables.issubset(existing_tables):
            return False

        from .models import CatalogTemplate, User
        from .session import get_session

        with get_session() as session:
            has_user = session.query(User).count() > 0
            has_template = session.query(CatalogTemplate).count() > 0
            return has_user and has_template
    except Exception:
        return False


def _seed_default_admin_user() -> None:
    """确保默认管理员账号存在，方便首次部署登录。"""
    try:
        from .models import User
        from .session import get_session

        with get_session() as session:
            existing = session.query(User).filter(User.username == AppConfig.DEFAULT_ADMIN_USER).first()
            if existing:
                return
            session.add(
                User(
                    username=AppConfig.DEFAULT_ADMIN_USER,
                    password_hash=AppConfig.DEFAULT_ADMIN_PASS,
                    display_name="系统管理员",
                    theme="light",
                )
            )
            session.commit()
    except Exception:
        # 数据库不可用/表不存在时不阻断后续流程
        pass


def bootstrap_host_database(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> None:
    """主机首次初始化：创建数据库、建表、写入默认用户和目录模板。"""
    ensure_database_exists(host, port, user, password, database)

    DatabaseConfig.set_connection(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    reset_engine()

    create_all()
    _seed_default_admin_user()

    from common.seed_templates import seed_templates

    seed_templates()


def migrate_existing_images_to_root(target_root: str) -> dict:
    """
    将数据库里已存在的图片文件迁移到新的共享图片根目录。

    迁移规则：
    - 按 <target_root>/<entry_id>/<template_item_id>/<file_name> 结构复制
    - 成功后同步更新 entry_item_images.file_path
    - 目标目录已存在时直接复用

    Returns:
        dict: 迁移统计信息
    """
    root = (target_root or "").strip()
    stats = {
        "total": 0,
        "copied": 0,
        "updated": 0,
        "missing": 0,
        "errors": [],
    }
    if not root:
        return stats

    import os
    import shutil

    from .models import EntryCatalogItem, EntryItemImage
    from .session import get_session

    os.makedirs(root, exist_ok=True)

    with get_session() as session:
        rows = (
            session.query(EntryItemImage, EntryCatalogItem.entry_id, EntryCatalogItem.template_item_id)
            .join(EntryCatalogItem, EntryCatalogItem.id == EntryItemImage.entry_catalog_item_id)
            .order_by(EntryItemImage.id.asc())
            .all()
        )

        for img, entry_id, template_item_id in rows:
            stats["total"] += 1
            src_path = (img.file_path or "").strip()
            file_name = (img.file_name or "").strip() or os.path.basename(src_path)
            if not file_name:
                stats["missing"] += 1
                continue

            dest_dir = os.path.join(root, str(int(entry_id)), str(int(template_item_id)))
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, file_name)

            if src_path and os.path.exists(src_path):
                try:
                    if os.path.abspath(src_path) != os.path.abspath(dest_path):
                        shutil.copy2(src_path, dest_path)
                        stats["copied"] += 1
                    if img.file_path != dest_path:
                        img.file_path = dest_path
                        stats["updated"] += 1
                except Exception as e:
                    stats["errors"].append(f"{file_name}: {e}")
            elif os.path.exists(dest_path):
                if img.file_path != dest_path:
                    img.file_path = dest_path
                    stats["updated"] += 1
            else:
                stats["missing"] += 1

        session.commit()

    return stats


def _ensure_entries_org_unit_id():
    """
    轻量迁移（无 Alembic）：
    - 确保 entries 表存在 org_unit_id 列
    - 尝试创建索引/外键
    """
    try:
        engine = get_engine()
        with engine.begin() as conn:
            # 当前数据库名
            db_name = conn.execute(text("SELECT DATABASE()")).scalar()
            if not db_name:
                return

            # === entries.id_card ===
            try:
                col_id_card = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = :db
                          AND TABLE_NAME = 'entries'
                          AND COLUMN_NAME = 'id_card'
                        LIMIT 1
                        """
                    ),
                    {"db": db_name},
                ).scalar()
                if not col_id_card:
                    conn.execute(text("ALTER TABLE entries ADD COLUMN id_card VARCHAR(32) NULL"))
            except Exception:
                pass

            # === entries.custom_fields ===
            try:
                col_cf = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = :db
                          AND TABLE_NAME = 'entries'
                          AND COLUMN_NAME = 'custom_fields'
                        LIMIT 1
                        """
                    ),
                    {"db": db_name},
                ).scalar()
                if not col_cf:
                    conn.execute(text("ALTER TABLE entries ADD COLUMN custom_fields TEXT NULL"))
            except Exception:
                pass

            # 是否已有 org_unit_id 列
            col = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = :db
                      AND TABLE_NAME = 'entries'
                      AND COLUMN_NAME = 'org_unit_id'
                    LIMIT 1
                    """
                ),
                {"db": db_name},
            ).scalar()
            if not col:
                conn.execute(text("ALTER TABLE entries ADD COLUMN org_unit_id BIGINT NULL"))

            # 尝试加索引
            try:
                idx = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = :db
                          AND TABLE_NAME = 'entries'
                          AND INDEX_NAME = 'idx_entries_org_unit_id'
                        LIMIT 1
                        """
                    ),
                    {"db": db_name},
                ).scalar()
                if not idx:
                    conn.execute(text("CREATE INDEX idx_entries_org_unit_id ON entries (org_unit_id)"))
            except Exception:
                pass

            # 尝试加外键
            try:
                fk = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.TABLE_CONSTRAINTS
                        WHERE TABLE_SCHEMA = :db
                          AND TABLE_NAME = 'entries'
                          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
                          AND CONSTRAINT_NAME = 'fk_entries_org_unit'
                        LIMIT 1
                        """
                    ),
                    {"db": db_name},
                ).scalar()
                if not fk:
                    conn.execute(
                        text(
                            """
                            ALTER TABLE entries
                            ADD CONSTRAINT fk_entries_org_unit
                            FOREIGN KEY (org_unit_id) REFERENCES org_units(id)
                            """
                        )
                    )
            except Exception:
                pass
    except Exception:
        # DB 不可用/权限不足时不阻断启动
        return


def _ensure_performance_indexes():
    try:
        engine = get_engine()
        with engine.begin() as conn:
            db_name = conn.execute(text("SELECT DATABASE()")).scalar()
            if not db_name:
                return

            lock_name = f"{db_name}:cadre_performance_indexes"
            lock_acquired = False
            try:
                lock_value = conn.execute(text("SELECT GET_LOCK(:name, 1)"), {"name": lock_name}).scalar()
                lock_acquired = int(lock_value or 0) == 1
            except Exception:
                lock_acquired = True
            if not lock_acquired:
                return

            try:
                def ensure_index(table_name: str, index_name: str, columns: str):
                    try:
                        exists = conn.execute(
                            text(
                                """
                                SELECT 1
                                FROM information_schema.STATISTICS
                                WHERE TABLE_SCHEMA = :db
                                  AND TABLE_NAME = :table
                                  AND INDEX_NAME = :idx
                                LIMIT 1
                                """
                            ),
                            {"db": db_name, "table": table_name, "idx": index_name},
                        ).scalar()
                        if not exists:
                            safe_table = table_name.replace("`", "``")
                            safe_index = index_name.replace("`", "``")
                            conn.execute(text(f"CREATE INDEX `{safe_index}` ON `{safe_table}` ({columns})"))
                    except Exception:
                        pass

                ensure_index("entries", "idx_entries_org_name", "org_unit_id, name")
                ensure_index("entries", "idx_entries_name", "name")
                ensure_index("entry_catalog_items", "idx_ec_entry_tpl", "entry_id, template_item_id")
                ensure_index("entry_item_images", "idx_images_ec_sort", "entry_catalog_item_id, sort_order, id")
                ensure_index("entry_item_images", "idx_images_ec_type", "entry_catalog_item_id, image_type")
                ensure_index("entry_item_images", "idx_images_original_id", "original_id")
            finally:
                try:
                    conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
                except Exception:
                    pass
    except Exception:
        return


def ensure_performance_indexes():
    global _PERFORMANCE_INDEXES_ENSURED
    if _PERFORMANCE_INDEXES_ENSURED:
        return
    _ensure_performance_indexes()
    _PERFORMANCE_INDEXES_ENSURED = True


# ── field_options 种子数据 ──
_DEFAULT_FIELD_OPTIONS = {
    "status": ["待录入", "录入中", "已完成"],
    "role_title": ["管理员", "科员", "主任", "副主任"],
}


def _seed_field_options():
    """首次建表后预置默认下拉选项（已有数据则跳过）"""
    try:
        from .models import FieldOption
        from .session import get_session

        with get_session() as session:
            existing = session.query(FieldOption).count()
            if existing > 0:
                return  # 已有数据，不再重复插入
            for field_name, values in _DEFAULT_FIELD_OPTIONS.items():
                for idx, val in enumerate(values):
                    session.add(FieldOption(
                        field_name=field_name,
                        option_value=val,
                        sort_order=idx + 1,
                    ))
            session.commit()
    except Exception:
        # 数据库不可用时不阻断启动
        pass


if __name__ == "__main__":
    create_all()
    print("数据库表已创建完成。")

# -*- coding: utf-8 -*-
"""
数据库模块
提供数据库连接、会话管理和模型定义
"""

from .engine import engine, Base, get_engine, reset_engine, test_connection
from .session import SessionLocal, get_session, SessionContext
from .init_db import (
    create_all,
    bootstrap_host_database,
    is_database_initialized,
    migrate_existing_images_to_root,
    ensure_performance_indexes,
)
from .models import (
    User,
    CatalogTemplate,
    CatalogTemplateItem,
    Entry,
    EntryCatalogItem,
    EntryItemImage,
    FieldOption,
    OrgUnit,
)

__all__ = [
    # 引擎和基类
    'engine',
    'Base',
    'get_engine',
    'reset_engine',
    'test_connection',
    'create_all',
    'bootstrap_host_database',
    'is_database_initialized',
    'migrate_existing_images_to_root',
    'ensure_performance_indexes',
    # 会话管理
    'SessionLocal',
    'get_session',
    'SessionContext',
    # 模型
    'User',
    'CatalogTemplate',
    'CatalogTemplateItem',
    'Entry',
    'EntryCatalogItem',
    'EntryItemImage',
    'FieldOption',
    'OrgUnit',
]

# -*- coding: utf-8 -*-
"""
Common 模块
提供数据库、配置、服务等核心功能

重构后的架构:
- common/config/    统一配置模块
- common/db/        数据库模块
- common/repositories/  数据访问层
- common/services/  业务逻辑层

向后兼容:
- 保留原有的导入路径
"""

# 导出数据库相关（向后兼容）
from .db import (
    engine,
    Base,
    SessionLocal,
    get_session,
    User,
    CatalogTemplate,
    CatalogTemplateItem,
    Entry,
    EntryCatalogItem,
    EntryItemImage,
    OrgUnit,
)

# 导出初始化函数（向后兼容）
from .db.init_db import create_all

# 导出配置（向后兼容）
from .config import AppConfig, AppSettings

__all__ = [
    # 数据库
    'engine',
    'Base',
    'SessionLocal',
    'get_session',
    'create_all',
    # 模型
    'User',
    'CatalogTemplate',
    'CatalogTemplateItem',
    'Entry',
    'EntryCatalogItem',
    'EntryItemImage',
    'OrgUnit',
    # 配置
    'AppConfig',
    'AppSettings',
]

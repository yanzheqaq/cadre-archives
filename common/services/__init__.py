# -*- coding: utf-8 -*-
"""
业务服务模块
提供业务逻辑处理
"""

from .auth_service import AuthService, auth_service
from .org_service import OrgService, org_service
from .entry_service import EntryService, entry_service
from .theme_service import ThemeService, theme_service

# 上传队列服务（需要 redis 库）
from .upload_queue_service import (
    get_upload_queue_manager,
    shutdown_upload_queue,
    build_upload_task,
)

# 目录录入本地 WAL（SQLite 持久化 pending，保证 app 强杀后不丢目录字段）
from .catalog_wal_service import (
    CatalogWAL,
    get_catalog_wal,
    replay_pending_saves,
)

# 加密服务（可选，需要 pycryptodome）
try:
    from .crypto_service import (
        CryptoService,
        get_crypto_service,
        encrypt_image,
        encrypt_image_bytes,
        decrypt_image,
        decrypt_image_to_memory,
        is_encrypted,
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

__all__ = [
    'AuthService',
    'auth_service',
    'OrgService',
    'org_service',
    'EntryService',
    'entry_service',
    'ThemeService',
    'theme_service',
    # 上传队列
    'get_upload_queue_manager',
    'shutdown_upload_queue',
    'build_upload_task',
    # 目录 WAL
    'CatalogWAL',
    'get_catalog_wal',
    'replay_pending_saves',
    # 加密服务
    'CRYPTO_AVAILABLE',
]

# 如果加密服务可用，添加到导出
if CRYPTO_AVAILABLE:
    __all__.extend([
        'CryptoService',
        'get_crypto_service',
        'encrypt_image',
        'encrypt_image_bytes',
        'decrypt_image',
        'decrypt_image_to_memory',
        'is_encrypted',
    ])

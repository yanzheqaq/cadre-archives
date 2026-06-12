# -*- coding: utf-8 -*-
"""
数据仓库模块
提供数据访问层的抽象和实现
"""

from .base_repo import BaseRepository
from .user_repo import UserRepository
from .org_repo import OrgRepository
from .entry_repo import EntryRepository
from .template_repo import TemplateRepository
from .image_repo import ImageRepository

__all__ = [
    'BaseRepository',
    'UserRepository',
    'OrgRepository',
    'EntryRepository',
    'TemplateRepository',
    'ImageRepository',
]

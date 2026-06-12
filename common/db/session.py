# -*- coding: utf-8 -*-
"""
数据库会话管理
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import sessionmaker, Session

from .engine import get_engine
from common.config.db_config import DatabaseConfig


# 延迟创建会话工厂
_SessionLocal = None


def _get_session_factory():
    """获取会话工厂（延迟初始化）"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=DatabaseConfig.SESSION_AUTOFLUSH,
            autocommit=DatabaseConfig.SESSION_AUTOCOMMIT,
            future=True,
        )
    return _SessionLocal


def reset_session_factory():
    """重置会话工厂（在引擎重置后调用）"""
    global _SessionLocal
    _SessionLocal = None


# 向后兼容的 SessionLocal
class _SessionLocalProxy:
    """会话工厂代理类"""
    
    def __call__(self, *args, **kwargs):
        return _get_session_factory()(*args, **kwargs)
    
    def __getattr__(self, name):
        return getattr(_get_session_factory(), name)


SessionLocal = _SessionLocalProxy()


def get_session() -> Session:
    """
    获取一个新的数据库会话
    调用方负责关闭会话
    
    推荐使用 with 语句或 SessionContext
    """
    return _get_session_factory()()


@contextmanager
def SessionContext() -> Generator[Session, None, None]:
    """
    数据库会话上下文管理器
    自动处理提交和回滚
    
    用法:
        with SessionContext() as session:
            session.query(User).all()
    """
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

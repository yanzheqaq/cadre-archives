# -*- coding: utf-8 -*-
"""
SQLAlchemy 引擎配置
使用延迟初始化避免在模块导入时就连接数据库
支持运行时重置连接
"""

from typing import Tuple, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base

from common.config.db_config import DatabaseConfig


# 声明式基类（可以立即创建，不需要数据库连接）
Base = declarative_base()


# 延迟初始化的引擎
_engine = None


def get_engine():
    """获取数据库引擎（延迟初始化）"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DatabaseConfig.get_database_url(),
            echo=DatabaseConfig.ENGINE_ECHO,
            future=DatabaseConfig.ENGINE_FUTURE,
            pool_pre_ping=DatabaseConfig.ENGINE_POOL_PRE_PING,
            pool_size=DatabaseConfig.ENGINE_POOL_SIZE,
            max_overflow=DatabaseConfig.ENGINE_POOL_MAX_OVERFLOW,
            pool_timeout=DatabaseConfig.ENGINE_POOL_TIMEOUT,
            pool_recycle=DatabaseConfig.ENGINE_POOL_RECYCLE,
            pool_use_lifo=DatabaseConfig.ENGINE_POOL_USE_LIFO,
        )
    return _engine


def reset_engine():
    """
    重置数据库引擎
    在修改 DatabaseConfig 连接配置后调用此方法
    """
    global _engine
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
        _engine = None
    
    # 同时重置 session 工厂
    from .session import reset_session_factory
    reset_session_factory()


def test_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    timeout: int = 5
) -> Tuple[bool, str]:
    """
    测试数据库连接
    
    Args:
        host: 数据库主机
        port: 端口
        user: 用户名
        password: 密码
        database: 数据库名
        timeout: 连接超时（秒）
    
    Returns:
        (成功, 消息)
    """
    url = (
        f"mysql+pymysql://{user}:{password}"
        f"@{host}:{port}/{database}"
        f"?charset=utf8mb4&connect_timeout={timeout}"
    )
    
    test_engine = None
    try:
        test_engine = create_engine(
            url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        # 测试连接
        with test_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return True, "连接成功"
    except Exception as e:
        err_msg = str(e)
        # 简化错误信息
        if "Access denied" in err_msg:
            return False, "用户名或密码错误"
        elif "Unknown database" in err_msg:
            return False, f"数据库 '{database}' 不存在"
        elif "Can't connect" in err_msg or "Connection refused" in err_msg:
            return False, f"无法连接到 {host}:{port}"
        elif "timed out" in err_msg.lower():
            return False, "连接超时"
        else:
            return False, f"连接失败: {err_msg[:100]}"
    finally:
        if test_engine is not None:
            try:
                test_engine.dispose()
            except Exception:
                pass


# 为了向后兼容，提供 engine 属性
class _EngineProxy:
    """引擎代理类，延迟获取实际引擎"""
    
    def __getattr__(self, name):
        return getattr(get_engine(), name)
    
    def __repr__(self):
        return repr(get_engine())


engine = _EngineProxy()

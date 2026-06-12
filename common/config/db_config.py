# -*- coding: utf-8 -*-
"""
数据库配置
支持运行时动态配置数据库连接
"""

import os
from typing import Optional, Tuple


class DatabaseConfig:
    """数据库配置"""
    
    # 默认数据库连接信息
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 3306
    DEFAULT_USER = "root"
    DEFAULT_PASSWORD = "123456"
    DEFAULT_DATABASE = "pfms"
    DEFAULT_CHARSET = "utf8mb4"
    
    # 运行时配置（可动态修改）
    _runtime_host: Optional[str] = None
    _runtime_port: Optional[int] = None
    _runtime_user: Optional[str] = None
    _runtime_password: Optional[str] = None
    _runtime_database: Optional[str] = None
    
    @classmethod
    def get_host(cls) -> str:
        return cls._runtime_host or cls.DEFAULT_HOST
    
    @classmethod
    def get_port(cls) -> int:
        return cls._runtime_port or cls.DEFAULT_PORT
    
    @classmethod
    def get_user(cls) -> str:
        return cls._runtime_user or cls.DEFAULT_USER
    
    @classmethod
    def get_password(cls) -> str:
        return cls._runtime_password or cls.DEFAULT_PASSWORD
    
    @classmethod
    def get_database(cls) -> str:
        return cls._runtime_database or cls.DEFAULT_DATABASE
    
    @classmethod
    def set_connection(
        cls,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        """
        设置运行时数据库连接配置
        设置后需要调用 reset_engine() 重新创建连接
        """
        if host is not None:
            cls._runtime_host = host.strip() if host.strip() else None
        if port is not None:
            cls._runtime_port = port if port > 0 else None
        if user is not None:
            cls._runtime_user = user.strip() if user.strip() else None
        if password is not None:
            cls._runtime_password = password if password else None
        if database is not None:
            cls._runtime_database = database.strip() if database.strip() else None
    
    @classmethod
    def get_connection_info(cls) -> Tuple[str, int, str, str, str]:
        """获取当前连接配置 (host, port, user, password, database)"""
        return (
            cls.get_host(),
            cls.get_port(),
            cls.get_user(),
            cls.get_password(),
            cls.get_database(),
        )
    
    @classmethod
    def get_database_url(cls) -> str:
        """
        获取数据库连接 URL
        优先使用运行时配置，其次环境变量，最后默认配置
        """
        env_url = os.getenv("DATABASE_URL")
        if env_url and not cls._runtime_host:
            return env_url
        
        host = cls.get_host()
        port = cls.get_port()
        user = cls.get_user()
        password = cls.get_password()
        database = cls.get_database()
        
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{host}:{port}/{database}"
            f"?charset={cls.DEFAULT_CHARSET}&connect_timeout={cls.ENGINE_CONNECT_TIMEOUT}"
        )
    
    @classmethod
    def get_display_info(cls) -> str:
        """获取用于显示的连接信息（隐藏密码）"""
        return f"{cls.get_host()}:{cls.get_port()}/{cls.get_database()}"
    
    # SQLAlchemy 引擎配置
    ENGINE_ECHO = False          # 是否打印 SQL 语句
    ENGINE_FUTURE = True         # 使用 2.0 风格
    ENGINE_POOL_PRE_PING = True  # 连接池预检查
    ENGINE_POOL_SIZE = 2         # 连接池大小
    ENGINE_POOL_MAX_OVERFLOW = 2
    ENGINE_POOL_TIMEOUT = 10     # 连接超时（秒）
    ENGINE_POOL_RECYCLE = 1800
    ENGINE_POOL_USE_LIFO = True
    ENGINE_CONNECT_TIMEOUT = 5
    
    # Session 配置
    SESSION_AUTOFLUSH = False
    SESSION_AUTOCOMMIT = False

# -*- coding: utf-8 -*-
"""
Redis 配置
用于上传任务队列等场景
"""

import os
from typing import Optional


class RedisConfig:
    """Redis 连接配置"""

    # 默认连接信息
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 6379
    DEFAULT_DB = 0
    DEFAULT_PASSWORD = ""

    # 队列键名前缀
    QUEUE_PREFIX = "pfms:"
    UPLOAD_QUEUE_KEY = "pfms:upload:image:queue"        # 待处理任务列表
    UPLOAD_PROCESSING_KEY = "pfms:upload:image:processing"  # 正在处理的任务
    UPLOAD_FAILED_KEY = "pfms:upload:image:failed"      # 失败的任务

    # 运行时配置（可动态修改）
    _runtime_host: Optional[str] = None
    _runtime_port: Optional[int] = None
    _runtime_db: Optional[int] = None
    _runtime_password: Optional[str] = None

    @classmethod
    def get_host(cls) -> str:
        return cls._runtime_host or os.getenv("REDIS_HOST", cls.DEFAULT_HOST)

    @classmethod
    def get_port(cls) -> int:
        env_port = os.getenv("REDIS_PORT")
        if cls._runtime_port is not None:
            return cls._runtime_port
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                pass
        return cls.DEFAULT_PORT

    @classmethod
    def get_db(cls) -> int:
        return cls._runtime_db if cls._runtime_db is not None else cls.DEFAULT_DB

    @classmethod
    def get_password(cls) -> str:
        return cls._runtime_password or os.getenv("REDIS_PASSWORD", cls.DEFAULT_PASSWORD)

    @classmethod
    def set_connection(
        cls,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
    ) -> None:
        """设置运行时 Redis 连接配置"""
        if host is not None:
            cls._runtime_host = host.strip() if host.strip() else None
        if port is not None:
            cls._runtime_port = port if port > 0 else None
        if db is not None:
            cls._runtime_db = db if db >= 0 else None
        if password is not None:
            cls._runtime_password = password if password else None

    @classmethod
    def get_connection_kwargs(cls) -> dict:
        """获取 redis.Redis() 的连接参数"""
        kwargs = {
            "host": cls.get_host(),
            "port": cls.get_port(),
            "db": cls.get_db(),
            "decode_responses": True,
            "socket_connect_timeout": 3,
            "socket_timeout": 5,
            "retry_on_timeout": True,
        }
        pwd = cls.get_password()
        if pwd:
            kwargs["password"] = pwd
        return kwargs

    @classmethod
    def get_display_info(cls) -> str:
        """获取用于显示的连接信息"""
        return f"{cls.get_host()}:{cls.get_port()}/{cls.get_db()}"

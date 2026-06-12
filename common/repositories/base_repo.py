# -*- coding: utf-8 -*-
"""
Repository 基类
提供通用的 CRUD 操作
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from common.db import get_session, Base


T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    """
    Repository 基类
    提供通用的数据库操作方法
    """
    
    model: Type[T] = None
    
    def __init__(self, session: Optional[Session] = None):
        """
        初始化 Repository
        
        Args:
            session: 可选的数据库会话，如果不提供则每次操作创建新会话
        """
        self._session = session
        self._owns_session = session is None
    
    def _get_session(self) -> Session:
        """获取数据库会话"""
        if self._session is not None:
            return self._session
        return get_session()
    
    def get_by_id(self, id: int) -> Optional[T]:
        """根据 ID 获取单条记录"""
        with get_session() as session:
            return session.query(self.model).filter(self.model.id == id).first()
    
    def get_all(self) -> List[T]:
        """获取所有记录"""
        with get_session() as session:
            return session.query(self.model).all()
    
    def create(self, **kwargs) -> Optional[int]:
        """创建新记录，返回 ID"""
        with get_session() as session:
            obj = self.model(**kwargs)
            session.add(obj)
            session.commit()
            return int(obj.id) if obj.id else None
    
    def update(self, id: int, **kwargs) -> bool:
        """更新记录"""
        with get_session() as session:
            result = session.query(self.model).filter(self.model.id == id).update(kwargs)
            session.commit()
            return result > 0
    
    def delete(self, id: int) -> bool:
        """删除记录"""
        with get_session() as session:
            result = session.query(self.model).filter(self.model.id == id).delete()
            session.commit()
            return result > 0
    
    def exists(self, id: int) -> bool:
        """检查记录是否存在"""
        with get_session() as session:
            return session.query(self.model).filter(self.model.id == id).count() > 0
    
    def count(self) -> int:
        """统计记录数"""
        with get_session() as session:
            return session.query(self.model).count()

# -*- coding: utf-8 -*-
"""
用户数据仓库
"""

from typing import Optional

from common.db import get_session, User
from .base_repo import BaseRepository


class UserRepository(BaseRepository[User]):
    """用户数据仓库"""
    
    model = User
    
    def get_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        with get_session() as session:
            return session.query(User).filter(User.username == username).first()
    
    def verify_password(self, username: str, password: str) -> bool:
        """
        验证用户密码
        注意：当前示例使用明文对比，生产环境应使用哈希
        """
        try:
            with get_session() as session:
                user = session.query(User).filter(User.username == username).first()
                if user and user.password_hash == password:
                    return True
        except Exception as e:
            print(f"[UserRepository] verify_password failed: {e}")
        return False
    
    def create_user(
        self,
        username: str,
        password: str,
        display_name: str = None,
        theme: str = "light"
    ) -> Optional[int]:
        """创建新用户"""
        return self.create(
            username=username,
            password_hash=password,  # 生产环境应该哈希
            display_name=display_name,
            theme=theme,
        )
    
    def update_theme(self, user_id: int, theme: str) -> bool:
        """更新用户主题偏好"""
        return self.update(user_id, theme=theme)


# 单例实例
user_repo = UserRepository()

# -*- coding: utf-8 -*-
"""
认证服务
处理用户登录、验证等业务逻辑
"""

from typing import Optional, Tuple

from common.config import AppConfig, AppSettings
from common.repositories import UserRepository


class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.user_repo = UserRepository()
        self.settings = AppSettings()
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str]:
        """
        验证用户登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            (成功与否, 错误消息)
        """
        if not username or not password:
            return False, "请输入完整的账号和密码"
        
        # 先尝试数据库验证
        if self.user_repo.verify_password(username, password):
            return True, ""
        
        # 兼容内置默认账号
        if username == AppConfig.DEFAULT_ADMIN_USER and password == AppConfig.DEFAULT_ADMIN_PASS:
            return True, ""
        
        return False, "账号或密码错误"
    
    def save_login_info(self, remember: bool, username: str, password: str) -> None:
        """保存登录信息"""
        self.settings.set_login_info(remember, username, password)
    
    def load_login_info(self) -> Tuple[bool, str, str]:
        """加载保存的登录信息"""
        return self.settings.get_login_info()


# 单例实例
auth_service = AuthService()

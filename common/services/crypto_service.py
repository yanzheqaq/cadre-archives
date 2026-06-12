# -*- coding: utf-8 -*-
"""
图片加密服务
使用 AES-256-CBC 对图片进行加密，确保只能在客户端查看
"""

import os
import hashlib
import secrets
from typing import Tuple, Optional
from pathlib import Path

# 尝试导入加密库
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.Util.Padding import pad, unpad
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False


class CryptoService:
    """
    图片加密服务
    - 使用 AES-256-CBC 加密
    - 加密文件格式: [16字节IV][加密数据]
    - 文件扩展名: .hfenc (自定义加密格式)
    """
    
    # 加密文件扩展名
    ENCRYPTED_EXT = ".hfenc"
    
    # 文件头标识（用于验证文件是否为加密文件）
    FILE_MAGIC = b"HFIMG001"  # 8 字节魔数
    
    # AES 块大小
    BLOCK_SIZE = 16
    
    # 密钥长度 (256 bit = 32 bytes)
    KEY_SIZE = 32
    
    def __init__(self, master_key: Optional[str] = None):
        """
        初始化加密服务
        
        Args:
            master_key: 主密钥字符串，如果不提供则使用内置密钥
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError(
                "加密库未安装！请运行: pip install pycryptodome"
            )
        
        # 使用提供的密钥或内置密钥
        # 注意：生产环境中应该使用更安全的密钥管理方式
        if master_key:
            self._key = self._derive_key(master_key)
        else:
            # 内置密钥 - 基于应用特征派生
            # 实际部署时应该替换为更安全的密钥
            self._key = self._derive_key("HLFW-CADRE-ARCHIVES-2024-SECURE-KEY")
    
    def _derive_key(self, password: str) -> bytes:
        """
        从密码派生 AES 密钥
        使用 PBKDF2-like 方式增强安全性
        """
        # 固定盐值（应用级别）
        salt = b"HLFW_SALT_2024"
        # 使用 SHA-256 多次迭代派生密钥
        key = password.encode('utf-8')
        for _ in range(10000):
            key = hashlib.sha256(salt + key).digest()
        return key[:self.KEY_SIZE]
    
    def encrypt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        加密文件
        
        Args:
            input_path: 原始文件路径
            output_path: 加密后文件路径，默认为原路径 + .hfenc
            
        Returns:
            加密后文件的路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        
        # 默认输出路径
        if output_path is None:
            output_path = input_path + self.ENCRYPTED_EXT
        
        # 读取原始数据
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # 加密
        ciphertext, iv = self._encrypt_data(plaintext)
        
        # 保存原始扩展名（用于解密后恢复）
        original_ext = Path(input_path).suffix.encode('utf-8')
        ext_len = len(original_ext)
        
        # 写入加密文件
        # 格式: [魔数8B][扩展名长度1B][扩展名][IV 16B][密文]
        with open(output_path, 'wb') as f:
            f.write(self.FILE_MAGIC)
            f.write(bytes([ext_len]))
            f.write(original_ext)
            f.write(iv)
            f.write(ciphertext)
        
        return output_path

    def encrypt_bytes_to_file(self, data: bytes, output_path: str, original_ext: str = "") -> str:
        if not output_path:
            raise ValueError("加密输出路径不能为空")
        original_ext = (original_ext or "").strip()
        if original_ext and not original_ext.startswith("."):
            original_ext = "." + original_ext
        if not original_ext:
            original_ext = Path(output_path).suffix
            if original_ext == self.ENCRYPTED_EXT:
                original_ext = ""
        encoded_ext = original_ext.encode('utf-8')
        if len(encoded_ext) > 255:
            raise ValueError("图片扩展名过长，无法加密保存")
        ciphertext, iv = self._encrypt_data(data or b"")
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(self.FILE_MAGIC)
            f.write(bytes([len(encoded_ext)]))
            f.write(encoded_ext)
            f.write(iv)
            f.write(ciphertext)
        return output_path
    
    def decrypt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        解密文件
        
        Args:
            input_path: 加密文件路径
            output_path: 解密后文件路径，默认自动恢复原扩展名
            
        Returns:
            解密后文件的路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        
        with open(input_path, 'rb') as f:
            # 读取并验证魔数
            magic = f.read(8)
            if magic != self.FILE_MAGIC:
                raise ValueError("不是有效的加密文件")
            
            # 读取原始扩展名
            ext_len = f.read(1)[0]
            original_ext = f.read(ext_len).decode('utf-8')
            
            # 读取 IV
            iv = f.read(self.BLOCK_SIZE)
            
            # 读取密文
            ciphertext = f.read()
        
        # 解密
        plaintext = self._decrypt_data(ciphertext, iv)
        
        # 默认输出路径：去掉 .hfenc，恢复原扩展名
        if output_path is None:
            base = input_path
            if base.endswith(self.ENCRYPTED_EXT):
                base = base[:-len(self.ENCRYPTED_EXT)]
            # 如果原文件名已经有扩展名，直接使用
            if not base.endswith(original_ext):
                output_path = base + original_ext
            else:
                output_path = base
        
        # 写入解密文件
        with open(output_path, 'wb') as f:
            f.write(plaintext)
        
        return output_path
    
    def encrypt_bytes(self, data: bytes) -> bytes:
        """
        加密字节数据（用于内存中处理）
        
        Returns:
            加密后的数据（包含 IV）
        """
        ciphertext, iv = self._encrypt_data(data)
        return self.FILE_MAGIC + iv + ciphertext
    
    def decrypt_bytes(self, data: bytes) -> bytes:
        """
        解密字节数据（用于内存中处理）
        """
        if not data.startswith(self.FILE_MAGIC):
            raise ValueError("不是有效的加密数据")
        
        offset = len(self.FILE_MAGIC)
        iv = data[offset:offset + self.BLOCK_SIZE]
        ciphertext = data[offset + self.BLOCK_SIZE:]
        
        return self._decrypt_data(ciphertext, iv)
    
    def decrypt_to_memory(self, input_path: str) -> Tuple[bytes, str]:
        """
        解密文件到内存（不写入磁盘）
        
        Args:
            input_path: 加密文件路径
            
        Returns:
            (解密后的数据, 原始扩展名)
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        
        with open(input_path, 'rb') as f:
            # 读取并验证魔数
            magic = f.read(8)
            if magic != self.FILE_MAGIC:
                raise ValueError("不是有效的加密文件")
            
            # 读取原始扩展名
            ext_len = f.read(1)[0]
            original_ext = f.read(ext_len).decode('utf-8')
            
            # 读取 IV
            iv = f.read(self.BLOCK_SIZE)
            
            # 读取密文
            ciphertext = f.read()
        
        # 解密
        plaintext = self._decrypt_data(ciphertext, iv)
        
        return plaintext, original_ext
    
    def is_encrypted_file(self, file_path: str) -> bool:
        """
        检查文件是否为加密文件
        """
        if not os.path.exists(file_path):
            return False
        
        # 检查扩展名
        if file_path.endswith(self.ENCRYPTED_EXT):
            return True
        
        # 检查文件头
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(8)
                return magic == self.FILE_MAGIC
        except Exception:
            return False
    
    def _encrypt_data(self, plaintext: bytes) -> Tuple[bytes, bytes]:
        """
        内部加密方法
        
        Returns:
            (密文, IV)
        """
        # 生成随机 IV
        iv = secrets.token_bytes(self.BLOCK_SIZE)
        
        # 创建加密器
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        
        # 填充并加密
        padded = pad(plaintext, self.BLOCK_SIZE)
        ciphertext = cipher.encrypt(padded)
        
        return ciphertext, iv
    
    def _decrypt_data(self, ciphertext: bytes, iv: bytes) -> bytes:
        """
        内部解密方法
        """
        # 创建解密器
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        
        # 解密并去除填充
        padded = cipher.decrypt(ciphertext)
        plaintext = unpad(padded, self.BLOCK_SIZE)
        
        return plaintext


# 全局单例
_crypto_service: Optional[CryptoService] = None


def get_crypto_service() -> CryptoService:
    """获取加密服务单例"""
    global _crypto_service
    if _crypto_service is None:
        _crypto_service = CryptoService()
    return _crypto_service


def encrypt_image(input_path: str, output_path: Optional[str] = None) -> str:
    """便捷函数：加密图片"""
    return get_crypto_service().encrypt_file(input_path, output_path)


def encrypt_image_bytes(data: bytes, output_path: str, original_ext: str = "") -> str:
    return get_crypto_service().encrypt_bytes_to_file(data, output_path, original_ext)


def decrypt_image(input_path: str, output_path: Optional[str] = None) -> str:
    """便捷函数：解密图片"""
    return get_crypto_service().decrypt_file(input_path, output_path)


def decrypt_image_to_memory(input_path: str) -> Tuple[bytes, str]:
    """便捷函数：解密图片到内存"""
    return get_crypto_service().decrypt_to_memory(input_path)


def is_encrypted(file_path: str) -> bool:
    """便捷函数：检查是否为加密文件"""
    return get_crypto_service().is_encrypted_file(file_path)

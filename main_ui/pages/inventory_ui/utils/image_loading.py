import os
import io
from collections import OrderedDict
from typing import Optional

from PyQt5.QtCore import Qt, QBuffer, QIODevice
from PyQt5.QtGui import QImage, QPixmap

# 加密服务（可选）
try:
    from common.services.crypto_service import get_crypto_service, is_encrypted
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    is_encrypted = lambda x: False


def cache_key(file_path: str, max_side: int):
    """缓存 key：路径 + mtime + max_side，文件变更后自动失效。"""
    try:
        mtime = os.path.getmtime(file_path) if file_path and os.path.exists(file_path) else 0
    except Exception:
        mtime = 0
    return (file_path or "", int(mtime), int(max_side))


def lru_get(cache: "OrderedDict[tuple, QImage]", key):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    return None


def lru_put(cache: "OrderedDict[tuple, QImage]", key, value: QImage, max_items: int):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > max_items:
        cache.popitem(last=False)


def resolve_image_path(
    file_path: str,
    *,
    entry_id: Optional[int] = None,
    template_item_id: Optional[int] = None,
    file_name: str = "",
    image_root: str = "",
) -> str:
    """
    解析图片文件的实际可访问路径。

    优先返回当前已存在的 file_path；如果不存在，则尝试按当前共享图片根目录
    + entry_id/template_item_id/文件名 的结构回退查找。
    """
    raw_path = (file_path or "").strip()
    if raw_path and os.path.exists(raw_path):
        return raw_path

    resolved_root = (image_root or "").strip()
    if not resolved_root:
        try:
            from common.config import AppSettings

            resolved_root = AppSettings().get_image_root()
        except Exception:
            resolved_root = ""
    resolved_root = (resolved_root or "").strip()

    base_name = os.path.basename((file_name or raw_path or "").strip())
    candidates = []

    if resolved_root and base_name:
        if entry_id is not None and template_item_id is not None:
            try:
                candidates.append(
                    os.path.join(resolved_root, str(int(entry_id)), str(int(template_item_id)), base_name)
                )
            except Exception:
                pass
        candidates.append(os.path.join(resolved_root, base_name))

    if raw_path:
        candidates.append(raw_path)

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return candidates[0] if candidates else raw_path


def load_qimage_any(file_path: str, max_side: int = 0) -> QImage:
    """
    后台线程安全的图片加载（返回 QImage）：
    - 支持自动解密加密图片（.hfenc 文件）
    - 先用 Qt(QImage) 解码
    - 若失败（常见 TIFF 插件缺失），回退 Pillow
    - 可选按 max_side 缩放，避免解码出超大图导致卡顿/内存飙升
    """
    if not file_path or not os.path.exists(file_path):
        return QImage()
    
    # 检查是否为加密文件
    if CRYPTO_AVAILABLE and is_encrypted(file_path):
        return _load_encrypted_qimage(file_path, max_side)
    
    # 1) Qt 解码
    qimg = QImage(file_path)
    if not qimg.isNull():
        if max_side and max(qimg.width(), qimg.height()) > max_side:
            qimg = qimg.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return qimg
    # 2) Pillow fallback
    try:
        from PIL import Image  # type: ignore

        im = Image.open(file_path)
        # 只取第一页（多页 tiff 后续可扩展）
        im.load()
        if max_side:
            # 先缩略再转 RGBA，减少内存与耗时
            im.thumbnail((max_side, max_side), resample=Image.BILINEAR)
        im = im.convert("RGBA")
        w, h = im.size
        raw = im.tobytes("raw", "RGBA")
        return QImage(raw, w, h, QImage.Format_RGBA8888).copy()
    except Exception:
        return QImage()


def _load_encrypted_qimage(file_path: str, max_side: int = 0) -> QImage:
    """
    加载加密图片（解密到内存，不写入磁盘）
    """
    try:
        crypto = get_crypto_service()
        data, ext = crypto.decrypt_to_memory(file_path)
        
        # 尝试用 Qt 解码
        qimg = QImage()
        qimg.loadFromData(data)
        
        if not qimg.isNull():
            if max_side and max(qimg.width(), qimg.height()) > max_side:
                qimg = qimg.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return qimg
        
        # Qt 解码失败，尝试 Pillow
        try:
            from PIL import Image  # type: ignore
            
            im = Image.open(io.BytesIO(data))
            im.load()
            if max_side:
                im.thumbnail((max_side, max_side), resample=Image.BILINEAR)
            im = im.convert("RGBA")
            w, h = im.size
            raw = im.tobytes("raw", "RGBA")
            return QImage(raw, w, h, QImage.Format_RGBA8888).copy()
        except Exception:
            return QImage()
    except Exception:
        return QImage()


def load_pixmap_any(file_path: str) -> QPixmap:
    """
    加载图片为 QPixmap。
    - 支持自动解密加密图片（.hfenc 文件）
    - 优先使用 Qt 内置解码（QPixmap）
    - 若 Qt 不支持（常见于 TIFF 插件缺失），则回退 Pillow 解码
    """
    if not file_path:
        return QPixmap()
    
    # 检查是否为加密文件
    if CRYPTO_AVAILABLE and is_encrypted(file_path):
        return _load_encrypted_pixmap(file_path)
    
    pix = QPixmap(file_path)
    if not pix.isNull():
        return pix
    # Pillow fallback（支持 tif/tiff 等）
    try:
        from PIL import Image  # type: ignore

        im = Image.open(file_path)
        # 只取第一页（多页 tiff 后续可扩展）
        im = im.convert("RGBA")
        w, h = im.size
        raw = im.tobytes("raw", "RGBA")
        qimg = QImage(raw, w, h, QImage.Format_RGBA8888).copy()
        return QPixmap.fromImage(qimg)
    except Exception:
        return QPixmap()


def _load_encrypted_pixmap(file_path: str) -> QPixmap:
    """
    加载加密图片为 QPixmap（解密到内存，不写入磁盘）
    """
    try:
        crypto = get_crypto_service()
        data, ext = crypto.decrypt_to_memory(file_path)
        
        # 尝试用 Qt 解码
        pix = QPixmap()
        pix.loadFromData(data)
        
        if not pix.isNull():
            return pix
        
        # Qt 解码失败，尝试 Pillow
        try:
            from PIL import Image  # type: ignore
            
            im = Image.open(io.BytesIO(data))
            im = im.convert("RGBA")
            w, h = im.size
            raw = im.tobytes("raw", "RGBA")
            qimg = QImage(raw, w, h, QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(qimg)
        except Exception:
            return QPixmap()
    except Exception:
        return QPixmap()
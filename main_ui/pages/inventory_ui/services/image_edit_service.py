from __future__ import annotations

import math
import os
import io
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt5.QtGui import QImage

from common.services.crypto_service import (
    CryptoService,
    decrypt_image_to_memory,
    encrypt_image_bytes,
    is_encrypted,
)


RGB = Tuple[int, int, int]
RectNorm = Tuple[float, float, float, float]  # nx, ny, nw, nh
Pending = Dict[str, Any]


def new_pending() -> Pending:
    """pending 默认结构（与原 inventory_entry.py 一致）。"""
    return {
        "angle": 0.0, "crop_box": None, "border_fill": None, "pad_a4": None, "spots": [],
        "enhance": None,  # {"gray_remove": bool, "brightness": float, "contrast": float, "sharpen": float}
    }


def is_dirty(p: Optional[Pending]) -> bool:
    if not p:
        return False
    return (
        (abs(float(p.get("angle") or 0.0)) > 1e-6)
        or (p.get("crop_box") is not None)
        or (p.get("border_fill") is not None)
        or (p.get("pad_a4") is not None)
        or bool(p.get("spots") or [])
        or (p.get("enhance") is not None)
    )


def pad_to_a4(im, bg_color: RGB = (255, 255, 255)):
    """
    自动补边到 A4 长宽比（不缩放内容，只扩展画布并居中贴图）。
    A4 比例：1:√2（竖版 h/w=√2；横版 w/h=√2）
    """
    try:
        from PIL import Image  # type: ignore

        ratio = math.sqrt(2.0)
        w, h = im.size
        if w < 2 or h < 2:
            return im
        if im.mode != "RGB":
            im = im.convert("RGB")

        if w >= h:
            cur = w / max(1, h)
            if cur < ratio:
                new_w = int(math.ceil(h * ratio))
                new_h = h
            else:
                new_w = w
                new_h = int(math.ceil(w / ratio))
        else:
            cur = h / max(1, w)
            if cur < ratio:
                new_w = w
                new_h = int(math.ceil(w * ratio))
            else:
                new_w = int(math.ceil(h / ratio))
                new_h = h

        new_w = max(new_w, w)
        new_h = max(new_h, h)
        canvas = Image.new("RGB", (new_w, new_h), tuple(bg_color))
        ox = (new_w - w) // 2
        oy = (new_h - h) // 2
        canvas.paste(im, (ox, oy))
        return canvas
    except Exception:
        return im


def dominant_color_around_rect(im, rect: Tuple[int, int, int, int], ring: int = 6) -> RGB:
    """
    取矩形选区周围 ring 像素带的“代表色”用于填充。
    使用环带采样的 RGB 中位数，较稳定。
    """
    try:
        if im.mode != "RGB":
            im = im.convert("RGB")
        w, h = im.size
        x, y, rw, rh = rect
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(w, int(x + rw))
        y2 = min(h, int(y + rh))
        if x2 <= x1 or y2 <= y1:
            return (255, 255, 255)
        r = max(1, int(ring or 1))
        px = im.load()
        step = max(1, max(w, h) // 800)

        rs: List[int] = []
        gs: List[int] = []
        bs: List[int] = []

        def add(xx: int, yy: int):
            rr, gg, bb = px[xx, yy]
            rs.append(int(rr))
            gs.append(int(gg))
            bs.append(int(bb))

        yy0 = max(0, y1 - r)
        for yy in range(yy0, y1):
            for xx in range(max(0, x1 - r), min(w, x2 + r), step):
                add(xx, yy)
        yy1 = min(h, y2 + r)
        for yy in range(y2, yy1):
            for xx in range(max(0, x1 - r), min(w, x2 + r), step):
                add(xx, yy)
        xx0 = max(0, x1 - r)
        for xx in range(xx0, x1):
            for yy in range(max(0, y1 - r), min(h, y2 + r), step):
                add(xx, yy)
        xx1 = min(w, x2 + r)
        for xx in range(x2, xx1):
            for yy in range(max(0, y1 - r), min(h, y2 + r), step):
                add(xx, yy)

        if not rs:
            return (255, 255, 255)

        def median(vals: List[int]) -> int:
            vals = sorted(vals)
            n = len(vals)
            mid = n // 2
            return int(vals[mid]) if n % 2 == 1 else int((vals[mid - 1] + vals[mid]) / 2)

        return (median(rs), median(gs), median(bs))
    except Exception:
        return (255, 255, 255)


def rect_from_norm(im, rect_norm: RectNorm) -> Optional[Tuple[int, int, int, int]]:
    """将归一化矩形 (nx,ny,nw,nh) 映射为像素矩形 (x,y,w,h)，并做边界裁剪。"""
    try:
        nx, ny, nw, nh = rect_norm
        w, h = im.size
        x = int(round(float(nx) * w))
        y = int(round(float(ny) * h))
        rw = int(round(float(nw) * w))
        rh = int(round(float(nh) * h))
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))
        rw = max(1, min(w - x, rw))
        rh = max(1, min(h - y, rh))
        return (x, y, rw, rh)
    except Exception:
        return None


def apply_spot_fills(im, spots: Sequence[RectNorm]) -> Any:
    """对多个矩形选区执行“污点去除”：取选区周边主色并填充选区。"""
    try:
        from PIL import ImageDraw  # type: ignore

        if not spots:
            return im
        if im.mode != "RGB":
            im = im.convert("RGB")
        draw = ImageDraw.Draw(im)
        for rect_norm in spots:
            rect = rect_from_norm(im, rect_norm)
            if not rect:
                continue
            x, y, w, h = rect
            if w < 2 or h < 2:
                continue
            color = dominant_color_around_rect(im, (x, y, w, h), ring=4)
            draw.rectangle([int(x), int(y), int(x + w), int(y + h)], fill=tuple(color))
        return im
    except Exception:
        return im


def apply_outer_ring_fill(im, thickness: int = 1, color: RGB = (255, 255, 255)):
    """
    去黑边（新算法）：将图片最外围 thickness 像素宽的“外圈”填充为背景色。
    """
    try:
        from PIL import ImageDraw  # type: ignore

        thickness = max(1, int(thickness or 1))
        w, h = im.size
        if w <= 2 or h <= 2:
            return im
        if im.mode != "RGB":
            im = im.convert("RGB")
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 0, w - 1, thickness - 1], fill=color)
        draw.rectangle([0, h - thickness, w - 1, h - 1], fill=color)
        draw.rectangle([0, 0, thickness - 1, h - 1], fill=color)
        draw.rectangle([w - thickness, 0, w - 1, h - 1], fill=color)
        return im
    except Exception:
        return im


def mm_to_pixels(mm: float, dpi: int = 300) -> int:
    """
    将毫米转换为像素数（基于指定 DPI）。
    - 1 英寸 = 25.4 毫米
    - 像素数 = mm / 25.4 * dpi
    """
    return max(1, int(round(float(mm) / 25.4 * int(dpi))))


def _plain_image_name(name: str) -> str:
    enc_ext = CryptoService.ENCRYPTED_EXT
    text = name or ""
    return text[:-len(enc_ext)] if text.lower().endswith(enc_ext) else text


def _is_encrypted_path(file_path: str) -> bool:
    try:
        return is_encrypted(file_path)
    except Exception:
        return (file_path or "").lower().endswith(CryptoService.ENCRYPTED_EXT)


def _open_pil_image(file_path: str):
    from PIL import Image  # type: ignore

    if _is_encrypted_path(file_path):
        data, _ext = decrypt_image_to_memory(file_path)
        im = Image.open(io.BytesIO(data))
    else:
        im = Image.open(file_path)
    im.load()
    return im


def _image_bytes_for_save(im, out_name: str) -> Tuple[bytes, str]:
    plain_name = _plain_image_name(out_name)
    _stem, ext = os.path.splitext(plain_name)
    ext_l = ext.lower()
    buf = io.BytesIO()
    if ext_l in (".jpg", ".jpeg"):
        im.convert("RGB").save(buf, format="JPEG", quality=95)
    else:
        formats = {
            ".png": "PNG",
            ".bmp": "BMP",
            ".tif": "TIFF",
            ".tiff": "TIFF",
            ".webp": "WEBP",
        }
        fmt = formats.get(ext_l)
        if fmt:
            im.save(buf, format=fmt)
        else:
            im.convert("RGB").save(buf, format="JPEG", quality=95)
            ext = ".jpg"
    return buf.getvalue(), ext


def dominant_border_color(file_path: str, thickness: int = 1) -> RGB:
    """
    自动估算"外围占比最多"的背景色（返回 RGB 三元组）。
    """
    try:
        from PIL import Image  # type: ignore

        if not file_path or not os.path.exists(file_path):
            return (255, 255, 255)
        im0 = _open_pil_image(file_path)
        im = im0.convert("RGB")
        w0, h0 = im.size
        if w0 < 2 or h0 < 2:
            return (255, 255, 255)

        max_side = 800
        scale = min(1.0, max_side / max(w0, h0))
        if scale < 1.0:
            im = im.resize((max(2, int(w0 * scale)), max(2, int(h0 * scale))), resample=Image.BILINEAR)

        w, h = im.size
        t = max(1, int(thickness or 1))
        t = min(t, max(1, min(w, h) // 2))

        px = im.load()
        step = max(1, max(w, h) // 500)

        def q(c: RGB) -> RGB:
            r, g, b = c
            return ((r >> 4) << 4, (g >> 4) << 4, (b >> 4) << 4)

        cnt: Counter = Counter()
        for y in range(0, t):
            for x in range(0, w, step):
                cnt[q(px[x, y])] += 1
        for y in range(h - t, h):
            for x in range(0, w, step):
                cnt[q(px[x, y])] += 1
        for x in range(0, t):
            for y in range(0, h, step):
                cnt[q(px[x, y])] += 1
        for x in range(w - t, w):
            for y in range(0, h, step):
                cnt[q(px[x, y])] += 1

        if not cnt:
            return (255, 255, 255)
        (r, g, b), _n = cnt.most_common(1)[0]
        return (min(255, int(r) + 8), min(255, int(g) + 8), min(255, int(b) + 8))
    except Exception:
        return (255, 255, 255)


def remove_gray_background(im, strength: float = 1.0):
    """
    去灰底：将灰色/暗淡背景提亮为白色，同时保留文字和内容。
    原理：对每个像素，如果 RGB 三通道差异小（接近灰色），则向白色拉升。
    strength: 0.0~2.0，默认1.0，越大去灰效果越强。
    """
    try:
        import numpy as np
        from PIL import Image  # type: ignore

        if im.mode != "RGB":
            im = im.convert("RGB")
        arr = np.array(im, dtype=np.float32)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # 计算亮度和饱和度
        brightness = (r + g + b) / 3.0
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        chroma = max_c - min_c  # 色差，灰色区域色差很小

        # 灰色区域掩码：色差小且亮度在中间范围（非纯黑、非纯白）
        gray_mask = (chroma < 60) & (brightness > 80) & (brightness < 245)
        gray_mask = gray_mask.astype(np.float32)

        # 平滑掩码边缘
        try:
            from PIL import ImageFilter
            mask_im = Image.fromarray((gray_mask * 255).astype(np.uint8), mode="L")
            mask_im = mask_im.filter(ImageFilter.GaussianBlur(radius=3))
            gray_mask = np.array(mask_im, dtype=np.float32) / 255.0
        except Exception:
            pass

        # 计算提亮量：越灰越暗的区域提亮越多
        lift = (255.0 - brightness) * gray_mask * min(2.0, max(0.0, float(strength))) * 0.85

        # 应用提亮
        arr[:, :, 0] = np.clip(r + lift, 0, 255)
        arr[:, :, 1] = np.clip(g + lift, 0, 255)
        arr[:, :, 2] = np.clip(b + lift, 0, 255)

        return Image.fromarray(arr.astype(np.uint8), mode="RGB")
    except Exception:
        return im


def adjust_brightness_contrast(im, brightness: float = 1.0, contrast: float = 1.0):
    """
    调整亮度和对比度。
    brightness: 1.0=不变，>1.0=变亮，<1.0=变暗
    contrast: 1.0=不变，>1.0=增大对比度，<1.0=减小对比度
    """
    try:
        from PIL import ImageEnhance  # type: ignore

        if im.mode != "RGB":
            im = im.convert("RGB")
        if abs(brightness - 1.0) > 0.01:
            im = ImageEnhance.Brightness(im).enhance(float(brightness))
        if abs(contrast - 1.0) > 0.01:
            im = ImageEnhance.Contrast(im).enhance(float(contrast))
        return im
    except Exception:
        return im


def sharpen_image(im, amount: float = 1.0):
    """
    锐化图片。
    amount: 0.0=不锐化，1.0=标准锐化，2.0=强锐化
    """
    try:
        from PIL import ImageEnhance  # type: ignore

        if im.mode != "RGB":
            im = im.convert("RGB")
        if amount > 0.01:
            # Sharpness: 0.0=模糊, 1.0=原图, 2.0=锐化
            factor = 1.0 + float(amount)
            im = ImageEnhance.Sharpness(im).enhance(factor)
        return im
    except Exception:
        return im


def apply_enhance(im, enh: Dict[str, Any]):
    """
    统一应用增强参数。
    enh 结构: {"gray_remove": float, "brightness": float, "contrast": float, "sharpen": float}
    """
    try:
        gray_remove = float(enh.get("gray_remove") or 0.0)
        if gray_remove > 0.01:
            im = remove_gray_background(im, strength=gray_remove)

        brightness = float(enh.get("brightness") or 1.0)
        contrast = float(enh.get("contrast") or 1.0)
        if abs(brightness - 1.0) > 0.01 or abs(contrast - 1.0) > 0.01:
            im = adjust_brightness_contrast(im, brightness=brightness, contrast=contrast)

        sharpen = float(enh.get("sharpen") or 0.0)
        if sharpen > 0.01:
            im = sharpen_image(im, amount=sharpen)

        return im
    except Exception:
        return im


def apply_pending(im0, pending: Pending):
    """
    按既定顺序把 pending 应用到 PIL Image 上（不落盘）：
    crop -> rotate -> outer ring fill -> enhance -> pad_a4 -> spots
    """
    try:
        from PIL import Image  # type: ignore

        im = im0
        crop = pending.get("crop_box")
        if crop:
            im = im.crop(tuple(crop))

        angle = float(pending.get("angle") or 0.0)
        if abs(angle) > 1e-6:
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.paste(im, mask=im.getchannel("A"))
            im = bg.convert("RGB").rotate(
                angle,
                resample=Image.BICUBIC,
                expand=False,
                fillcolor=(255, 255, 255),
            )

        bf = pending.get("border_fill")
        if bf:
            thickness = int(bf.get("thickness") or 1)
            color = tuple(bf.get("color") or (255, 255, 255))
            im = apply_outer_ring_fill(im, thickness=thickness, color=color)  # type: ignore[arg-type]

        enh = pending.get("enhance")
        if enh:
            im = apply_enhance(im, enh)

        pad = pending.get("pad_a4")
        if pad:
            bgc = tuple(pad.get("color") or (255, 255, 255))
            im = pad_to_a4(im, bg_color=bgc)  # type: ignore[arg-type]

        spots = pending.get("spots") or []
        if spots:
            im = apply_spot_fills(im, spots)

        return im
    except Exception:
        return im0


def render_preview_qimage(
    *,
    orig_path: str,
    pending: Pending,
    max_side: int,
) -> QImage:
    """从原图+pending 渲染预览 QImage（RGBA）。失败返回空 QImage。"""
    try:
        from PIL import Image  # type: ignore

        if not orig_path or not os.path.exists(orig_path):
            return QImage()
        im0 = _open_pil_image(orig_path)
        im = apply_pending(im0, pending)
        if max_side:
            im.thumbnail((max_side, max_side), resample=Image.BILINEAR)
        im = im.convert("RGBA")
        w, h = im.size
        raw = im.tobytes("raw", "RGBA")
        return QImage(raw, w, h, QImage.Format_RGBA8888).copy()
    except Exception:
        return QImage()


def save_image_like_source(im, out_path: str, out_name: str) -> None:
    """
    保存图片：遵循原逻辑
    - jpg/jpeg：quality=95
    - 其他：按扩展名保存
    """
    from PIL import Image  # type: ignore

    target_name = out_name or out_path
    if (out_path or "").lower().endswith(CryptoService.ENCRYPTED_EXT) or target_name.lower().endswith(CryptoService.ENCRYPTED_EXT):
        data, original_ext = _image_bytes_for_save(im, target_name)
        encrypt_image_bytes(data, out_path, original_ext)
        return

    _stem, ext = os.path.splitext(_plain_image_name(target_name))
    ext_l = ext.lower()
    try:
        if ext_l in (".jpg", ".jpeg"):
            im.convert("RGB").save(out_path, quality=95)
        else:
            im.save(out_path)
    except Exception:
        im.convert("RGB").save(out_path)


def process_and_save(*, orig_path: str, pending: Pending, out_path: str, out_name: str) -> None:
    """
    从 orig_path 读取原图，应用 pending，并按 out_name 的扩展名保存到 out_path。
    """
    from PIL import Image  # type: ignore

    im0 = _open_pil_image(orig_path)
    im = apply_pending(im0, pending)

    # 覆盖写入安全：当输入与输出是同一路径时，先写临时文件再原子替换
    try:
        same_path = os.path.abspath(str(orig_path)) == os.path.abspath(str(out_path))
    except Exception:
        same_path = False
    if same_path:
        import tempfile

        out_dir = os.path.dirname(out_path) or "."
        _stem, ext = os.path.splitext(out_path)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_retouched_", suffix=(ext or ".tmp"), dir=out_dir)
        os.close(fd)
        try:
            tmp_name = out_name if not (out_path or "").lower().endswith(CryptoService.ENCRYPTED_EXT) else _plain_image_name(out_name)
            save_image_like_source(im, tmp_path, tmp_name)
            os.replace(tmp_path, out_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    else:
        save_image_like_source(im, out_path, out_name)


def legacy_detect_black_border_crop_box_from_path(
    file_path: str,
    *,
    max_side: int = 800,
    black_thresh: int = 30,
    border_ratio: float = 0.96,
    min_content_size: int = 50,
) -> Optional[Tuple[int, int, int, int]]:
    """
    legacy 去黑边：检测裁剪框并返回原图坐标 crop_box=(l,t,r,b)；检测失败返回 None。
    算法与原 inventory_entry.py 的 _on_trim_border_legacy_save_now 基本一致。
    """
    try:
        from PIL import Image  # type: ignore

        if not file_path or not os.path.exists(file_path):
            return None
        im0 = _open_pil_image(file_path)

        im = im0.convert("L")
        w0, h0 = im.size
        if w0 < 2 or h0 < 2:
            return None

        scale = min(1.0, float(max_side) / max(w0, h0))
        im_s = im.resize((max(2, int(w0 * scale)), max(2, int(h0 * scale))), resample=Image.BILINEAR) if scale < 1.0 else im
        w, h = im_s.size

        def row_is_border(y: int) -> bool:
            row = im_s.crop((0, y, w, y + 1))
            hist = row.histogram()
            black = sum(hist[: int(black_thresh) + 1])
            return (black / max(1, w)) >= float(border_ratio)

        def col_is_border(x: int) -> bool:
            col = im_s.crop((x, 0, x + 1, h))
            hist = col.histogram()
            black = sum(hist[: int(black_thresh) + 1])
            return (black / max(1, h)) >= float(border_ratio)

        top = 0
        while top < h and row_is_border(top):
            top += 1
        bottom = h - 1
        while bottom >= 0 and row_is_border(bottom):
            bottom -= 1
        left = 0
        while left < w and col_is_border(left):
            left += 1
        right = w - 1
        while right >= 0 and col_is_border(right):
            right -= 1

        if left >= right or top >= bottom:
            return None

        sx = w0 / w
        sy = h0 / h
        crop_box = (
            int(left * sx),
            int(top * sy),
            int((right + 1) * sx),
            int((bottom + 1) * sy),
        )
        if crop_box[2] - crop_box[0] < int(min_content_size) or crop_box[3] - crop_box[1] < int(min_content_size):
            return None
        return crop_box
    except Exception:
        return None


def legacy_crop_and_save(
    *,
    file_path: str,
    crop_box: Tuple[int, int, int, int],
    out_path: str,
    out_name: str,
) -> None:
    """legacy：从 file_path 裁剪 crop_box 并保存到 out_path。"""
    from PIL import Image  # type: ignore

    im0 = _open_pil_image(file_path)
    im_cropped = im0.crop(crop_box)
    try:
        same_path = os.path.abspath(str(file_path)) == os.path.abspath(str(out_path))
    except Exception:
        same_path = False
    if same_path:
        import tempfile

        out_dir = os.path.dirname(out_path) or "."
        _stem, ext = os.path.splitext(out_path)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_crop_", suffix=(ext or ".tmp"), dir=out_dir)
        os.close(fd)
        try:
            tmp_name = out_name if not (out_path or "").lower().endswith(CryptoService.ENCRYPTED_EXT) else _plain_image_name(out_name)
            save_image_like_source(im_cropped, tmp_path, tmp_name)
            os.replace(tmp_path, out_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    else:
        save_image_like_source(im_cropped, out_path, out_name)


def legacy_rotate_with_white_bg_and_save(
    *,
    file_path: str,
    angle: float,
    out_path: str,
    out_name: str,
    jpeg_quality: int = 95,
) -> None:
    """legacy：按 angle 旋转（白底、无 alpha），并保存到 out_path。"""
    from PIL import Image  # type: ignore

    im0 = _open_pil_image(file_path)

    # 先白底合成，确保没有 alpha（与原逻辑一致）
    try:
        if ("A" in im0.getbands()) or ("transparency" in getattr(im0, "info", {})):
            base = Image.new("RGB", im0.size, (255, 255, 255))
            rgba = im0.convert("RGBA")
            base.paste(rgba, mask=rgba.getchannel("A"))
            im_rgb = base
        else:
            im_rgb = im0.convert("RGB")
    except Exception:
        im_rgb = im0.convert("RGB")

    im_rot = im_rgb.rotate(
        float(angle),
        resample=Image.BICUBIC,
        expand=False,
        fillcolor=(255, 255, 255),
    )

    # 保存：复用通用保存策略（jpg/jpeg quality=95）
    _stem, ext = os.path.splitext(out_name or out_path)
    try:
        same_path = os.path.abspath(str(file_path)) == os.path.abspath(str(out_path))
    except Exception:
        same_path = False
    if same_path:
        import tempfile

        out_dir = os.path.dirname(out_path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_rot_", suffix=(ext or ".tmp"), dir=out_dir)
        os.close(fd)
        try:
            tmp_name = out_name if not (out_path or "").lower().endswith(CryptoService.ENCRYPTED_EXT) else _plain_image_name(out_name)
            save_image_like_source(im_rot, tmp_path, tmp_name)
            os.replace(tmp_path, out_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    else:
        save_image_like_source(im_rot, out_path, out_name)



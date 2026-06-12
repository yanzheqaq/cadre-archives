from __future__ import annotations

import os
import re
import shutil
import json
from typing import Any, Dict, List, Optional, Tuple

from xml.etree import ElementTree as ET

from ..repo.inventory_entry_repo import (
    get_entry_info,
    list_entry_catalog_items_for_export,
    list_entry_item_images,
)
from ..utils.image_loading import resolve_image_path

# 加密服务（必须）
from common.services.crypto_service import get_crypto_service


_INVALID_FS_CHARS = re.compile(r"[\\\\/:*?\"<>|]+")


def _safe_name(s: str, *, fallback: str = "未命名") -> str:
    s = (s or "").strip()
    if not s:
        return fallback
    s = _INVALID_FS_CHARS.sub("_", s)
    s = s.replace("\n", " ").replace("\r", " ").strip()
    # Windows/SMB 等环境对末尾点/空格敏感
    s = s.rstrip(" .")
    return s or fallback


def _custom_field_value(entry: Dict[str, Any], field_name: str) -> str:
    raw = entry.get("custom_fields") or ""
    if not raw:
        return ""
    try:
        fields = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return ""
    if not isinstance(fields, list):
        return ""
    for item in fields:
        if not isinstance(item, dict):
            continue
        if (item.get("field_name") or "").strip() == field_name:
            return str(item.get("field_value") or "").strip()
    return ""


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _copy_file(src: str, dst_dir: str, *, preferred_name: str = "") -> str:
    """
    复制并加密图片文件到目标目录
    
    Args:
        src: 源文件路径
        dst_dir: 目标目录
        preferred_name: 首选文件名
        
    Returns:
        复制后的文件名（加密后扩展名为 .hfenc）
    """
    _ensure_dir(dst_dir)
    base = preferred_name.strip() if preferred_name else os.path.basename(src)
    base = _safe_name(base, fallback="image")
    name, ext = os.path.splitext(base)
    if not ext:
        ext = os.path.splitext(src)[1]
    
    # 强制加密，添加加密扩展名
    crypto = get_crypto_service()
    final_ext = ext + crypto.ENCRYPTED_EXT
    
    dst = os.path.join(dst_dir, f"{name}{final_ext}")
    i = 1
    while os.path.exists(dst):
        dst = os.path.join(dst_dir, f"{name}_{i}{final_ext}")
        i += 1
    
    # 加密复制
    crypto.encrypt_file(src, dst)
    
    return os.path.basename(dst)


def _pick_images_for_export(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    返回 (original_images, hd_images)
    - original_images：尽量选 original；若没有 original 但有 retouched，则退化为 retouched
    - hd_images：优先选 retouched（按 original_id 对应），若没有则用 original 占位
    """
    originals: Dict[int, Dict[str, Any]] = {}
    retouched_by_orig: Dict[int, Dict[str, Any]] = {}
    standalone_retouched: List[Dict[str, Any]] = []

    for r in rows:
        try:
            rid = int(r.get("id"))
        except Exception:
            continue
        typ = (r.get("image_type") or "").strip()
        oid = r.get("original_id")
        if typ == "original" and not oid:
            originals[rid] = r
        elif typ == "retouched" and oid:
            try:
                retouched_by_orig[int(oid)] = r
            except Exception:
                standalone_retouched.append(r)
        elif typ == "retouched":
            standalone_retouched.append(r)

    original_list: List[Dict[str, Any]] = []
    hd_list: List[Dict[str, Any]] = []

    # 以 original 为主键配对
    for orig_id, orig in originals.items():
        original_list.append(orig)
        hd_list.append(retouched_by_orig.get(orig_id) or orig)

    # 没有 original 但存在 retouched 的旧数据
    for r in standalone_retouched:
        original_list.append(r)
        hd_list.append(r)

    # 排序：沿用 sort_order / id
    def k(x: Dict[str, Any]) -> Tuple[int, int]:
        try:
            so = int(x.get("sort_order") or 0)
        except Exception:
            so = 0
        try:
            rid = int(x.get("id") or 0)
        except Exception:
            rid = 0
        return (so, rid)

    original_list.sort(key=k)
    hd_list.sort(key=k)
    return original_list, hd_list


def export_person_package(*, entry_id: int, export_root_dir: str) -> str:
    """
    导出人员包（图片自动 AES 加密）
    
    Args:
        entry_id: 人员 ID
        export_root_dir: 导出根目录
    
    导出结构：
      <export_root_dir>/
        <姓名（身份证）>/
          人员信息.xml          (不加密)
          图片/
            原图/<序号+名称>/*.hfenc    (AES 加密)
            高清图/<序号+名称>/*.hfenc  (AES 加密)
            
    图片文件使用 AES-256-CBC 加密，扩展名为 .hfenc
    加密后的图片只能在本客户端中查看。
    
    Returns:
        导出目录绝对路径
    """
    entry = get_entry_info(entry_id=int(entry_id))
    if not entry:
        raise RuntimeError("找不到该人员（Entry）")

    name = _safe_name(entry.get("name") or "人员", fallback="人员")
    id_card = (entry.get("id_card") or "").strip()
    folder_name = _safe_name(f"{name}（{id_card}）", fallback=f"{name}（{id_card}）")

    root_dir = os.path.abspath(export_root_dir)
    out_dir = os.path.join(root_dir, folder_name)
    _ensure_dir(out_dir)

    xml_path = os.path.join(out_dir, "人员信息.xml")
    img_root = os.path.join(out_dir, "图片")
    img_orig_root = os.path.join(img_root, "原图")
    img_hd_root = os.path.join(img_root, "高清图")
    _ensure_dir(img_orig_root)
    _ensure_dir(img_hd_root)

    # 目录项 + 图片拷贝清单，用于写入 XML
    catalog_items = list_entry_catalog_items_for_export(entry_id=int(entry_id))
    exported_nodes: List[Dict[str, Any]] = []

    for node in catalog_items:
        ec_id = int(node["entry_catalog_item_id"])
        serial = (node.get("serial") or "").strip()
        title = (node.get("name") or "").strip()
        # 文件夹名：序号+名称（保持与目录树一致）
        folder = _safe_name(f"{serial}{title}", fallback=f"{serial or ''}{title or ''}" or f"目录_{ec_id}")

        rows = list_entry_item_images(entry_catalog_item_id=ec_id)
        originals, hds = _pick_images_for_export(rows)

        orig_files: List[str] = []
        hd_files: List[str] = []

        orig_src = []
        for r in originals:
            fp = resolve_image_path(
                r.get("file_path") or "",
                entry_id=r.get("entry_id"),
                template_item_id=r.get("template_item_id"),
                file_name=r.get("file_name") or "",
            )
            if fp and os.path.exists(fp):
                orig_src.append((fp, (r.get("file_name") or os.path.basename(fp))))

        hd_src = []
        for r in hds:
            fp = resolve_image_path(
                r.get("file_path") or "",
                entry_id=r.get("entry_id"),
                template_item_id=r.get("template_item_id"),
                file_name=r.get("file_name") or "",
            )
            if fp and os.path.exists(fp):
                hd_src.append((fp, (r.get("file_name") or os.path.basename(fp))))

        # 所有目录项都创建子文件夹（即使没有图片）
        orig_dir = os.path.join(img_orig_root, folder)
        hd_dir = os.path.join(img_hd_root, folder)
        _ensure_dir(orig_dir)
        _ensure_dir(hd_dir)

        # 原图：尽量选 original（自动加密）
        for fp, fn in orig_src:
            orig_files.append(_copy_file(fp, orig_dir, preferred_name=fn))

        # 高清图：优先 retouched；若没有则用 original 占位（自动加密）
        for fp, fn in hd_src:
            hd_files.append(_copy_file(fp, hd_dir, preferred_name=fn))

        exported_nodes.append(
            {
                "entry_catalog_item_id": ec_id,
                "template_item_id": int(node.get("template_item_id") or 0),
                "tpl_parent_id": node.get("tpl_parent_id"),
                "tpl_sort_order": node.get("tpl_sort_order"),
                "serial": serial,
                "name": title,
                "year": node.get("year"),
                "month": node.get("month"),
                "day": node.get("day"),
                "pages": node.get("pages"),
                "remark": node.get("remark") or "",
                "attachment_path": node.get("attachment_path") or "",
                "export_folder": folder,
                "original_files": orig_files,
                "hd_files": hd_files,
            }
        )

    # === 写 XML（不加密） ===
    root = ET.Element("PersonPackage")
    meta = ET.SubElement(root, "Person")
    for k in [
        "id",
        "name",
        "id_card",
        "ethnicity",
        "native_place",
        "birth_date",
        "emp_no",
        "role_title",
        "phone",
        "status",
        "org_unit_id",
        "org_unit_name",
        "org_path",
        "template_id",
        "created_at",
        "updated_at",
    ]:
        if k == "ethnicity":
            value = _custom_field_value(entry, "民族")
        elif k == "native_place":
            value = _custom_field_value(entry, "籍贯")
        elif k == "birth_date":
            value = _custom_field_value(entry, "出生日期")
        else:
            value = entry.get(k)
        ET.SubElement(meta, k).text = str(value or "")

    cat = ET.SubElement(root, "CatalogItems")
    for n in exported_nodes:
        it = ET.SubElement(cat, "Item")
        for k in [
            "entry_catalog_item_id",
            "template_item_id",
            "tpl_parent_id",
            "tpl_sort_order",
            "serial",
            "name",
            "year",
            "month",
            "day",
            "pages",
            "remark",
            "attachment_path",
            "export_folder",
        ]:
            ET.SubElement(it, k).text = str(n.get(k) or "")

        imgs = ET.SubElement(it, "Images")
        origs = ET.SubElement(imgs, "Original")
        for fn in n.get("original_files") or []:
            ET.SubElement(origs, "File").text = fn
        hds = ET.SubElement(imgs, "HD")
        for fn in n.get("hd_files") or []:
            ET.SubElement(hds, "File").text = fn

    tree = ET.ElementTree(root)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return out_dir



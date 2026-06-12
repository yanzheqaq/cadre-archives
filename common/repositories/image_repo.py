# -*- coding: utf-8 -*-
"""
图片数据仓库
"""

import os
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from common.db import get_session, EntryItemImage, EntryCatalogItem
from .base_repo import BaseRepository


class ImageRepository(BaseRepository[EntryItemImage]):
    """图片数据仓库"""
    
    model = EntryItemImage
    
    def count_entry_images(self, entry_id: int) -> int:
        """统计条目的图片数量"""
        with get_session() as session:
            catalog_item_ids = [
                row[0] for row in 
                session.query(EntryCatalogItem.id).filter(EntryCatalogItem.entry_id == int(entry_id)).all()
            ]
            if not catalog_item_ids:
                return 0
            count = (
                session.query(EntryItemImage)
                .filter(
                    EntryItemImage.entry_catalog_item_id.in_(catalog_item_ids),
                    EntryItemImage.image_type == "original"
                )
                .count()
            )
            return count

    def count_entries_images(self, entry_ids: List[int]) -> Dict[int, int]:
        ids = []
        for raw_id in entry_ids or []:
            try:
                entry_id = int(raw_id)
            except Exception:
                continue
            if entry_id > 0 and entry_id not in ids:
                ids.append(entry_id)
        if not ids:
            return {}
        with get_session() as session:
            rows = (
                session.query(EntryCatalogItem.entry_id, func.count(EntryItemImage.id))
                .join(EntryItemImage, EntryItemImage.entry_catalog_item_id == EntryCatalogItem.id)
                .filter(
                    EntryCatalogItem.entry_id.in_(ids),
                    EntryItemImage.image_type == "original",
                )
                .group_by(EntryCatalogItem.entry_id)
                .all()
            )
            result = {entry_id: 0 for entry_id in ids}
            for entry_id, count in rows:
                result[int(entry_id)] = int(count or 0)
            return result
    
    def list_images(self, entry_catalog_item_id: int) -> List[Dict[str, Any]]:
        """列出目录项的所有图片"""
        with get_session() as session:
            rows = (
                session.query(EntryItemImage, EntryCatalogItem.entry_id, EntryCatalogItem.template_item_id)
                .join(EntryCatalogItem, EntryCatalogItem.id == EntryItemImage.entry_catalog_item_id)
                .filter(EntryItemImage.entry_catalog_item_id == entry_catalog_item_id)
                .order_by(EntryItemImage.sort_order, EntryItemImage.id)
                .all()
            )
            return [
                {
                    "id": img.id,
                    "entry_catalog_item_id": img.entry_catalog_item_id,
                    "entry_id": int(entry_id) if entry_id is not None else None,
                    "template_item_id": int(template_item_id) if template_item_id is not None else None,
                    "image_type": img.image_type or "",
                    "original_id": img.original_id,
                    "file_path": img.file_path or "",
                    "file_name": img.file_name or "",
                    "file_size": img.file_size,
                    "mime_type": img.mime_type or "",
                    "sort_order": img.sort_order,
                }
                for img, entry_id, template_item_id in rows
            ]
    
    def get_next_sort_order(self, entry_catalog_item_id: int) -> int:
        """获取下一个排序值"""
        with get_session() as session:
            max_sort = (
                session.query(EntryItemImage.sort_order)
                .filter(EntryItemImage.entry_catalog_item_id == entry_catalog_item_id)
                .order_by(EntryItemImage.sort_order.desc())
                .first()
            )
            return int((max_sort[0] if max_sort else 0) + 1)
    
    def upsert_original_images(
        self,
        entry_catalog_item_id: int,
        files: List[Dict[str, Any]]
    ) -> None:
        """新增或更新原始图片"""
        with get_session() as session:
            for f in files:
                dest_path = f.get("file_path") or ""
                file_name = f.get("file_name") or os.path.basename(dest_path)
                mime = f.get("mime_type") or ""
                size = f.get("file_size")
                sort_order = f.get("sort_order")
                existing = (
                    session.query(EntryItemImage)
                    .filter(
                        EntryItemImage.entry_catalog_item_id == entry_catalog_item_id,
                        EntryItemImage.file_name == file_name,
                    )
                    .first()
                )
                if existing:
                    existing.file_path = dest_path
                    existing.file_size = size
                    existing.mime_type = mime or ""
                    existing.image_type = "original"
                    if sort_order is not None:
                        existing.sort_order = sort_order
                else:
                    img = EntryItemImage(
                        entry_catalog_item_id=entry_catalog_item_id,
                        image_type="original",
                        file_path=dest_path,
                        file_name=file_name,
                        file_size=size,
                        mime_type=mime or "",
                        sort_order=sort_order,
                    )
                    session.add(img)
            session.commit()
    
    def delete_image(self, image_id: int) -> None:
        """删除图片"""
        with get_session() as session:
            # 先清除其他图片对该图片的 original_id 引用
            session.query(EntryItemImage).filter(
                EntryItemImage.original_id == image_id
            ).update({EntryItemImage.original_id: None}, synchronize_session=False)
            session.query(EntryItemImage).filter(EntryItemImage.id == image_id).delete()
            session.commit()
    
    def set_cover(self, entry_catalog_item_id: int, image_id: int) -> None:
        """设置封面图片"""
        with get_session() as session:
            session.query(EntryItemImage).filter(
                EntryItemImage.entry_catalog_item_id == entry_catalog_item_id
            ).update({EntryItemImage.sort_order: 1})
            session.query(EntryItemImage).filter(EntryItemImage.id == image_id).update(
                {EntryItemImage.sort_order: 0}
            )
            session.commit()
    
    def swap_sort_order(self, image_id_a: int, image_id_b: int) -> bool:
        """交换两张图片的排序"""
        with get_session() as session:
            img_a = session.query(EntryItemImage).filter(EntryItemImage.id == image_id_a).first()
            img_b = session.query(EntryItemImage).filter(EntryItemImage.id == image_id_b).first()
            if not img_a or not img_b:
                return False
            sort_a = img_a.sort_order
            sort_b = img_b.sort_order
            img_a.sort_order = sort_b
            img_b.sort_order = sort_a
            session.commit()
            return True
    
    def resolve_original_info(self, image_id: int, fallback_path: str = "") -> Optional[Dict[str, Any]]:
        """解析原始图片信息"""
        with get_session() as session:
            cur = session.query(EntryItemImage).filter(EntryItemImage.id == image_id).first()
            if not cur:
                return None
            orig_id = cur.original_id or cur.id
            orig = session.query(EntryItemImage).filter(EntryItemImage.id == orig_id).first() or cur
            orig_path = orig.file_path or ""
            if (not orig_path) and fallback_path:
                orig_path = fallback_path
            return {
                "orig_id": int(orig_id),
                "orig_file_path": orig_path,
                "orig_entry_catalog_item_id": orig.entry_catalog_item_id,
                "orig_sort_order": orig.sort_order,
                "cur_id": cur.id,
                "cur_file_path": cur.file_path or "",
            }


# 单例实例
image_repo = ImageRepository()


# 向后兼容的函数接口
def count_entry_total_images(*, entry_id: int) -> int:
    return image_repo.count_entry_images(entry_id)

def count_entries_total_images(entry_ids: List[int]) -> Dict[int, int]:
    return image_repo.count_entries_images(entry_ids)

def list_entry_item_images(*, entry_catalog_item_id: int) -> List[Dict[str, Any]]:
    return image_repo.list_images(entry_catalog_item_id)

def get_next_image_sort_base(*, entry_catalog_item_id: int) -> int:
    return image_repo.get_next_sort_order(entry_catalog_item_id)

def upsert_original_images(*, entry_catalog_item_id: int, files: List[Dict[str, Any]]) -> None:
    return image_repo.upsert_original_images(entry_catalog_item_id, files)

def delete_entry_item_image(*, image_id: int) -> None:
    return image_repo.delete_image(image_id)

def set_cover_image(*, entry_catalog_item_id: int, image_id: int) -> None:
    return image_repo.set_cover(entry_catalog_item_id, image_id)

def swap_image_sort_order(*, image_id_a: int, image_id_b: int) -> bool:
    return image_repo.swap_sort_order(image_id_a, image_id_b)

def resolve_original_image_info(*, image_id: int, fallback_path: str = "") -> Optional[Dict[str, Any]]:
    return image_repo.resolve_original_info(image_id, fallback_path)

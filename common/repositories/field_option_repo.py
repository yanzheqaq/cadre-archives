# -*- coding: utf-8 -*-
"""
字段下拉选项（数据字典）数据仓库
"""

from typing import Any, Dict, List, Optional

from common.db import get_session, FieldOption
from .base_repo import BaseRepository


class FieldOptionRepository(BaseRepository[FieldOption]):
    """字段下拉选项仓库"""

    model = FieldOption

    def list_options(self, field_name: str) -> List[str]:
        """返回指定字段的候选值列表（按 sort_order 排序）"""
        with get_session() as session:
            rows = (
                session.query(FieldOption)
                .filter(FieldOption.field_name == field_name)
                .order_by(FieldOption.sort_order, FieldOption.id)
                .all()
            )
            return [r.option_value for r in rows]

    def list_options_full(self, field_name: str) -> List[Dict[str, Any]]:
        """返回指定字段的候选值完整信息"""
        with get_session() as session:
            rows = (
                session.query(FieldOption)
                .filter(FieldOption.field_name == field_name)
                .order_by(FieldOption.sort_order, FieldOption.id)
                .all()
            )
            return [
                {
                    "id": int(r.id),
                    "field_name": r.field_name,
                    "option_value": r.option_value,
                    "sort_order": r.sort_order or 0,
                }
                for r in rows
            ]

    def add_option(self, field_name: str, option_value: str, sort_order: int = 0) -> Optional[int]:
        """新增一个候选值，返回新记录 ID"""
        with get_session() as session:
            # 检查是否已存在
            existing = (
                session.query(FieldOption)
                .filter(
                    FieldOption.field_name == field_name,
                    FieldOption.option_value == option_value,
                )
                .first()
            )
            if existing:
                return int(existing.id)
            obj = FieldOption(
                field_name=field_name,
                option_value=option_value,
                sort_order=sort_order,
            )
            session.add(obj)
            session.commit()
            return int(obj.id)

    def delete_option(self, option_id: int) -> bool:
        """删除一个候选值"""
        with get_session() as session:
            result = (
                session.query(FieldOption)
                .filter(FieldOption.id == int(option_id))
                .delete()
            )
            session.commit()
            return result > 0

    def reorder_options(self, field_name: str, ordered_ids: List[int]) -> None:
        """按给定 ID 顺序重新排序"""
        with get_session() as session:
            for idx, opt_id in enumerate(ordered_ids):
                session.query(FieldOption).filter(
                    FieldOption.id == int(opt_id),
                    FieldOption.field_name == field_name,
                ).update({FieldOption.sort_order: idx + 1})
            session.commit()

    def list_field_names(self) -> List[str]:
        """返回所有已配置选项的字段名"""
        with get_session() as session:
            rows = (
                session.query(FieldOption.field_name)
                .distinct()
                .order_by(FieldOption.field_name)
                .all()
            )
            return [r[0] for r in rows]


# 单例
field_option_repo = FieldOptionRepository()


# 便捷函数接口
def list_field_options(field_name: str) -> List[str]:
    """返回指定字段的候选值列表"""
    return field_option_repo.list_options(field_name)


def list_field_options_full(field_name: str) -> List[Dict[str, Any]]:
    """返回指定字段的候选值完整信息"""
    return field_option_repo.list_options_full(field_name)


def add_field_option(field_name: str, option_value: str, sort_order: int = 0) -> Optional[int]:
    """新增候选值"""
    return field_option_repo.add_option(field_name, option_value, sort_order)


def delete_field_option(option_id: int) -> bool:
    """删除候选值"""
    return field_option_repo.delete_option(option_id)

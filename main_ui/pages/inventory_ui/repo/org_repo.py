# -*- coding: utf-8 -*-
"""
向后兼容模块
请使用 common.repositories.org_repo 代替
"""

# 从新模块导入，保持向后兼容
from common.repositories.org_repo import (
    org_repo,
    list_root_org_units,
    list_all_org_units,
    create_org_unit,
    update_org_unit,
    count_entries_in_org_subtree,
    count_entries_grouped_by_org,
    delete_org_unit_subtree,
    build_org_tree_for_root,
)

__all__ = [
    'org_repo',
    'list_root_org_units',
    'list_all_org_units',
    'create_org_unit',
    'update_org_unit',
    'count_entries_in_org_subtree',
    'count_entries_grouped_by_org',
    'delete_org_unit_subtree',
    'build_org_tree_for_root',
]

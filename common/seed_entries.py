"""
向 entries 表写入一些示例数据，便于目录录入联调。

使用方式：
    python -m common.seed_entries
或：
    python common/seed_entries.py
依赖：
    已配置好 DATABASE_URL，且已存在对应的模板（默认使用 template_id=1）。
"""
import os
import sys
from typing import List, Dict, Any

# 允许 python common/seed_entries.py 直接运行
if __package__ is None:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(CURRENT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)
    from common.db.session import get_session  # type: ignore
    from common.db.models import Entry  # type: ignore
else:
    from .db.session import get_session
    from .db.models import Entry


# 示例数据（可按需修改）
SEED_ENTRIES: List[Dict[str, Any]] = [
    {
        "name": "王小明",
        "emp_no": "EMP-1001",
        "role_title": "管理员",
        "phone": "13800000001",
        "status": "在岗",
        "org_path": "国家图书馆/总馆",
        "template_id": 1,
        "owner_id": 1,
    },
    {
        "name": "李主任",
        "emp_no": "EMP-1002",
        "role_title": "东馆负责人",
        "phone": "13800000002",
        "status": "在岗",
        "org_path": "国家图书馆/东馆",
        "template_id": 1,
        "owner_id": 1,
    },
    {
        "name": "周老师",
        "emp_no": "EMP-1003",
        "role_title": "少儿部",
        "phone": "13800000003",
        "status": "休假",
        "org_path": "国家图书馆/东馆/少儿部",
        "template_id": 1,
        "owner_id": 1,
    },
]


def seed_entries(entries: List[Dict[str, Any]] = SEED_ENTRIES):
    with get_session() as session:
        for data in entries:
            emp_no = data.get("emp_no")
            tpl_id = data.get("template_id", 1)
            exists = (
                session.query(Entry)
                .filter(Entry.emp_no == emp_no, Entry.template_id == tpl_id)
                .first()
            )
            if exists:
                # 更新基础信息
                exists.name = data.get("name", exists.name)
                exists.role_title = data.get("role_title", exists.role_title)
                exists.phone = data.get("phone", exists.phone)
                exists.status = data.get("status", exists.status)
                exists.org_path = data.get("org_path", exists.org_path)
            else:
                session.add(Entry(**data))
        session.commit()
        print(f"已写入/更新 {len(entries)} 条 Entry 数据。")


if __name__ == "__main__":
    seed_entries()


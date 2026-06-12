"""
将现有目录模板写入数据库 (SQLAlchemy)。

使用方式：
    # 环境变量可覆盖 DATABASE_URL
    # 默认: mysql+pymysql://root:1234@127.0.0.1:3306/pfms?charset=utf8mb4
    python -m common.seed_templates
    # 若直接 python common/seed_templates.py，需要下面的 sys.path 修正生效
"""
import os
import sys
from typing import List, Dict, Any

# 允许脚本以 "python common/seed_templates.py" 直接运行
if __package__ is None:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(CURRENT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)
    from common.db.session import get_session  # type: ignore
    from common.db.models import CatalogTemplate, CatalogTemplateItem, User  # type: ignore
    from common.config.app_config import AppConfig  # type: ignore
else:
    from .db.session import get_session
    from .db.models import CatalogTemplate, CatalogTemplateItem, User
    from .config.app_config import AppConfig


# 默认模板数据（与现有界面保持一致）
TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "干部档案目录",
        "description": "干部档案目录模板",
        "items": [
            {"serial": "一", 
            "name": "履历材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {"serial": "二", 
            "name": "自传材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {"serial": "三", 
            "name": "考察、鉴定、考核材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {
                "serial": "四",
                "name": "学历学位、职称、学术、培训等材料",
                "children": [
                    {"serial": "4-1", 
                    "name": "学位学位材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "4-2", "name": "评聘专业技术职务材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "4-3", "name": "反映科研学术水平材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "4-4", "name": "培训材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                ],
            },
            {"serial": "五", 
            "name": "政审、审计、审核材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {"serial": "六", 
            "name": "党团材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {"serial": "七", 
            "name": "奖励材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {"serial": "八", 
            "name": "处理处分材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
            {
                "serial": "九",
                "name": "工资、任免、出国、会议等材料",
                "children": [
                    {"serial": "9-1", 
                    "name": "工资材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "9-2", 
                    "name": "任免材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "9-3", 
                    "name": "出国(境)材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                    {"serial": "9-4", 
                    "name": "会议代表材料",
                    "children": [
                        {"serial": "", "name": ""},
                        {"serial": "", "name": ""}
                    ]
                    },
                ],
            },
            {"serial": "十", 
            "name": "其他材料",
            "children": [
                {"serial": "", "name": ""},
                {"serial": "", "name": ""}
            ]
            },
        ],
    },
]


def _upsert_template(session, tpl_data: Dict[str, Any], owner_id: int = 1, visibility: str = "shared"):
    tpl = session.query(CatalogTemplate).filter(CatalogTemplate.name == tpl_data["name"]).first()
    if not tpl:
        tpl = CatalogTemplate(
            name=tpl_data["name"],
            description=tpl_data.get("description", ""),
            owner_id=owner_id,
            visibility=visibility,
            is_default=0,
        )
        session.add(tpl)
        session.flush()
    else:
        tpl.description = tpl_data.get("description", tpl.description)
        tpl.visibility = visibility
        session.flush()

    existing_count = session.query(CatalogTemplateItem).filter(CatalogTemplateItem.template_id == tpl.id).count()
    if existing_count > 0:
        return tpl

    def add_items(items, parent_id=None, sort_start=1):
        sort_no = sort_start
        for node in items:
            item = CatalogTemplateItem(
                template_id=tpl.id,
                parent_id=parent_id,
                serial=node.get("serial"),
                name=node.get("name"),
                year=node.get("year"),
                month=node.get("month"),
                day=node.get("day"),
                pages=node.get("pages"),
                remark=node.get("remark"),
                sort_order=sort_no,
            )
            session.add(item)
            session.flush()
            sort_no += 1
            children = node.get("children", [])
            if children:
                add_items(children, parent_id=item.id, sort_start=1)
    add_items(tpl_data.get("items", []), parent_id=None, sort_start=1)
    return tpl


def seed_templates():
    with get_session() as session:
        owner = session.query(User).filter(User.username == AppConfig.DEFAULT_ADMIN_USER).first()
        if owner is None:
            owner = session.query(User).order_by(User.id.asc()).first()
        if owner is None:
            owner = User(
                username=AppConfig.DEFAULT_ADMIN_USER,
                password_hash=AppConfig.DEFAULT_ADMIN_PASS,
                display_name="系统管理员",
                theme="light",
            )
            session.add(owner)
            session.flush()

        for tpl_data in TEMPLATES:
            _upsert_template(session, tpl_data, owner_id=int(owner.id), visibility="shared")
        session.commit()
        print("模板写入完成。")


if __name__ == "__main__":
    seed_templates()


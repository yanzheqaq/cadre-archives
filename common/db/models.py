# -*- coding: utf-8 -*-
"""
SQLAlchemy 模型定义
"""

from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .engine import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(128))
    theme = Column(String(10), default="light")
    remember_pwd = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CatalogTemplate(Base):
    """目录模板"""
    __tablename__ = "catalog_templates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    visibility = Column(Enum("private", "shared"), default="private", nullable=False)
    is_default = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    items = relationship(
        "CatalogTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class CatalogTemplateItem(Base):
    """目录模板项"""
    __tablename__ = "catalog_template_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_id = Column(BigInteger, ForeignKey("catalog_templates.id"), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("catalog_template_items.id"))
    serial = Column(String(64))
    name = Column(String(255))
    year = Column(String(10))
    month = Column(String(10))
    day = Column(String(10))
    pages = Column(Integer)
    remark = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    template = relationship("CatalogTemplate", back_populates="items")
    parent = relationship(
        "CatalogTemplateItem",
        back_populates="children",
        remote_side=[id],
    )
    children = relationship(
        "CatalogTemplateItem",
        back_populates="parent",
        cascade="all, delete-orphan",
        single_parent=True,
    )


class Entry(Base):
    """档案条目（人员/案卷）"""
    __tablename__ = "entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    template_id = Column(BigInteger, ForeignKey("catalog_templates.id"), nullable=False)
    name = Column(String(128))
    emp_no = Column(String(64))
    role_title = Column(String(128))
    phone = Column(String(64))
    status = Column(String(64))
    id_card = Column(String(32))
    custom_fields = Column(Text)  # JSON: [{"field_name": "...", "field_value": "..."}, ...]
    org_path = Column(String(255))
    org_unit_id = Column(BigInteger, ForeignKey("org_units.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    org_unit = relationship("OrgUnit")


class EntryCatalogItem(Base):
    """档案目录项

    数据完整性约束（重要）
    ----------------------
    业务上 ``(entry_id, template_item_id)`` 必须唯一：每个档案对每个模板槽位
    只应有一条 EC 行。但历史 schema **没有**给这两列加 ``UNIQUE`` 约束，
    并发 upsert / WAL 回放 / 多客户端写入有概率产生多条同槽位 EC 行，
    UI 加载时若空行排在数据行后面，会让用户的数据"看不见"——这就是
    用户反馈"每类第一条都没了"的潜在成因之一。

    应用层已经在以下入口做了双重防护：

    - ``main_ui.pages.inventory_ui.repo.inventory_entry_repo._pick_most_complete_ec``：
      所有"按 ``(entry_id, template_item_id)`` 找已有 EC 行"的查询统一走它，
      重复时按完整度评分挑选，**绝不**让空行替身被选中。
    - ``merge_duplicate_entry_catalog_items``：录入对话框第一次加载时自愈合并，
      把同槽位多条行合并成一条（字段补空、图片重定向、删除多余行）。

    长期目标 / 部署注意
    -------------------
    - 新建数据库 / 全新部署后，建议运行一次合并函数后，**手动**为旧库加上
      ``UNIQUE INDEX uq_entry_tpl ON entry_catalog_items (entry_id, template_item_id)``，
      从 schema 层根除重复（迁移前必须先合并干净，否则 ALTER 会失败）。
    - **新版本表结构 / ORM 层要不要直接声明 ``UniqueConstraint``** 留待后续讨论：
      现在直接加会让"已存在重复的旧库"无法启动，所以暂留注释提示。
    """
    __tablename__ = "entry_catalog_items"
    # TODO(data-safety): 等存量数据合并完成后，启用下面的唯一约束，
    # 把"每类第一条都没了"的潜在 schema 漏洞从根本上堵死：
    # __table_args__ = (
    #     UniqueConstraint("entry_id", "template_item_id", name="uq_entry_tpl"),
    # )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entry_id = Column(BigInteger, ForeignKey("entries.id"), nullable=False)
    template_item_id = Column(BigInteger, ForeignKey("catalog_template_items.id"), nullable=False)
    serial = Column(String(64))
    name = Column(String(255))
    year = Column(String(10))
    month = Column(String(10))
    day = Column(String(10))
    pages = Column(Integer)
    remark = Column(Text)
    attachment_path = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class EntryItemImage(Base):
    """档案图片"""
    __tablename__ = "entry_item_images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entry_catalog_item_id = Column(BigInteger, ForeignKey("entry_catalog_items.id"), nullable=False)
    image_type = Column(Enum("original", "retouched"), nullable=False)
    file_path = Column(Text, nullable=False)
    file_name = Column(String(255))
    file_size = Column(BigInteger)
    mime_type = Column(String(128))
    checksum = Column(String(128))
    width = Column(Integer)
    height = Column(Integer)
    sort_order = Column(Integer, default=0)
    original_id = Column(BigInteger, ForeignKey("entry_item_images.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class FieldOption(Base):
    """字段下拉选项（数据字典）"""
    __tablename__ = "field_options"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    field_name = Column(String(64), nullable=False)        # 字段标识，如 status / role_title
    option_value = Column(String(255), nullable=False)      # 候选值
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class OrgUnit(Base):
    """机构单位"""
    __tablename__ = "org_units"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_id = Column(BigInteger, ForeignKey("org_units.id"))
    name = Column(String(255), nullable=False)
    code = Column(String(64))
    contact = Column(String(128))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    parent = relationship("OrgUnit", back_populates="children", remote_side=[id])
    children = relationship(
        "OrgUnit",
        back_populates="parent",
        cascade="all, delete-orphan",
        single_parent=True,
    )

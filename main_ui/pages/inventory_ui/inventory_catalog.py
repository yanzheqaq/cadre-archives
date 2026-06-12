import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QButtonGroup,
    QHeaderView, QPushButton, QLabel, QSplitter, QStackedWidget,
    QListWidget, QListWidgetItem, QAbstractItemView, QToolButton,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox, QMenu
)
from PyQt5.QtCore import Qt, QSize, QEvent
from PyQt5.QtGui import QIcon, QFont, QWheelEvent
from functools import partial

from common.config import AppSettings
from main_ui.config_pages import PagesConfig
from .style_inventory import InventoryReceiveStyle
from common.db.session import get_session
from common.db.models import CatalogTemplate, CatalogTemplateItem
from .widgets.org_tree import OrgTreeWidget

ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icons'))


class InventoryCatalogWidget(QWidget):
    """
    馆藏模块 - 目录管理页面
    布局和交互与机构管理一致，但保持独立文件方便定制
    """

    def __init__(self):
        super().__init__()
        self.config_manager = AppSettings()
        self.current_theme = self.config_manager.load_theme_preference()
        # 字体缩放
        self._base_font: QFont = self.font()
        self._font_min = 9
        self._font_max = 20
        self._tree_font_size = self._base_font.pointSizeF()
        self._list_font_size = self._base_font.pointSizeF()
        self.templates = []  # [{'id':..., 'name':...}]
        self.current_tpl_id = None
        self._suppress_item_changed = False
        self.initUI()
        self.apply_theme()

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 顶部左右选项卡
        tool_bar = QHBoxLayout()
        tool_bar.setContentsMargins(0, 0, 0, 0)

        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)

        self.btn_all_batches = QPushButton("所有批次")
        self.btn_all_batches.setCursor(Qt.PointingHandCursor)
        self.btn_all_batches.setCheckable(True)
        self.btn_all_batches.setChecked(True)
        self.btn_all_batches.setObjectName("tab_btn")
        self.tab_group.addButton(self.btn_all_batches, 0)

        self.btn_received_batches = QPushButton("已接收批次")
        self.btn_received_batches.setCursor(Qt.PointingHandCursor)
        self.btn_received_batches.setCheckable(True)
        self.btn_received_batches.setObjectName("tab_btn")
        self.tab_group.addButton(self.btn_received_batches, 1)

        self.tab_group.buttonClicked[int].connect(self.on_tab_changed)

        tool_bar.addWidget(self.btn_all_batches)
        tool_bar.addWidget(self.btn_received_batches)
        tool_bar.addStretch()

        self.right_tab_group = QButtonGroup(self)
        self.right_tab_group.setExclusive(True)

        self.btn_tab_detail = QPushButton("批次详情")
        self.btn_tab_detail.setObjectName("tab_btn")
        self.btn_tab_detail.setCheckable(True)
        self.btn_tab_detail.setChecked(True)
        self.btn_tab_detail.setCursor(Qt.PointingHandCursor)
        self.right_tab_group.addButton(self.btn_tab_detail, 0)

        self.btn_tab_process = QPushButton("加工情况")
        self.btn_tab_process.setObjectName("tab_btn")
        self.btn_tab_process.setCheckable(True)
        self.btn_tab_process.setCursor(Qt.PointingHandCursor)
        self.right_tab_group.addButton(self.btn_tab_process, 1)

        # 目录树仅展示，不需要右侧tab切换，禁用连接
        # self.right_tab_group.buttonClicked[int].connect(self.on_right_tab_changed)

        tool_bar.addWidget(self.btn_tab_detail)
        tool_bar.addWidget(self.btn_tab_process)

        main_layout.addLayout(tool_bar)

        # 左右分割
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setObjectName("main_splitter_inventory")

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        func_btn_layout = QHBoxLayout()
        func_btn_layout.setSpacing(PagesConfig.BATCH_FUNC_ICON_SPACING)

        func_btns = [
            ("新增", "add.png", "add"),
            ("删除", "delete.png", "delete"),
            ("排序", "sort.png", "sort"),
            ("退回", "return.png", "return"),
            ("流转", "transfer.png", "transfer"),
        ]

        icon_size = PagesConfig.BATCH_FUNC_ICON_SIZE

        for tooltip, filename, suffix in func_btns:
            btn = QToolButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName(f"func_btn_{suffix}")
            icon_path = os.path.join(ICON_DIR, filename)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(icon_size, icon_size))
            else:
                btn.setText(tooltip[:2])
            btn.setFixedSize(QSize(icon_size + 12, icon_size + 12))
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            func_btn_layout.addWidget(btn)

        func_btn_layout.addStretch()
        left_layout.addLayout(func_btn_layout)

        self.batch_list = QListWidget()
        self.batch_list.setAlternatingRowColors(True)
        self.batch_list.setObjectName("batch_list_inventory")
        # 捕获 Ctrl+滚轮用于左侧列表缩放
        self.batch_list.installEventFilter(self)
        self.batch_list.viewport().installEventFilter(self)

        # 左侧列表显示模板名称（数据库）
        self._load_templates_from_db()
        if self.batch_list.count() > 0:
            self.batch_list.setCurrentRow(0)

        self.batch_list.itemClicked.connect(self.load_cases_for_batch)

        left_layout.addWidget(self.batch_list)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(5)

        self.lbl_case_title = QLabel("📄 目录管理列表")
        self.lbl_case_title.setObjectName("section_title")

        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(0, 0, 0, 0)
        title_bar_layout.setSpacing(PagesConfig.BATCH_FUNC_ICON_SPACING)
        title_bar_layout.addWidget(self.lbl_case_title)
        title_bar_layout.addStretch()

        right_actions = [
            ("批次检测", "Batch_testing.jpg"),
            ("二维码打印", "QR_printing.png")
        ]

        right_icon_size = PagesConfig.BATCH_FUNC_ICON_SIZE

        for tooltip, filename in right_actions:
            btn = QToolButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("right_func_btn")
            icon_path = os.path.join(ICON_DIR, filename)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(right_icon_size, right_icon_size))
            else:
                btn.setText(tooltip[:2])
            btn.setFixedSize(QSize(right_icon_size + 12, right_icon_size + 12))
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            title_bar_layout.addWidget(btn)

        right_layout.addLayout(title_bar_layout)

        self.right_stack = QStackedWidget()

        detail_page = QWidget()
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # 目录操作按钮（代替右键菜单）
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(8)
        btn_add_peer = QPushButton("新增同级")
        btn_add_child = QPushButton("新增子级")
        btn_del = QPushButton("删除节点")
        for btn in (btn_add_peer, btn_add_child, btn_del):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("right_func_btn")
            btn.setFixedHeight(28)
            action_bar.addWidget(btn)
        action_bar.addStretch()
        detail_layout.addLayout(action_bar)

        # 目录树，展示层级关系（与数据库字段对齐：名称/序号/父ID/备注）
        self.org_tree = OrgTreeWidget(theme="dark" if self.current_theme == "dark" else "light", with_grid_lines=True)
        self.org_tree.setColumnCount(7)
        # 编号(serial) | 目录名称(name) | 年 | 月 | 日 | 页数 | 备注
        self.org_tree.setHeaderLabels(["编号", "目录名称", "年", "月", "日", "页数", "备注"])
        self.org_tree.setUniformRowHeights(True)
        # 关闭交替底色，避免主题下出现色块
        self.org_tree.setAlternatingRowColors(False)
        # 调整列宽：序号列自适应内容，其余列拉伸
        header = self.org_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)  # 允许拖拽列宽
        header.setMinimumSectionSize(60)
        # 初始列宽，可根据需要调整，仍可拖拽覆盖
        header.resizeSection(0, 120)  # 编号
        header.resizeSection(1, 220)  # 目录名称
        header.resizeSection(2, 80)   # 年
        header.resizeSection(3, 80)   # 月
        header.resizeSection(4, 80)   # 日
        header.resizeSection(5, 90)   # 页数
        header.resizeSection(6, 180)  # 备注
        self.org_tree.setObjectName("org_tree")
        self.org_tree.installEventFilter(self)  # 捕获滚轮事件以支持 Ctrl 缩放
        # 初始应用字体缩放
        self._apply_tree_font_zoom(self._tree_font_size)
        # 禁用右键菜单，改用上方操作栏
        self.org_tree.setContextMenuPolicy(Qt.NoContextMenu)
        # 捕获滚轮事件以支持 Ctrl 缩放（树和其 viewport 都需要监听）
        self.org_tree.installEventFilter(self)
        self.org_tree.viewport().installEventFilter(self)
        # 操作按钮事件
        btn_add_peer.clicked.connect(self.on_add_peer)
        btn_add_child.clicked.connect(self.on_add_child)
        btn_del.clicked.connect(self.on_delete_node)
        # 编辑变更时实时保存
        self.org_tree.itemChanged.connect(self.on_item_changed)

        detail_layout.addWidget(self.org_tree)

        process_page = QWidget()
        process_layout = QVBoxLayout(process_page)
        process_layout.setContentsMargins(0, 0, 0, 0)
        process_label = QLabel("加工情况数据开发中...")
        process_label.setAlignment(Qt.AlignCenter)
        process_label.setObjectName("section_title")
        process_layout.addWidget(process_label)

        self.right_stack.addWidget(detail_page)
        self.right_stack.addWidget(process_page)

        right_layout.addWidget(self.right_stack)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter)

        self.load_cases_for_batch(self.batch_list.currentItem())
        # 初始字体应用到树
        self._apply_tree_font_zoom(self._tree_font_size)
        # 初始字体应用到左侧列表
        self._apply_list_font_zoom(self._list_font_size)

    def on_tab_changed(self, tab_index):
        self.batch_list.clear()
        if hasattr(self, "org_tree"):
            self.org_tree.clear()
        self.lbl_case_title.setText("📄 目录管理列表")

        # 两个 tab 均展示模板列表
        self._load_templates_from_db()

        if self.batch_list.count() > 0:
            self.batch_list.setCurrentRow(0)
            self.load_cases_for_batch(self.batch_list.currentItem())
        else:
            self.load_cases_for_batch(None)

    def load_cases_for_batch(self, item):
        if not item:
            return

        root_name = item.text()
        self.lbl_case_title.setText(f"📄 目录管理 - {root_name}")

        self.org_tree.clear()
        tpl = next((t for t in self.templates if t["name"] == root_name), None)
        if not tpl:
            return

        # 记录当前模板ID，后续新增/编辑/删除时使用
        self.current_tpl_id = tpl["id"]

        try:
            with get_session() as session:
                rows = (
                    session.query(CatalogTemplateItem)
                    .filter(CatalogTemplateItem.template_id == tpl["id"])
                    .order_by(CatalogTemplateItem.sort_order, CatalogTemplateItem.id)
                    .all()
                )
                # 如需调试可临时打印模板名与条目数：
                # print(f"[catalog] template='{tpl['name']}' items={len(rows)}")
        except Exception as e:
            print(f"[catalog] load template items failed: {e}")
            return

        # 有些库中 parent_id 可能存储为 0（而非 NULL），会导致根节点无法挂载。
        # 统一将 0 归一化为 None 再分组，避免树为空。
        by_parent = {}
        for r in rows:
            parent_key = r.parent_id or None
            by_parent.setdefault(parent_key, []).append(r)

        def build(parent_id, parent_item):
            for r in by_parent.get(parent_id, []):
                item = QTreeWidgetItem(parent_item)
                # 对应表头：编号 | 目录名称 | 年 | 月 | 日 | 页数 | 备注
                item.setText(0, r.serial or "")
                item.setText(1, r.name or "")
                item.setText(2, str(r.year or ""))
                item.setText(3, str(r.month or ""))
                item.setText(4, str(r.day or ""))
                item.setText(5, str(r.pages or ""))
                item.setText(6, r.remark or "")
                # 可编辑，并存储数据库ID
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                item.setData(0, Qt.UserRole, r.id)
                build(r.id, item)

        # 构建树时不触发保存
        self._suppress_item_changed = True
        build(None, self.org_tree.invisibleRootItem())
        self._suppress_item_changed = False
        self.org_tree.expandAll()

    def _load_templates_from_db(self):
        """加载模板列表到左侧列表。"""
        self.batch_list.clear()
        self.templates = []
        try:
            with get_session() as session:
                tpls = session.query(CatalogTemplate).order_by(CatalogTemplate.id).all()
                for t in tpls:
                    self.templates.append({"id": t.id, "name": t.name})
                    self.batch_list.addItem(QListWidgetItem(t.name))
        except Exception as e:
            print(f"[catalog] load templates failed: {e}")

    def _get_orgs_by_root(self, root_name):
        # 默认返回空列表
        return []

    def apply_theme(self):
        if self.current_theme == "light":
            self.setStyleSheet(InventoryReceiveStyle.LIGHT_STYLE)
            self.org_tree.set_theme("light")
        else:
            self.setStyleSheet(InventoryReceiveStyle.DARK_STYLE)
            self.org_tree.set_theme("dark")

    def update_theme(self, theme_name):
        self.current_theme = theme_name
        self.apply_theme()

    # Ctrl + 滚轮调整机构树字体（仅鼠标位于树区域时生效）
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            # 将事件坐标映射到树控件，只有在树区域内才执行缩放
            local_pos = self.org_tree.mapFrom(self, event.pos())
            if self.org_tree.rect().contains(local_pos):
                delta = event.angleDelta().y()
                step = 1 if delta > 0 else -1
                new_size = self._tree_font_size + step
                new_size = max(self._font_min, min(self._font_max, new_size))
                self._tree_font_size = new_size
                self._apply_tree_font_zoom(new_size)
                event.accept()
                return
        super().wheelEvent(event)

    def _apply_tree_font_zoom(self, point_size: float):
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.org_tree.setFont(f)

    def _apply_list_font_zoom(self, point_size: float):
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.batch_list.setFont(f)

    # === 操作栏按钮逻辑 ===
    def _create_blank_item(self):
        item = QTreeWidgetItem(["", "", "", "", "", "", ""])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        return item

    def _create_and_persist_item(self, parent_item):
        """创建空白节点并写入数据库，返回已挂 action 的 QTreeWidgetItem。"""
        if not self.current_tpl_id:
            QMessageBox.warning(self, "提示", "请先选择模板")
            return None
        if parent_item is None:
            parent_item = self.org_tree.invisibleRootItem()
        parent_id = parent_item.data(0, Qt.UserRole) if parent_item != self.org_tree.invisibleRootItem() else None
        sort_order = parent_item.childCount() + 1

        try:
            with get_session() as session:
                obj = CatalogTemplateItem(
                    template_id=self.current_tpl_id,
                    parent_id=parent_id,
                    sort_order=sort_order,
                )
                session.add(obj)
                session.commit()
                new_id = obj.id
        except Exception as e:
            print(f"[catalog] create item failed: {e}")
            return None

        item = self._create_blank_item()
        item.setData(0, Qt.UserRole, new_id)
        parent_item.addChild(item)
        return item

    def on_add_child_for_item(self, parent_item):
        item = self._create_and_persist_item(parent_item or self.org_tree.invisibleRootItem())
        if item:
            (parent_item or self.org_tree.invisibleRootItem()).setExpanded(True)
            self.org_tree.setCurrentItem(item)

    def on_delete_item(self, target_item):
        if target_item is None:
            return
        parent = target_item.parent() or self.org_tree.invisibleRootItem()
        # 收集子树所有 ID，一并删除
        ids = []
        def collect(node):
            item_id = node.data(0, Qt.UserRole)
            if item_id:
                ids.append(item_id)
            for i in range(node.childCount()):
                collect(node.child(i))
        collect(target_item)
        if not ids:
            parent.removeChild(target_item)
            return

        # 先检查是否有 entry_catalog_items 还在引用这些 tpl_item。
        # 如果有，绝不能静默删除——那会导致所有 entry 的对应行一起丢（历史 bug）。
        # 让管理员明确选择：要么先到录入页清掉这些数据，要么级联删（会丢数据）。
        try:
            from common.db.models import EntryCatalogItem
            from common.services.ec_delete_audit import snapshot_and_log_before_delete
            with get_session() as session:
                rows = session.query(CatalogTemplateItem.id, CatalogTemplateItem.parent_id).all()
                children_by_parent = {}
                for row in rows:
                    item_id = int(row.id)
                    parent_id = int(row.parent_id) if row.parent_id is not None else None
                    children_by_parent.setdefault(parent_id, []).append(item_id)
                expanded_ids = []
                seen = set()
                stack = [int(x) for x in ids if x is not None and int(x) > 0]
                while stack:
                    cur = int(stack.pop())
                    if cur in seen:
                        continue
                    seen.add(cur)
                    expanded_ids.append(cur)
                    stack.extend(children_by_parent.get(cur, []))
                ids = expanded_ids
                ref_count = (
                    session.query(EntryCatalogItem)
                    .filter(EntryCatalogItem.template_item_id.in_(ids))
                    .count()
                )
                if ref_count > 0:
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Warning)
                    box.setWindowTitle("无法删除模板项")
                    box.setText(
                        f"这些模板项下还有 {ref_count} 条录入数据。\n"
                        f"直接删除会导致所有档案下对应的数据一起丢失。\n\n"
                        f"请先到录入页把这些数据清理掉，再回来删模板项。"
                    )
                    box.setStandardButtons(QMessageBox.Ok)
                    box.exec_()
                    return

                # 真正执行删除（此时没有 EC 行引用，FK 不会阻止）
                id_set = {int(x) for x in ids if x is not None and int(x) > 0}
                parent_by_id = {
                    int(row.id): int(row.parent_id) if row.parent_id is not None else None
                    for row in rows
                    if int(row.id) in id_set
                }

                def depth(item_id):
                    d = 0
                    cur = int(item_id)
                    visited = set()
                    while cur in parent_by_id:
                        parent_id = parent_by_id.get(cur)
                        if parent_id not in id_set or parent_id in visited or parent_id == cur:
                            break
                        visited.add(cur)
                        cur = int(parent_id)
                        d += 1
                    return d

                for item_id in sorted(id_set, key=lambda x: (depth(x), x), reverse=True):
                    session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id).delete(synchronize_session=False)
                session.commit()
        except Exception as e:
            print(f"[catalog] delete items failed: {e}")
            try:
                QMessageBox.critical(
                    self, "删除失败",
                    f"模板项删除失败：{e}\n\n请截屏联系管理员。",
                )
            except Exception:
                pass
            return

        parent.removeChild(target_item)

    def on_add_peer(self):
        current = self.org_tree.currentItem()
        if current:
            parent = current.parent() or self.org_tree.invisibleRootItem()
        else:
            parent = self.org_tree.invisibleRootItem()
        item = self._create_and_persist_item(parent)
        if item:
            parent.setExpanded(True)
            self.org_tree.setCurrentItem(item)

    def on_add_child(self):
        current = self.org_tree.currentItem() or self.org_tree.invisibleRootItem()
        item = self._create_and_persist_item(current)
        if item:
            current.setExpanded(True)
            self.org_tree.setCurrentItem(item)

    def on_delete_node(self):
        current = self.org_tree.currentItem()
        if not current:
            return
        self.on_delete_item(current)

    def on_item_changed(self, item, column):
        """单元格编辑后实时保存到数据库。"""
        if self._suppress_item_changed:
            return
        if column == 7:  # 操作列不处理
            return
        item_id = item.data(0, Qt.UserRole)
        if not item_id or not self.current_tpl_id:
            return

        field_map = {
            0: ("serial", "str"),
            1: ("name", "str"),
            2: ("year", "int"),
            3: ("month", "int"),
            4: ("day", "int"),
            5: ("pages", "int"),
            6: ("remark", "str"),
        }
        if column not in field_map:
            return

        field, typ = field_map[column]
        raw = item.text(column).strip()
        value = raw
        if typ == "int":
            if raw == "":
                value = None
            else:
                try:
                    value = int(raw)
                except ValueError:
                    return

        try:
            with get_session() as session:
                session.query(CatalogTemplateItem).filter(CatalogTemplateItem.id == item_id).update({field: value})
                session.commit()
        except Exception as e:
            print(f"[catalog] update item failed: {e}")

    def eventFilter(self, obj, event):
        # 若初始化未完成，直接透传
        if not hasattr(self, "org_tree"):
            return super().eventFilter(obj, event)
        # 直接在树及其 viewport 上拦截 Ctrl+滚轮，不做坐标判断
        if obj in (self.org_tree, getattr(self.org_tree, "viewport", lambda: None)()) and event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                delta = event.angleDelta().y()
                step = 1 if delta > 0 else -1
                new_size = self._tree_font_size + step
                new_size = max(self._font_min, min(self._font_max, new_size))
                self._tree_font_size = new_size
                self._apply_tree_font_zoom(new_size)
                event.accept()
                return True
        # 左侧列表及其 viewport 上拦截 Ctrl+滚轮
        if obj in (self.batch_list, getattr(self.batch_list, "viewport", lambda: None)()) and event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                delta = event.angleDelta().y()
                step = 1 if delta > 0 else -1
                new_size = self._list_font_size + step
                new_size = max(self._font_min, min(self._font_max, new_size))
                self._list_font_size = new_size
                self._apply_list_font_zoom(new_size)
                event.accept()
                return True
        return super().eventFilter(obj, event)

class OrgEditDialog(QDialog):
    """目录编辑/新增对话框（简易样例，可后续替换为正式表单）"""

    def __init__(self, parent_name="（顶级）", name="", code="", contact="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("目录信息")
        self.resize(360, 180)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.addRow("上级目录:", QLabel(parent_name))

        self.le_name = QLineEdit(name)
        form.addRow("目录名称:", self.le_name)

        self.le_code = QLineEdit(code)
        form.addRow("目录编码:", self.le_code)

        self.le_contact = QLineEdit(contact)
        form.addRow("联系人:", self.le_contact)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        return {
            "name": self.le_name.text().strip(),
            "code": self.le_code.text().strip(),
            "contact": self.le_contact.text().strip(),
        }



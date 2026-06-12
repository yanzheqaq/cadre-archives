import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QButtonGroup,
    QHeaderView, QPushButton, QLabel, QSplitter, QStackedWidget,
    QListWidget, QListWidgetItem, QAbstractItemView, QToolButton,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox, QMenu,
    QFrame, QGridLayout,
)
from PyQt5.QtCore import Qt, QSize, QEvent, QThreadPool
from PyQt5.QtGui import QIcon, QFont, QWheelEvent

from common.config import AppSettings
from main_ui.config_pages import PagesConfig
from .style_inventory import InventoryReceiveStyle
from .widgets.org_tree import OrgTreeWidget
from .repo.org_repo import (
    build_org_tree_for_root,
    count_entries_in_org_subtree,
    create_org_unit,
    delete_org_unit_subtree,
    list_root_org_units,
    update_org_unit,
)
from .styled_message_box import StyledMessageBox
from .widgets.qt_worker import Worker

ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icons'))


class InventoryReceiveWidget(QWidget):
    """
    馆藏模块 - 接收页面
    布局和交互与增量模块的档案接收一致，但使用独立文件方便后续定制
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
        self._thread_pool = QThreadPool.globalInstance()
        self._root_load_token = 0
        self._tree_load_token = 0
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

        # 机构树仅展示，不需要右侧tab切换，禁用连接
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
            ("流转", "transfer.png", "transfer")
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

            # 预留按钮：机构管理（在 org_tree 创建后再 connect）
            if suffix == "add":
                self.btn_org_add = btn
            elif suffix == "delete":
                self.btn_org_delete = btn

        func_btn_layout.addStretch()
        left_layout.addLayout(func_btn_layout)

        self.batch_list = QListWidget()
        self.batch_list.setAlternatingRowColors(True)
        self.batch_list.setObjectName("batch_list_inventory")
        # 捕获 Ctrl+滚轮用于左侧列表缩放
        self.batch_list.installEventFilter(self)
        self.batch_list.viewport().installEventFilter(self)

        self.batch_list.itemClicked.connect(self.load_cases_for_batch)

        left_layout.addWidget(self.batch_list)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(5)

        self.lbl_case_title = QLabel("📄 机构管理列表")
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

        # 机构树，展示层级关系
        self.org_tree = OrgTreeWidget(theme="dark" if self.current_theme == "dark" else "light")
        self.org_tree.setColumnCount(4)
        self.org_tree.setHeaderLabels(["机构名称", "机构编码", "上级机构", "联系人"])
        self.org_tree.setUniformRowHeights(True)
        # 关闭交替底色，避免主题下出现色块
        self.org_tree.setAlternatingRowColors(False)
        self.org_tree.header().setSectionResizeMode(QHeaderView.Stretch)
        self.org_tree.setObjectName("org_tree")
        self.org_tree.installEventFilter(self)  # 捕获滚轮事件以支持 Ctrl 缩放
        # 初始应用字体缩放
        self._apply_tree_font_zoom(self._tree_font_size)
        # 右键菜单
        self.org_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.org_tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        # 捕获滚轮事件以支持 Ctrl 缩放（树和其 viewport 都需要监听）
        self.org_tree.installEventFilter(self)
        self.org_tree.viewport().installEventFilter(self)

        detail_layout.addWidget(self.org_tree)

        # 顶部预留按钮：新增/删除机构
        if hasattr(self, "btn_org_add"):
            # 顶部“新增”按钮：只新增顶级机构（不跟随当前选中节点）
            self.btn_org_add.clicked.connect(lambda: self.add_org(None))
        if hasattr(self, "btn_org_delete"):
            self.btn_org_delete.clicked.connect(self.delete_org)

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

        self._load_root_org_units_async(auto_select=True)
        # 初始字体应用到树
        self._apply_tree_font_zoom(self._tree_font_size)
        # 初始字体应用到左侧列表
        self._apply_list_font_zoom(self._list_font_size)

    def on_tab_changed(self, tab_index):
        self._tree_load_token += 1
        self.batch_list.clear()
        if hasattr(self, "org_tree"):
            self.org_tree.clear()
        self.lbl_case_title.setText("📄 机构管理列表")

        self._load_root_org_units_async(auto_select=True)

    def _load_root_org_units_async(self, auto_select=False, selected_id=None):
        self._root_load_token += 1
        self._tree_load_token += 1
        token = self._root_load_token
        self.batch_list.clear()
        if hasattr(self, "org_tree"):
            self.org_tree.clear()

        def do_load():
            try:
                return {"token": token, "rows": list_root_org_units(), "error": ""}
            except Exception as e:
                return {"token": token, "rows": [], "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._root_load_token:
                return
            if res.get("error"):
                print(f"[inventory-receive] load root org units failed: {res.get('error')}")
                return
            self.batch_list.setUpdatesEnabled(False)
            try:
                self.batch_list.clear()
                for r in res.get("rows") or []:
                    it = QListWidgetItem(r.get("name") or "")
                    it.setData(Qt.UserRole, int(r.get("id")))
                    self.batch_list.addItem(it)
            finally:
                self.batch_list.setUpdatesEnabled(True)
            target_row = -1
            if selected_id is not None:
                for i in range(self.batch_list.count()):
                    it = self.batch_list.item(i)
                    if it and it.data(Qt.UserRole) == int(selected_id):
                        target_row = i
                        break
            elif auto_select and self.batch_list.count() > 0:
                target_row = 0
            if target_row >= 0:
                self.batch_list.setCurrentRow(target_row)
                self.load_cases_for_batch(self.batch_list.currentItem())

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

    def load_cases_for_batch(self, item):
        if not item:
            return

        root_name = item.text()
        root_id = item.data(Qt.UserRole)
        self.lbl_case_title.setText(f"📄 机构管理 - {root_name}")

        self.org_tree.clear()

        # 顶级机构本身作为根节点展示
        root_item = QTreeWidgetItem(self.org_tree.invisibleRootItem())
        root_item.setText(0, root_name)
        root_item.setText(1, "")
        root_item.setText(2, "")
        root_item.setText(3, "")
        if root_id is not None:
            root_item.setData(0, Qt.UserRole, int(root_id))

        self._tree_load_token += 1
        token = self._tree_load_token

        def build_tree(nodes, parent_item):
            for node in nodes:
                it = QTreeWidgetItem(parent_item)
                it.setText(0, node.get("name") or "")
                it.setText(1, node.get("code") or "")
                it.setText(2, node.get("parent_name") or "")
                it.setText(3, node.get("contact") or "")
                it.setData(0, Qt.UserRole, int(node.get("id")))
                build_tree(node.get("children") or [], it)

        def do_load():
            try:
                children = build_org_tree_for_root(int(root_id)) if root_id is not None else []
                return {"token": token, "children": children, "error": ""}
            except Exception as e:
                return {"token": token, "children": [], "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._tree_load_token:
                return
            if res.get("error"):
                print(f"[inventory-receive] load org tree failed: {res.get('error')}")
                return
            self.org_tree.setUpdatesEnabled(False)
            try:
                build_tree(res.get("children") or [], root_item)
                root_item.setExpanded(True)
                self.org_tree.expandAll()
            finally:
                self.org_tree.setUpdatesEnabled(True)

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

        # 顶部按钮绑定（确保 org_tree 已存在）
        if hasattr(self, "btn_org_add"):
            try:
                self.btn_org_add.clicked.disconnect()
            except Exception:
                pass
            # 顶部“新增”按钮：只新增顶级机构（不跟随当前选中节点）
            self.btn_org_add.clicked.connect(lambda: self.add_org(None))
        if hasattr(self, "btn_org_delete"):
            try:
                self.btn_org_delete.clicked.disconnect()
            except Exception:
                pass
            self.btn_org_delete.clicked.connect(lambda: self.delete_org(self.org_tree.currentItem()))

    def _get_orgs_by_root(self, root_name):
        if root_name == "国家图书馆总馆":
            return [
                {
                    "name": "国家图书馆总馆",
                    "code": "ORG-1001",
                    "parent": "总部",
                    "contact": "王馆长",
                    "children": [
                        {
                            "name": "国家图书馆东馆",
                            "code": "ORG-1001-01",
                            "parent": "国家图书馆总馆",
                            "contact": "李主任",
                            "children": [
                                {
                                    "name": "东馆少儿部",
                                    "code": "ORG-1001-01-01",
                                    "parent": "国家图书馆东馆",
                                    "contact": "周老师",
                                    "children": [],
                                }
                            ],
                        },
                        {
                            "name": "国家图书馆文献修复中心",
                            "code": "ORG-1001-02",
                            "parent": "国家图书馆总馆",
                            "contact": "赵主管",
                            "children": [],
                        },
                    ],
                }
            ]
        if root_name == "省档案馆":
            return [
                {
                    "name": "省档案馆",
                    "code": "ORG-2001",
                    "parent": "省级机构",
                    "contact": "陈馆长",
                    "children": [
                        {
                            "name": "省档案馆第一分馆",
                            "code": "ORG-2001-01",
                            "parent": "省档案馆",
                            "contact": "刘主任",
                            "children": [],
                        },
                        {
                            "name": "省档案馆第二分馆",
                            "code": "ORG-2001-02",
                            "parent": "省档案馆",
                            "contact": "孙主任",
                            "children": [],
                        },
                    ],
                }
            ]
        # 默认市级
        return [
            {
                "name": "市政务中心档案室",
                "code": "ORG-3001",
                "parent": "市政务中心",
                "contact": "何负责人",
                "children": [
                    {
                        "name": "市政务中心档案室（新区）",
                        "code": "ORG-3001-01",
                        "parent": "市政务中心档案室",
                        "contact": "丁管理员",
                        "children": [],
                    }
                ],
            }
        ]

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

    # === 机构增删改 ===
    # === 机构增删改（通过树节点右键菜单） ===
    def on_tree_context_menu(self, pos):
        item = self.org_tree.itemAt(pos)
        # 右键时选中节点
        if item:
            self.org_tree.setCurrentItem(item)

        menu = QMenu(self)
        act_add = menu.addAction("新增机构")
        act_edit = menu.addAction("编辑机构")
        act_del = menu.addAction("删除机构")

        act_edit.setEnabled(bool(item))
        act_del.setEnabled(bool(item))

        global_pos = self.org_tree.viewport().mapToGlobal(pos)
        chosen = menu.exec_(global_pos)
        if chosen == act_add:
            self.add_org(item)
        elif chosen == act_edit and item:
            self.edit_org(item)
        elif chosen == act_del and item:
            self.delete_org(item)

    def add_org(self, parent_item=None):
        parent_name = parent_item.text(0) if parent_item else "（顶级）"
        dlg = OrgEditDialog(parent_name=parent_name, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            parent_id = None
            if parent_item is not None:
                try:
                    parent_id = parent_item.data(0, Qt.UserRole)
                except Exception:
                    parent_id = None

            new_id = create_org_unit(
                name=data.get("name") or "",
                code=data.get("code") or "",
                contact=data.get("contact") or "",
                parent_id=int(parent_id) if parent_id is not None else None,
            )
            if not new_id:
                StyledMessageBox.warning(self, "提示", "机构名称不能为空", self.current_theme)
                return

            # 新增顶级机构：刷新左侧并选中；否则刷新当前树
            if parent_id is None:
                self._load_root_org_units_async(auto_select=False, selected_id=int(new_id))
            else:
                self.load_cases_for_batch(self.batch_list.currentItem())

    def edit_org(self, item):
        parent_item = item.parent()
        parent_name = parent_item.text(0) if parent_item else "（顶级）"
        dlg = OrgEditDialog(
            parent_name=parent_name,
            name=item.text(0),
            code=item.text(1),
            contact=item.text(3),
            parent=self
        )
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            org_id = item.data(0, Qt.UserRole)
            ok = update_org_unit(
                org_id=int(org_id),
                name=data.get("name") or "",
                code=data.get("code") or "",
                contact=data.get("contact") or "",
            )
            if not ok:
                StyledMessageBox.warning(self, "提示", "保存失败（机构名称不能为空或记录不存在）", self.current_theme)
                return
            self.load_cases_for_batch(self.batch_list.currentItem())

    def delete_org(self, item=None):
        """删除机构 - 基于树中当前选中的节点"""
        # 始终从树中获取当前选中项（忽略传入的item参数）
        item = self.org_tree.currentItem()
        
        if item is None:
            StyledMessageBox.information(self, "提示", "请先点击选择要删除的机构", self.current_theme)
            return
        
        # 高亮显示即将删除的机构，确保用户知道选中了哪个
        self.org_tree.scrollToItem(item)
        name = item.text(0)
        ret = StyledMessageBox.question(self, "确认删除", f"确定删除机构「{name}」及其子机构吗？", theme=self.current_theme)
        if ret != StyledMessageBox.Yes:
            return
        org_id = item.data(0, Qt.UserRole)
        if org_id is None:
            return
        
        # 检查机构下是否有人员
        entry_count = count_entries_in_org_subtree(org_id=int(org_id))
        if entry_count > 0:
            StyledMessageBox.warning(
                self, "无法删除",
                f"该机构（含子机构）下有 {entry_count} 名人员，请先删除或移动人员后再删除机构。",
                self.current_theme
            )
            return
        
        deleted = delete_org_unit_subtree(org_id=int(org_id))
        if deleted <= 0:
            return
        
        # 删除顶级机构：刷新左侧；否则刷新当前树
        parent_item = item.parent()
        if parent_item is None:
            self.on_tab_changed(0)
        else:
            self.load_cases_for_batch(self.batch_list.currentItem())


class OrgEditDialog(QDialog):
    """机构编辑/新增对话框"""

    def __init__(self, parent_name="（顶级）", name="", code="", contact="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("机构信息")
        self.resize(480, 300)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel#title_label {
                font-size: 16px;
                font-weight: bold;
                color: #333;
                padding: 8px 0;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QLabel.field_label {
                font-size: 13px;
                color: #666;
                font-weight: 500;
            }
            QLineEdit {
                font-size: 13px;
                padding: 8px 12px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: #fafafa;
                min-height: 20px;
            }
            QLineEdit:focus {
                border-color: #4A90D9;
                background-color: #ffffff;
            }
            QLineEdit:read-only {
                background-color: #f0f0f0;
                color: #888;
            }
            QPushButton {
                font-size: 13px;
                padding: 8px 24px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton#save_btn {
                background-color: #4A90D9;
                color: white;
                border: none;
            }
            QPushButton#save_btn:hover {
                background-color: #3a7bc8;
            }
            QPushButton#cancel_btn {
                background-color: #ffffff;
                color: #666;
                border: 1px solid #d0d0d0;
            }
            QPushButton#cancel_btn:hover {
                background-color: #f0f0f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 标题
        title_label = QLabel("机构信息")
        title_label.setObjectName("title_label")
        layout.addWidget(title_label)

        # 卡片区域
        card = QFrame()
        card.setObjectName("card")
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setHorizontalSpacing(24)
        card_layout.setVerticalSpacing(12)

        # 第一行：上级机构
        lbl_parent = QLabel("上级机构")
        lbl_parent.setProperty("class", "field_label")
        self.le_parent = QLineEdit(parent_name)
        self.le_parent.setReadOnly(True)
        card_layout.addWidget(lbl_parent, 0, 0)
        card_layout.addWidget(self.le_parent, 0, 1)

        # 第二行：机构名称
        lbl_name = QLabel("机构名称")
        lbl_name.setProperty("class", "field_label")
        self.le_name = QLineEdit(name)
        self.le_name.setPlaceholderText("请输入机构名称")
        card_layout.addWidget(lbl_name, 1, 0)
        card_layout.addWidget(self.le_name, 1, 1)

        # 第三行：机构编码
        lbl_code = QLabel("机构编码")
        lbl_code.setProperty("class", "field_label")
        self.le_code = QLineEdit(code)
        self.le_code.setPlaceholderText("可选")
        card_layout.addWidget(lbl_code, 2, 0)
        card_layout.addWidget(self.le_code, 2, 1)

        # 第四行：联系人
        lbl_contact = QLabel("联系人")
        lbl_contact.setProperty("class", "field_label")
        self.le_contact = QLineEdit(contact)
        self.le_contact.setPlaceholderText("可选")
        card_layout.addWidget(lbl_contact, 3, 0)
        card_layout.addWidget(self.le_contact, 3, 1)

        # 设置列伸缩
        card_layout.setColumnStretch(1, 1)

        layout.addWidget(card)
        layout.addStretch()

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancel_btn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("save_btn")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def get_data(self):
        return {
            "name": self.le_name.text().strip(),
            "code": self.le_code.text().strip(),
            "contact": self.le_contact.text().strip(),
        }



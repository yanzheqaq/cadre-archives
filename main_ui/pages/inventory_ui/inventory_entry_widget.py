import os
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QButtonGroup,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, QSplitter, QStackedWidget,
    QAbstractItemView, QToolButton, QTreeWidget, QTreeWidgetItem, QMessageBox,
    QMenu, QAction, QFileDialog, QStyle, QCheckBox, QDialog, QComboBox,
)
from PyQt5.QtCore import Qt, QSize, QThreadPool
from PyQt5.QtGui import QIcon, QFont, QWheelEvent, QBrush, QColor

from common.config import AppSettings
from main_ui.config_pages import PagesConfig
from .style_inventory import InventoryReceiveStyle
from .repo.inventory_entry_repo import (
    create_entry_person,
    get_default_template_id,
    list_entries_by_org_unit_id,
    move_entries_to_org_unit,
    delete_entry,
)
from .repo.org_repo import list_all_org_units, count_entries_grouped_by_org
from .inventory_entry_dialog import InventoryEntryDialog
from .catalog_search_dialog import CatalogSearchDialog
from .widgets.person_create_dialog import PersonCreateDialog
from .widgets.qt_worker import Worker
from .services.person_export_service import export_person_package
from .services.catalog_export_service import export_info_and_catalog, export_info_and_catalog_batch
from .services.person_import_service import import_person_archive_batch, import_person_archive_folder
from .styled_message_box import StyledMessageBox

ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icons'))


class OrgMigrationDialog(QDialog):
    def __init__(
        self,
        *,
        org_options: List[Tuple[Optional[int], str]],
        default_org_unit_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("迁移类别")
        self.resize(420, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("请选择要迁移到的类别")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        self.cb_org = QComboBox()
        self._org_ids: List[Optional[int]] = []
        for oid, label in org_options:
            self.cb_org.addItem(label)
            self._org_ids.append(oid)
        if default_org_unit_id in self._org_ids:
            self.cb_org.setCurrentIndex(self._org_ids.index(default_org_unit_id))
        elif self._org_ids:
            self.cb_org.setCurrentIndex(0)
        layout.addWidget(self.cb_org)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定迁移")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def selected_org_unit_id(self) -> Optional[int]:
        idx = self.cb_org.currentIndex()
        if 0 <= idx < len(self._org_ids):
            return self._org_ids[idx]
        return None

    def selected_org_label(self) -> str:
        return self.cb_org.currentText().strip()


class InventoryEntryWidget(QWidget):
    """
    馆藏模块 - 录入页面
    布局与"接收"页面保持一致，便于后续按需修改
    """

    LEFT_PANEL_MIN_WIDTH = 280    # 左侧列表最小宽度，可按需调整

    def __init__(self):
        super().__init__()
        self.config_manager = AppSettings()
        self.current_theme = self.config_manager.load_theme_preference()
        # 字体缩放
        self._base_font: QFont = self.font()
        self._font_min = 9
        self._font_max = 20
        self._tree_font_size = self._base_font.pointSizeF()
        self._table_font_size = self._base_font.pointSizeF()
        self._suppress_catalog_changed = False
        self.current_entry_id = None
        self.current_template_id = None
        self._sort_asc = True  # 排序状态：True为升序，False为降序
        self._import_in_progress = False
        self._thread_pool = QThreadPool.globalInstance()
        self._org_tree_load_token = 0
        self._person_load_token = 0
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

        self.btn_tab_detail = QPushButton("录入列表")
        self.btn_tab_detail.setObjectName("tab_btn")
        self.btn_tab_detail.setCheckable(True)
        self.btn_tab_detail.setChecked(True)
        self.btn_tab_detail.setCursor(Qt.PointingHandCursor)
        self.right_tab_group.addButton(self.btn_tab_detail, 0)

        self.btn_tab_process = QPushButton("录入进度")
        self.btn_tab_process.setObjectName("tab_btn")
        self.btn_tab_process.setCheckable(True)
        self.btn_tab_process.setCursor(Qt.PointingHandCursor)
        self.right_tab_group.addButton(self.btn_tab_process, 1)

        self.right_tab_group.buttonClicked[int].connect(self.on_right_tab_changed)

        tool_bar.addWidget(self.btn_tab_detail)
        tool_bar.addWidget(self.btn_tab_process)

        main_layout.addLayout(tool_bar)

        # 左右分割
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setObjectName("main_splitter_inventory_entry")

        # 左侧列表
        left_widget = QWidget()
        left_widget.setMinimumWidth(self.LEFT_PANEL_MIN_WIDTH)
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
            ("迁移", "transfer.png", "migrate")
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

            if suffix == "add":
                self.btn_person_add = btn
            elif suffix == "sort":
                self.btn_sort = btn
            elif suffix == "delete":
                self.btn_delete = btn
            elif suffix == "migrate":
                self.btn_migrate = btn

        func_btn_layout.addStretch()
        left_layout.addLayout(func_btn_layout)

        # 左侧机构树
        self.org_tree = QTreeWidget()
        self.org_tree.setObjectName("org_tree_inventory_entry")
        self.org_tree.setHeaderHidden(True)
        self.org_tree.setIndentation(18)
        self.org_tree.itemClicked.connect(self.load_personnel_for_org)
        self.org_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.org_tree.customContextMenuRequested.connect(self._on_org_tree_context_menu)

        left_layout.addWidget(self.org_tree)

        # 顶部预留按钮：新增人员
        if hasattr(self, "btn_person_add"):
            self.btn_person_add.clicked.connect(self._on_add_person)
        
        # 排序按钮：切换升序/降序
        if hasattr(self, "btn_sort"):
            self.btn_sort.clicked.connect(self._on_sort_refresh)
        
        # 删除按钮：删除选中的人员
        if hasattr(self, "btn_delete"):
            self.btn_delete.clicked.connect(self._on_delete_person)

        if hasattr(self, "btn_migrate"):
            self.btn_migrate.clicked.connect(self._on_migrate_person)

        # 右侧表格/进度
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(5)

        self.lbl_case_title = QLabel("📄 信息录入列表")
        self.lbl_case_title.setObjectName("section_title")

        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(0, 0, 0, 0)
        title_bar_layout.setSpacing(PagesConfig.BATCH_FUNC_ICON_SPACING)
        title_bar_layout.addWidget(self.lbl_case_title)
        title_bar_layout.addStretch()

        right_icon_size = PagesConfig.BATCH_FUNC_ICON_SIZE

        self.btn_catalog_search = QToolButton()
        self.btn_catalog_search.setCursor(Qt.PointingHandCursor)
        self.btn_catalog_search.setObjectName("right_func_btn")
        self.btn_catalog_search.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogContentsView)
        )
        self.btn_catalog_search.setIconSize(QSize(right_icon_size, right_icon_size))
        self.btn_catalog_search.setText("条目搜索")
        self.btn_catalog_search.setToolTip("搜索全部人员的目录内容，并可直接修改目录条目")
        self.btn_catalog_search.setAutoRaise(True)
        self.btn_catalog_search.setFixedSize(
            QSize(right_icon_size + 48, right_icon_size + 12)
        )
        self.btn_catalog_search.clicked.connect(self._on_catalog_search_clicked)
        title_bar_layout.addWidget(self.btn_catalog_search)

        # 数据自检（数据安全保险入口）：对比"上次快照"vs"当前 DB"，
        # 列出"是谁的、哪一条目录条目"丢了，方便排查/上报/恢复
        self.btn_data_integrity = QToolButton()
        self.btn_data_integrity.setCursor(Qt.PointingHandCursor)
        self.btn_data_integrity.setObjectName("right_func_btn")
        self.btn_data_integrity.setIcon(
            self.style().standardIcon(QStyle.SP_DialogHelpButton)
        )
        self.btn_data_integrity.setIconSize(QSize(right_icon_size, right_icon_size))
        self.btn_data_integrity.setText("数据自检")
        self.btn_data_integrity.setToolTip(
            "数据完整性自检：对比上次快照与当前 DB 状态，"
            "列出可能丢失的目录条目（点击后弹出报告窗口）"
        )
        self.btn_data_integrity.setAutoRaise(True)
        self.btn_data_integrity.setFixedSize(
            QSize(right_icon_size + 38, right_icon_size + 12)
        )
        self.btn_data_integrity.clicked.connect(self._on_data_integrity_clicked)
        title_bar_layout.addWidget(self.btn_data_integrity)

        # 导出（放在“批次检测”左侧）
        self.btn_export = QToolButton()
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setObjectName("right_func_btn")
        self.btn_export.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_export.setIconSize(QSize(right_icon_size, right_icon_size))
        self.btn_export.setText("导出")
        self.btn_export.setToolTip("导出（CSV）")
        self.btn_export.setAutoRaise(True)
        # 稍微大一点点，便于点击
        self.btn_export.setFixedSize(QSize(right_icon_size + 22, right_icon_size + 12))
        title_bar_layout.addWidget(self.btn_export)

        right_actions = [
            ("批次检测", "Batch_testing.jpg"),
            ("二维码打印", "QR_printing.png")
        ]

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

        self.case_table = QTableWidget()
        self.case_table.setColumnCount(7)
        self.case_table.setHorizontalHeaderLabels(["选择", "姓名", "工号", "岗位", "电话", "身份证号", "状态"])
        self.case_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.case_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.case_table.setObjectName("case_table_inventory_entry")
        # 第0列“选择”固定窄宽，其余列自适应填充
        header = self.case_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.case_table.setColumnWidth(0, 46)
        for c in range(1, self.case_table.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.Stretch)
        self.case_table.setAlternatingRowColors(True)
        self.case_table.verticalHeader().setVisible(False)

        # 全选复选框
        select_all_layout = QHBoxLayout()
        select_all_layout.setContentsMargins(0, 0, 0, 0)
        self.cb_select_all = QCheckBox("全选")
        self.cb_select_all.setStyleSheet("QCheckBox { font-size: 12px; }")
        self.cb_select_all.stateChanged.connect(self._on_select_all_changed)
        select_all_layout.addWidget(self.cb_select_all)
        select_all_layout.addStretch()
        detail_layout.addLayout(select_all_layout)

        # 标题栏功能绑定：导出
        self._init_export_menu()

        detail_layout.addWidget(self.case_table)

        process_page = QWidget()
        process_layout = QVBoxLayout(process_page)
        process_layout.setContentsMargins(0, 0, 0, 0)
        process_label = QLabel("录入进度数据开发中...")
        process_label.setAlignment(Qt.AlignCenter)
        process_label.setObjectName("section_title")
        process_layout.addWidget(process_label)

        self.right_stack.addWidget(detail_page)
        self.right_stack.addWidget(process_page)

        right_layout.addWidget(self.right_stack)

        # 双击行打开全屏录入弹窗
        self.case_table.itemDoubleClicked.connect(self.on_case_double_clicked)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter)

        # 初始填充表格 & 标题
        self._populate_org_tree(auto_select_first=True, load_after_select=True)
        # 初始字体缩放应用到树和表
        self._apply_tree_font_zoom(self._tree_font_size)
        self._apply_table_font_zoom(self._table_font_size)

    def _export_current_table_csv(self):
        """导出右侧人员表为 CSV（导出勾选行）。"""
        if not hasattr(self, "case_table"):
            return
        if self.case_table.rowCount() <= 0:
            StyledMessageBox.information(self, "提示", "当前没有可导出的数据", self.current_theme)
            return

        checked_ids = self._checked_entry_ids()
        if not checked_ids:
            StyledMessageBox.information(self, "提示", "请先勾选需要导出的人员（表格第1列“选择”）", self.current_theme)
            return
        selected_rows = set()
        for r in range(self.case_table.rowCount()):
            it = self.case_table.item(r, 1)
            if not it:
                continue
            eid = it.data(Qt.UserRole)
            try:
                if eid is not None and int(eid) in checked_ids:
                    selected_rows.add(r)
            except Exception:
                continue

        default_name = "人员列表.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return

        import csv

        # 可见列（不导出“选择”列）
        cols = [c for c in range(self.case_table.columnCount()) if (c != 0) and (not self.case_table.isColumnHidden(c))]
        headers = []
        for c in cols:
            hi = self.case_table.horizontalHeaderItem(c)
            headers.append(hi.text() if hi else f"列{c + 1}")

        try:
            # utf-8-sig：兼容 Excel 直接打开不乱码
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in sorted(selected_rows):
                    row = []
                    for c in cols:
                        it = self.case_table.item(r, c)
                        row.append(it.text() if it else "")
                    w.writerow(row)
            StyledMessageBox.information(self, "提示", f"导出成功：{path}", self.current_theme)
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"导出失败：{e}", self.current_theme)

    def _current_selected_entry_id(self) -> Optional[int]:
        """从右侧人员表当前选中行提取 entry_id（存放在“姓名”列 Qt.UserRole）。"""
        if not hasattr(self, "case_table"):
            return None
        row = self.case_table.currentRow()
        if row < 0:
            return None
        it = self.case_table.item(row, 1)
        if not it:
            return None
        eid = it.data(Qt.UserRole)
        try:
            return int(eid) if eid is not None else None
        except Exception:
            return None

    def _checked_entry_ids(self) -> List[int]:
        """获取勾选的人员 entry_id 列表（第0列复选框；entry_id 存在“姓名”列 Qt.UserRole）。"""
        ids: List[int] = []
        if not hasattr(self, "case_table"):
            return ids
        for r in range(self.case_table.rowCount()):
            w = self.case_table.cellWidget(r, 0)
            cb = w.findChild(QCheckBox) if w else None
            if not cb or (not cb.isChecked()):
                continue
            name_it = self.case_table.item(r, 1)
            if not name_it:
                continue
            eid = name_it.data(Qt.UserRole)
            try:
                if eid is not None:
                    ids.append(int(eid))
            except Exception:
                continue
        # 去重但保持顺序
        seen = set()
        out: List[int] = []
        for x in ids:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    def _entry_ids_for_migration(self) -> List[int]:
        ids = self._checked_entry_ids()
        if ids:
            return ids
        entry_id = self._current_selected_entry_id()
        return [entry_id] if entry_id else []

    def _current_org_unit_id(self) -> Optional[int]:
        item = self.org_tree.currentItem() if hasattr(self, "org_tree") else None
        if not item:
            return None
        try:
            return item.data(0, Qt.UserRole)
        except Exception:
            return None

    def _on_org_tree_context_menu(self, pos):
        item = self.org_tree.itemAt(pos)
        if item:
            self.org_tree.setCurrentItem(item)
        menu = QMenu(self)
        act_single = QAction("导入单个人事档案文件夹", self)
        act_batch = QAction("批量导入人事档案文件夹", self)
        act_single.triggered.connect(self._on_import_single_person_folder)
        act_batch.triggered.connect(self._on_import_batch_person_folder)
        menu.addAction(act_single)
        menu.addAction(act_batch)
        menu.exec_(self.org_tree.viewport().mapToGlobal(pos))

    def _refresh_after_import(self):
        self._refresh_org_tree_keep_selection(load_after_select=True)

    def _on_import_single_person_folder(self):
        if self._import_in_progress:
            StyledMessageBox.information(self, "提示", "当前已有导入任务正在执行，请稍候。", self.current_theme)
            return
        org_unit_id = self._current_org_unit_id()
        folder = QFileDialog.getExistingDirectory(self, "选择单个人事档案文件夹")
        if not folder:
            return
        self._start_import_task(
            lambda: import_person_archive_folder(folder, org_unit_id=org_unit_id),
            lambda res: self._show_single_import_result(folder, res),
        )

    def _on_import_batch_person_folder(self):
        if self._import_in_progress:
            StyledMessageBox.information(self, "提示", "当前已有导入任务正在执行，请稍候。", self.current_theme)
            return
        org_unit_id = self._current_org_unit_id()
        folder = QFileDialog.getExistingDirectory(self, "选择批量人事档案父文件夹")
        if not folder:
            return
        self._start_import_task(
            lambda: import_person_archive_batch(folder, org_unit_id=org_unit_id),
            self._show_batch_import_result,
        )

    def _start_import_task(self, import_fn, on_success):
        self._import_in_progress = True
        self.setEnabled(False)
        worker = Worker(import_fn)

        def on_done(res):
            self._import_in_progress = False
            self.setEnabled(True)
            try:
                self._refresh_after_import()
                on_success(res)
            except Exception as e:
                StyledMessageBox.warning(self, "导入完成但刷新失败", str(e), self.current_theme)

        def on_error(err):
            self._import_in_progress = False
            self.setEnabled(True)
            StyledMessageBox.warning(self, "导入失败", str(err), self.current_theme)

        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        self._thread_pool.start(worker)

    def _show_single_import_result(self, folder: str, res: dict):
        lines = [
            f"人员：{res.get('name') or os.path.basename(folder)}",
            f"目录：{res.get('catalog_rows', 0)} 条",
            f"高清图：{res.get('original_images', 0)} 张",
            f"处理图：{res.get('retouched_images', 0)} 张",
        ]
        warnings = res.get("warnings") or []
        if warnings:
            lines.append("")
            lines.extend(warnings[:5])
        StyledMessageBox.information(self, "导入完成", "\n".join(lines), self.current_theme)

    def _show_batch_import_result(self, res: dict):
        lines = [
            f"发现：{res.get('total', 0)} 人",
            f"成功：{res.get('success', 0)} 人",
            f"新增：{res.get('created', 0)} 人",
            f"更新：{res.get('updated', 0)} 人",
            f"高清图：{res.get('original_images', 0)} 张",
            f"处理图：{res.get('retouched_images', 0)} 张",
        ]
        errors = res.get("errors") or []
        if errors:
            lines.append("")
            lines.append(f"失败：{len(errors)} 人")
            lines.extend(errors[:8])
        StyledMessageBox.information(self, "批量导入完成", "\n".join(lines), self.current_theme)

    def _export_selected_person_package(self):
        """
        导出勾选人员的导出包（姓名（身份证）/人员信息.xml/图片/原图/高清图）。
        图片自动使用 AES-256 加密，仅可在本客户端查看。
        """
        entry_ids = self._checked_entry_ids()
        if not entry_ids:
            StyledMessageBox.information(self, "提示", "请先勾选需要导出的人员（表格第1列「选择」）", self.current_theme)
            return
        root_dir = QFileDialog.getExistingDirectory(self, "选择导出位置")
        if not root_dir:
            return
        try:
            for eid in entry_ids:
                export_person_package(entry_id=int(eid), export_root_dir=root_dir)
            msg = f"导出成功：{len(entry_ids)} 人\n（图片已加密，仅可在本客户端查看）"
            StyledMessageBox.information(self, "提示", msg, self.current_theme)
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"导出失败：{e}", self.current_theme)

    def _on_data_integrity_clicked(self):
        """数据自检按钮点击：弹出"数据完整性自检"对话框。

        即使最近一次快照不存在也允许打开（对话框会引导用户创建第一份基线）。
        """
        try:
            from .data_integrity_dialog import DataIntegrityDialog
            dlg = DataIntegrityDialog(self)
            dlg.exec_()
        except Exception as e:
            StyledMessageBox.warning(
                self, "数据自检",
                f"打开数据自检失败：\n{type(e).__name__}: {e}",
                getattr(self, "current_theme", "light"),
            )

    def _on_catalog_search_clicked(self):
        try:
            dlg = CatalogSearchDialog("", self, theme=getattr(self, "current_theme", "light"))
            dlg.exec_()
        except Exception as e:
            StyledMessageBox.warning(
                self, "目录条目搜索",
                f"打开目录条目搜索失败：\n{type(e).__name__}: {e}",
                getattr(self, "current_theme", "light"),
            )

    def _init_export_menu(self):
        """导出按钮：默认导出人员包，同时提供导出CSV。"""
        if not hasattr(self, "btn_export"):
            return
        menu = QMenu(self)
        
        # 导出人员包（图片自动加密）
        act_pkg = QAction("导出人员包（XML + 加密图片）🔒", self)
        act_pkg.triggered.connect(self._export_selected_person_package)
        menu.addAction(act_pkg)
        
        menu.addSeparator()
        
        # CSV 导出
        act_csv = QAction("导出列表CSV", self)
        act_csv.triggered.connect(self._export_current_table_csv)
        menu.addAction(act_csv)

        menu.addSeparator()

        # 导出信息及目录（Excel）
        act_excel = QAction("导出信息及目录（Excel）", self)
        act_excel.triggered.connect(self._export_info_and_catalog)
        menu.addAction(act_excel)

        # 默认点击=导出人员包；右侧下拉=选择其他导出
        self.btn_export.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_export.setMenu(menu)
        self.btn_export.clicked.connect(self._export_selected_person_package)

    def _on_select_all_changed(self, state):
        """全选/取消全选"""
        checked = (state == Qt.Checked)
        for r in range(self.case_table.rowCount()):
            w = self.case_table.cellWidget(r, 0)
            if w:
                cb = w.findChild(QCheckBox)
                if cb:
                    cb.setChecked(checked)

    def _on_migrate_person(self):
        entry_ids = self._entry_ids_for_migration()
        if not entry_ids:
            StyledMessageBox.information(self, "提示", "请先勾选或单击需要迁移的人员", self.current_theme)
            return

        current_org_unit_id = self._current_org_unit_id()
        dlg = OrgMigrationDialog(
            org_options=self._org_options_flat(),
            default_org_unit_id=current_org_unit_id,
            parent=self,
        )
        if dlg.exec_() != dlg.Accepted:
            return

        target_org_unit_id = dlg.selected_org_unit_id()
        target_label = dlg.selected_org_label().replace("　", "").strip() or "未分类"
        if target_org_unit_id == current_org_unit_id:
            StyledMessageBox.information(self, "提示", "目标类别与当前类别相同，无需迁移。", self.current_theme)
            return

        reply = StyledMessageBox.question(
            self,
            "确认迁移",
            f"确定将选中的 {len(entry_ids)} 条档案迁移到「{target_label}」吗？\n人员信息总览、目录和图片会随档案一起保留。",
            theme=self.current_theme,
            yes_text="确定迁移",
            no_text="取消",
        )
        if reply != StyledMessageBox.Yes:
            return

        try:
            moved_count = move_entries_to_org_unit(
                entry_ids=entry_ids,
                target_org_unit_id=target_org_unit_id,
            )
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"迁移失败：{e}", self.current_theme)
            return

        self._populate_org_tree(
            selected_org_id=target_org_unit_id,
            auto_select_first=True,
            load_after_select=True,
        )

        if moved_count <= 0:
            StyledMessageBox.warning(self, "提示", "没有迁移任何记录，所选档案可能已被删除。", self.current_theme)
        else:
            StyledMessageBox.information(self, "完成", f"成功迁移 {moved_count} 条档案到「{target_label}」", self.current_theme)

    def _export_info_and_catalog(self):
        """导出勾选人员的基本信息和目录到 Excel（一人一个文件）"""
        entry_ids = self._checked_entry_ids()
        if not entry_ids:
            StyledMessageBox.information(self, "提示", "请先勾选需要导出的人员（表格第1列「选择」）", self.current_theme)
            return

        # 构建 entry_id → 姓名 映射
        id_to_name = {}
        for r in range(self.case_table.rowCount()):
            name_item = self.case_table.item(r, 1)
            if name_item and name_item.data(Qt.UserRole) is not None:
                try:
                    eid = int(name_item.data(Qt.UserRole))
                    if eid in entry_ids:
                        id_to_name[eid] = name_item.text().strip()
                except Exception:
                    pass

        if len(entry_ids) == 1:
            # 单人：选文件保存路径
            eid = entry_ids[0]
            person_name = id_to_name.get(eid, "")
            default_name = f"{person_name}-信息及目录.xlsx" if person_name else "信息及目录.xlsx"
            path, _ = QFileDialog.getSaveFileName(self, "导出信息及目录", default_name, "Excel Files (*.xlsx)")
            if not path:
                return
            try:
                export_info_and_catalog([eid], path)
                StyledMessageBox.information(self, "提示", f"导出成功：{path}", self.current_theme)
            except Exception as e:
                StyledMessageBox.warning(self, "提示", f"导出失败：{e}", self.current_theme)
        else:
            # 多人：选文件夹，每人一个 Excel
            folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
            if not folder:
                return
            try:
                saved = export_info_and_catalog_batch(entry_ids, folder, id_to_name)
                StyledMessageBox.information(self, "提示", f"导出成功，共 {len(saved)} 个文件\n保存位置：{folder}", self.current_theme)
            except Exception as e:
                StyledMessageBox.warning(self, "提示", f"导出失败：{e}", self.current_theme)

    # Ctrl + 滚轮调整字体（树或人员表，分开缩放）
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            in_tree = self.org_tree.rect().contains(self.org_tree.mapFrom(self, event.pos()))
            in_table = self.case_table.rect().contains(self.case_table.mapFrom(self, event.pos()))
            if in_tree or in_table:
                delta = event.angleDelta().y()
                step = 1 if delta > 0 else -1
                if in_tree:
                    new_size = self._tree_font_size + step
                    new_size = max(self._font_min, min(self._font_max, new_size))
                    self._tree_font_size = new_size
                    self._apply_tree_font_zoom(new_size)
                elif in_table:
                    new_size = self._table_font_size + step
                    new_size = max(self._font_min, min(self._font_max, new_size))
                    self._table_font_size = new_size
                    self._apply_table_font_zoom(new_size)
                event.accept()
                return
        super().wheelEvent(event)

    def _apply_tree_font_zoom(self, point_size: float):
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.org_tree.setFont(f)

    def _apply_table_font_zoom(self, point_size: float):
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.case_table.setFont(f)

    def on_tab_changed(self, index):
        # index 0: 全部机构；index 1: 已接收（示例同数据）
        self._populate_org_tree(auto_select_first=True, load_after_select=True)

    def on_right_tab_changed(self, index):
        self.right_stack.setCurrentIndex(index)

    def _populate_org_tree(self, selected_org_id=None, auto_select_first=False, load_after_select=False):
        """从 org_units 表构建机构树，并显示各节点人数。"""
        self._org_tree_load_token += 1
        self._person_load_token += 1
        token = self._org_tree_load_token
        self.org_tree.clear()
        self.case_table.setRowCount(0)

        def do_load():
            try:
                direct_counts = count_entries_grouped_by_org()
                all_nodes = list_all_org_units()
                return {
                    "token": token,
                    "direct_counts": direct_counts,
                    "all_nodes": all_nodes,
                    "roots": [n for n in all_nodes if n.get("parent_id") is None],
                    "error": "",
                }
            except Exception as e:
                return {"token": token, "direct_counts": {}, "all_nodes": [], "roots": [], "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._org_tree_load_token:
                return
            if res.get("error"):
                print(f"[inventory-entry] load org tree failed: {res.get('error')}")
                return

            direct_counts = res.get("direct_counts") or {}
            all_nodes = res.get("all_nodes") or []
            roots = res.get("roots") or []

            # 构建父子关系映射
            by_parent = {}
            for n in all_nodes:
                by_parent.setdefault(n.get("parent_id"), []).append(n)

            # 递归计算每个节点的累计人数（包含子节点）
            subtree_counts = {}

            def calc_subtree_count(org_id):
                if org_id in subtree_counts:
                    return subtree_counts[org_id]
                total = direct_counts.get(org_id, 0)
                for child in by_parent.get(org_id, []):
                    child_id = int(child.get("id"))
                    total += calc_subtree_count(child_id)
                subtree_counts[org_id] = total
                return total

            for n in all_nodes:
                calc_subtree_count(int(n.get("id")))

            def create_tree_item(name: str, org_id, count: int) -> QTreeWidgetItem:
                display_text = f"{name} ({count})" if count > 0 else name
                item = QTreeWidgetItem([display_text])
                item.setData(0, Qt.UserRole, org_id)
                if count > 0:
                    item.setToolTip(0, f"{name}：共 {count} 人")
                return item

            def add_children(parent_item: QTreeWidgetItem, parent_id):
                for n in by_parent.get(parent_id, []) or []:
                    org_id = int(n.get("id"))
                    count = subtree_counts.get(org_id, 0)
                    it = create_tree_item(n.get("name") or "", org_id, count)
                    parent_item.addChild(it)
                    add_children(it, org_id)

            self.org_tree.setUpdatesEnabled(False)
            try:
                self.org_tree.clear()
                unclassified_count = direct_counts.get(None, 0)
                unc = create_tree_item("未分类", None, unclassified_count)
                self.org_tree.addTopLevelItem(unc)

                for r in roots:
                    org_id = int(r.get("id"))
                    count = subtree_counts.get(org_id, 0)
                    it = create_tree_item(r.get("name") or "", org_id, count)
                    self.org_tree.addTopLevelItem(it)
                    add_children(it, org_id)
            finally:
                self.org_tree.setUpdatesEnabled(True)

            selected = False
            if selected_org_id is not None:
                selected = self._select_org_by_id(selected_org_id)
            if (not selected) and auto_select_first and self.org_tree.topLevelItemCount() > 0:
                self.org_tree.setCurrentItem(self.org_tree.topLevelItem(0))
            if load_after_select:
                current_item = self.org_tree.currentItem()
                if current_item:
                    self.load_personnel_for_org(current_item)

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

    def load_personnel_for_org(self, item, name_filter: str = ""):
        if item is None:
            return
        display_name = item.text(0)
        self.lbl_case_title.setText(f"📄 信息录入 - {display_name}")
        self._person_load_token += 1
        token = self._person_load_token

        self.case_table.setRowCount(0)
        # 重置全选复选框
        if hasattr(self, "cb_select_all"):
            self.cb_select_all.blockSignals(True)
            self.cb_select_all.setChecked(False)
            self.cb_select_all.blockSignals(False)
        try:
            org_unit_id = item.data(0, Qt.UserRole)
        except Exception as e:
            print(f"[catalog-entry] load entries failed: {e}")
            return

        self.lbl_case_title.setText(f"📄 信息录入 - {display_name}（加载中...）")
        sort_asc = self._sort_asc

        def do_load():
            try:
                persons = list_entries_by_org_unit_id(
                    org_unit_id,
                    sort_field="name",
                    sort_asc=sort_asc,
                    name_filter=name_filter,
                )
                return {"token": token, "display_name": display_name, "persons": persons, "error": ""}
            except Exception as e:
                return {"token": token, "display_name": display_name, "persons": [], "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._person_load_token:
                return
            self.lbl_case_title.setText(f"📄 信息录入 - {res.get('display_name') or display_name}")
            if res.get("error"):
                print(f"[catalog-entry] load entries failed: {res.get('error')}")
                return
            self._render_personnel_rows(res.get("persons") or [])

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

    def _render_personnel_rows(self, persons):
        self.case_table.setUpdatesEnabled(False)
        try:
            self.case_table.setRowCount(0)
            for p in persons:
                row = self.case_table.rowCount()
                self.case_table.insertRow(row)
                # col0：选择复选框（居中显示）。entry_id 存到“姓名”列 Qt.UserRole，避免 cellWidget 无法取 data。
                cb = QCheckBox()
                cb.setChecked(False)
                cb.setTristate(False)
                box = QWidget()
                lay = QHBoxLayout(box)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setAlignment(Qt.AlignCenter)
                lay.addWidget(cb)
                self.case_table.setCellWidget(row, 0, box)

                cells = [
                    p.get("name") or "",
                    p.get("emp_no") or "",
                    p.get("role_title") or "",
                    p.get("phone") or "",
                    p.get("id_card") or "",
                    p.get("status") or "",
                ]
                for col, value in enumerate(cells, start=1):
                    cell = QTableWidgetItem(value)
                    cell.setTextAlignment(Qt.AlignCenter)
                    if col == 1:
                        cell.setData(Qt.UserRole, p.get("id"))
                    self.case_table.setItem(row, col, cell)
        finally:
            self.case_table.setUpdatesEnabled(True)

    def _org_options_flat(self):
        """
        为“新增人员”弹窗生成机构下拉选项：
        - 第一项：未分类（None）
        - 后续：按树结构缩进展示
        """
        options = [(None, "（空/未分类）")]
        try:
            all_nodes = list_all_org_units()
        except Exception:
            all_nodes = []
        by_parent = {}
        by_id = {}
        for n in all_nodes:
            oid = int(n.get("id"))
            by_id[oid] = n
            by_parent.setdefault(n.get("parent_id"), []).append(oid)

        def walk(parent_id, depth: int):
            for cid in by_parent.get(parent_id, []) or []:
                name = (by_id.get(cid) or {}).get("name") or ""
                label = ("　" * depth) + name  # 全角空格缩进
                options.append((cid, label))
                walk(cid, depth + 1)

        # roots
        for r in [n for n in all_nodes if n.get("parent_id") is None]:
            rid = int(r.get("id"))
            name = r.get("name") or ""
            options.append((rid, name))
            walk(rid, 1)
        return options

    def _on_add_person(self):
        # 默认机构：当前选择的机构（允许为空）
        cur = self.org_tree.currentItem()
        default_org_unit_id = None
        try:
            default_org_unit_id = cur.data(0, Qt.UserRole) if cur else None
        except Exception:
            default_org_unit_id = None

        tpl_id = None
        try:
            tpl_id = get_default_template_id()
        except Exception:
            tpl_id = None
        if not tpl_id:
            StyledMessageBox.warning(self, "提示", "当前系统没有目录模板，无法新增人员。请先创建目录模板。", self.current_theme)
            return

        dlg = PersonCreateDialog(
            org_options=self._org_options_flat(),
            default_org_unit_id=default_org_unit_id,
            parent=self,
        )
        if dlg.exec_() != dlg.Accepted:
            return
        data = dlg.get_data()
        name = (data.get("name") or "").strip()
        if not name and not (data.get("emp_no") or "").strip():
            StyledMessageBox.warning(self, "提示", "请至少填写姓名或工号", self.current_theme)
            return

        try:
            create_entry_person(
                owner_id=1,
                template_id=int(tpl_id),
                name=name,
                emp_no=data.get("emp_no") or "",
                role_title=data.get("role_title") or "",
                phone=data.get("phone") or "",
                status=data.get("status") or "",
                id_card=data.get("id_card") or "",
                org_unit_id=data.get("org_unit_id"),
            )
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"新增人员失败：{e}", self.current_theme)
            return

        # 刷新机构树（更新人数统计）
        self._refresh_org_tree_keep_selection(load_after_select=True)

    def _refresh_org_tree_keep_selection(self, load_after_select=False):
        """刷新机构树并保持当前选中状态"""
        current_item = self.org_tree.currentItem()
        current_org_id = current_item.data(0, Qt.UserRole) if current_item else None
        self._populate_org_tree(
            selected_org_id=current_org_id,
            auto_select_first=True,
            load_after_select=load_after_select,
        )

    def _on_sort_refresh(self):
        """切换排序方向并刷新数据（同时刷新机构树和人员表）"""
        # 切换排序状态
        self._sort_asc = not self._sort_asc
        
        # 记住当前选中的机构ID
        current_item = self.org_tree.currentItem()
        current_org_id = current_item.data(0, Qt.UserRole) if current_item else None
        
        # 刷新机构树（从数据库重新获取最新数据）
        self._populate_org_tree(
            selected_org_id=current_org_id,
            auto_select_first=True,
            load_after_select=True,
        )
    
    def _select_org_by_id(self, org_id):
        """根据org_id选中机构树中的节点"""
        def find_item(parent_item, target_id):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.data(0, Qt.UserRole) == target_id:
                    return child
                found = find_item(child, target_id)
                if found:
                    return found
            return None
        
        # 搜索顶级节点
        for i in range(self.org_tree.topLevelItemCount()):
            top_item = self.org_tree.topLevelItem(i)
            if top_item.data(0, Qt.UserRole) == org_id:
                self.org_tree.setCurrentItem(top_item)
                return True
            found = find_item(top_item, org_id)
            if found:
                self.org_tree.setCurrentItem(found)
                return True
        return False

    def _on_delete_person(self):
        """删除选中的人员"""
        # 收集选中的人员ID
        selected_ids = []
        for row in range(self.case_table.rowCount()):
            cb_widget = self.case_table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb and cb.isChecked():
                    # 从姓名列获取entry_id
                    name_item = self.case_table.item(row, 1)
                    if name_item:
                        entry_id = name_item.data(Qt.UserRole)
                        if entry_id:
                            selected_ids.append(entry_id)
        
        if not selected_ids:
            StyledMessageBox.information(self, "提示", "请先选择要删除的人员", self.current_theme)
            return
        
        # 确认删除
        reply = StyledMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(selected_ids)} 条记录吗？\n此操作不可恢复！",
            theme=self.current_theme
        )
        
        if reply != StyledMessageBox.Yes:
            return
        
        # 执行删除
        deleted_count = 0
        for entry_id in selected_ids:
            try:
                if delete_entry(entry_id):
                    deleted_count += 1
            except Exception as e:
                print(f"[delete-entry] failed for {entry_id}: {e}")
        
        # 刷新机构树（更新人数统计）
        self._refresh_org_tree_keep_selection(load_after_select=True)
        
        if deleted_count > 0:
            StyledMessageBox.information(self, "完成", f"成功删除 {deleted_count} 条记录", self.current_theme)

    def _get_org_data(self):
        return [
            {
                "name": "国家图书馆总馆",
                "children": [
                    {
                        "name": "国家图书馆东馆",
                        "children": [
                            {"name": "东馆少儿部", "children": []},
                        ],
                    },
                    {"name": "国家图书馆文献修复中心", "children": []},
                ],
            },
            {
                "name": "省档案馆",
                "children": [
                    {"name": "省档案馆第一分馆", "children": []},
                    {"name": "省档案馆第二分馆", "children": []},
                ],
            },
            {
                "name": "市政务中心档案室",
                "children": [
                    {"name": "市政务中心档案室（新区）", "children": []},
                ],
            },
        ]

    def on_case_double_clicked(self, item):
        """双击案件行，打开全屏录入对话框（仅允许打开一个，应用级模态）"""
        if item is None:
            return

        row = item.row()
        data = {}
        headers = ["姓名", "工号", "岗位", "电话", "身份证号", "状态"]
        # 跳过第0列“选择”
        for col, header in enumerate(headers, start=1):
            cell = self.case_table.item(row, col)
            data[header] = cell.text() if cell else ""
        # 传递 entry_id 便于后续复用
        entry_id_cell = self.case_table.item(row, 1)
        if entry_id_cell:
            data["entry_id"] = entry_id_cell.data(Qt.UserRole)

        # 加载自定义字段（从数据库读取完整 entry 信息）
        if data.get("entry_id"):
            try:
                from .repo.inventory_entry_repo import get_entry_info
                full_info = get_entry_info(entry_id=int(data["entry_id"]))
                if full_info:
                    data["custom_fields"] = full_info.get("custom_fields") or ""
            except Exception:
                pass

        dialog = InventoryEntryDialog(data, parent=self)
        dialog.setWindowModality(Qt.ApplicationModal)
        # 设置为可用最大化按钮，并在显示前请求最大化
        dialog.setWindowState(dialog.windowState() | Qt.WindowMaximized)
        dialog.showMaximized()
        dialog.exec_()           # 阻塞，关闭后才能操作原界面

    def apply_theme(self):
        # 与现有页面保持一致的常量命名方式
        self.setStyleSheet(
            InventoryReceiveStyle.DARK_STYLE
            if self.current_theme == "dark"
            else InventoryReceiveStyle.LIGHT_STYLE
        )
        self._apply_toolbar_style()
        self._apply_catalog_btn_style()
        self._apply_catalog_btn_style()

    def update_theme(self, theme_name):
        self.current_theme = theme_name
        self.apply_theme()

    def _apply_toolbar_style(self):
        """同步模板选择区与操作按钮的样式，适配主题（录入列表页）。"""
        if self.current_theme == "dark":
            bg = "#1f2937"
            border = "#2f3a4c"
            text = "#e5e7eb"
            combo_bg = "#2b3544"
        else:
            bg = "#f7f9fb"
            border = "#d0d7de"
            text = "#1f2937"
            combo_bg = "#ffffff"

        if hasattr(self, "action_frame"):
            self.action_frame.setStyleSheet(
                f"""
                QFrame#catalog_action_frame {{
                    background: {bg};
                    border: 1px solid {border};
                    border-radius: 6px;
                }}
                """
            )
        if hasattr(self, "tpl_combo"):
            self.tpl_combo.setStyleSheet(
                f"""
                QLabel#tpl_label {{
                    color: {text};
                    font-size: 14px;
                }}
                QComboBox#tpl_combo {{
                    background: {combo_bg};
                    border: 1px solid {border};
                    border-radius: 6px;
                    padding: 6px 10px;
                    color: {text};
                    min-height: 28px;
                }}
                QComboBox#tpl_combo::drop-down {{
                    width: 22px;
                    border: none;
                }}
                """
            )

    def _apply_catalog_btn_style(self):
        """为目录录入 Tab 的操作按钮单独设置样式。"""
        if not hasattr(self, "btn_cat_add_peer"):
            return
        btn_style = """
        QPushButton#catalog_action_btn {
            background: #f5f7fa;
            border: 1px solid #cfd8dc;
            border-radius: 6px;
            padding: 4px 10px;
            color: #1f2937;
            font-weight: 600;
            min-height: 26px;
        }
        QPushButton#catalog_action_btn:hover {
            background: #e8f0fe;
            border: 1px solid #90a4ae;
        }
        QPushButton#catalog_action_btn:pressed {
            background: #dbeafe;
            border: 1px solid #7b8794;
        }
        """
        for btn in (self.btn_cat_add_peer, self.btn_cat_add_child, self.btn_cat_del):
            btn.setStyleSheet(btn_style)

    def _apply_catalog_btn_style(self):
        """为目录录入 Tab 的操作按钮单独设置样式，避免被父级样式覆盖。"""
        if not hasattr(self, "btn_cat_add_peer"):
            return
        btn_style = """
        QPushButton#catalog_action_btn {
            background: #f5f7fa;
            border: 1px solid #cfd8dc;
            border-radius: 6px;
            padding: 4px 10px;
            color: #1f2937;
            font-weight: 600;
            min-height: 26px;
        }
        QPushButton#catalog_action_btn:hover {
            background: #e8f0fe;
            border: 1px solid #90a4ae;
        }
        QPushButton#catalog_action_btn:pressed {
            background: #dbeafe;
            border: 1px solid #7b8794;
        }
        """
        for btn in (self.btn_cat_add_peer, self.btn_cat_add_child, self.btn_cat_del):
            btn.setStyleSheet(btn_style)


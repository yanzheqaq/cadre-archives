import os

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QButtonGroup,
                             QTableWidgetItem, QHeaderView, QPushButton, QLabel, QSplitter, QStackedWidget,
                             QListWidget, QListWidgetItem, QAbstractItemView, QToolButton)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon

from common.config import AppSettings
from main_ui.config_pages import PagesConfig
from .style_archive import ArchiveReceiveStyle

ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icons'))

class ArchiveReceiveWidget(QWidget):
    """
    二级页面：档案接收
    左右两栏设计：左侧批次列表，右侧案件详情表格
    """
    def __init__(self):
        super().__init__()
        self.config_manager = AppSettings()
        self.current_theme = self.config_manager.load_theme_preference()
        self.initUI()
        self.apply_theme()

    def initUI(self):
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. 顶部工具栏 (选项卡)
        tool_bar = QHBoxLayout()
        tool_bar.setContentsMargins(0, 0, 0, 0)
        
        # 使用 QButtonGroup 管理两个选项卡按钮，实现互斥
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        
        # 选项卡 1: 所有批次
        self.btn_all_batches = QPushButton("所有批次")
        self.btn_all_batches.setCursor(Qt.PointingHandCursor)
        self.btn_all_batches.setCheckable(True)
        self.btn_all_batches.setChecked(True) # 默认选中
        self.btn_all_batches.setObjectName("tab_btn")
        self.tab_group.addButton(self.btn_all_batches, 0)
        
        # 选项卡 2: 已接收批次
        self.btn_received_batches = QPushButton("已接收批次")
        self.btn_received_batches.setCursor(Qt.PointingHandCursor)
        self.btn_received_batches.setCheckable(True)
        self.btn_received_batches.setObjectName("tab_btn")
        self.tab_group.addButton(self.btn_received_batches, 1)
        
        # 连接信号
        self.tab_group.buttonClicked[int].connect(self.on_tab_changed)

        tool_bar.addWidget(self.btn_all_batches)
        tool_bar.addWidget(self.btn_received_batches)
        tool_bar.addStretch()

        # 右侧选项卡与左侧同一行
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

        self.right_tab_group.buttonClicked[int].connect(self.on_right_tab_changed)

        tool_bar.addWidget(self.btn_tab_detail)
        tool_bar.addWidget(self.btn_tab_process)
        
        main_layout.addLayout(tool_bar)

        # 2. 左右分割布局
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setObjectName("main_splitter")

        # === 左侧：批次列表 ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        # 左侧标题改为功能按钮组
        func_btn_layout = QHBoxLayout()
        func_btn_layout.setSpacing(PagesConfig.BATCH_FUNC_ICON_SPACING)
        
        # 定义左侧功能按钮 (仅图标 + tooltip)
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
        
        func_btn_layout.addStretch()
            
        left_layout.addLayout(func_btn_layout)

        # 批次列表控件
        self.batch_list = QListWidget()
        self.batch_list.setAlternatingRowColors(True)
        self.batch_list.setObjectName("batch_list")
        
        # 模拟批次数据
        batches = ["REC-20231128-001 (人事科)", "REC-20231128-002 (财务科)", "REC-20231127-005 (基建科)", "REC-20231126-003 (档案室)"]
        for batch in batches:
            item = QListWidgetItem(batch)
            self.batch_list.addItem(item)
            
        # 默认选中第一项
        if self.batch_list.count() > 0:
            self.batch_list.setCurrentRow(0)
            
        # 连接点击信号
        self.batch_list.itemClicked.connect(self.load_cases_for_batch)

        left_layout.addWidget(self.batch_list)
        
        # === 右侧：案件详情表格 + 选项卡 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0) # 左边距留点空隙
        right_layout.setSpacing(5)

        # 右侧标题 (动态显示当前批次)
        self.lbl_case_title = QLabel("📄 案件列表")
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

        # 右侧堆叠窗口
        self.right_stack = QStackedWidget()

        # --- 页面1：批次详情（现有案件表格） ---
        detail_page = QWidget()
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # 案件表格
        self.case_table = QTableWidget()
        self.case_table.setColumnCount(5)
        self.case_table.setHorizontalHeaderLabels(["案件号", "档号", "案由", "当事人", "页数"])
        self.case_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.case_table.setEditTriggers(QAbstractItemView.NoEditTriggers) # 不可编辑
        self.case_table.setObjectName("case_table")
        
        # 表格样式配置
        self.case_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.case_table.setAlternatingRowColors(True)
        self.case_table.verticalHeader().setVisible(False)

        detail_layout.addWidget(self.case_table)

        # --- 页面2：加工情况（占位） ---
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

        # 将左右部件加入分割器
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        
        # 设置初始比例 (例如 1:3)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter)
        
        # 初始加载数据
        self.load_cases_for_batch(self.batch_list.currentItem())

    def on_tab_changed(self, tab_index):
        """
        切换选项卡时触发
        tab_index: 0=所有批次, 1=已接收批次
        """
        self.batch_list.clear()
        self.case_table.setRowCount(0)
        self.lbl_case_title.setText("📄 案件列表")
        
        if tab_index == 0:
            # 加载所有批次
            batches = ["REC-20231128-001 (人事科)", "REC-20231128-002 (财务科)", "REC-20231127-005 (基建科)", "REC-20231126-003 (档案室)"]
        else:
            # 加载已接收批次 (模拟数据)
            batches = ["REC-20231128-002 (财务科) [已完成]", "REC-20231126-003 (档案室) [已完成]"]
            
        for batch in batches:
            item = QListWidgetItem(batch)
            self.batch_list.addItem(item)
            
        # 默认选中第一项
        if self.batch_list.count() > 0:
            self.batch_list.setCurrentRow(0)
            self.load_cases_for_batch(self.batch_list.currentItem())

    def load_cases_for_batch(self, item):
        """根据选中的批次加载案件数据"""
        if not item:
            return
            
        batch_name = item.text()
        self.lbl_case_title.setText(f"📄 档案接收 - {batch_name}")
        
        # 模拟不同批次的数据
        self.case_table.setRowCount(0) # 清空旧数据
        
        if "001" in batch_name:
            cases = [
                ("AJ-2023-001", "DH-001-001", "劳动合同纠纷", "张三", "25"),
                ("AJ-2023-002", "DH-001-002", "工伤赔偿", "李四", "30"),
                ("AJ-2023-003", "DH-001-003", "离职补偿", "王五", "15"),
            ]
        elif "002" in batch_name:
            cases = [
                ("AJ-2023-010", "DH-002-001", "财务报表审核", "公司财务部", "120"),
                ("AJ-2023-011", "DH-002-002", "税务申报", "税务局", "45"),
            ]
        else:
            cases = []

        self.case_table.setRowCount(len(cases))
        for row_idx, case_data in enumerate(cases):
            for col_idx, cell_data in enumerate(case_data):
                item = QTableWidgetItem(cell_data)
                item.setTextAlignment(Qt.AlignCenter)
                self.case_table.setItem(row_idx, col_idx, item)

    def on_right_tab_changed(self, tab_index):
        """切换右侧选项卡"""
        self.right_stack.setCurrentIndex(tab_index)

    def update_theme(self, theme_name):
        """响应主题切换"""
        self.current_theme = theme_name
        self.apply_theme()

    def apply_theme(self):
        """应用当前主题样式"""
        if self.current_theme == "light":
            self.setStyleSheet(ArchiveReceiveStyle.LIGHT_STYLE)
        else:
            self.setStyleSheet(ArchiveReceiveStyle.DARK_STYLE)

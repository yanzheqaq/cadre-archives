import os
import shutil
import mimetypes
from collections import OrderedDict
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSplitter,
    QAbstractItemView, QToolButton, QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QTreeWidget, QTreeWidgetItem, QApplication, QTabWidget, QFrame, QComboBox, QMessageBox,
    QSizePolicy, QFileDialog, QListWidget, QListWidgetItem, QStyle, QHeaderView,
    QStyledItemDelegate, QStyleOptionViewItem, QGridLayout, QMenu, QProgressBar, QInputDialog,
    QLayout,
)
from PyQt5.QtCore import Qt, QSize, QThreadPool, QTimer, QModelIndex, QEvent, QItemSelectionModel
from PyQt5.QtGui import QIcon, QFont, QFontMetrics, QWheelEvent, QPixmap, QImage, QKeyEvent

from common.config import AppConfig, AppSettings
from common.services.crypto_service import CryptoService
from common.services.scanner_service import ScannerSettings, get_scanner_service
from .widgets.image_preview import ImagePreview
from .widgets.qt_worker import Worker
from .utils.image_loading import cache_key, lru_get, lru_put, load_qimage_any, resolve_image_path
from .services.image_edit_service import (
    dominant_border_color,
    is_dirty,
    legacy_crop_and_save,
    legacy_detect_black_border_crop_box_from_path,
    legacy_rotate_with_white_bg_and_save,
    mm_to_pixels,
    new_pending,
    process_and_save,
    render_preview_qimage,
)
from .repo.inventory_entry_repo import (
    count_entry_total_images,
    create_catalog_template_item,
    delete_catalog_template_items_and_entry_catalog_items,
    delete_empty_entry_catalog_items,  # Import the empty-catalog purge helper
    merge_duplicate_entry_catalog_items,  # 数据安全：合并同槽位重复 EC 行（杜绝"每类第一条都没了"）
    delete_entry_catalog_rows_only,  # 方案A：用户删行时只删本 entry 的 EC 行，不级联删模板条目
    delete_orphan_template_item_safely,  # 孤儿清理：仅当无 EC 引用时才删模板，杜绝跨 entry 数据丢失
    delete_entry_item_image,
    ensure_entry_catalog_item,
    ensure_entry_record,
    find_entry_for_autoselect,
    get_entry_catalog_item_readonly,
    get_entry_info,
    get_next_image_sort_base,
    list_catalog_template_items,
    list_catalog_templates,
    list_entry_item_images,
    resolve_edit_base_image_info,
    resolve_original_image_info,
    set_cover_image,
    swap_catalog_template_item_sort_order,
    swap_entry_catalog_item_order,
    swap_image_sort_order,
    upsert_entry_catalog_item_field,
    batch_get_entry_catalog_items,
    upsert_entry_catalog_item_fields,
    upsert_original_images,
    upsert_retouched_batch,
    upsert_single_retouched,
    update_entry_person_fields,
    move_catalog_template_items_to_parent,
    migrate_entry_catalog_items_to_parent,
)


from PyQt5.QtCore import pyqtSignal

from common.services.upload_queue_service import (
    build_upload_task,
    get_upload_queue_manager,
)
from common.services.catalog_wal_service import get_catalog_wal

# 自动补全模块
from .autocomplete_manager import get_autocomplete_manager
from .autocomplete_popup import AutocompletePopup
from .styled_message_box import StyledMessageBox
from .print_preview_dialog import PrintPreviewDialog
from .ai_retouch_config_dialog import AIRetouchConfigDialog
from .widgets.person_create_dialog import _make_field_combo


class CatalogTreeDelegate(QStyledItemDelegate):
    """
    目录树编辑代理：控制哪些单元格可以编辑，并处理 Tab 键在同一行内切换列。
    - 编号(0) 和 目录名称(1)：如果模板有预设值，则不允许编辑
    - Tab键：在同一行内切换列，不换行
    - 自动补全：输入时自动显示候选词
    """
    # 信号：请求编辑指定列 (item, column)
    requestEditColumn = pyqtSignal(object, int)
    # 信号：请求自动补全 (item, column, editor, input_text)
    requestAutocomplete = pyqtSignal(object, int, object, str)
    # 信号：弹窗上下选择 (direction: -1=上, 1=下)
    autocompleteMove = pyqtSignal(int)
    # 信号：确认补全选择
    autocompleteConfirm = pyqtSignal()
    # 信号：隐藏补全弹窗
    autocompleteHide = pyqtSignal()
    # 信号：请求 Enter 键换行 (item)
    requestEnterNewRow = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_editor = None
        self._current_item = None
        self._current_col = -1
        self._setting_editor_data = False  # 防止 setEditorData 时触发自动补全
        self._autocomplete_request_seq = 0
        # 用于检查弹窗是否可见的回调函数
        self._is_popup_visible_fn = None
    
    def set_popup_visible_checker(self, fn):
        """设置检查弹窗是否可见的回调函数。"""
        self._is_popup_visible_fn = fn
    
    def _is_popup_visible(self):
        """检查自动补全弹窗是否可见。"""
        if self._is_popup_visible_fn:
            return self._is_popup_visible_fn()
        return False

    def setEditorData(self, editor, index):
        self._setting_editor_data = True
        try:
            super().setEditorData(editor, index)
        finally:
            self._setting_editor_data = False
        # ⚠️ 这里**绝对不要**再加 ``QTimer.singleShot(0, lambda: editor.end(False))``。
        # QLineEdit::setText 已经把光标放到末尾（Qt 文档承诺的行为），end() 在空编辑器
        # 上视觉无变化，但会同步发 cursorPositionChanged。如果用户用拼音输入法刚敲了
        # 首字母（IME 已开始 composition），这个 0ms timer 在事件循环里抢在用户后续
        # 按键之前 fire，cursorPositionChanged 让 IME 取消当前 composition，导致首字母
        # 丢失（用户可见现象：输入 "zhende" 想打"真的"，IME 显示框只剩 "hende"）。
        # 已确认：super().setEditorData → editor.setProperty("text", value) →
        # QLineEdit::setText 自带光标置末，无需补一刀。

    def createEditor(self, parent, option, index: QModelIndex):
        column = index.column()
        # 编号(0) 和 目录名称(1)：大类（根级类别）不可编辑
        if column in (0, 1):
            tree = self.parent()
            if tree:
                item = tree.itemFromIndex(index)
                if item and (item.parent() is None or item.parent() == tree.invisibleRootItem()):
                    return None  # 大类节点禁止编辑编号和名称
        # 创建编辑器并安装事件过滤器
        editor = super().createEditor(parent, option, index)
        if editor:
            try:
                editor.setFont(option.font)
            except Exception:
                pass
            self._autocomplete_request_seq += 1
            self._current_editor = editor
            self._current_col = column
            # 保存 item 引用
            tree = self.parent()
            if tree:
                self._current_item = tree.itemFromIndex(index)
            try:
                editor.setAttribute(Qt.WA_InputMethodEnabled, True)
                editor.setFocus(Qt.OtherFocusReason)
            except Exception:
                pass
            editor.installEventFilter(self)
            
            # 如果是目录名称列（列 1），连接文本变化信号以触发自动补全
            if column == 1 and hasattr(editor, 'textChanged'):
                editor.textChanged.connect(self._on_text_changed_for_autocomplete)
        return editor

    def _on_text_changed_for_autocomplete(self, text):
        """文本变化时触发自动补全。

        注意：**绝对不要**在这里调用 ``self._current_item.setText(1, text)``。
        ``setText`` 会同步触发 ``itemChanged → _on_catalog_item_changed``，
        该链路里包含 ``_ensure_entry_record()``（同步 DB 查询）以及 view 层
        ``dataChanged → setEditorData`` 的重入，会让用户键入的首字在某些
        时序下被刷新覆盖一次（看起来就是“字闪一下就消失”）。

        数据安全由以下三条独立保障：
        1. ``destroyEditor`` 在 editor 被销毁前会兜底把 ``editor.text()`` 写回 item；
        2. Tab / Enter / 切行：delegate 的事件过滤器显式 ``commitData`` + ``closeEditor``；
        3. 关对话框：``closeEvent`` / ``accept`` 在 sync flush 之前先调用
           ``_commit_active_catalog_editor`` 把当前 editor 的输入提交到 item / pending / WAL。
        """
        if self._setting_editor_data:
            return
        if self._current_item and self._current_col == 1 and self._current_editor:
            self._autocomplete_request_seq += 1
            seq = self._autocomplete_request_seq
            item = self._current_item
            column = self._current_col
            editor = self._current_editor

            def emit_later():
                if self._setting_editor_data:
                    return
                if seq != self._autocomplete_request_seq:
                    return
                if item is not self._current_item or column != self._current_col or editor is not self._current_editor:
                    return
                try:
                    if editor is None or editor.text() != text:
                        return
                except RuntimeError:
                    return
                self.requestAutocomplete.emit(item, column, editor, text)

            QTimer.singleShot(50, emit_later)

    def eventFilter(self, obj, event):
        """Tab键在同一行内切换列，不换行。自动补全在输入时自动触发。"""
        # 弹窗可见时拦截编辑器的失焦事件，防止编辑器被提交/销毁（鼠标点击弹窗会触发此事件）
        if obj == self._current_editor and event.type() == QEvent.FocusOut:
            if self._is_popup_visible():
                return True
        if obj == self._current_editor and event.type() == QEvent.KeyPress:
            key = event.key()
            tree = self.parent()
            popup_visible = self._is_popup_visible()
            
            # 如果弹窗可见，处理上下键和确认键
            if popup_visible:
                if key == Qt.Key_Up:
                    self.autocompleteMove.emit(-1)
                    return True
                elif key == Qt.Key_Down:
                    self.autocompleteMove.emit(1)
                    return True
                elif key == Qt.Key_Tab:
                    # Tab 键：确认自动补全选择
                    self.autocompleteConfirm.emit()
                    return True
                elif key == Qt.Key_Escape:
                    self.autocompleteHide.emit()
                    return True
                elif key in (Qt.Key_Return, Qt.Key_Enter):
                    # Enter 键：确认自动补全选择，不换行
                    self.autocompleteConfirm.emit()
                    return True
            
            if key == Qt.Key_Tab and tree and self._current_item:
                # 先保存需要的数据，因为 closeEditor 后 destroyEditor 会清空 _current_item
                item = self._current_item
                col_count = tree.columnCount()
                next_col = self._current_col + 1
                
                # 如果超出最后一列，跳到下一行的目录名称列（列1），不跳过任何行
                if next_col >= col_count:
                    current_index = tree.indexFromItem(item)
                    next_index = tree.indexBelow(current_index)
                    if next_index.isValid():
                        next_item = tree.itemFromIndex(next_index)
                        if next_item:
                            item = next_item
                            next_col = 1  # 目录名称列
                        else:
                            next_col = col_count - 1  # 保持在最后一列
                    else:
                        next_col = col_count - 1  # 保持在最后一列
                
                # 提交当前编辑
                self.commitData.emit(self._current_editor)
                self.closeEditor.emit(self._current_editor, QStyledItemDelegate.NoHint)
                # 通过信号通知 dialog 编辑下一列
                self.requestEditColumn.emit(item, next_col)
                return True  # 拦截 Tab
            elif key == Qt.Key_Backtab and tree and self._current_item:  # Shift+Tab
                # 先保存需要的数据
                item = self._current_item
                col_count = tree.columnCount()
                prev_col = (self._current_col - 1) % col_count
                self.commitData.emit(self._current_editor)
                self.closeEditor.emit(self._current_editor, QStyledItemDelegate.NoHint)
                self.requestEditColumn.emit(item, prev_col)
                return True
            elif key in (Qt.Key_Return, Qt.Key_Enter) and tree and self._current_item:
                # Enter键：同行列切换 序号(0)→目录名称(1)→年(2)→月(3)→日(4)→页数(5)→下一行目录名称(1)
                item = self._current_item
                col = self._current_col
                # 列0-4：移到同行下一列
                _ENTER_NEXT = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
                if col in _ENTER_NEXT:
                    next_col = _ENTER_NEXT[col]
                    self.commitData.emit(self._current_editor)
                    self.closeEditor.emit(self._current_editor, QStyledItemDelegate.NoHint)
                    self.requestEditColumn.emit(item, next_col)
                else:
                    # 列5/6：提交后跳到下一行
                    self.commitData.emit(self._current_editor)
                    self.closeEditor.emit(self._current_editor, QStyledItemDelegate.NoHint)
                    self.requestEnterNewRow.emit(item)
                return True  # 拦截 Enter，避免传递到对话框按钮
        return super().eventFilter(obj, event)

    def sizeHint(self, option, index):
        if index.column() == 1:
            tree = self.parent()
            col_w = tree.columnWidth(1) if tree else 200
            text = index.data(Qt.DisplayRole) or ""
            if text:
                opt = QStyleOptionViewItem(option)
                self.initStyleOption(opt, index)
                fm = QFontMetrics(opt.font)
                br = fm.boundingRect(0, 0, max(1, col_w - 8), 10000,
                                     Qt.AlignLeft | Qt.TextWordWrap, text)
                return QSize(col_w, max(br.height() + 8, 24))
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        if index.column() == 1:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            text = opt.text
            opt.text = ""  # suppress text so style only draws background/selection/lines
            _widget = self.parent()
            _style = _widget.style() if _widget else QApplication.style()
            _style.drawControl(QStyle.CE_ItemViewItem, opt, painter, _widget)
            if text:
                painter.save()
                if option.state & QStyle.State_Selected:
                    painter.setPen(Qt.black)
                else:
                    fg = index.data(Qt.ForegroundRole)
                    try:
                        painter.setPen(fg.color())
                    except (AttributeError, TypeError):
                        painter.setPen(opt.palette.text().color())
                painter.setFont(opt.font)
                text_rect = opt.rect.adjusted(4, 2, -4, -2)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, text)
                painter.restore()
            return
        super().paint(painter, option, index)

    def setModelData(self, editor, model, index):
        try:
            if editor is not None and hasattr(editor, "text"):
                model.setData(index, editor.text(), Qt.EditRole)
                return
        except RuntimeError:
            return
        super().setModelData(editor, model, index)

    def destroyEditor(self, editor, index):
        # 销毁兜底：在 Qt 把 editor 销毁掉之前，把 editor 的当前文本写回 QTreeWidgetItem。
        # 正常 commit 路径（Tab / Enter / 失焦）已经写过 item，此处的 setText 会因为
        # `item.text(col) == text` 直接跳过；只有在 Qt 走异常关闭路径（例如父控件销毁、
        # 树重建）没有调到 commitData/setModelData 时，这一段才会真正落字段。
        # 触发的 itemChanged 会进入 _on_catalog_item_changed → _stage_pending → WAL，
        # 与 Tab/Enter 路径完全等价，因此不会破坏「不丢数据 / 关闭时 sync flush」契约。
        try:
            if (editor is not None
                    and editor == self._current_editor
                    and self._current_item is not None
                    and self._current_col >= 0
                    and hasattr(editor, "text")):
                text = editor.text()
                if self._current_item.text(self._current_col) != text:
                    self._current_item.setText(self._current_col, text)
        except RuntimeError:
            # editor / item 的 C++ 对象已被销毁，安静忽略——此时数据要么已经
            # 落盘，要么由 closeEvent/accept 的 sync flush 兜底
            pass
        if editor == self._current_editor:
            self._autocomplete_request_seq += 1
            self._current_editor = None
            self._current_item = None
            self._current_col = -1
            # 编辑器关闭时隐藏自动补全弹窗
            self.autocompleteHide.emit()
        super().destroyEditor(editor, index)


class InventoryEntryDialog(QDialog):
    """
    案件录入示例对话框：全屏、应用级模态。
    可根据需要扩展字段或嵌入实际表单。
    """

    def __init__(self, case_data: dict, parent=None):
        super().__init__(parent)
        self.case_data = case_data
        title_name = case_data.get("姓名") or case_data.get("工号") or case_data.get("案卷号", "")
        self._title_text = f"录入 - {title_name}"
        # 状态变量
        # 优先使用外部传入的 entry_id，保证“信息总览”可立即实时保存
        self.current_entry_id = self.case_data.get("entry_id")
        self.current_template_id = None
        self._suppress_catalog_changed = False
        self.setWindowTitle(self._title_text)
        # 使用无边框窗口，自定义标题栏颜色与主窗口一致（避免系统默认标题栏）
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.CustomizeWindowHint)
        # 提供一个合理的最小尺寸，防止窗口过小
        screen_geo = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(1200, 800)
        # 窗口初始大小尽量贴近可用屏幕
        if screen_geo.isValid():
            self.resize(screen_geo.width(), screen_geo.height())
        # 继承父窗口的主题（用于标题条颜色）
        self.current_theme = getattr(parent, "current_theme", "light")
        self._drag_pos = None
        # 目录录入字体缩放
        self._base_font: QFont = self.font()
        self._catalog_font_size = max(12.0, self._base_font.pointSizeF())
        self._font_min = 9.0
        self._font_max = 20.0
        # 图片加载：线程池 + token（防止快速切换串图）+ 简单 LRU 缓存（减少重复解码抖动）
        self._thread_pool = QThreadPool.globalInstance()
        self._scanner_settings = ScannerSettings()
        self._scan_in_progress = False
        self._thumb_token = 0
        self._preview_token = 0
        self._preload_token = 0  # 预加载 token，用于取消过时的预加载任务
        self._thumb_cache: "OrderedDict[tuple, QImage]" = OrderedDict()
        self._preview_cache: "OrderedDict[tuple, QImage]" = OrderedDict()
        self._thumb_cache_max = 256
        self._preview_cache_max = 24
        self._preview_expected_path = ""
        # 预加载配置
        self._preload_ahead = 1   # 向后预加载张数
        self._preload_behind = 0  # 向前预加载张数
        self._preloading_paths: set = set()  # 正在预加载的路径，避免重复提交
        # 刷新图片列表后恢复选中（避免“保存修图”后跳回第一张）
        # {"file_path": str, "img_id": int}
        self._select_after_reload = None
        self._date_warning_suppressed = False  # 年月日校验提示只弹一次
        self._catalog_name_editor = None
        self._catalog_name_editor_item = None
        self._catalog_name_editor_updating = False
        self._catalog_name_editor_seq = 0
        # 方案A：参数化修图（不立即落盘/写库），仅记录 pending 参数并实时预览
        # pending: {orig_id: {"angle": float, "crop_box": (l,t,r,b) or None}}
        self._pending_edits = {}
        self._image_view_mode = "retouched"
        self._image_view_restore_row = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # 自定义标题栏，与主窗口顶部颜色保持一致
        header = QFrame()
        header.setObjectName("dialog_header")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(8)

        title_label = QLabel(self._title_text)
        title_label.setObjectName("dialog_title_label")
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addStretch()
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("dialog_close_btn")
        close_btn.setFixedSize(32, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)

        if self.current_theme == "dark":
            header.setStyleSheet(
                "#dialog_header {"
                " background-color: #0f0f0f;"
                " border-bottom: 1px solid #333;"
                "}"
                "#dialog_title_label { color: white; font-weight: bold; font-size: 16px; }"
                "#dialog_close_btn { border: none; color: #ccc; background: transparent; }"
                "#dialog_close_btn:hover { background-color: rgba(255,255,255,0.1); color: white; }"
            )
        else:
            header.setStyleSheet(
                f"#dialog_header {{"
                f" background-color: {AppConfig.LIGHT_BTN_GRADIENT_START};"
                f" border-bottom: 1px solid {AppConfig.LIGHT_INPUT_BORDER};"
                f"}}"
                "#dialog_title_label { color: white; font-weight: bold; font-size: 16px; }"
                "#dialog_close_btn { border: none; color: white; background: transparent; }"
                "#dialog_close_btn:hover { background-color: rgba(255,255,255,0.15); }"
            )

        layout.addWidget(header)

        self.tab = QTabWidget()
        layout.addWidget(self.tab)

        # === Tab 1: 信息总览（人员基础信息，美化布局） ===
        info_widget = QWidget()
        info_main_layout = QVBoxLayout(info_widget)
        info_main_layout.setContentsMargins(20, 20, 20, 20)
        info_main_layout.setSpacing(16)
        
        # 标题区域
        title_label = QLabel("人员基本信息")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; padding-bottom: 8px;")
        info_main_layout.addWidget(title_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #e0e0e0;")
        line.setFixedHeight(1)
        info_main_layout.addWidget(line)
        
        # 信息卡片区域
        info_card = QFrame()
        info_card.setObjectName("info_card")
        info_card.setStyleSheet("""
            QFrame#info_card {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        card_layout = QGridLayout(info_card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setHorizontalSpacing(24)
        card_layout.setVerticalSpacing(12)
        
        # 标签样式
        label_style = "font-size: 13px; color: #666; font-weight: 500;"
        input_style = """
            QLineEdit, QComboBox {
                font-size: 14px;
                padding: 8px 12px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: #fafafa;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4A90D9;
                background-color: #ffffff;
            }
        """
        
        # 第一行：姓名、工号
        lbl_user = QLabel("姓名")
        lbl_user.setStyleSheet(label_style)
        self.le_user = QLineEdit(self.case_data.get("姓名", ""))
        self.le_user.setStyleSheet(input_style)
        self.le_user.setMinimumWidth(200)
        card_layout.addWidget(lbl_user, 0, 0)
        card_layout.addWidget(self.le_user, 0, 1)
        
        lbl_empid = QLabel("工号")
        lbl_empid.setStyleSheet(label_style)
        self.le_empid = QLineEdit(self.case_data.get("工号", ""))
        self.le_empid.setStyleSheet(input_style)
        self.le_empid.setMinimumWidth(200)
        card_layout.addWidget(lbl_empid, 0, 2)
        card_layout.addWidget(self.le_empid, 0, 3)
        
        # 第二行：岗位、电话
        lbl_role = QLabel("岗位")
        lbl_role.setStyleSheet(label_style)
        self.le_role = _make_field_combo("role_title", "请选择或输入岗位", self.case_data.get("岗位", ""))
        self.le_role.setStyleSheet(input_style)
        card_layout.addWidget(lbl_role, 1, 0)
        card_layout.addWidget(self.le_role, 1, 1)
        
        lbl_phone = QLabel("电话")
        lbl_phone.setStyleSheet(label_style)
        self.le_phone = QLineEdit(self.case_data.get("电话", ""))
        self.le_phone.setStyleSheet(input_style)
        card_layout.addWidget(lbl_phone, 1, 2)
        card_layout.addWidget(self.le_phone, 1, 3)
        
        # 第三行：身份证号、状态
        lbl_id_card = QLabel("身份证号")
        lbl_id_card.setStyleSheet(label_style)
        self.le_id_card = QLineEdit(self.case_data.get("身份证号", ""))
        self.le_id_card.setStyleSheet(input_style)
        card_layout.addWidget(lbl_id_card, 2, 0)
        card_layout.addWidget(self.le_id_card, 2, 1)
        
        lbl_status = QLabel("状态")
        lbl_status.setStyleSheet(label_style)
        self.le_status = _make_field_combo("status", "请选择或输入状态", self.case_data.get("状态", ""))
        self.le_status.setStyleSheet(input_style)
        card_layout.addWidget(lbl_status, 2, 2)
        card_layout.addWidget(self.le_status, 2, 3)

        lbl_ethnicity = QLabel("民族")
        lbl_ethnicity.setStyleSheet(label_style)
        self.le_ethnicity = QLineEdit(self._get_fixed_custom_field_value("民族"))
        self.le_ethnicity.setStyleSheet(input_style)
        self.le_ethnicity.setPlaceholderText("请输入民族")
        card_layout.addWidget(lbl_ethnicity, 3, 0)
        card_layout.addWidget(self.le_ethnicity, 3, 1)

        lbl_native_place = QLabel("籍贯")
        lbl_native_place.setStyleSheet(label_style)
        self.le_native_place = QLineEdit(self._get_fixed_custom_field_value("籍贯"))
        self.le_native_place.setStyleSheet(input_style)
        self.le_native_place.setPlaceholderText("请输入籍贯")
        card_layout.addWidget(lbl_native_place, 3, 2)
        card_layout.addWidget(self.le_native_place, 3, 3)

        lbl_birth_date = QLabel("出生日期")
        lbl_birth_date.setStyleSheet(label_style)
        self.le_birth_date = QLineEdit(self._get_fixed_custom_field_value("出生日期"))
        self.le_birth_date.setStyleSheet(input_style)
        self.le_birth_date.setPlaceholderText("如 1980-01-01")
        card_layout.addWidget(lbl_birth_date, 4, 0)
        card_layout.addWidget(self.le_birth_date, 4, 1)
        
        # 设置列伸缩
        card_layout.setColumnStretch(1, 1)
        card_layout.setColumnStretch(3, 1)
        
        info_main_layout.addWidget(info_card)

        # === 自定义扩展字段区域 ===
        custom_card = QFrame()
        custom_card.setObjectName("custom_fields_card")
        custom_card.setStyleSheet("""
            QFrame#custom_fields_card {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        custom_card_layout = QVBoxLayout(custom_card)
        custom_card_layout.setContentsMargins(20, 12, 20, 12)
        custom_card_layout.setSpacing(8)

        custom_header = QHBoxLayout()
        custom_title = QLabel("自定义字段")
        custom_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        custom_header.addWidget(custom_title)
        custom_header.addStretch()
        self.btn_add_custom_field = QPushButton("+ 添加字段")
        self.btn_add_custom_field.setCursor(Qt.PointingHandCursor)
        self.btn_add_custom_field.setFixedHeight(28)
        self.btn_add_custom_field.setAutoDefault(False)
        self.btn_add_custom_field.setStyleSheet(
            "QPushButton { font-size: 12px; color: #2563eb; background: transparent; border: 1px solid #2563eb; "
            "border-radius: 4px; padding: 2px 12px; }"
            "QPushButton:hover { background: #eff6ff; }"
        )
        self.btn_add_custom_field.clicked.connect(self._on_add_custom_field)
        custom_header.addWidget(self.btn_add_custom_field)
        custom_card_layout.addLayout(custom_header)

        # 动态字段行容器
        self._custom_fields_container = QVBoxLayout()
        self._custom_fields_container.setSpacing(6)
        self._custom_field_rows = []  # [(combo, line_edit, del_btn, row_widget), ...]
        custom_card_layout.addLayout(self._custom_fields_container)

        info_main_layout.addWidget(custom_card)

        # 加载已有的自定义字段
        self._load_custom_fields_from_data()

        info_main_layout.addStretch()
        
        self.tab.addTab(info_widget, "信息总览")
        # 信息总览：改为可编辑 + 防抖实时保存
        self._init_live_person_save()
        # 目录录入：防抖保存（避免每次 Tab 触发一次同步 DB 写入）
        self._pending_catalog_saves = {}  # {tpl_item_id: [tree_item, ec_item_id, {field: value}]}
        
        # Shift+click 范围选择锚点（Excel 风格多选）
        self._selection_anchor = None
        self._validation_failed_reenter = False  # 校验失败后阻止 Tab 导航跳到下一列
        self._catalog_save_timer = QTimer(self)
        self._catalog_save_timer.setSingleShot(True)
        self._catalog_save_timer.setInterval(350)
        self._catalog_save_timer.timeout.connect(self._flush_catalog_pending_saves)
        # 同一时刻最多一个异步写 worker 在跑，失败可安全重试，不会并发乱序
        self._catalog_save_in_flight = False
        # 正在异步写入的字段快照：{tpl_item_id: {field: value}}，worker 出错时回退到 pending
        self._catalog_save_in_flight_snapshot = {}
        # 异步新建模板项：用负数作占位 tpl_item_id，后台 worker 拿到真实 id 后迁移
        self._next_placeholder_id = 0
        self._placeholders_in_flight = set()  # 尚未拿到真实 id 的占位 id 集合
        # ---------------------------------------------------------------
        # 防闪退：对话框关闭标志。所有 Worker 回调回到主线程前都先查这个标志，
        # 避免触到已被 Qt deleteLater() 释放的 C++ 对象（会抛 RuntimeError: wrapped
        # C/C++ object has been deleted，直接导致进程闪退）。
        # ---------------------------------------------------------------
        self._is_closing = False
        # ---------------------------------------------------------------
        # 防卡顿：底部"总页数 / 图片数 / 总条数"统计的防抖 + 异步
        # 旧实现在每次 Tab 切列（col 1 或 5）都同步调 count_entry_total_images()
        # （远程 MySQL 往返 10~100ms），键入密集时光标一直转圈。
        # 新方案：
        #   1) 文本统计（页数/总条数）改成 180ms 防抖合并，多次连续输入只刷一次 UI；
        #   2) 图片数改成异步查询并缓存，只有在"图片真正被增删"时才强制重刷。
        # ---------------------------------------------------------------
        self._stats_refresh_timer = QTimer(self)
        self._stats_refresh_timer.setSingleShot(True)
        self._stats_refresh_timer.setInterval(180)
        self._stats_refresh_timer.timeout.connect(self._do_refresh_stats_ui)
        self._stats_refresh_need_image_count = False  # True 时才发起异步图片数查询
        self._total_images_cache: Optional[int] = None  # 最近一次查到的图片数
        self._image_count_in_flight = False

        # === Tab 2: 目录录入（左侧目录，右侧图片预览） ===
        catalog_widget = QWidget()
        catalog_layout = QVBoxLayout(catalog_widget)
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_layout.setSpacing(6)

        # 顶部：模板选择（卡片式）
        # 合并的操作与模板选择区域
        self.action_frame = QFrame()
        self.action_frame.setObjectName("catalog_action_frame")
        self.action_frame.setMaximumHeight(56)
        self.action_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_bar = QHBoxLayout(self.action_frame)
        action_bar.setContentsMargins(8, 6, 8, 6)
        action_bar.setSpacing(8)

        self.btn_cat_move_up = QPushButton("上移")
        self.btn_cat_move_down = QPushButton("下移")
        self.btn_cat_add_peer = QPushButton("新增同级")
        self.btn_cat_add_child = QPushButton("新增子级")
        self.btn_cat_del = QPushButton("删除节点")
        for btn in (self.btn_cat_move_up, self.btn_cat_move_down, self.btn_cat_add_peer, self.btn_cat_add_child, self.btn_cat_del):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("catalog_action_btn")
            btn.setMinimumWidth(88)
            btn.setFixedHeight(28)
            action_bar.addWidget(btn)

        action_bar.addSpacing(12)
        tpl_label = QLabel("目录模板")
        tpl_label.setObjectName("tpl_label")
        tpl_label.setStyleSheet("font-weight: 600;")
        self.tpl_combo = QComboBox()
        self.tpl_combo.setMinimumWidth(180)
        self.tpl_combo.setMaximumWidth(220)
        self.tpl_combo.setObjectName("tpl_combo")
        self.tpl_combo.currentIndexChanged.connect(self._on_tpl_changed)
        action_bar.addWidget(tpl_label)
        action_bar.addWidget(self.tpl_combo, 0)

        # 图片操作按钮放在同一行右侧
        action_bar.addSpacing(12)
        self.btn_img_upload = QPushButton("上传图片")
        self.btn_img_batch_upload = QPushButton("批量上传")
        self.btn_img_scan = QPushButton("扫描")
        self.btn_scan_settings = QPushButton("扫描设置")
        self.btn_img_delete = QPushButton("删除图片")
        self.btn_img_set_cover = QPushButton("设为首图")
        self.btn_img_commit = QPushButton("保存修图")
        self.btn_img_reset = QPushButton("撤销修图")
        self.btn_print_preview = QPushButton("打印预览")
        self.btn_ai_retouch_config = QPushButton("AI修图配置")
        self.lbl_img_dirty = QLabel("")
        self.lbl_img_dirty.setObjectName("tpl_label")
        for btn in (
            self.btn_img_upload,
            self.btn_img_batch_upload,
            self.btn_img_scan,
            self.btn_scan_settings,
            self.btn_img_delete,
            self.btn_img_set_cover,
            self.btn_img_commit,
            self.btn_img_reset,
            self.btn_print_preview,
            self.btn_ai_retouch_config,
        ):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("catalog_action_btn")
            btn.setFixedHeight(28)
            action_bar.addWidget(btn)

        # 未保存提示（轻量，不抢占空间）
        self.lbl_img_dirty.setStyleSheet("color:#d97706; font-weight:700;")
        action_bar.addWidget(self.lbl_img_dirty)
        action_bar.addStretch()

        catalog_layout.addWidget(self.action_frame)

        # ── 上传进度条（默认隐藏，有上传任务时显示） ──
        self._upload_progress_frame = QFrame()
        self._upload_progress_frame.setObjectName("upload_progress_frame")
        self._upload_progress_frame.setFixedHeight(32)
        self._upload_progress_frame.setVisible(False)
        _prog_layout = QHBoxLayout(self._upload_progress_frame)
        _prog_layout.setContentsMargins(8, 2, 8, 2)
        _prog_layout.setSpacing(8)
        self._upload_progress_label = QLabel("上传中...")
        self._upload_progress_label.setObjectName("upload_progress_label")
        self._upload_progress_bar = QProgressBar()
        self._upload_progress_bar.setObjectName("upload_progress_bar")
        self._upload_progress_bar.setMinimum(0)
        self._upload_progress_bar.setMaximum(100)
        self._upload_progress_bar.setValue(0)
        self._upload_progress_bar.setFixedHeight(18)
        self._upload_progress_bar.setTextVisible(True)
        self._upload_progress_bar.setFormat("%v / %m")
        _prog_layout.addWidget(self._upload_progress_label)
        _prog_layout.addWidget(self._upload_progress_bar, 1)
        # 进度条样式
        self._upload_progress_frame.setStyleSheet("""
            #upload_progress_frame {
                background: rgba(52,152,219,0.08);
                border: 1px solid rgba(52,152,219,0.25);
                border-radius: 4px;
            }
            #upload_progress_label {
                color: #2980b9; font-size: 12px; font-weight: bold;
            }
            #upload_progress_bar {
                border: 1px solid #bdc3c7; border-radius: 3px;
                background: #ecf0f1;
            }
            #upload_progress_bar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2ecc71);
                border-radius: 2px;
            }
        """)
        catalog_layout.addWidget(self._upload_progress_frame)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("catalog_splitter")
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            "QSplitter#catalog_splitter::handle { background: #d0d7de; }"
            "QSplitter#catalog_splitter::handle:hover { background: #409eff; }"
        )
        self.catalog_splitter = splitter

        # 左侧：目录树
        left_panel = QWidget()
        left_panel.setMinimumWidth(260)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.catalog_tree = QTreeWidget()
        self.catalog_tree.setObjectName("catalog_tree")
        # 启用多选：支持 Ctrl 多选和 Shift 范围选择
        self.catalog_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # 列表头：编号(serial) | 目录名称(name) | 年 | 月 | 日 | 页数 | 备注
        self.catalog_tree.setColumnCount(7)
        self.catalog_tree.setHeaderLabels([
            "编号",
            "目录名称",
            "年",
            "月",
            "日",
            "页数",
            "备注"
        ])
        header = self.catalog_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)  # 允许用户拖动调整列宽
        # 设置初始列宽（用户仍可拖拽修改）
        header.resizeSection(0, 130)    # 编号
        header.resizeSection(1, 400)   # 目录名称
        header.resizeSection(2, 100)    # 年
        header.resizeSection(3, 70)    # 月
        header.resizeSection(4, 70)    # 日
        header.resizeSection(5, 80)    # 页数
        header.resizeSection(6, 120)   # 备注
        self._apply_catalog_font_zoom(self._catalog_font_size)
        self.catalog_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 网格线效果
        self.catalog_tree.setStyleSheet(
            """
            QTreeWidget#catalog_tree {
                border: 1px solid #d0d7de;
            }
            QTreeWidget#catalog_tree::item {
                border-top: 1px solid #d0d7de;
                border-bottom: 1px solid #d0d7de;
                border-right: 1px solid #d0d7de;
            }
            QTreeWidget#catalog_tree::item:selected {
                background: rgba(64,158,255,0.12);
                color: #000000;
            }
            QHeaderView::section {
                border: 1px solid #d0d7de;
            }
            """
        )
        # 启用自定义右键菜单
        self.catalog_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.catalog_tree.customContextMenuRequested.connect(self._on_catalog_context_menu)
        # 设置自定义代理：控制模板预设值的单元格不可编辑，并处理 Tab 键
        self._catalog_delegate = CatalogTreeDelegate(self.catalog_tree)
        self._catalog_delegate.requestEditColumn.connect(self._on_request_edit_column)
        self._catalog_delegate.requestAutocomplete.connect(self._on_request_autocomplete)
        # 连接自动补全控制信号
        self._catalog_delegate.autocompleteMove.connect(self._on_autocomplete_move)
        self._catalog_delegate.autocompleteConfirm.connect(self._on_autocomplete_confirm)
        self._catalog_delegate.autocompleteHide.connect(self._on_autocomplete_hide)
        self._catalog_delegate.requestEnterNewRow.connect(self._on_request_enter_new_row)
        self.catalog_tree.setItemDelegate(self._catalog_delegate)
        self.catalog_tree.itemChanged.connect(self._on_catalog_item_changed)
        self.catalog_tree.itemPressed.connect(self._on_catalog_item_pressed)
        self.catalog_tree.itemClicked.connect(self._on_catalog_item_clicked)
        self.catalog_tree.currentItemChanged.connect(self.on_catalog_current_changed)
        # 安装事件过滤器：监听 Enter 键实现自动新增行
        self.catalog_tree.installEventFilter(self)
        self.catalog_tree.viewport().installEventFilter(self)
        self._catalog_name_editor = QLineEdit(self.catalog_tree.viewport())
        self._catalog_name_editor.hide()
        self._catalog_name_editor.setFrame(False)
        self._catalog_name_editor.setFont(self.catalog_tree.font())
        self._catalog_name_editor.setAttribute(Qt.WA_InputMethodEnabled, True)
        self._catalog_name_editor.installEventFilter(self)
        self._catalog_name_editor.textChanged.connect(self._on_catalog_name_editor_text_changed)
        left_layout.addWidget(self.catalog_tree)
        
        # 左下角页数统计（美化样式+图标）
        pages_frame = QFrame()
        pages_frame.setObjectName("pages_stat_frame")
        pages_frame.setStyleSheet("""
            QFrame#pages_stat_frame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e8f4fd, stop:1 #f0f7ff);
                border: 1px solid #c5dff5;
                border-radius: 6px;
                padding: 4px 8px;
                margin: 4px 0;
            }
        """)
        pages_layout = QHBoxLayout(pages_frame)
        pages_layout.setContentsMargins(8, 4, 8, 4)
        pages_layout.setSpacing(6)
        
        # 图标
        pages_icon = QLabel("📄")
        pages_icon.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        pages_layout.addWidget(pages_icon)
        
        # 文字
        self.total_pages_label = QLabel("总页数：0")
        self.total_pages_label.setObjectName("total_pages_label")
        self.total_pages_label.setStyleSheet("""
            color: #1a5fb4;
            font-size: 13px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        pages_layout.addWidget(self.total_pages_label)

        # 分隔线
        sep = QLabel("|")
        sep.setStyleSheet("color: #b0bec5; font-size: 13px; background: transparent; border: none; margin: 0 4px;")
        pages_layout.addWidget(sep)

        # 图片数量
        self.total_images_label = QLabel("图片数：0")
        self.total_images_label.setObjectName("total_images_label")
        self.total_images_label.setStyleSheet("""
            color: #2e7d32;
            font-size: 13px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        pages_layout.addWidget(self.total_images_label)

        # 分隔线
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #b0bec5; font-size: 13px; background: transparent; border: none; margin: 0 4px;")
        pages_layout.addWidget(sep2)

        # 总条数
        self.total_entries_label = QLabel("总条数：0")
        self.total_entries_label.setObjectName("total_entries_label")
        self.total_entries_label.setStyleSheet("""
            color: #6a1b9a;
            font-size: 13px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        pages_layout.addWidget(self.total_entries_label)
        pages_layout.addStretch()
        
        left_layout.addWidget(pages_frame)
        
        # 初始化自动补全弹窗（传递当前主题）
        self._autocomplete_popup = AutocompletePopup(self, theme=self.current_theme)
        self._autocomplete_popup.candidate_selected.connect(self._on_autocomplete_selected)
        self._autocomplete_editor = None  # 当前编辑器引用
        self._autocomplete_item = None
        self._autocomplete_column = -1
        self._autocomplete_context = None  # 保存自动补全上下文 (template_name, item_name, parent_item_name)
        # 设置弹窗可见性检查回调
        self._catalog_delegate.set_popup_visible_checker(self._is_autocomplete_popup_visible)

        # 目录按钮事件（支持批量操作）
        self.btn_cat_move_up.clicked.connect(self._on_move_nodes_up)
        self.btn_cat_move_down.clicked.connect(self._on_move_nodes_down)
        self.btn_cat_add_peer.clicked.connect(self._on_add_peer)
        self.btn_cat_add_child.clicked.connect(self._on_add_child)
        self.btn_cat_del.clicked.connect(self._on_delete_nodes)
        self._apply_toolbar_style()

        splitter.addWidget(left_panel)

        # 右侧：图片工具+列表+预览
        right_panel = QWidget()
        right_panel.setMinimumWidth(200)
        right_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.setSizeConstraint(QLayout.SetNoConstraint)

        # 缩略图列表逻辑保留但不占用界面空间（不加入布局）
        self.image_list = QListWidget()
        self.image_list.setViewMode(QListWidget.IconMode)
        self.image_list.setIconSize(QSize(120, 120))
        self.image_list.setResizeMode(QListWidget.Adjust)
        self.image_list.setMovement(QListWidget.Static)
        self.image_list.setSpacing(8)
        self.image_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.image_list.itemSelectionChanged.connect(self._on_image_selected)

        # 预览上方的翻页区域（独立一行，控高）
        pager_frame = QWidget()
        pager_frame.setMinimumWidth(0)
        pager_frame.setMaximumHeight(32)
        pager_frame.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        pager_bar = QHBoxLayout(pager_frame)
        pager_bar.setSizeConstraint(QLayout.SetNoConstraint)
        pager_bar.setContentsMargins(4, 2, 4, 2)
        pager_bar.setSpacing(4)
        # 统一高度为36px
        unified_height = 36
        
        self.btn_img_prev = QPushButton()
        self.btn_img_next = QPushButton()
        for btn in (self.btn_img_prev, self.btn_img_next):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("pager_btn")
            btn.setFixedSize(unified_height, unified_height)
            btn.setIconSize(QSize(20, 20))
        self.btn_img_prev.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.btn_img_next.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        
        self.img_page_edit = QLineEdit("1")
        self.img_page_edit.setFixedSize(34, unified_height)
        self.img_page_edit.setAlignment(Qt.AlignCenter)
        self.img_page_edit.setObjectName("pager_input")
        self.img_page_edit.setPlaceholderText("")
        self.img_page_edit.setStyleSheet("font-size: 14px;")

        self.img_page_total = QLabel("/   0")
        self.img_page_total.setObjectName("pager_total")
        self.img_page_total.setFixedHeight(unified_height)  # 统一高度
        self.img_page_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 垂直居中
        self.img_page_total.setStyleSheet("font-size: 14px;")

        self.img_zoom_label = QLabel("100%")
        self.img_zoom_label.setObjectName("pager_total")
        self.img_zoom_label.setFixedHeight(unified_height)  # 统一高度
        self.img_zoom_label.setStyleSheet("font-size: 14px;")

        self.image_view_mode_combo = QComboBox()
        self.image_view_mode_combo.addItem("处理图", "retouched")
        self.image_view_mode_combo.addItem("高清图", "original")
        self.image_view_mode_combo.setFixedHeight(unified_height)
        self.image_view_mode_combo.setMinimumWidth(86)
        self.image_view_mode_combo.setObjectName("tpl_combo")

        # 图像处理功能键（图标方式，放在翻页控件右侧）
        def mk_icon_btn(text: str, tooltip: str):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tooltip)
            b.setObjectName("pager_icon_btn")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(36, 36)
            b.setAutoRaise(True)
            b.setStyleSheet("font-size: 16px;") 
            return b

        self.btn_img_trim = mk_icon_btn("✂", "去黑边")
        self.btn_img_trim_1mm = mk_icon_btn("1", "擦除1毫米")
        self.btn_img_trim_2mm = mk_icon_btn("2", "擦除2毫米")
        self.btn_img_trim_3mm = mk_icon_btn("3", "擦除3毫米")
        # 角度输入框（在左右微调按钮前面）
        self.rotate_angle_input = QLineEdit("0")
        self.rotate_angle_input.setFixedSize(50, 36)
        self.rotate_angle_input.setToolTip("输入旋转角度（度）")
        self.rotate_angle_input.setAlignment(Qt.AlignCenter)
        self.rotate_angle_input.setStyleSheet("font-size: 12px;")
        self.btn_img_rotate_l = mk_icon_btn("⟲", "角度左微调")
        self.btn_img_rotate_r = mk_icon_btn("⟳", "角度右微调")
        self.btn_img_rot90_l = mk_icon_btn("↶", "左转90°")
        self.btn_img_rot90_r = mk_icon_btn("↷", "右转90°")
        self.btn_img_fill = mk_icon_btn("▭", "框选污点去除")
        self.btn_img_fill.setCheckable(True)
        self.btn_img_a4 = mk_icon_btn("A4", "自动补边成A4")
        self.btn_img_gray_remove = mk_icon_btn("🌫", "去灰底")
        self.btn_img_brightness_up = mk_icon_btn("☀", "增亮")
        self.btn_img_brightness_dn = mk_icon_btn("🌙", "减暗")
        self.btn_img_contrast_up = mk_icon_btn("◑", "增对比度")
        self.btn_img_contrast_dn = mk_icon_btn("◐", "减对比度")
        self.btn_img_sharpen = mk_icon_btn("◇", "锐化")
        self.btn_img_auto_enhance = mk_icon_btn("✨", "一键美化")

        pager_bar.addWidget(self.btn_img_prev)
        pager_bar.addSpacing(2)
        pager_bar.addWidget(self.img_page_edit)
        pager_bar.addSpacing(8)
        pager_bar.addWidget(self.img_page_total)
        pager_bar.addSpacing(10)
        pager_bar.addWidget(self.btn_img_next)
        pager_bar.addSpacing(10)
        pager_bar.addWidget(self.btn_img_trim)
        pager_bar.addWidget(self.btn_img_trim_1mm)
        pager_bar.addWidget(self.btn_img_trim_2mm)
        pager_bar.addWidget(self.btn_img_trim_3mm)
        pager_bar.addWidget(self.rotate_angle_input)  # 角度输入框（在左右微调前面）
        pager_bar.addWidget(self.btn_img_rotate_l)
        pager_bar.addWidget(self.btn_img_rotate_r)
        pager_bar.addWidget(self.btn_img_rot90_l)
        pager_bar.addWidget(self.btn_img_rot90_r)
        pager_bar.addWidget(self.btn_img_fill)
        pager_bar.addWidget(self.btn_img_a4)
        pager_bar.addSpacing(6)
        pager_bar.addWidget(self.btn_img_gray_remove)
        pager_bar.addWidget(self.btn_img_brightness_up)
        pager_bar.addWidget(self.btn_img_brightness_dn)
        pager_bar.addWidget(self.btn_img_contrast_up)
        pager_bar.addWidget(self.btn_img_contrast_dn)
        pager_bar.addWidget(self.btn_img_sharpen)
        pager_bar.addWidget(self.btn_img_auto_enhance)
        pager_bar.addSpacing(10)
        pager_bar.addWidget(self.image_view_mode_combo)
        pager_bar.addSpacing(6)
        pager_bar.addWidget(self.img_zoom_label)
        pager_bar.addStretch()
        right_layout.addWidget(pager_frame)

        # 图片预览（支持 Ctrl+滚轮缩放 / 双击放大还原）
        self.catalog_preview = ImagePreview()
        self.catalog_preview.setMinimumSize(200, 200)
        self.catalog_preview.zoomChanged = self._on_preview_zoom_changed
        self.catalog_preview.selectionFinished.connect(self._on_spot_selected)
        self.catalog_preview.imageChanged.connect(self._on_preview_image_changed)
        right_layout.addWidget(self.catalog_preview)

        self.btn_img_upload.clicked.connect(self._on_upload_images)
        self.btn_img_batch_upload.clicked.connect(self._on_batch_upload_images)
        self.btn_img_scan.clicked.connect(self._on_scan_images)
        self.btn_scan_settings.clicked.connect(self._on_scan_settings)
        self.btn_img_delete.clicked.connect(self._on_delete_image)
        self.btn_img_set_cover.clicked.connect(self._on_set_cover)

        # ── 上传队列信号连接 ──
        _uq = get_upload_queue_manager()
        _uq.task_started.connect(self._on_upload_task_started)
        _uq.file_progress.connect(self._on_upload_file_progress)
        _uq.task_finished.connect(self._on_upload_task_finished)
        _uq.worker_error.connect(self._on_upload_worker_error)
        _uq.queue_empty.connect(self._on_upload_queue_empty)
        # 方案A：修图按钮只更新 pending 参数并刷新预览，不立即保存文件/写库
        self.btn_img_trim.clicked.connect(self._on_trim_border)
        self.btn_img_trim_1mm.clicked.connect(lambda: self._on_trim_border_mm(1))
        self.btn_img_trim_2mm.clicked.connect(lambda: self._on_trim_border_mm(2))
        self.btn_img_trim_3mm.clicked.connect(lambda: self._on_trim_border_mm(3))
        # 调换左右转方向
        self.btn_img_rotate_l.clicked.connect(lambda: self._on_rotate_fine(1))  # 左微调改为正方向
        self.btn_img_rotate_r.clicked.connect(lambda: self._on_rotate_fine(-1))  # 右微调改为负方向
        self.btn_img_rot90_l.clicked.connect(lambda: self._on_rotate_90(90))  # 左转90°改为正方向
        self.btn_img_rot90_r.clicked.connect(lambda: self._on_rotate_90(-90))  # 右转90°改为负方向
        self.btn_img_fill.toggled.connect(self._on_spot_mode_toggled)
        self.btn_img_a4.clicked.connect(self._on_pad_a4_toggle)
        self.btn_img_gray_remove.clicked.connect(self._on_gray_remove)
        self.btn_img_brightness_up.clicked.connect(lambda: self._on_adjust_brightness(0.1))
        self.btn_img_brightness_dn.clicked.connect(lambda: self._on_adjust_brightness(-0.1))
        self.btn_img_contrast_up.clicked.connect(lambda: self._on_adjust_contrast(0.1))
        self.btn_img_contrast_dn.clicked.connect(lambda: self._on_adjust_contrast(-0.1))
        self.btn_img_sharpen.clicked.connect(self._on_sharpen)
        self.btn_img_auto_enhance.clicked.connect(self._on_auto_enhance)
        self.btn_img_prev.clicked.connect(lambda: self._shift_image(-1))
        self.btn_img_next.clicked.connect(lambda: self._shift_image(1))
        self.img_page_edit.returnPressed.connect(self._on_jump_page)
        self.btn_img_commit.clicked.connect(self._commit_current_pending)
        self.btn_img_reset.clicked.connect(self._reset_current_pending)
        self.btn_print_preview.clicked.connect(self._on_print_preview)
        self.btn_ai_retouch_config.clicked.connect(self._on_ai_retouch_config)
        self.image_view_mode_combo.currentIndexChanged.connect(self._on_image_view_mode_changed)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([1000, 300])

        catalog_layout.addWidget(splitter)

        self._load_templates_to_combo()
        # 若已有 entry 数据，则按其模板自动选中并加载；无数据则保持占位
        self._autoselect_entry_template()

        self.tab.addTab(catalog_widget, "目录录入")
        # 清除模板/按钮区域样式，稍后单独给按钮设置样式
        self.tpl_combo.setStyleSheet("")
        for btn in (self.btn_cat_add_peer, self.btn_cat_add_child, self.btn_cat_del):
            btn.setStyleSheet("")

    # === 方案A：对话框保存时自动提交所有 pending 修图 ===
    def accept(self):
        # 先把 sync flush 跑完（确保 WAL/DB 落盘），再标记关闭状态——因为 sync
        # flush 内部会 processEvents() 等待飞行中的 worker，worker 的 on_done
        # 回调仍然需要访问 C++ 对象（例如 tree_item.setData / _catalog_save_timer）。
        try:
            # 关闭前先把当前正在编辑的 editor 文本提交到 item / pending / WAL，
            # 否则用户在编辑中直接「保存」而没按 Enter/Tab 时会丢失最后一字段。
            self._commit_active_catalog_editor()
            self._flush_catalog_pending_saves_sync()  # 先同步落盘 pending 目录保存
            if self._has_unmaterialized_placeholders():
                self._warn_unmaterialized_placeholders()
                return
            # 保存前记住当前选中图片，提交后刷新列表时恢复
            img_id, fp, _orig_id, _orig_path = self._current_image_ctx()
            self._select_after_reload = {"file_path": fp or "", "img_id": img_id}
            if self._commit_all_pending(blocking=True) is False:
                return
        except Exception:
            pass
        if self._has_unmaterialized_placeholders():
            self._warn_unmaterialized_placeholders()
            return
        # 等待自动补全词频后台落盘（非主机端也保证本地 txt 一致性）
        try:
            get_autocomplete_manager().flush_sync(timeout=3.0)
        except Exception:
            pass
        # sync flush 已完成，后续任何晚到的 worker 回调都不再允许触 C++ 对象
        self._is_closing = True
        self._stop_ui_timers_safely()
        super().accept()

    def closeEvent(self, event):
        """关闭对话框前同步落盘所有 pending 目录保存，防止用户刚录入就关闭导致数据丢失。

        顺序（防闪退 + 防丢数据）：
        1. 先 sync flush 目录保存（内部会 processEvents 等 worker 完成，
           此时需要 C++ 对象还活着）；
        2. 再刷 autocomplete 词频落盘；
        3. 最后置 ``_is_closing=True`` 并停掉 UI 定时器——晚到的 worker
           回调看到标志就直接 return，避免触到已被 deleteLater() 的 C++
           对象（RuntimeError: wrapped C/C++ object has been deleted）。
        """
        # 关闭前先把当前正在编辑的 editor 文本提交到 item / pending / WAL，
        # 这一步必须早于 _flush_catalog_pending_saves_sync，否则编辑中的最后一字段
        # 不在 pending 里，sync flush 也就写不出去。
        try:
            self._commit_active_catalog_editor()
        except Exception:
            pass
        try:
            self._flush_catalog_pending_saves_sync()
        except Exception:
            pass
        if self._has_unmaterialized_placeholders():
            self._warn_unmaterialized_placeholders()
            event.ignore()
            return
        try:
            get_autocomplete_manager().flush_sync(timeout=3.0)
        except Exception:
            pass
        self._is_closing = True
        self._stop_ui_timers_safely()
        super().closeEvent(event)

    def _stop_ui_timers_safely(self):
        """停掉所有 UI 定时器；每个都独立 try/except 以免一个挂掉影响其他。"""
        for attr in ("_catalog_save_timer", "_stats_refresh_timer", "_info_save_timer"):
            t = getattr(self, attr, None)
            if t is None:
                continue
            try:
                t.stop()
            except RuntimeError:
                pass

    def _has_unmaterialized_placeholders(self) -> bool:
        for tpl_item_id, (_tree_item, _ec_item_id, fields) in self._pending_catalog_saves.items():
            try:
                if fields and int(tpl_item_id) < 0:
                    return True
            except Exception:
                continue
        return False

    def _warn_unmaterialized_placeholders(self):
        StyledMessageBox.warning(
            self,
            "提示",
            "当前有新增目录行尚未保存完成，请等待网络/数据库恢复后再保存或关闭。",
            self.current_theme,
        )

    # === 信息总览：实时保存 Entry 基础信息 ===
    def _init_live_person_save(self):
        try:
            self._info_save_timer = QTimer(self)
            self._info_save_timer.setSingleShot(True)
            self._info_save_timer.timeout.connect(self._flush_person_info_save)

            for w in (
                self.le_user,
                self.le_empid,
                self.le_role,
                self.le_phone,
                self.le_status,
                self.le_id_card,
                self.le_ethnicity,
                self.le_native_place,
                self.le_birth_date,
            ):
                try:
                    # QComboBox 使用 currentTextChanged，QLineEdit 使用 textChanged
                    if isinstance(w, QComboBox):
                        w.currentTextChanged.connect(self._schedule_person_info_save)
                    else:
                        w.textChanged.connect(self._schedule_person_info_save)
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_person_info_save(self):
        # 防抖：用户持续输入时不频繁写库
        try:
            self._info_save_timer.start(350)
        except Exception:
            pass

    def _flush_person_info_save(self):
        entry_id = self.current_entry_id or self.case_data.get("entry_id")
        if not entry_id:
            # 无 entry_id 时无法写库（通常不应发生：人员从列表进入一定有 entry_id）
            return
        try:
            # le_role / le_status 可能是 QComboBox，统一用 _text_of 取值
            def _text_of(w):
                return w.currentText() if isinstance(w, QComboBox) else w.text()

            custom_fields = self._serialize_custom_fields()
            update_entry_person_fields(
                entry_id=int(entry_id),
                name=self.le_user.text(),
                emp_no=self.le_empid.text(),
                role_title=_text_of(self.le_role),
                phone=self.le_phone.text(),
                status=_text_of(self.le_status),
                id_card=self.le_id_card.text(),
                custom_fields=custom_fields,
            )
            # 同步本地 case_data（用于标题/后续逻辑）
            self.case_data["姓名"] = self.le_user.text()
            self.case_data["工号"] = self.le_empid.text()
            self.case_data["岗位"] = _text_of(self.le_role)
            self.case_data["电话"] = self.le_phone.text()
            self.case_data["状态"] = _text_of(self.le_status)
            self.case_data["身份证号"] = self.le_id_card.text()
            self.case_data["民族"] = self.le_ethnicity.text()
            self.case_data["籍贯"] = self.le_native_place.text()
            self.case_data["出生日期"] = self.le_birth_date.text()
            self.case_data["custom_fields"] = custom_fields
            self.case_data["自定义字段"] = custom_fields

            # 更新标题栏文本
            title_name = self.case_data.get("姓名") or self.case_data.get("工号") or ""
            self._title_text = f"录入 - {title_name}"
            self.setWindowTitle(self._title_text)
            try:
                # 对应 initUI 中的 title_label
                if hasattr(self, "header") and self.header:
                    pass
            except Exception:
                pass
            # 直接查找标题 label 更新（避免持有引用失效）
            try:
                for lab in self.findChildren(QLabel, "dialog_title_label"):
                    lab.setText(self._title_text)
            except Exception:
                pass
        except Exception:
            # 实时保存失败不弹窗打断输入
            pass

    # === 自定义扩展字段 ===
    FIXED_CUSTOM_FIELD_NAMES = ("民族", "籍贯", "出生日期")
    CUSTOM_FIELD_OPTIONS = [
        "入党日期", "参加工作时间",
        "学历", "学位", "毕业院校", "专业", "婚姻状况",
        "政治面貌", "现任职务", "任职时间", "原单位",
        "档案编号", "备注", "性别", "血型", "户籍地址", "现住址",
    ]

    def _custom_fields_from_data(self):
        import json
        raw = self.case_data.get("自定义字段") or self.case_data.get("custom_fields") or ""
        if not raw:
            return []
        try:
            fields = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return []
        return fields if isinstance(fields, list) else []

    def _get_fixed_custom_field_value(self, field_name: str) -> str:
        direct = self.case_data.get(field_name)
        if direct:
            return str(direct)
        for item in self._custom_fields_from_data():
            if not isinstance(item, dict):
                continue
            if (item.get("field_name") or "").strip() == field_name:
                return str(item.get("field_value") or "")
        return ""

    def _load_custom_fields_from_data(self):
        """从 case_data 加载已有的自定义字段并创建 UI 行。"""
        for item in self._custom_fields_from_data():
            if not isinstance(item, dict):
                continue
            fn = item.get("field_name") or ""
            fv = item.get("field_value") or ""
            if fn and fn not in self.FIXED_CUSTOM_FIELD_NAMES:
                self._add_custom_field_row(field_name=fn, field_value=fv)

    def _add_custom_field_row(self, field_name: str = "", field_value: str = ""):
        """添加一行自定义字段（下拉选字段名 + 输入框 + 删除按钮）。"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        label_style = "font-size: 13px; color: #666; font-weight: 500;"
        input_style = (
            "QLineEdit, QComboBox { font-size: 14px; padding: 8px 12px; "
            "border: 1px solid #d0d0d0; border-radius: 4px; background-color: #fafafa; }"
            "QLineEdit:focus, QComboBox:focus { border-color: #4A90D9; background-color: #ffffff; }"
        )

        # 字段名下拉（可编辑，允许手输新字段名）
        combo = QComboBox()
        combo.setEditable(True)
        combo.setMinimumWidth(140)
        combo.setMaximumWidth(180)
        combo.setStyleSheet(input_style)
        combo.addItems(self.CUSTOM_FIELD_OPTIONS)
        if field_name:
            idx = combo.findText(field_name)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(field_name)
        else:
            combo.setCurrentIndex(0)

        # 字段值输入框
        line_edit = QLineEdit(field_value)
        line_edit.setStyleSheet(input_style)
        line_edit.setPlaceholderText("请输入值")

        # 删除按钮
        del_btn = QPushButton("✕")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            "QPushButton { font-size: 14px; color: #dc2626; background: transparent; "
            "border: 1px solid #fca5a5; border-radius: 4px; }"
            "QPushButton:hover { background: #fef2f2; }"
        )

        row_layout.addWidget(combo)
        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(del_btn)

        self._custom_fields_container.addWidget(row_widget)
        entry = (combo, line_edit, del_btn, row_widget)
        self._custom_field_rows.append(entry)

        # 信号连接：编辑时触发防抖保存
        combo.currentTextChanged.connect(self._schedule_person_info_save)
        line_edit.textChanged.connect(self._schedule_person_info_save)
        del_btn.clicked.connect(lambda checked=False, e=entry: self._remove_custom_field_row(e))

    def _remove_custom_field_row(self, entry):
        """删除一行自定义字段。"""
        combo, line_edit, del_btn, row_widget = entry
        if entry in self._custom_field_rows:
            self._custom_field_rows.remove(entry)
        self._custom_fields_container.removeWidget(row_widget)
        row_widget.deleteLater()
        # 触发保存
        self._schedule_person_info_save()

    def _on_add_custom_field(self):
        """点击"添加字段"按钮：新增一行空白自定义字段。"""
        self._add_custom_field_row()
        self._schedule_person_info_save()

    def _serialize_custom_fields(self) -> str:
        """将当前自定义字段行序列化为 JSON 字符串。"""
        import json
        fields = []
        fixed_widgets = [
            ("民族", getattr(self, "le_ethnicity", None)),
            ("籍贯", getattr(self, "le_native_place", None)),
            ("出生日期", getattr(self, "le_birth_date", None)),
        ]
        for fn, widget in fixed_widgets:
            if widget is None:
                continue
            fv = widget.text().strip()
            if fv:
                fields.append({"field_name": fn, "field_value": fv})
        for combo, line_edit, _del_btn, _row_widget in self._custom_field_rows:
            fn = combo.currentText().strip()
            fv = line_edit.text().strip()
            if fn and fn not in self.FIXED_CUSTOM_FIELD_NAMES:
                fields.append({"field_name": fn, "field_value": fv})
        return json.dumps(fields, ensure_ascii=False) if fields else ""

    # === 方案A：pending 状态 & 预览渲染 ===
    def _current_image_ctx(self):
        """
        返回当前选中图片的上下文：
        - img_id: 当前列表项对应记录 ID（可能是 original 或 retouched）
        - file_path: 当前列表项显示的文件路径（通常是“优先修图版”的路径）
        - orig_id: 该图片归属的 original_id（用于 pending 归一化）
        - base_path: 当前编辑基线路径（优先修图版；若无修图版则为原图）
        """
        items = self.image_list.selectedItems()
        if not items:
            return None, None, None, None
        it = items[0]
        img_id = it.data(Qt.UserRole)
        file_path = it.data(Qt.UserRole + 1) or ""
        orig_id = it.data(Qt.UserRole + 2) or None
        base_path = it.data(Qt.UserRole + 3) or ""
        return img_id, file_path, orig_id, base_path

    def _pending_for(self, orig_id: int):
        p = self._pending_edits.get(orig_id)
        if not p:
            p = new_pending()
            self._pending_edits[orig_id] = p
        return p

    def _set_dirty_badge(self, orig_id: Optional[int]):
        if not hasattr(self, "lbl_img_dirty"):
            return
        if not orig_id:
            self.lbl_img_dirty.setText("")
            return
        p = self._pending_edits.get(orig_id)
        if not p:
            self.lbl_img_dirty.setText("")
            return
        dirty = is_dirty(p)
        self.lbl_img_dirty.setText("未保存修图" if dirty else "")

    def _render_effective_preview(self, orig_id: int, orig_path: str):
        """渲染当前 original 的“有效预览”：若存在 pending 则按参数渲染；否则退回默认预览逻辑。"""
        if not orig_id or not orig_path:
            return
        p = self._pending_edits.get(orig_id)
        if not p:
            # 无 pending：走原有预览（优先显示当前 file_path）
            self._on_image_selected()
            return
        dirty = is_dirty(p)
        if not dirty:
            self._on_image_selected()
            return

        # 有 pending：后台渲染（从原图 + 参数），避免阻塞 UI
        self._preview_token += 1
        token = self._preview_token
        self._preview_expected_path = orig_path
        self._set_dirty_badge(orig_id)

        view_size = self.catalog_preview.viewport().size() if hasattr(self, "catalog_preview") else QSize(800, 800)
        max_side = int(min(2200, max(900, max(view_size.width(), view_size.height()) * 2)))

        # 快照，避免后台执行时 pending 被修改导致“预览跳动”
        angle0 = float(p.get("angle") or 0.0)
        crop0 = p.get("crop_box")
        bf0 = p.get("border_fill")
        pad0 = p.get("pad_a4")
        spots0 = list(p.get("spots") or [])

        def make_fn(fp=orig_path, ms=max_side, tok=token, angle=angle0, crop=crop0, bf=bf0, pad=pad0, spots=spots0):
            try:
                pending = {"angle": angle, "crop_box": crop, "border_fill": bf, "pad_a4": pad, "spots": spots}
                qimg = render_preview_qimage(orig_path=fp, pending=pending, max_side=int(ms or 0))
                return {"token": tok, "file_path": fp, "img": qimg}
            except Exception as e:
                return {"token": tok, "file_path": fp, "img": QImage(), "err": str(e)}

        worker = Worker(make_fn)

        def on_done(res):
            if getattr(self, "_is_closing", False):
                return
            try:
                if res.get("token") != self._preview_token:
                    return
                if (res.get("file_path") or "") != (self._preview_expected_path or ""):
                    return
                qimg = res.get("img")
                if qimg is None or qimg.isNull():
                    return
                # 同一张图的修图预览刷新：保持用户当前缩放与视图中心
                self.catalog_preview.set_image(QPixmap.fromImage(qimg), preserve_view=True)
            except Exception:
                pass

        worker.signals.finished.connect(on_done)
        self._thread_pool.start(worker)

    def _on_pad_a4_toggle(self):
        """一键开关：自动补边成 A4（背景色自动取外圈主色）。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path or not os.path.exists(orig_path):
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        p = self._pending_for(int(orig_id))
        # 几何变化会影响框选坐标，简单起见：切换 A4 时清空 spots
        p["spots"] = []
        if p.get("pad_a4"):
            p["pad_a4"] = None
        else:
            # 背景色：优先用“边缘占比最多色”
            color = dominant_border_color(orig_path, thickness=2)
            p["pad_a4"] = {"color": tuple(color)}
        self._set_dirty_badge(int(orig_id))
        self._render_effective_preview(int(orig_id), orig_path)

    def _on_preview_image_changed(self, has_image: bool):
        """用于“框选污点去除”在预览尚未加载完成时的自动启用。"""
        if not has_image:
            return
        # 若当前处于“污点去除模式”，确保预览控件持续可框选
        if hasattr(self, "btn_img_fill") and self.btn_img_fill.isChecked():
            try:
                self.catalog_preview.enable_selection_mode(True, one_shot=False)
            except Exception:
                pass

    def _on_spot_selected(self, payload: object):
        """接收预览框选结果，记录为 pending spots 并刷新预览。"""
        try:
            rect = (payload or {}).get("rect_norm")
        except Exception:
            rect = None
        if not rect:
            return
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            return
        p = self._pending_for(int(orig_id))
        p.setdefault("spots", [])
        p["spots"].append(tuple(rect))
        self._set_dirty_badge(int(orig_id))
        self._render_effective_preview(int(orig_id), orig_path)

    def _on_spot_mode_toggled(self, checked: bool):
        """进入/退出持续框选污点去除模式。"""
        if not hasattr(self, "catalog_preview"):
            return
        if not checked:
            try:
                self.catalog_preview.enable_selection_mode(False)
            except Exception:
                pass
            return
        # 进入模式：若预览尚未加载，先触发预览；加载完成后 _on_preview_image_changed 会启用框选
        if not getattr(self.catalog_preview, "_has_image", False):
            self._on_image_selected()
            return
        try:
            self.catalog_preview.enable_selection_mode(True, one_shot=False)
        except Exception:
            pass

    def _on_trim_border(self):
        """方案A：去黑边（新算法）= 外圈填充背景色；只记录 pending 并更新预览，不落盘。"""
        img_id, _file_path, orig_id, orig_path = self._current_image_ctx()
        if not img_id or not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        # 后台计算“外围占比最多”的颜色，避免大图取样阻塞 UI
        self._preview_token += 1
        token = self._preview_token
        self._preview_expected_path = orig_path

        def make_fn(fp=orig_path, tok=token):
            return {"token": tok, "file_path": fp, "color": dominant_border_color(fp, thickness=1)}

        worker = Worker(make_fn)

        def on_done(res):
            if getattr(self, "_is_closing", False):
                return
            try:
                if res.get("token") != self._preview_token:
                    return
                if (res.get("file_path") or "") != (self._preview_expected_path or ""):
                    return
                color = tuple(res.get("color") or (255, 255, 255))
                p = self._pending_for(orig_id)
                p["border_fill"] = {"thickness": 1, "color": color}
                self._set_dirty_badge(orig_id)
                self._render_effective_preview(orig_id, orig_path)
            except Exception:
                pass

        worker.signals.finished.connect(on_done)
        self._thread_pool.start(worker)

    def _on_trim_border_mm(self, mm: int):
        """按毫米数擦除图片边缘（基于 300 DPI 换算像素），只记录 pending 并更新预览。"""
        img_id, _file_path, orig_id, orig_path = self._current_image_ctx()
        if not img_id or not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        # 毫米转像素（300 DPI）
        thickness_px = mm_to_pixels(mm, dpi=300)
        # 后台计算外围主色
        self._preview_token += 1
        token = self._preview_token
        self._preview_expected_path = orig_path

        def make_fn(fp=orig_path, tok=token, t=thickness_px):
            return {"token": tok, "file_path": fp, "color": dominant_border_color(fp, thickness=t), "thickness": t}

        worker = Worker(make_fn)

        def on_done(res):
            if getattr(self, "_is_closing", False):
                return
            try:
                if res.get("token") != self._preview_token:
                    return
                if (res.get("file_path") or "") != (self._preview_expected_path or ""):
                    return
                color = tuple(res.get("color") or (255, 255, 255))
                t = res.get("thickness") or thickness_px
                p = self._pending_for(orig_id)
                p["border_fill"] = {"thickness": t, "color": color}
                self._set_dirty_badge(orig_id)
                self._render_effective_preview(orig_id, orig_path)
            except Exception:
                pass

        worker.signals.finished.connect(on_done)
        self._thread_pool.start(worker)

    def _get_enhance_pending(self, orig_id) -> dict:
        """获取或创建当前图片的 enhance 子字典。"""
        p = self._pending_for(orig_id)
        enh = p.get("enhance")
        if enh is None:
            enh = {"gray_remove": 0.0, "brightness": 1.0, "contrast": 1.0, "sharpen": 0.0}
            p["enhance"] = enh
        return enh

    def _on_gray_remove(self):
        """去灰底：将灰色背景提亮为白色，保留文字和内容。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        enh = self._get_enhance_pending(orig_id)
        # 切换：已开启则关闭，否则设置强度 1.0
        cur = float(enh.get("gray_remove") or 0.0)
        enh["gray_remove"] = 0.0 if cur > 0.01 else 1.0
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _on_adjust_brightness(self, delta: float):
        """增/减亮度，每次步进 delta（如 +0.1 / -0.1）。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        enh = self._get_enhance_pending(orig_id)
        cur = float(enh.get("brightness") or 1.0)
        enh["brightness"] = max(0.2, min(3.0, cur + float(delta)))
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _on_adjust_contrast(self, delta: float):
        """增/减对比度，每次步进 delta（如 +0.1 / -0.1）。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        enh = self._get_enhance_pending(orig_id)
        cur = float(enh.get("contrast") or 1.0)
        enh["contrast"] = max(0.2, min(3.0, cur + float(delta)))
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _on_sharpen(self):
        """锐化切换：未开启则设为 1.0，已开启则关闭。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        enh = self._get_enhance_pending(orig_id)
        cur = float(enh.get("sharpen") or 0.0)
        enh["sharpen"] = 0.0 if cur > 0.01 else 1.0
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _on_auto_enhance(self):
        """一键美化：去灰底 + 轻微增亮 + 轻微增对比 + 轻微锐化。"""
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        p = self._pending_for(orig_id)
        p["enhance"] = {
            "gray_remove": 1.0,
            "brightness": 1.1,
            "contrast": 1.15,
            "sharpen": 0.8,
        }
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _on_rotate_fine(self, direction: int):
        """方案A：角度微调只累计 angle 并更新预览，不落盘。"""
        img_id, _file_path, orig_id, orig_path = self._current_image_ctx()
        if not img_id or not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        # 从输入框获取角度
        angle_text = self.rotate_angle_input.text().strip().replace("°", "")
        try:
            step_deg = float(angle_text) if angle_text else 0.0
        except ValueError:
            step_deg = 0.0
        # direction > 0 为正方向（顺时针），direction < 0 为负方向（逆时针）
        delta = step_deg if direction > 0 else -step_deg
        p = self._pending_for(orig_id)
        p["angle"] = float(p.get("angle") or 0.0) + float(delta)
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _reset_current_pending(self):
        _img_id, _fp, orig_id, orig_path = self._current_image_ctx()
        if not orig_id:
            return
        self._pending_edits.pop(orig_id, None)
        self._set_dirty_badge(orig_id)
        # 重新显示当前选择（优先修图版/原图）
        self._on_image_selected()

    def _on_move_node_up(self):
        """将当前选中的目录节点上移一位。"""
        self._move_node_in_tree(-1)

    def _on_move_node_down(self):
        """将当前选中的目录节点下移一位。"""
        self._move_node_in_tree(1)

    def _move_node_in_tree(self, direction: int):
        """
        移动当前选中的目录节点：
        - direction < 0: 上移（与前一个同级节点交换）
        - direction > 0: 下移（与后一个同级节点交换）
        """
        # 设置标志，跳过 on_catalog_current_changed 的校验
        self._moving_node = True
        try:
            current_item = self.catalog_tree.currentItem()
            if not current_item:
                StyledMessageBox.information(self, "提示", "请先选择一个目录节点", self.current_theme)
                return

            # 获取父节点
            parent_item = current_item.parent()
            if parent_item:
                # 有父节点，在父节点的子节点中查找位置
                current_index = parent_item.indexOfChild(current_item)
                sibling_count = parent_item.childCount()
            else:
                # 没有父节点，在根节点中查找
                root = self.catalog_tree.invisibleRootItem()
                current_index = root.indexOfChild(current_item)
                sibling_count = root.childCount()
                parent_item = root

            if sibling_count < 2:
                return

            # 计算目标位置
            target_index = current_index + direction
            if target_index < 0 or target_index >= sibling_count:
                # 已经在边界，无法移动
                return

            # 获取目标节点
            target_item = parent_item.child(target_index)
            if not target_item:
                return

            # 获取两个节点的模板项 ID（存储在 Qt.UserRole 中）
            current_tpl_id = current_item.data(0, Qt.UserRole)
            target_tpl_id = target_item.data(0, Qt.UserRole)
            if not current_tpl_id or not target_tpl_id:
                return
            # 占位 id（负数）：真实模板项后台创建中，DB 里还没有记录，交换会触发外键错误
            if int(current_tpl_id) <= 0 or int(target_tpl_id) <= 0:
                StyledMessageBox.information(self, "提示", "该目录正在保存中，请稍候再试", self.current_theme)
                return

            # 调用 repo 层交换当前 entry 的 EC 行顺序
            try:
                success = swap_entry_catalog_item_order(
                    entry_id=int(self.current_entry_id),
                    template_item_id_a=int(current_tpl_id),
                    template_item_id_b=int(target_tpl_id)
                )
                if not success:
                    return
            except Exception as e:
                print(f"[catalog-entry] swap sort order failed: {e}")
                return

            # 记住当前选中的节点 ID，刷新后恢复选中
            selected_tpl_id = current_tpl_id

            # 刷新目录树
            self._populate_catalog_tree()

            # 恢复选中状态
            try:
                self._select_tree_item_by_tpl_id(selected_tpl_id)
            except Exception as e:
                print(f"[catalog-entry] restore selection failed: {e}")
            
            # 移动后更新同级节点的序号（需要重新获取 parent_item）
            # 注意：如果移动的是模板固定节点，不需要更新序号
            try:
                current_item_after_refresh = self.catalog_tree.currentItem()
                if current_item_after_refresh:
                    # 检查当前节点是否是模板固定的
                    tpl_serial = current_item_after_refresh.data(0, Qt.UserRole + 10) or ""
                    tpl_name = current_item_after_refresh.data(1, Qt.UserRole + 10) or ""
                    # 如果是模板固定节点（有预设的编号或名称），不更新序号
                    if not (tpl_serial.strip() or tpl_name.strip()):
                        parent_item_after_refresh = current_item_after_refresh.parent()
                        if parent_item_after_refresh is None:
                            parent_item_after_refresh = self.catalog_tree.invisibleRootItem()
                        self._update_sibling_serials(parent_item_after_refresh)
            except Exception as e:
                print(f"[catalog-entry] update serials after move failed: {e}")
        except Exception as e:
            print(f"[catalog-entry] move node failed: {e}")
            # 不要闪退，只是静默失败
        finally:
            # 确保标志被清除
            self._moving_node = False

    def _select_tree_item_by_tpl_id(self, tpl_id: int):
        """根据模板项 ID 选中目录树中的节点。"""
        if not tpl_id:
            return

        try:
            def find_and_select(parent_item):
                if not parent_item:
                    return False
                for i in range(parent_item.childCount()):
                    try:
                        child = parent_item.child(i)
                        if not child:
                            continue
                        if child.data(0, Qt.UserRole) == tpl_id:
                            self.catalog_tree.setCurrentItem(child)
                            return True
                        if find_and_select(child):
                            return True
                    except Exception:
                        continue
                return False

            find_and_select(self.catalog_tree.invisibleRootItem())
        except Exception as e:
            print(f"[catalog-entry] select tree item failed: {e}")

    def _update_sibling_serials(self, parent_item):
        """
        更新同级节点的序号：按照当前顺序重新编号为 1, 2, 3...
        如果序号是模板固定的，则不更新。
        """
        if not parent_item:
            return
        
        try:
            # 确保 entry 已存在
            self._ensure_entry_record()
            if not self.current_entry_id:
                return

            child_count = parent_item.childCount()
            for i in range(child_count):
                try:
                    child = parent_item.child(i)
                    if not child:
                        continue
                    
                    # 检查序号是否是模板固定的
                    tpl_serial = child.data(0, Qt.UserRole + 10) or ""
                    if tpl_serial.strip():
                        # 模板固定的序号，不更新
                        continue
                    
                    # 计算新序号：索引 + 1
                    new_serial = str(i + 1)
                    
                    # 更新 UI
                    self._suppress_catalog_changed = True
                    child.setText(0, new_serial)
                    self._suppress_catalog_changed = False
                    
                    # 序号改由 pending 队列异步批量落盘（经由 _stage_pending 同时镜像到 WAL）
                    tpl_item_id = child.data(0, Qt.UserRole)
                    ec_item_id = child.data(1, Qt.UserRole)
                    if tpl_item_id:
                        self._stage_pending(tpl_item_id, child, ec_item_id, {"serial": new_serial})
                except Exception as e:
                    print(f"[catalog-entry] process child {i} failed: {e}")
                    continue
        except Exception as e:
            print(f"[catalog-entry] update sibling serials failed: {e}")

    def _commit_current_pending(self):
        img_id, fp, orig_id, _orig_path = self._current_image_ctx()
        if not orig_id:
            return
        # 保存修图后刷新列表时恢复当前选中
        self._select_after_reload = {"file_path": fp or "", "img_id": img_id}
        self._commit_all_pending(blocking=True, only_orig_id=orig_id)

    def _commit_all_pending(self, blocking: bool = True, only_orig_id=None):
        """
        将 pending 修图一次性落盘 + 写库：
        - 输出固定为 *_retouched*（覆盖）
        - upsert retouched（唯一性由 repo 层保证）
        """
        if not self._pending_edits:
            return True
        # 收集要提交的列表，避免遍历过程中修改 dict
        targets = []
        for oid, p in list(self._pending_edits.items()):
            if only_orig_id is not None and oid != only_orig_id:
                continue
            dirty = is_dirty(p)
            if dirty:
                targets.append((oid, p))
        if not targets:
            return True
        badge_orig_id = only_orig_id
        if badge_orig_id is None:
            try:
                _, _, badge_orig_id, _ = self._current_image_ctx()
            except Exception:
                badge_orig_id = None

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            updates = []
            saved_orig_ids = []
            for orig_id, p in targets:
                info = None
                try:
                    # 连续修图：输入基线优先使用 retouched；输出命名仍以 original 为准
                    info = resolve_edit_base_image_info(image_id=int(orig_id), fallback_path="")
                except Exception:
                    info = None
                if not info:
                    raise RuntimeError("数据库中找不到原图记录")
                base_src_path = (info.get("base_file_path") or "").strip()
                orig_path_for_name = (info.get("orig_file_path") or "").strip()
                if (not base_src_path) or (not os.path.exists(base_src_path)):
                    raise FileNotFoundError(f"修图基线文件不存在：{base_src_path}")

                if not orig_path_for_name:
                    orig_path_for_name = base_src_path
                out_path, out_name = self._retouched_output_path(orig_path_for_name)

                # 从“基线图”（优先修图版）应用本次 pending 生成最终图并保存（覆盖同一文件）
                process_and_save(orig_path=base_src_path, pending=p, out_path=out_path, out_name=out_name)

                mime_name = out_name[:-len(CryptoService.ENCRYPTED_EXT)] if out_name.lower().endswith(CryptoService.ENCRYPTED_EXT) else out_name
                mime, _ = mimetypes.guess_type(mime_name)
                size = os.path.getsize(out_path) if os.path.exists(out_path) else None
                updates.append(
                    {
                        "orig_id": int(info.get("orig_id") or orig_id),
                        "entry_catalog_item_id": info.get("orig_entry_catalog_item_id"),
                        "orig_sort_order": info.get("orig_sort_order"),
                        "out_path": out_path,
                        "out_name": out_name,
                        "mime_type": mime or "",
                        "file_size": size,
                    }
                )
                saved_orig_ids.append(orig_id)
            # 批量写库：一次提交更接近原行为
            try:
                upsert_retouched_batch(updates)
            except Exception as e:
                self._set_dirty_badge(badge_orig_id)
                StyledMessageBox.warning(self, "保存修图失败", f"修图文件已生成，但数据库记录保存失败：{e}\n\n未保存标记已保留，请检查数据库连接后重试。", self.current_theme)
                return False
            for orig_id in saved_orig_ids:
                self._pending_edits.pop(orig_id, None)
        except Exception as e:
            self._set_dirty_badge(badge_orig_id)
            StyledMessageBox.warning(self, "保存修图失败", f"修图保存失败：{e}\n\n未保存标记已保留，请检查后重试。", self.current_theme)
            return False
        finally:
            QApplication.restoreOverrideCursor()

        # 刷新并更新标记/预览
        self._set_dirty_badge(None)
        self._load_images_for_item(self._current_catalog_item())
        return True

    def _populate_catalog_tree(self):
        """从数据库加载当前选中模板的目录树。"""
        # 刷新树时隐藏自动补全弹窗
        self._on_autocomplete_hide()
        self.catalog_tree.clear()
        tpl_id = self._current_template_id()
        if not tpl_id:
            print("[catalog-entry] no template selected")
            return
        self.current_template_id = tpl_id
        # 确保当前 entry 存在
        self._ensure_entry_record()
        if not getattr(self, "_purged_empty_catalog_items_once", False):
            self._purged_empty_catalog_items_once = True
            try:
                if self.current_entry_id:
                    # 1) 先合并同槽位重复 EC 行（关键：避免空行遮蔽数据行）
                    #    历史并发 upsert / WAL 回放可能产生重复，加载前必须先合并，
                    #    否则用户看到的可能是一条空白替身，而真正有数据的行被隐藏。
                    merged = merge_duplicate_entry_catalog_items(
                        entry_id=int(self.current_entry_id)
                    )
                    if merged:
                        print(f"[catalog-entry] merged duplicate catalog items: {merged}")
                    # 2) 再清掉真正的空行（只删 1 小时以前都没字段的行，保守策略）
                    purged = delete_empty_entry_catalog_items(entry_id=int(self.current_entry_id))
                    if purged:
                        print(f"[catalog-entry] purged empty catalog items: {purged}")
            except Exception as e:
                print(f"[catalog-entry] purge empty catalog items failed: {e}")

        try:
            rows = list_catalog_template_items(tpl_id)
        except Exception as e:
            print(f"[catalog-entry] load template items failed: {e}")
            return

        by_parent = {}
        for r in rows:
            parent_key = r.get("parent_id") or None  # 兼容 parent_id 为 0 的数据
            by_parent.setdefault(parent_key, []).append(r)

        # 批量加载所有 EC 项（1 次 DB 查询替代 N 次）
        _empty_ec = {"id": None, "serial": "", "name": "", "year": None,
                     "month": None, "day": None, "pages": None, "remark": ""}
        ec_cache = {}
        if self.current_entry_id:
            try:
                ec_cache = batch_get_entry_catalog_items(entry_id=int(self.current_entry_id))
            except Exception as e:
                print(f"[catalog-entry] batch load ec items failed: {e}")

        def add_nodes(parent_id, parent_item):
            children = by_parent.get(parent_id, [])
            child_infos = []
            has_real_leaf_data = False

            for r in children:
                # 模板预设的编号和名称（用于判断是否锁定）
                tpl_serial = r.get("serial") or ""
                tpl_name = r.get("name") or ""
                is_structural = bool(tpl_serial.strip() or tpl_name.strip())
                # 有子节点的模板项是"类别节点"，不是叶子槽位
                has_children = bool(by_parent.get(r["id"]))

                # 从缓存中获取 EC 数据（替代单次 DB 查询）
                ec_item = ec_cache.get(r["id"]) or dict(_empty_ec)
                has_data = ec_item.get("id") is not None
                child_infos.append((r, tpl_serial, tpl_name, is_structural, ec_item, has_data, has_children))
                if not is_structural and has_data:
                    has_real_leaf_data = True

            blank_shown = False  # 每个父节点下只保留一个空白行

            for r, tpl_serial, tpl_name, is_structural, ec_item, has_data, has_children in child_infos:
                if not is_structural and not has_data:
                    # 类别节点（有子节点）不需要空白行占位，只有叶子槽位才需要
                    if has_children:
                        continue
                    # 只有在当前父节点没有任何实际录入内容时，才保留一个空行
                    if has_real_leaf_data:
                        continue
                    if blank_shown:
                        continue
                    blank_shown = True
                    # 显示为完全空白行（无序号、无数据）
                    item = self._create_item(
                        data={"serial": "", "name": "", "year": None,
                              "month": None, "day": None, "pages": None, "desc": ""},
                        tpl_serial=tpl_serial,
                        tpl_name=tpl_name,
                    )
                else:
                    item = self._create_item(
                        data={
                            # 优先显示已录入数据的编号/名称，若无则回退模板定义
                            "serial": ec_item.get("serial") or tpl_serial,
                            "name": ec_item.get("name") or tpl_name,
                            "year": ec_item["year"],
                            "month": ec_item["month"],
                            "day": ec_item["day"],
                            "pages": ec_item["pages"],
                            "desc": ec_item["remark"],
                        },
                        tpl_serial=tpl_serial,
                        tpl_name=tpl_name,
                    )

                # 存储模板项ID和 entry_catalog_item ID
                item.setData(0, Qt.UserRole, r["id"])
                item.setData(1, Qt.UserRole, ec_item["id"])
                # 乐观锁基线：加载时观察到的 updated_at，staging 时会传回 DB 检测冲突
                item.setData(1, Qt.UserRole + 20, ec_item.get("updated_at"))
                # 将节点挂载到父节点/根节点
                parent_item.addChild(item)
                if r.get("id"):
                    add_nodes(r["id"], item)

        self._suppress_catalog_changed = True
        add_nodes(None, self.catalog_tree.invisibleRootItem())
        # 加载后自动为没有序号的子节点分配序号
        self._auto_assign_serials(self.catalog_tree.invisibleRootItem())
        # 修正序号：确保同级数据行从 1 连续编号（消除因空槽位偏移导致的错误序号）
        self._fix_serials_recursive(self.catalog_tree.invisibleRootItem())
        self._suppress_catalog_changed = False
        self.catalog_tree.expandAll()
        # 更新总页数统计
        self._update_total_pages_label()
        # 后台预热自动补全词库：用户第一次键入就命中缓存，不会卡 UI
        try:
            tpl_name = self._get_current_template_name()
            if tpl_name:
                get_autocomplete_manager().warmup_template_async(tpl_name)
        except Exception as e:
            print(f"[catalog-entry] autocomplete warmup schedule failed: {e}")

    def _update_total_pages_label(self, *, refresh_image_count: bool = True):
        """更新左下角的总页数 / 图片数 / 总条数统计（防抖 + 异步）。

        性能说明（2026-05 修复）
        -----------------------
        旧实现对图片数做了同步 DB 查询 ``count_entry_total_images()``，并在每次
        Tab 切列（col 1 或 5）都被调用一次——远程 MySQL 往返 10~100ms，
        密集录入时光标一直转圈。修复思路：

        1. **合并重复调用**：通过 ``_stats_refresh_timer``（180ms 单次定时器）
           把连续键入的多次请求合并成一次真正刷 UI。
        2. **图片数异步化**：只有在显式要求（图片被增删/目录刚加载）时才调
           ``count_entry_total_images()``，并且放到后台 Worker 线程去跑，
           结果回来再缓存、刷 label。主线程零 DB IO。
        3. **光标移动/键入路径不触发 DB**：``_on_catalog_item_changed`` 走
           ``refresh_image_count=False`` 分支，只刷新前端汇总字段。

        参数
        ----
        refresh_image_count
            True（默认）—— 下一次 timer tick 会发起异步图片数查询。
            False —— 仅刷新基于树内容的统计（页数/总条数），不查 DB。
        """
        if not hasattr(self, 'total_pages_label'):
            return
        if refresh_image_count:
            self._stats_refresh_need_image_count = True
        try:
            self._stats_refresh_timer.start()
        except RuntimeError:
            # 对话框已被 deleteLater，忽略
            pass

    def _do_refresh_stats_ui(self):
        """真正执行统计刷新的地方（防抖 timer 触发）。主线程纯内存扫描，无 DB IO。"""
        if getattr(self, "_is_closing", False):
            return
        if not hasattr(self, 'total_pages_label'):
            return
        # 再次保护：C++ tree 可能已被 destroy
        try:
            root = self.catalog_tree.invisibleRootItem()
        except RuntimeError:
            return

        total_pages = 0
        entry_count = 0

        def _walk(node):
            nonlocal total_pages, entry_count
            pages_str = node.text(5).strip()
            if pages_str:
                try:
                    total_pages += int(pages_str)
                except ValueError:
                    pass
            tpl_serial = node.data(0, Qt.UserRole + 10) or ""
            tpl_name = node.data(1, Qt.UserRole + 10) or ""
            is_tpl = bool(tpl_serial.strip() or tpl_name.strip())
            name = node.text(1).strip()
            if not is_tpl and name:
                entry_count += 1
            for i in range(node.childCount()):
                _walk(node.child(i))

        try:
            for i in range(root.childCount()):
                _walk(root.child(i))
        except RuntimeError:
            return

        try:
            self.total_pages_label.setText(f"总页数：{total_pages}")
        except RuntimeError:
            return
        if hasattr(self, 'total_entries_label'):
            try:
                self.total_entries_label.setText(f"总条数：{entry_count}")
            except RuntimeError:
                pass

        # 图片数：优先展示缓存值；需要时再启异步查询刷新
        if hasattr(self, 'total_images_label'):
            cached = self._total_images_cache
            if cached is not None:
                try:
                    self.total_images_label.setText(f"图片数：{cached}")
                except RuntimeError:
                    return
            if self._stats_refresh_need_image_count:
                self._stats_refresh_need_image_count = False
                self._schedule_image_count_refresh()

    def _schedule_image_count_refresh(self):
        """把 count_entry_total_images 放到后台 Worker 线程，避免阻塞 UI。"""
        if getattr(self, "_is_closing", False):
            return
        if self._image_count_in_flight:
            return  # 已在飞行，忽略
        if not self.current_entry_id:
            # 没有 entry 时直接显示 0
            self._total_images_cache = 0
            if hasattr(self, 'total_images_label'):
                try:
                    self.total_images_label.setText("图片数：0")
                except RuntimeError:
                    pass
            return
        entry_id = int(self.current_entry_id)
        self._image_count_in_flight = True

        def _do_count():
            try:
                return int(count_entry_total_images(entry_id=entry_id))
            except Exception as e:
                print(f"[catalog-entry] count_entry_total_images failed: {e}")
                return None

        def _on_loaded(value):
            # 已关闭就丢弃结果，绝不触 C++ 对象
            if getattr(self, "_is_closing", False):
                return
            try:
                self._image_count_in_flight = False
                if value is None:
                    return
                self._total_images_cache = int(value)
                if hasattr(self, 'total_images_label'):
                    self.total_images_label.setText(f"图片数：{value}")
            except RuntimeError:
                # C++ label 已销毁
                return

        def _on_error(err):
            # 标志复位；保留旧缓存，下次刷新再重试
            if getattr(self, "_is_closing", False):
                return
            self._image_count_in_flight = False
            print(f"[catalog-entry] image-count worker error: {err}")

        worker = Worker(_do_count)
        worker.signals.finished.connect(_on_loaded)
        worker.signals.error.connect(_on_error)
        self._thread_pool.start(worker)

    def _apply_catalog_font_zoom(self, point_size: float):
        f = QFont(self._base_font)
        f.setPointSizeF(point_size)
        self.catalog_tree.setFont(f)
        if getattr(self, "_catalog_name_editor", None) is not None:
            try:
                self._catalog_name_editor.setFont(QFont(f))
            except RuntimeError:
                pass
        if hasattr(self, "catalog_preview"):
            self.catalog_preview.setFont(f)

    def _apply_toolbar_style(self):
        """同步模板选择区与操作按钮的样式，适配主题。"""
        if not hasattr(self, "action_frame"):
            return
        if self.current_theme == "dark":
            bg = "#1f2937"
            border = "#2f3a4c"
            text = "#e5e7eb"
            combo_bg = "#2b3544"
            btn_bg = "#2b3544"
            btn_bg_hover = "#334155"
        else:
            bg = "#f7f9fb"
            border = "#d0d7de"
            text = "#1f2937"
            combo_bg = "#ffffff"
            btn_bg = "#ffffff"
            btn_bg_hover = "#e8f0fe"

        self.action_frame.setStyleSheet(
            f"""
            QFrame#catalog_action_frame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
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
            QPushButton#catalog_action_btn {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 10px;
                color: {text};
                font-weight: 600;
                min-height: 26px;
            }}
            QPushButton#catalog_action_btn:hover {{
                background: {btn_bg_hover};
            }}
            QPushButton#catalog_action_btn:pressed {{
                background: {btn_bg};
            }}
            QPushButton#pager_btn {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 2px 8px;
                color: {text};
                font-weight: 500;
                min-height: 20px;
                max-height: 24px;
            }}
            QPushButton#pager_btn:hover {{
                background: {btn_bg_hover};
            }}
            QPushButton#pager_btn:pressed {{
                background: {btn_bg};
            }}
            QLineEdit#pager_input {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 2px 6px;
                color: {text};
                min-height: 22px;
                max-height: 22px;
            }}
            QLabel#pager_total {{
                color: {text};
            }}
            QToolButton#pager_icon_btn {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 2px;
                min-height: 22px;
                min-width: 22px;
            }}
            QToolButton#pager_icon_btn:hover {{
                background: {btn_bg_hover};
            }}
            QToolButton#pager_icon_btn:pressed {{
                background: {btn_bg};
            }}
            """
        )

    # === 图片挂接（单节点） ===
    def _image_root(self):
        try:
            root = AppSettings().get_image_root()
            if root:
                return root
        except Exception:
            pass
        return os.getenv("IMAGE_ROOT", os.path.join(os.getcwd(), "data", "images"))

    # 图片相关的纯工具函数已抽到：inventory_ui/utils/image_loading.py

    def on_catalog_current_changed(self, item, prev=None):
        """行切换时触发：检查离开的行的日期完整性和升序。"""
        # 行切换时隐藏自动补全弹窗
        self._on_autocomplete_hide()
        if self._catalog_name_editor_item is not None and self._catalog_name_editor_item is not item:
            self._hide_catalog_name_editor()
        # 行切换时立即落盘 pending 保存，避免数据丢失
        self._flush_catalog_pending_saves()
        # 如果正在移动节点，跳过所有校验
        if getattr(self, '_moving_node', False):
            return
        
        # 如果正在程序化恢复选中，跳过校验
        if getattr(self, '_restoring_selection', False):
            self._load_images_for_item(item)
            return

        # 如果是同一行内切换列（Tab切换），跳过校验
        if item is prev or item == prev:
            return

        # 检查离开的行（prev）是否需要校验
        if prev is not None:
            # 检查是否是模板原有条目（有预设名称的），模板原有条目不检查年月日
            tpl_name = prev.data(1, Qt.UserRole + 10) or ""
            if tpl_name.strip():
                # 模板原有条目，跳过年月日检查
                self._load_images_for_item(item)
                return
            
            # 检查是否输入了目录名称
            name_str = prev.text(1).strip()
            
            # 只要输入了目录名称，就必须填写年月日
            if name_str:
                year_str = prev.text(2).strip()
                month_str = prev.text(3).strip()
                day_str = prev.text(4).strip()
                has_any = bool(year_str or month_str or day_str)
                is_complete = bool(year_str and month_str and day_str)

                # 如枟有输入但不完整，或者完全没输入，提示并恢复选中
                if not is_complete:
                    if self._date_warning_suppressed:
                        pass  # 已提示过，允许跳过
                    # else:
                    #     missing = []
                    #     if not year_str: missing.append("年")
                    #     if not month_str: missing.append("月")
                    #     if not day_str: missing.append("日")
                    #     StyledMessageBox.warning(self, "提示", f"输入目录名称后必须填写年月日\n\n缺少：{'、'.join(missing)}", self.current_theme)
                    #     self._date_warning_suppressed = True
                    #     self._restoring_selection = True
                    #     self.catalog_tree.setCurrentItem(prev)
                    #     self._restoring_selection = False
                    #     if not year_str:
                    #         self._reenter_edit(prev, 2)
                    #     elif not month_str:
                    #         self._reenter_edit(prev, 3)
                    #     else:
                    #         self._reenter_edit(prev, 4)
                    #     return

                # 如果日期完整，检查升序（这是提示，可以忽略）
                if is_complete:
                    passed, edit_col = self._check_date_ascending(prev)
                    if not passed:
                        # 用户选择修改，恢复选中并定位到对应字段
                        self._restoring_selection = True
                        self.catalog_tree.setCurrentItem(prev)
                        self._restoring_selection = False
                        self._reenter_edit(prev, edit_col or 2)
                        return

        self._load_images_for_item(item)

    def _on_request_edit_column(self, item, column):
        """Tab 键切换列时由 delegate 触发，进入指定列的编辑状态。"""
        if self._validation_failed_reenter:
            self._validation_failed_reenter = False
            return
        if item:
            self.catalog_tree.setCurrentItem(item, column)
            self._schedule_catalog_edit(item, column)

    def _on_catalog_item_pressed(self, item, column):
        if not item or getattr(self, "_is_closing", False):
            return
        self.catalog_tree.setCurrentItem(item, column)
        self._schedule_catalog_edit(item, column)

    def _on_catalog_item_clicked(self, item, column):
        if not item or getattr(self, "_is_closing", False):
            return
        self._schedule_catalog_edit(item, column)

    def _catalog_cell_rect(self, item, column):
        row_rect = self.catalog_tree.visualItemRect(item)
        header = self.catalog_tree.header()
        x = header.sectionViewportPosition(column)
        w = header.sectionSize(column)
        return x, row_rect.y(), w, row_rect.height()

    def _show_catalog_name_editor(self, item):
        editor = self._catalog_name_editor
        if editor is None or item is None:
            return False
        try:
            if item.treeWidget() is not self.catalog_tree:
                return False
            tpl_value = item.data(1, Qt.UserRole + 10) or ""
            if str(tpl_value).strip():
                return False
            x, y, w, h = self._catalog_cell_rect(item, 1)
            editor.setFont(self.catalog_tree.font())
            self._catalog_name_editor_item = item
            self._catalog_name_editor_updating = True
            try:
                if editor.text() != item.text(1):
                    editor.setText(item.text(1))
                editor.setCursorPosition(len(editor.text()))
            finally:
                self._catalog_name_editor_updating = False
            editor.setGeometry(x + 1, y + 1, max(1, w - 2), max(1, h - 2))
            editor.show()
            editor.raise_()
            editor.setFocus(Qt.OtherFocusReason)
            return True
        except RuntimeError:
            return False

    def _hide_catalog_name_editor(self):
        editor = self._catalog_name_editor
        if editor is None:
            return
        try:
            if editor.isVisible():
                self._sync_catalog_name_editor_to_item()
                editor.hide()
        except RuntimeError:
            pass
        self._catalog_name_editor_item = None

    def _sync_catalog_name_editor_to_item(self):
        editor = self._catalog_name_editor
        item = self._catalog_name_editor_item
        if editor is None or item is None:
            return
        try:
            text = editor.text()
            if item.text(1) == text and not (text and not item.text(0).strip()):
                return
            if item.text(1) != text:
                self._suppress_catalog_changed = True
                try:
                    item.setText(1, text)
                finally:
                    self._suppress_catalog_changed = False

            fields = {"name": text}
            if text and not item.text(0).strip() and not (item.data(0, Qt.UserRole + 10) or "").strip():
                parent_item = item.parent() or self.catalog_tree.invisibleRootItem()
                auto_serial = str(parent_item.indexOfChild(item) + 1)
                self._suppress_catalog_changed = True
                try:
                    item.setText(0, auto_serial)
                finally:
                    self._suppress_catalog_changed = False
                fields["serial"] = auto_serial

            if not self.current_entry_id and not text:
                return
            self._ensure_entry_record()
            if not self.current_entry_id:
                return
            tpl_item_id = item.data(0, Qt.UserRole)
            ec_item_id = item.data(1, Qt.UserRole)
            if tpl_item_id:
                self._stage_pending(tpl_item_id, item, ec_item_id, fields)
            if text:
                QTimer.singleShot(0, lambda v=text, i=item: self._record_autocomplete_entry(i, v))
            self._update_total_pages_label(refresh_image_count=False)
        except RuntimeError:
            return

    def _on_catalog_name_editor_text_changed(self, text):
        if self._catalog_name_editor_updating:
            return
        editor = self._catalog_name_editor
        item = self._catalog_name_editor_item
        if editor is None or item is None:
            return
        self._catalog_name_editor_seq += 1
        seq = self._catalog_name_editor_seq

        def emit_later():
            if seq != self._catalog_name_editor_seq:
                return
            if self._catalog_name_editor is not editor or self._catalog_name_editor_item is not item:
                return
            try:
                if not editor.isVisible() or editor.text() != text:
                    return
            except RuntimeError:
                return
            self._on_request_autocomplete(item, 1, editor, text)

        QTimer.singleShot(80, emit_later)

    def _commit_active_catalog_editor(self):
        # 提交编辑器时隐藏自动补全弹窗
        self._on_autocomplete_hide()
        if self._catalog_name_editor is not None:
            try:
                if self._catalog_name_editor.isVisible():
                    self._sync_catalog_name_editor_to_item()
                    return True
            except RuntimeError:
                return False
        delegate = getattr(self, "_catalog_delegate", None)
        if delegate is None:
            return False
        editor = getattr(delegate, "_current_editor", None)
        item = getattr(delegate, "_current_item", None)
        column = getattr(delegate, "_current_col", -1)
        if editor is None or item is None or column < 0:
            return False
        try:
            if hasattr(editor, "text"):
                text = editor.text()
                if item.text(column) != text:
                    item.setText(column, text)
            delegate.commitData.emit(editor)
            delegate.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
            return True
        except RuntimeError:
            return False

    def _schedule_catalog_edit(self, item, column, delay_ms: int = 0):
        if not item or getattr(self, "_is_closing", False):
            return
        try:
            tree = getattr(self, "catalog_tree", None)
            if tree is None or item.treeWidget() is not tree:
                return
            if int(column) == 1:
                self._show_catalog_name_editor(item)
                return
            self._hide_catalog_name_editor()
        except RuntimeError:
            return

        def _do_edit(i=item, c=column):
            if getattr(self, "_is_closing", False):
                return
            try:
                tree = getattr(self, "catalog_tree", None)
                if tree is None or i.treeWidget() is not tree:
                    return
                if tree.currentItem() is not i or tree.currentColumn() != c:
                    return
                delegate = getattr(self, "_catalog_delegate", None)
                if delegate is not None:
                    active_editor = getattr(delegate, "_current_editor", None)
                    active_item = getattr(delegate, "_current_item", None)
                    active_col = getattr(delegate, "_current_col", -1)
                    if active_editor is not None and active_item is i and active_col == c:
                        try:
                            active_editor.setFocus(Qt.OtherFocusReason)
                        except RuntimeError:
                            pass
                        return
                tree.editItem(i, c)
                active_editor = getattr(getattr(self, "_catalog_delegate", None), "_current_editor", None)
                if active_editor is not None:
                    active_editor.setFocus(Qt.OtherFocusReason)
            except RuntimeError:
                return

        if int(delay_ms or 0) <= 0:
            _do_edit()
        else:
            QTimer.singleShot(int(delay_ms or 0), _do_edit)

    def _is_plain_catalog_text_key(self, event):
        try:
            text = event.text()
            if not text:
                return False
            if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                return False
            if event.key() in (
                Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Return, Qt.Key_Enter,
                Qt.Key_Escape, Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right,
            ):
                return False
            return True
        except Exception:
            return False

    def _start_catalog_edit_with_initial_key(self, item, column, event):
        if not item or getattr(self, "_is_closing", False):
            return False
        try:
            if column < 0 or column >= self.catalog_tree.columnCount():
                return False
            if item.treeWidget() is not self.catalog_tree:
                return False
            tpl_value = item.data(column, Qt.UserRole + 10) or ""
            if column in (0, 1) and str(tpl_value).strip():
                return False
            key = event.key()
            modifiers = event.modifiers()
            text = event.text()
            auto_repeat = event.isAutoRepeat()
            count = event.count()

            posted = {"done": False}

            def post_initial_key():
                if posted["done"] or getattr(self, "_is_closing", False):
                    return
                try:
                    delegate = getattr(self, "_catalog_delegate", None)
                    if delegate is None:
                        return
                    editor = getattr(delegate, "_current_editor", None)
                    if editor is None:
                        return
                    if getattr(delegate, "_current_item", None) is not item:
                        return
                    if getattr(delegate, "_current_col", -1) != column:
                        return
                    editor.setFocus()
                    QApplication.postEvent(
                        editor,
                        QKeyEvent(QEvent.KeyPress, key, modifiers, text, auto_repeat, count),
                    )
                    posted["done"] = True
                except RuntimeError:
                    return

            self.catalog_tree.setCurrentItem(item, column)
            if int(column) == 1:
                if not self._show_catalog_name_editor(item):
                    return False
                editor = self._catalog_name_editor

                def post_initial_key_to_overlay():
                    if posted["done"] or getattr(self, "_is_closing", False):
                        return
                    try:
                        if self._catalog_name_editor is not editor or self._catalog_name_editor_item is not item:
                            return
                        if editor is None or not editor.isVisible():
                            return
                        editor.setFocus()
                        QApplication.postEvent(
                            editor,
                            QKeyEvent(QEvent.KeyPress, key, modifiers, text, auto_repeat, count),
                        )
                        posted["done"] = True
                    except RuntimeError:
                        return

                QTimer.singleShot(0, post_initial_key_to_overlay)
                return True
            self.catalog_tree.editItem(item, column)
            QTimer.singleShot(0, post_initial_key)
            return True
        except RuntimeError:
            return False

    def _on_request_enter_new_row(self, current):
        """Enter 键换行时由 delegate 触发，处理换行和新增行逻辑。"""
        if not current:
            return

        # 检查是否是模板原有条目（有预设名称的），模板原有条目不检查年月日
        tpl_name = current.data(1, Qt.UserRole + 10) or ""
        is_template_item = bool(tpl_name.strip())
        
        # 检查是否输入了目录名称
        name_str = current.text(1).strip()
        
        # 只要输入了目录名称，就必须填写年月日（模板原有条目除外）
        if name_str and not is_template_item:
            # 检查当前行日期是否完整
            year_str = current.text(2).strip()
            month_str = current.text(3).strip()
            day_str = current.text(4).strip()
            is_complete = bool(year_str and month_str and day_str)

            # 如果有输入但不完整，提示并阻止换行
            # if not is_complete:
            #     if not self._date_warning_suppressed:
            #         missing = []
            #         if not year_str: missing.append("年")
            #         if not month_str: missing.append("月")
            #         if not day_str: missing.append("日")
            #         StyledMessageBox.warning(self, "提示", f"输入目录名称后必须填写年月日\n\n缺少：{'、'.join(missing)}")
            #         self._date_warning_suppressed = True
            #         if not year_str:
            #             self._reenter_edit(current, 2)
            #         elif not month_str:
            #             self._reenter_edit(current, 3)
            #         else:
            #             self._reenter_edit(current, 4)
            #         return

            # 如果日期完整，检查升序
            if is_complete:
                passed, edit_col = self._check_date_ascending(current)
                if not passed:
                    self._reenter_edit(current, edit_col or 2)
                    return

        # 获取父节点
        parent_item = current.parent()
        if parent_item is None:
            parent_item = self.catalog_tree.invisibleRootItem()
        
        # 检查当前行是否是最后一行（同级中的最后一个）
        child_count = parent_item.childCount()
        current_index = parent_item.indexOfChild(current)
        is_last_row = (current_index == child_count - 1)
        
        # 生成下一年的目录名称（如果当前行有年份开头的名称）
        auto_name = self._generate_next_year_name(name_str) if name_str else ""
        
        if is_last_row:
            # 最后一行，创建新行
            self._create_tpl_node(parent_item, prev_item=current)
        else:
            # 不是最后一行，移动到下一行并自动填充年份
            next_item = parent_item.child(current_index + 1)
            if next_item:
                # 如果下一行序号为空且非模板固定序号，自动填充
                next_serial = next_item.text(0).strip()
                next_tpl_serial = next_item.data(0, Qt.UserRole + 10) or ""
                if not next_serial and not next_tpl_serial.strip():
                    auto_serial = str(current_index + 2)
                    self._suppress_catalog_changed = True
                    next_item.setText(0, auto_serial)
                    self._suppress_catalog_changed = False
                    self._ensure_entry_record()
                    if self.current_entry_id:
                        tpl_item_id_s = next_item.data(0, Qt.UserRole)
                        ec_item_id_s = next_item.data(1, Qt.UserRole)
                        if tpl_item_id_s:
                            self._stage_pending(tpl_item_id_s, next_item, ec_item_id_s, {"serial": auto_serial})

                # 如果下一行的目录名称为空，且有自动生成的名称，则填充
                next_name = next_item.text(1).strip()
                next_tpl_name = next_item.data(1, Qt.UserRole + 10) or ""
                if not next_name and not next_tpl_name.strip() and auto_name:
                    self._suppress_catalog_changed = True
                    next_item.setText(1, auto_name)
                    self._suppress_catalog_changed = False
                    # 保存到数据库（经由 _stage_pending 同步镜像到 WAL）
                    tpl_item_id = next_item.data(0, Qt.UserRole)
                    ec_id = next_item.data(1, Qt.UserRole)
                    if tpl_item_id and self.current_entry_id:
                        self._stage_pending(tpl_item_id, next_item, ec_id, {"name": auto_name})
                
                self.catalog_tree.setCurrentItem(next_item, 1)  # 设置到目录名称列
                self._schedule_catalog_edit(next_item, 1)

    def _on_request_autocomplete(self, item, column, editor, input_text):
        """处理自动补全请求。"""
        if column != 1:
            return
        if not item:
            return
        
        self._autocomplete_editor = editor
        self._autocomplete_item = item
        self._autocomplete_column = column
        template_name = self._get_current_template_name()
        if not template_name:
            return
        
        item_name, parent_item_name = self._get_catalog_item_context(item)
        if not item_name:
            item_name = parent_item_name or "默认"
            parent_item_name = None

        self._autocomplete_context = (template_name, item_name, parent_item_name)

        manager = get_autocomplete_manager()
        candidates = manager.match_candidates_global(
            template_name=template_name,
            input_text=input_text.strip(),
        )
        
        if not candidates:
            self._autocomplete_popup.hide()
            return
        
        if editor:
            editor_rect = editor.rect()
            global_pos = editor.mapToGlobal(editor_rect.bottomLeft())
            self._autocomplete_popup.show_candidates(candidates, global_pos)

    def _on_autocomplete_selected(self, candidate_text):
        """
        处理自动补全选择。
        将选中的候选词填充到编辑器中，并记录使用次数。
        """
        if self._autocomplete_editor is self._catalog_name_editor:
            try:
                self._catalog_name_editor_updating = True
                self._autocomplete_editor.setText(candidate_text)
                self._autocomplete_editor.setCursorPosition(len(candidate_text))
                self._autocomplete_editor.setFocus(Qt.OtherFocusReason)
            except RuntimeError:
                self._autocomplete_editor = None
            finally:
                self._catalog_name_editor_updating = False
            self._sync_catalog_name_editor_to_item()
        elif self._autocomplete_editor and hasattr(self._autocomplete_editor, 'setText'):
            # 先断开 textChanged 信号，避免填充时又触发自动补全
            try:
                self._autocomplete_editor.textChanged.disconnect(self._catalog_delegate._on_text_changed_for_autocomplete)
            except Exception:
                pass
            
            try:
                self._autocomplete_editor.setText(candidate_text)
                # 将光标移动到末尾
                if hasattr(self._autocomplete_editor, 'setCursorPosition'):
                    self._autocomplete_editor.setCursorPosition(len(candidate_text))
                # 让编辑器重新获得焦点
                self._autocomplete_editor.setFocus()
            except RuntimeError:
                self._autocomplete_editor = None
            
            # 重新连接 textChanged 信号
            try:
                if self._autocomplete_editor:
                    self._autocomplete_editor.textChanged.connect(self._catalog_delegate._on_text_changed_for_autocomplete)
            except Exception:
                pass

        target_item = self._autocomplete_item or getattr(self._catalog_delegate, "_current_item", None)
        target_column = self._autocomplete_column if self._autocomplete_column >= 0 else 1
        if target_item is not None and target_column == 1:
            try:
                if target_item.text(1) != candidate_text:
                    target_item.setText(1, candidate_text)
            except RuntimeError:
                pass
        
        if self._autocomplete_context and candidate_text:
            template_name, item_name, parent_item_name = self._autocomplete_context
            try:
                manager = get_autocomplete_manager()
                manager.record_usage(template_name, item_name, candidate_text, parent_item_name)
            except Exception:
                pass
    
    def _is_autocomplete_popup_visible(self):
        """检查自动补全弹窗是否可见。"""
        return self._autocomplete_popup.isVisible() if self._autocomplete_popup else False
    
    def _on_autocomplete_move(self, direction):
        """处理弹窗中的上下移动。"""
        if self._autocomplete_popup and self._autocomplete_popup.isVisible():
            self._autocomplete_popup.move_selection(direction)
    
    def _on_autocomplete_confirm(self):
        """处理弹窗中的确认选择。"""
        if self._autocomplete_popup and self._autocomplete_popup.isVisible():
            self._autocomplete_popup.confirm_selection()
    
    def _on_autocomplete_hide(self):
        """处理隐藏弹窗。"""
        if self._autocomplete_popup:
            self._autocomplete_popup.hide()

    def _get_current_template_name(self) -> str:
        """获取当前选中的模板名称。"""
        if hasattr(self, 'tpl_combo') and self.tpl_combo:
            return self.tpl_combo.currentText().strip()
        return ""

    def _get_catalog_item_context(self, item) -> tuple:
        """获取目录条目的上下文信息。"""
        if not item:
            return ("", "")
        
        current = item
        category_node = None
        
        while current:
            tpl_name = current.data(1, Qt.UserRole + 10) or ""
            if tpl_name.strip():
                category_node = current
                break
            current = current.parent()
        
        if not category_node:
            return ("", "")
        
        item_name = (category_node.data(1, Qt.UserRole + 10) or "").strip()
        
        parent_name = ""
        parent_node = category_node.parent()
        if parent_node:
            parent_tpl_name = parent_node.data(1, Qt.UserRole + 10) or ""
            if parent_tpl_name.strip():
                parent_name = parent_tpl_name.strip()
        
        return (item_name, parent_name)

    def _record_autocomplete_entry(self, item, value: str):
        """将用户输入的目录名称记录到自动补全配置文件中。"""
        if getattr(self, "_is_closing", False):
            return
        if not item or not value:
            return
        
        try:
            template_name = self._get_current_template_name()
            if not template_name:
                return
            
            item_name, parent_item_name = self._get_catalog_item_context(item)
            if not item_name:
                return
            
            manager = get_autocomplete_manager()
            manager.record_usage(template_name, item_name, value, parent_item_name or None)
        except Exception:
            pass

    def _reenter_edit(self, item, column):
        """
        辅助方法：校验失败后重新进入编辑状态。
        确保：
        1. 设置当前项和列
        2. 树控件获得焦点
        3. 延迟调用 editItem
        """
        if not item:
            return
        # 先设置当前项和列
        self.catalog_tree.setCurrentItem(item, column)
        # 确保树控件获得焦点
        self.catalog_tree.setFocus()
        # 延迟调用 editItem，避免事件冲突（使用默认参数捕获当前值）
        self._schedule_catalog_edit(item, column)

    def _on_image_view_mode_changed(self):
        data = self.image_view_mode_combo.currentData() if hasattr(self, "image_view_mode_combo") else "retouched"
        self._image_view_mode = data or "retouched"
        try:
            self._image_view_restore_row = self.image_list.currentRow()
        except Exception:
            self._image_view_restore_row = None
        self._load_images_for_item(self._current_catalog_item())

    def _load_images_for_item(self, item):
        self.image_list.clear()
        self.catalog_preview.clear()
        self._update_img_pager()
        # 新一轮加载：作废上一轮后台缩略图任务
        self._thumb_token += 1
        self._preview_token += 1
        self._preview_expected_path = ""
        if item is None:
            return
        tpl_item_id = item.data(0, Qt.UserRole)
        ec_item_id = item.data(1, Qt.UserRole)
        if not tpl_item_id:
            return
        if not ec_item_id:
            # 新行还没落盘，无法有图片，直接返回，避免一次多余的同步 DB 读
            return

        # 图片列表查询改为后台线程执行，避免每次切行时 UI 冻结
        token = self._thumb_token
        ec_id_snapshot = int(ec_item_id)

        def _do_query():
            try:
                return list_entry_item_images(entry_catalog_item_id=ec_id_snapshot)
            except Exception as e:
                print(f"[catalog-entry] load images failed: {e}")
                return []

        def _on_loaded(rows):
            # 对话框已关闭：C++ image_list/preview 已销毁，忽略本轮结果
            if getattr(self, "_is_closing", False):
                return
            # 本轮加载可能已被新的切行覆盖，过期结果丢弃
            try:
                if token != self._thumb_token:
                    return
            except RuntimeError:
                return
            # 当前选中行可能已经变了，还是沿用当初的 item 作为渲染目标
            try:
                self._render_images_rows(item, rows or [])
            except RuntimeError:
                # C++ widget 已销毁
                pass

        worker = Worker(_do_query)
        worker.signals.finished.connect(_on_loaded)
        self._thread_pool.start(worker)

    def _render_images_rows(self, item, rows):
        """在主线程渲染图片列表及缩略图（从 _load_images_for_item 拆分出的纯 UI 逻辑）。"""
        token = self._thumb_token
        # 展示规则：如果同一原图存在修图版，则只展示修图版；否则展示原图（不同时展示）
        originals = {}
        retouched_by_orig = {}
        standalone = []
        for r in rows:
            if (r.get("image_type") == "retouched") and r.get("original_id"):
                retouched_by_orig[int(r["original_id"])] = r
            elif (r.get("image_type") == "original") and (not r.get("original_id")):
                originals[int(r["id"])] = r
            else:
                # 兼容旧数据：没有 original_id 的 retouched / 其他类型
                standalone.append(r)

        picked = []
        view_mode = getattr(self, "_image_view_mode", "retouched")
        for orig_id, orig in originals.items():
            if view_mode == "original":
                use = orig
            else:
                use = retouched_by_orig.get(orig_id) or orig
            sort_key = orig.get("sort_order") if orig.get("sort_order") is not None else (use.get("sort_order") or 0)
            picked.append((sort_key, int(use["id"]), use))
        for r in standalone:
            if view_mode == "original" and r.get("image_type") == "retouched":
                continue
            picked.append(((r.get("sort_order") or 0), int(r["id"]), r))
        # 如果存在 retouched 但缺 original，也展示
        if view_mode != "original":
            for orig_id, r in retouched_by_orig.items():
                if orig_id not in originals:
                    picked.append(((r.get("sort_order") or 0), int(r["id"]), r))

        picked.sort(key=lambda x: (x[0], x[1]))

        # 说明：当前 UI 并未把 image_list 加入布局（主要用于翻页/选择逻辑），
        # 因此默认不做同步缩略图解码，避免加载时卡顿；若后续显示缩略图列表，再启用后台补齐 icon。
        token = self._thumb_token
        want_thumbs = self.image_list.isVisible()
        icon_side = self.image_list.iconSize().width() if self.image_list.iconSize().isValid() else 120

        for idx, (_, __, r) in enumerate(picked):
            lw_item = QListWidgetItem()
            lw_item.setData(Qt.UserRole, r.get("id"))
            resolved_fp = resolve_image_path(
                r.get("file_path") or "",
                entry_id=r.get("entry_id"),
                template_item_id=r.get("template_item_id"),
                file_name=r.get("file_name") or "",
                image_root=self._image_root(),
            )
            lw_item.setData(Qt.UserRole + 1, resolved_fp or "")
            # 方案A：存储 original 归一化信息，便于“从修图版继续编辑”也只产生一份 retouched
            oid_raw = r.get("original_id") or r.get("id")
            oid = int(oid_raw) if oid_raw is not None else None
            lw_item.setData(Qt.UserRole + 2, oid)        # orig_id
            # base_path：连续修图的输入基线（优先 retouched；列表本身已按规则优先展示 retouched）
            lw_item.setData(Qt.UserRole + 3, resolved_fp or "")
            # 轻量占位 icon（不解码图片，避免 UI 卡顿）
            if want_thumbs:
                lw_item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
            lw_item.setText(r.get("file_name") or "")
            self.image_list.addItem(lw_item)

            if want_thumbs and resolved_fp and os.path.exists(resolved_fp):
                file_path = resolved_fp
                key = cache_key(file_path, icon_side)
                cached = lru_get(self._thumb_cache, key)
                if cached is not None and not cached.isNull():
                    lw_item.setIcon(QIcon(QPixmap.fromImage(cached)))
                    continue

                # 后台生成缩略图（QImage），回到主线程再 setIcon
                def make_fn(fp=file_path, max_side=icon_side, tok=token):
                    return {"token": tok, "file_path": fp, "key": cache_key(fp, max_side), "img": load_qimage_any(fp, max_side=max_side)}

                worker = Worker(make_fn)

                def on_done(res, row_idx=idx):
                    if getattr(self, "_is_closing", False):
                        return
                    try:
                        if res.get("token") != self._thumb_token:
                            return
                        fp = res.get("file_path") or ""
                        qimg = res.get("img")
                        if not fp or qimg is None or qimg.isNull():
                            return
                        # item 可能已被清空/替换，按 row_idx 取一次并校验 file_path
                        it = self.image_list.item(row_idx)
                        if not it:
                            return
                        if (it.data(Qt.UserRole + 1) or "") != fp:
                            return
                        lru_put(self._thumb_cache, res.get("key"), qimg, self._thumb_cache_max)
                        it.setIcon(QIcon(QPixmap.fromImage(qimg)))
                    except Exception:
                        pass

                worker.signals.finished.connect(on_done)
                self._thread_pool.start(worker)
        if self.image_list.count() > 0:
            restored = False
            sel = self._select_after_reload or {}
            sel_fp = (sel.get("file_path") or "").strip()
            sel_id = sel.get("img_id")
            if sel_fp or (sel_id is not None):
                for i in range(self.image_list.count()):
                    it = self.image_list.item(i)
                    if not it:
                        continue
                    fp = (it.data(Qt.UserRole + 1) or "").strip()
                    iid = it.data(Qt.UserRole)
                    if (sel_fp and fp == sel_fp) or (sel_id is not None and iid == sel_id):
                        self.image_list.setCurrentRow(i)
                        restored = True
                        break
            if not restored and self._image_view_restore_row is not None:
                try:
                    row_idx = int(self._image_view_restore_row)
                except Exception:
                    row_idx = -1
                if 0 <= row_idx < self.image_list.count():
                    self.image_list.setCurrentRow(row_idx)
                    restored = True
            if not restored:
                self.image_list.setCurrentRow(0)
        self._select_after_reload = None
        self._image_view_restore_row = None
        self._update_img_pager()
        
        # 自动统计并更新页数（原图数量 = 页数）
        page_count = len(originals)
        self._update_pages_count(item, page_count)

    def _current_catalog_item(self):
        return self.catalog_tree.currentItem()

    def _update_pages_count(self, item, page_count: int):
        """
        自动更新目录条目的页数字段。
        item: 目录树节点
        page_count: 图片数量（原图数量）
        """
        if not item:
            return
        
        # 页数字段在第 5 列（索引 5）
        current_pages = item.text(5).strip()
        new_pages = str(page_count) if page_count > 0 else ""
        
        # 如果页数没有变化，不需要更新
        if current_pages == new_pages:
            return

        # 图片数量为 0 时，不覆盖用户手动录入的页数
        if page_count == 0 and current_pages:
            return

        # 更新 UI
        self._suppress_catalog_changed = True
        item.setText(5, new_pages)
        self._suppress_catalog_changed = False
        
        # 保存到数据库
        self._ensure_entry_record()
        if not self.current_entry_id:
            return
        
        tpl_item_id = item.data(0, Qt.UserRole)
        ec_item_id = item.data(1, Qt.UserRole)
        if tpl_item_id:
            # pages 字段也走 pending 异步写，统一 debounce + 失败重试 + WAL 持久化
            self._stage_pending(tpl_item_id, item, ec_item_id, {"pages": new_pages})

    def _current_ec_id(self, create=False):
        item = self._current_catalog_item()
        if not item:
            return None, None
        tpl_item_id = item.data(0, Qt.UserRole)
        ec_item_id = item.data(1, Qt.UserRole)
        if create and tpl_item_id and not ec_item_id:
            ec_item_id = self._ensure_entry_catalog_item(tpl_item_id, item)
        return tpl_item_id, ec_item_id

    def _on_upload_images(self):
        """选择图片并推入 Redis 上传队列（异步处理，不阻塞 UI）"""
        tpl_item_id, ec_item_id = self._current_ec_id(create=True)
        if not tpl_item_id or not ec_item_id:
            StyledMessageBox.warning(self, "提示", "请选择一个目录节点后再上传图片", self.current_theme)
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*)",
        )
        if not files:
            return

        # 构建上传任务并推入队列
        task = build_upload_task(
            entry_id=self.current_entry_id or "unknown",
            tpl_item_id=tpl_item_id,
            ec_item_id=int(ec_item_id),
            image_root=self._image_root(),
            files=files,
        )
        # 记录当前上传对应的 ec_item_id，用于完成后刷新
        if not hasattr(self, '_pending_upload_ec_ids'):
            self._pending_upload_ec_ids = set()
        self._pending_upload_ec_ids.add(int(ec_item_id))

        mgr = get_upload_queue_manager()
        mgr.push_task(task)

        self.btn_img_upload.setEnabled(False)
        self.btn_img_upload.setText("队列中...")
        # Redis 不可用时也会在 push_task 内部降级为本地后台处理
        # task_finished 信号会自动触发刷新

    def _on_scan_settings(self):
        service = get_scanner_service()
        try:
            devices = service.list_devices()
        except Exception as e:
            StyledMessageBox.warning(self, "扫描设置", f"读取扫描设备失败：{e}", self.current_theme)
            return
        if not devices:
            StyledMessageBox.warning(self, "扫描设置", "未发现可用扫描设备", self.current_theme)
            return

        labels = []
        current_index = 0
        for idx, dev in enumerate(devices):
            backend = dev.get("backend") or ""
            name = dev.get("name") or dev.get("id") or "未知设备"
            label = f"{name} ({'TWAIN' if backend == 'twain' else '模拟'})"
            labels.append(label)
            if dev.get("id") == self._scanner_settings.device_id:
                current_index = idx

        selected_label, ok = QInputDialog.getItem(self, "扫描设置", "选择扫描设备：", labels, current_index, False)
        if not ok:
            return
        selected = devices[labels.index(selected_label)]
        dpi, ok = QInputDialog.getInt(self, "扫描设置", "分辨率 DPI：", self._scanner_settings.dpi, 75, 1200, 25)
        if not ok:
            return
        color_labels = ["彩色", "灰度", "黑白"]
        color_values = {"彩色": "color", "灰度": "gray", "黑白": "bw"}
        color_index = {"color": 0, "gray": 1, "bw": 2}.get(self._scanner_settings.color_mode, 0)
        color_label, ok = QInputDialog.getItem(self, "扫描设置", "色彩模式：", color_labels, color_index, False)
        if not ok:
            return

        self._scanner_settings = ScannerSettings(
            device_id=selected.get("id") or "simulated_file_picker",
            dpi=dpi,
            color_mode=color_values.get(color_label, "color"),
            use_driver_ui=True,
        )
        StyledMessageBox.information(self, "扫描设置", f"已选择：{selected_label}\nDPI：{dpi}\n色彩：{color_label}", self.current_theme)

    def _on_scan_images(self):
        tpl_item_id, ec_item_id = self._current_ec_id(create=True)
        if not tpl_item_id or not ec_item_id:
            StyledMessageBox.warning(self, "提示", "请选择一个目录节点后再扫描", self.current_theme)
            return

        if self._scan_in_progress:
            StyledMessageBox.information(self, "提示", "当前已有扫描任务正在执行，请稍候。", self.current_theme)
            return

        service = get_scanner_service()
        try:
            devices = service.list_devices()
        except Exception:
            devices = []
        twain_devices = [d for d in devices if d.get("backend") == "twain"]
        settings = ScannerSettings.from_dict(self._scanner_settings.to_dict())
        if settings.device_id == "simulated_file_picker" and twain_devices:
            settings.device_id = twain_devices[0].get("id") or ""

        if settings.device_id == "simulated_file_picker":
            self._scan_images_by_picker(tpl_item_id, ec_item_id)
            return

        settings.parent_window = int(self.winId())
        self._scan_in_progress = True
        self.btn_img_scan.setEnabled(False)
        self.btn_img_scan.setText("扫描中...")
        worker = Worker(lambda: get_scanner_service().scan_to_files(settings=settings))

        def on_done(scanned_files):
            self._scan_in_progress = False
            try:
                self._enqueue_scanned_files(tpl_item_id, ec_item_id, scanned_files, cleanup_source_files=True)
            except Exception as e:
                self.btn_img_scan.setEnabled(True)
                self.btn_img_scan.setText("扫描")
                StyledMessageBox.warning(self, "扫描入库失败", str(e), self.current_theme)

        def on_error(err):
            self._scan_in_progress = False
            self.btn_img_scan.setEnabled(True)
            self.btn_img_scan.setText("扫描")
            StyledMessageBox.warning(self, "扫描失败", f"{err}\n\n如果现场暂未安装 TWAIN 驱动或 pytwain，可先在扫描设置中选择“模拟扫描”。", self.current_theme)

        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        self._thread_pool.start(worker)

    def _scan_images_by_picker(self, tpl_item_id, ec_item_id):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "模拟扫描：选择扫描得到的图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*)",
        )
        if not files:
            return

        try:
            scanned_files = get_scanner_service().scan_selected_files(files, ScannerSettings())
        except Exception as e:
            StyledMessageBox.warning(self, "扫描失败", str(e), self.current_theme)
            return

        self._enqueue_scanned_files(tpl_item_id, ec_item_id, scanned_files)

    def _enqueue_scanned_files(self, tpl_item_id, ec_item_id, files, cleanup_source_files=False):
        if not files:
            return
        task = build_upload_task(
            entry_id=self.current_entry_id or "unknown",
            tpl_item_id=tpl_item_id,
            ec_item_id=int(ec_item_id),
            image_root=self._image_root(),
            files=files,
            cleanup_source_files=cleanup_source_files,
        )
        if not hasattr(self, '_pending_upload_ec_ids'):
            self._pending_upload_ec_ids = set()
        self._pending_upload_ec_ids.add(int(ec_item_id))

        mgr = get_upload_queue_manager()
        mgr.push_task(task)

        self.btn_img_scan.setEnabled(False)
        self.btn_img_scan.setText("扫描入库中...")

    def _on_batch_upload_images(self):
        """批量上传：选择文件夹，按目录各条目页数顺序依次分配图片。
        总图片数必须与目录页数之和相等，否则提示报错。
        """
        import re

        if not self.current_entry_id:
            StyledMessageBox.warning(self, "提示", "请先选择一名人员再执行批量上传", self.current_theme)
            return

        # ── 1. 遍历目录树，收集有页数的条目（深度优先，保持显示顺序）──
        catalog_items = []

        def _collect(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if not child:
                    continue
                pages_text = (child.text(5) or "").strip()
                try:
                    pages = int(pages_text)
                except (ValueError, TypeError):
                    pages = 0
                tpl_item_id = child.data(0, Qt.UserRole)
                ec_item_id = child.data(1, Qt.UserRole)
                if pages > 0 and tpl_item_id:
                    catalog_items.append({
                        "tpl_item_id": int(tpl_item_id),
                        "ec_item_id": int(ec_item_id) if ec_item_id else None,
                        "pages": pages,
                        "name": child.text(1) or f"条目{i+1}",
                    })
                _collect(child)

        _collect(self.catalog_tree.invisibleRootItem())

        if not catalog_items:
            StyledMessageBox.warning(
                self, "提示",
                "目录中没有填写页数的条目，请先在目录树的「页数」列填写页数后再批量上传",
                self.current_theme,
            )
            return

        total_pages = sum(c["pages"] for c in catalog_items)

        # ── 2. 选择文件夹 ──
        folder = QFileDialog.getExistingDirectory(
            self, "选择图片文件夹（图片将按文件名顺序依页数分配）", ""
        )
        if not folder:
            return

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
        files = []
        for root_dir, _dirs, fnames in os.walk(folder):
            for fn in fnames:
                if os.path.splitext(fn)[1].lower() in IMAGE_EXTS:
                    files.append(os.path.join(root_dir, fn))

        def _natural_key(path):
            name = os.path.basename(path)
            parts = re.split(r"(\d+)", name)
            return [int(p) if p.isdigit() else p.lower() for p in parts]

        files.sort(key=_natural_key)

        if not files:
            StyledMessageBox.information(self, "提示", "所选文件夹中未找到图片文件", self.current_theme)
            return

        # ── 3. 验证总数 ──
        if len(files) != total_pages:
            StyledMessageBox.warning(
                self, "页数不匹配",
                f"目录共 {total_pages} 页，所选图片 {len(files)} 张，数量不一致，无法上传。",
                self.current_theme,
            )
            return

        # ── 4. 按页数分配并推队列 ──
        if not hasattr(self, '_pending_upload_ec_ids'):
            self._pending_upload_ec_ids = set()

        mgr = get_upload_queue_manager()
        idx = 0
        for cat in catalog_items:
            tpl_item_id = cat["tpl_item_id"]
            ec_item_id = cat["ec_item_id"]
            pages = cat["pages"]
            item_files = files[idx: idx + pages]
            idx += pages

            # 若 ec_item 还不存在，先创建
            if not ec_item_id:
                try:
                    ec_item_id = ensure_entry_catalog_item(
                        entry_id=int(self.current_entry_id),
                        template_item_id=tpl_item_id,
                    )
                except Exception as e:
                    print(f"[batch-upload] ensure ec_item failed tpl_item={tpl_item_id}: {e}")
                    continue

            task = build_upload_task(
                entry_id=self.current_entry_id,
                tpl_item_id=tpl_item_id,
                ec_item_id=int(ec_item_id),
                image_root=self._image_root(),
                files=item_files,
            )
            self._pending_upload_ec_ids.add(int(ec_item_id))
            mgr.push_task(task)

        self.btn_img_batch_upload.setEnabled(False)
        self.btn_img_batch_upload.setText("队列中...")

    # ── 上传队列回调（在 UI 主线程执行，由 pyqtSignal 保证线程安全） ──

    def _on_upload_task_started(self, task_id: str, total_files: int):
        """一个上传任务开始处理"""
        self._upload_progress_frame.setVisible(True)
        self._upload_progress_bar.setMaximum(total_files)
        self._upload_progress_bar.setValue(0)
        self._upload_progress_bar.setFormat(f"0 / {total_files}")
        self._upload_progress_label.setText(f"上传中 (共 {total_files} 张)...")

    def _on_upload_file_progress(self, task_id: str, current: int, total: int, file_name: str):
        """单个文件进度更新"""
        self._upload_progress_bar.setMaximum(total)
        self._upload_progress_bar.setValue(current)
        self._upload_progress_bar.setFormat(f"{current} / {total}")
        if file_name:
            self._upload_progress_label.setText(f"正在上传: {file_name}")
        else:
            self._upload_progress_label.setText("上传完成")

    def _on_upload_task_finished(self, result: dict):
        """一个上传任务处理完成"""
        success = result.get("success", 0)
        failed = result.get("failed", 0)
        errors = result.get("errors", [])
        ec_item_id = result.get("ec_item_id")

        # 刷新图片列表
        self._load_images_for_item(self._current_catalog_item())
        self._update_total_pages_label()

        # 从待处理集合中移除
        if hasattr(self, '_pending_upload_ec_ids') and ec_item_id:
            self._pending_upload_ec_ids.discard(int(ec_item_id))

        # 如果有失败项，提示用户
        if failed > 0:
            err_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                err_msg += f"\n... 还有 {len(errors) - 5} 个错误"
            StyledMessageBox.warning(
                self, "上传部分失败",
                f"成功: {success} 张, 失败: {failed} 张\n\n{err_msg}",
                self.current_theme,
            )

    def _on_upload_worker_error(self, error_msg: str):
        """Worker 级别错误"""
        print(f"[upload-queue] worker error: {error_msg}")

    def _on_upload_queue_empty(self):
        """队列中所有任务都已完成"""
        self._upload_progress_label.setText("全部上传完成")
        self._upload_progress_bar.setValue(self._upload_progress_bar.maximum())
        self.btn_img_upload.setEnabled(True)
        self.btn_img_upload.setText("上传图片")
        self.btn_img_batch_upload.setEnabled(True)
        self.btn_img_batch_upload.setText("批量上传")
        self.btn_img_scan.setEnabled(True)
        self.btn_img_scan.setText("扫描")
        # 1.5 秒后隐藏进度条
        QTimer.singleShot(1500, self._hide_upload_progress_safely)

    def _hide_upload_progress_safely(self):
        if getattr(self, "_is_closing", False):
            return
        try:
            self._upload_progress_frame.setVisible(False)
        except RuntimeError:
            pass

    def _on_image_selected(self):
        if getattr(self, "_is_closing", False):
            return
        items = self.image_list.selectedItems()
        if not items:
            self.catalog_preview.clear()
            return
        file_path = items[0].data(Qt.UserRole + 1) or ""
        orig_id = items[0].data(Qt.UserRole + 2) or None
        orig_path = items[0].data(Qt.UserRole + 3) or ""
        self._update_img_pager()

        # 方案A：如果该 original 有 pending 修图，则预览展示“待保存效果”（不落盘）
        if orig_id:
            p = self._pending_edits.get(int(orig_id))
            dirty = bool(p) and ((abs(float(p.get("angle") or 0.0)) > 1e-6) or (p.get("crop_box") is not None))
            if dirty and orig_path and os.path.exists(orig_path):
                self._render_effective_preview(int(orig_id), orig_path)
                # 预加载前后图片
                self._preload_nearby_images()
                return

        if not file_path or not os.path.exists(file_path):
            self.catalog_preview.clear()
            self._set_dirty_badge(int(orig_id) if orig_id else None)
            return

        # 新的预览请求：作废上一次
        self._preview_token += 1
        token = self._preview_token
        self._preview_expected_path = file_path

        # 优先走缓存
        view_size = self.catalog_preview.viewport().size() if hasattr(self, "catalog_preview") else QSize(800, 800)
        max_side = int(min(2400, max(800, max(view_size.width(), view_size.height()) * 2)))
        key = cache_key(file_path, max_side)
        cached = lru_get(self._preview_cache, key)
        if cached is not None and not cached.isNull():
            # 切换图片：默认回到自适应（不继承上一张的缩放）
            self.catalog_preview.set_image(QPixmap.fromImage(cached), preserve_view=False)
            self._set_dirty_badge(int(orig_id) if orig_id else None)
            # 即使命中缓存也触发预加载（为后续翻页准备）
            self._preload_nearby_images()
            return

        # 先清空，避免“旧图停留”造成错觉
        self.catalog_preview.clear()

        def make_fn(fp=file_path, ms=max_side, tok=token):
            return {"token": tok, "file_path": fp, "key": cache_key(fp, ms), "img": load_qimage_any(fp, max_side=ms)}

        worker = Worker(make_fn)

        def on_done(res):
            if getattr(self, "_is_closing", False):
                return
            try:
                if res.get("token") != self._preview_token:
                    return
                fp = res.get("file_path") or ""
                if fp != (self._preview_expected_path or ""):
                    return
                qimg = res.get("img")
                if qimg is None or qimg.isNull():
                    return
                lru_put(self._preview_cache, res.get("key"), qimg, self._preview_cache_max)
                # 切换图片：默认回到自适应
                self.catalog_preview.set_image(QPixmap.fromImage(qimg), preserve_view=False)
            except Exception:
                pass

        worker.signals.finished.connect(on_done)
        self._thread_pool.start(worker)
        self._set_dirty_badge(int(orig_id) if orig_id else None)

        # 触发预加载：后台加载前后若干张图片
        self._preload_nearby_images()

    def _preload_nearby_images(self):
        """
        预加载当前选中图片前后若干张到缓存中。
        - 向后预加载 _preload_ahead 张（用户翻页方向）
        - 向前预加载 _preload_behind 张
        - 已在缓存中的跳过
        - 快速翻页时自动取消过时预加载任务
        """
        if getattr(self, "_is_closing", False):
            return
        count = self.image_list.count()
        if count <= 1:
            return
        current_row = self.image_list.currentRow()
        if current_row < 0:
            return

        # 新一轮预加载：作废上一轮
        self._preload_token += 1
        token = self._preload_token
        self._preloading_paths.clear()

        # 计算预加载范围
        view_size = self.catalog_preview.viewport().size() if hasattr(self, "catalog_preview") else QSize(800, 800)
        max_side = int(min(1400, max(700, max(view_size.width(), view_size.height()))))

        # 收集需要预加载的索引（优先向后，其次向前）
        preload_indices = []
        # 向后
        for delta in range(1, self._preload_ahead + 1):
            idx = current_row + delta
            if idx < count:
                preload_indices.append(idx)
        # 向前
        for delta in range(1, self._preload_behind + 1):
            idx = current_row - delta
            if idx >= 0:
                preload_indices.append(idx)

        for idx in preload_indices:
            item = self.image_list.item(idx)
            if not item:
                continue
            file_path = item.data(Qt.UserRole + 1) or ""
            if not file_path or not os.path.exists(file_path):
                continue

            # 检查缓存：已有则跳过
            key = cache_key(file_path, max_side)
            if lru_get(self._preview_cache, key) is not None:
                continue

            # 避免重复提交
            if file_path in self._preloading_paths:
                continue
            self._preloading_paths.add(file_path)

            # 提交后台预加载任务
            def make_fn(fp=file_path, ms=max_side, tok=token):
                return {"token": tok, "file_path": fp, "key": cache_key(fp, ms), "img": load_qimage_any(fp, max_side=ms)}

            worker = Worker(make_fn)

            def on_done(res, fp=file_path):
                try:
                    if getattr(self, "_is_closing", False):
                        return
                    # 检查 token：如果用户已快速翻页，丢弃过时结果
                    if res.get("token") != self._preload_token:
                        return
                    qimg = res.get("img")
                    if qimg is None or qimg.isNull():
                        return
                    lru_put(self._preview_cache, res.get("key"), qimg, self._preview_cache_max)
                except Exception:
                    pass
                finally:
                    self._preloading_paths.discard(fp)

            worker.signals.finished.connect(on_done)
            self._thread_pool.start(worker)

    def _on_delete_image(self):
        items = self.image_list.selectedItems()
        if not items:
            return
        img_id = items[0].data(Qt.UserRole)
        file_path = items[0].data(Qt.UserRole + 1)
        try:
            delete_entry_item_image(image_id=int(img_id))
        except Exception as e:
            print(f"[catalog-entry] delete image failed: {e}")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        self._load_images_for_item(self._current_catalog_item())
        self._update_total_pages_label()

    def _on_set_cover(self):
        items = self.image_list.selectedItems()
        if not items:
            return
        img_id = items[0].data(Qt.UserRole)
        tpl_item_id, ec_item_id = self._current_ec_id()
        if not ec_item_id:
            return
        try:
            set_cover_image(entry_catalog_item_id=int(ec_item_id), image_id=int(img_id))
        except Exception as e:
            print(f"[catalog-entry] set cover failed: {e}")
        self._load_images_for_item(self._current_catalog_item())

    # === 图片处理占位功能 ===
    def _require_image_file(self):
        """返回 (image_id, file_path)。"""
        items = self.image_list.selectedItems()
        if not items:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return None, None
        img_id = items[0].data(Qt.UserRole)
        file_path = items[0].data(Qt.UserRole + 1) or ""
        if not file_path or not os.path.exists(file_path):
            StyledMessageBox.warning(self, "提示", "图片文件不存在", self.current_theme)
            return None, None
        return img_id, file_path

    def _retouched_output_path(self, orig_path: str, suffix: str = "_retouched"):
        """统一生成修图输出文件名：<orig_stem>_retouched<ext>（同一 original 始终覆盖同一路径）。"""
        base_dir = os.path.dirname(orig_path)
        base_name = os.path.basename(orig_path)
        if base_name.lower().endswith(CryptoService.ENCRYPTED_EXT):
            base_name = base_name[:-len(CryptoService.ENCRYPTED_EXT)]
        stem, ext = os.path.splitext(base_name)
        out_name = f"{stem}{suffix}{ext}{CryptoService.ENCRYPTED_EXT}"
        out_path = os.path.join(base_dir, out_name)
        return out_path, out_name

    def _on_trim_border_legacy_save_now(self):
        img_id, file_path = self._require_image_file()
        if not img_id or not file_path:
            return
        crop_box = legacy_detect_black_border_crop_box_from_path(file_path)
        if not crop_box:
            StyledMessageBox.information(self, "去黑边", "未检测到明显黑边，已跳过。", self.current_theme)
            return

        # 保存修图版：同一 original 固定输出为 *_retouched*，后续修改覆盖同一文件
        out_path = ""
        out_name = ""
        orig_info = None
        try:
            orig_info = resolve_original_image_info(image_id=int(img_id), fallback_path=file_path)
            if not orig_info:
                StyledMessageBox.warning(self, "提示", "数据库中找不到原图记录", self.current_theme)
                return
            src_path = (orig_info.get("orig_file_path") or file_path or "").strip()
            if not src_path:
                StyledMessageBox.warning(self, "提示", "数据库中找不到原图记录", self.current_theme)
                return
            out_path, out_name = self._retouched_output_path(src_path)
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"读取数据库失败：{e}", self.current_theme)
            return
        try:
            legacy_crop_and_save(file_path=file_path, crop_box=crop_box, out_path=out_path, out_name=out_name)
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"保存修图失败：{e}", self.current_theme)
            return

        mime_name = out_name[:-len(CryptoService.ENCRYPTED_EXT)] if out_name.lower().endswith(CryptoService.ENCRYPTED_EXT) else out_name
        mime, _ = mimetypes.guess_type(mime_name)
        size = os.path.getsize(out_path) if os.path.exists(out_path) else None

        # 写库：保存为 retouched，并关联 original（同一 original 只保留 1 条 retouched）
        try:
            if not orig_info:
                orig_info = resolve_original_image_info(image_id=int(img_id), fallback_path=file_path)
            if not orig_info:
                StyledMessageBox.warning(self, "提示", "数据库中找不到原图记录", self.current_theme)
                return
            upsert_single_retouched(
                orig_id=int(orig_info.get("orig_id") or img_id),
                entry_catalog_item_id=orig_info.get("orig_entry_catalog_item_id"),
                orig_sort_order=orig_info.get("orig_sort_order"),
                out_path=out_path,
                out_name=out_name,
                mime_type=mime or "",
                file_size=size,
            )
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"写入数据库失败：{e}", self.current_theme)
            return

        # 刷新列表并预览
        self._load_images_for_item(self._current_catalog_item())

    def _on_rotate_fine_legacy_save_now(self, direction: int):
        """
        角度微调：
        - direction = -1: 左微调
        - direction =  1: 右微调
        每次点击默认旋转 0.2°，并输出/更新为 retouched 版本。
        """
        img_id, file_path = self._require_image_file()
        if not img_id or not file_path:
            return

        step_deg = 0.2
        angle = -step_deg if direction < 0 else step_deg

        # 计算输出路径：按“原图(或其 original) stem + _retouched”统一命名，重复操作覆盖同一文件
        try:
            orig_info = resolve_original_image_info(image_id=int(img_id), fallback_path=file_path)
            if not orig_info:
                StyledMessageBox.warning(self, "提示", "数据库中找不到图片记录", self.current_theme)
                return
            src_path = (orig_info.get("orig_file_path") or file_path or "").strip()
            out_path, out_name = self._retouched_output_path(src_path)
            _stem, ext = os.path.splitext(out_name)
            ext_l = ext.lower()

            # 旋转+保存（白底、无 alpha）
            try:
                legacy_rotate_with_white_bg_and_save(file_path=file_path, angle=angle, out_path=out_path, out_name=out_name)
            except Exception as e:
                StyledMessageBox.warning(self, "提示", f"保存修图失败：{e}", self.current_theme)
                return

            mime_name = out_name[:-len(CryptoService.ENCRYPTED_EXT)] if out_name.lower().endswith(CryptoService.ENCRYPTED_EXT) else out_name
            mime, _ = mimetypes.guess_type(mime_name)
            size = os.path.getsize(out_path) if os.path.exists(out_path) else None

            upsert_single_retouched(
                orig_id=int(orig_info.get("orig_id") or img_id),
                entry_catalog_item_id=orig_info.get("orig_entry_catalog_item_id"),
                orig_sort_order=orig_info.get("orig_sort_order"),
                out_path=out_path,
                out_name=out_name,
                mime_type=mime or "",
                file_size=size,
            )
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"写入数据库失败：{e}", self.current_theme)
            return

        # 刷新并自动预览修图版
        self._load_images_for_item(self._current_catalog_item())
        # 选中 retouched 文件对应项
        for i in range(self.image_list.count()):
            it = self.image_list.item(i)
            if (it.data(Qt.UserRole + 1) or "") == out_path:
                self.image_list.setCurrentRow(i)
                break

    def _on_fill_region(self):
        """框选污点去除：进入一次性框选模式，拖拽选择矩形后自动填充该区域（pending）。"""
        # 兼容旧绑定：现在用 btn_img_fill 的 toggled 进入持续模式
        if hasattr(self, "btn_img_fill"):
            self.btn_img_fill.setChecked(True)

    def _on_rotate_90(self, degrees: int):
        """
        90度旋转：
        - degrees = -90: 左转90°
        - degrees =  90: 右转90°
        使用方案A：累计angle并更新预览，不立即落盘。
        """
        img_id, _file_path, orig_id, orig_path = self._current_image_ctx()
        if not img_id or not orig_id or not orig_path:
            StyledMessageBox.information(self, "提示", "请先选择一张图片", self.current_theme)
            return
        # 累计90度旋转
        p = self._pending_for(orig_id)
        p["angle"] = float(p.get("angle") or 0.0) + float(degrees)
        self._set_dirty_badge(orig_id)
        self._render_effective_preview(orig_id, orig_path)

    def _shift_image(self, delta):
        count = self.image_list.count()
        if count == 0:
            return
        row = self.image_list.currentRow()
        if row < 0:
            row = 0
        new_row = max(0, min(count - 1, row + delta))
        if new_row != row:
            self.image_list.setCurrentRow(new_row)
        else:
            self._update_img_pager()

    def _update_img_pager(self):
        count = self.image_list.count()
        row = self.image_list.currentRow()
        display_page = 0 if count == 0 else max(1, min(count, row + 1))
        if hasattr(self, "img_page_edit"):
            self.img_page_edit.setText(str(display_page))
        if hasattr(self, "img_page_total"):
            self.img_page_total.setText(f"/ {count}")

    def _on_preview_zoom_changed(self, percent: int):
        if hasattr(self, "img_zoom_label"):
            self.img_zoom_label.setText(f"{percent}%")

    def _on_jump_page(self):
        count = self.image_list.count()
        if count == 0:
            return
        try:
            raw = self.img_page_edit.text().strip()
            target = int(raw)
        except ValueError:
            return
        target = max(1, min(count, target))
        self.image_list.setCurrentRow(target - 1)

    def _on_print_preview(self):
        """打开打印预览对话框"""
        # 收集目录树数据
        catalog_data = self._collect_catalog_data_for_print()
        if not catalog_data:
            StyledMessageBox.information(self, "提示", "目录树中没有数据", self.current_theme)
            return
        
        # 从数据库的entries表获取人员姓名
        person_name = ""
        entry_id = self.current_entry_id or self.case_data.get("entry_id")
        if entry_id:
            try:
                entry_info = get_entry_info(entry_id=int(entry_id))
                if entry_info:
                    person_name = entry_info.get("name", "")
            except Exception as e:
                print(f"[print-preview] get entry name failed: {e}")
        
        # 打开打印预览对话框
        dialog = PrintPreviewDialog(
            catalog_data=catalog_data,
            person_name=person_name,
            parent=self,
            theme=self.current_theme
        )
        dialog.exec_()

    def _on_ai_retouch_config(self):
        """打开 AI 修图配置对话框"""
        dialog = AIRetouchConfigDialog(self, theme=self.current_theme)
        dialog.exec_()

    def _collect_catalog_data_for_print(self) -> list:
        """
        收集目录树数据用于打印
        
        Returns:
            列表，每项包含 serial, name, year, month, day, pages, remark, is_template
        """
        result = []
        
        def collect_item(item, depth=0):
            """递归收集目录项"""
            serial = item.text(0).strip()
            name = item.text(1).strip()
            year = item.text(2).strip()
            month = item.text(3).strip()
            day = item.text(4).strip()
            pages = item.text(5).strip()
            remark = item.text(6).strip()
            
            # 检查是否是模板本身有的项目（UserRole + 10 存储了模板预设值）
            tpl_serial = item.data(0, Qt.UserRole + 10) or ""
            tpl_name = item.data(1, Qt.UserRole + 10) or ""
            is_template = bool(tpl_serial.strip() or tpl_name.strip())

            result.append({
                "serial": serial,
                "name": name,
                "year": year,
                "month": month,
                "day": day,
                "pages": pages,
                "remark": remark,
                "depth": depth,
                "is_template": is_template,
                "is_blank": (not serial and not name and not is_template),
            })
            
            # 递归收集子项
            for i in range(item.childCount()):
                collect_item(item.child(i), depth + 1)
        
        # 从根节点开始收集
        root = self.catalog_tree.invisibleRootItem()
        for i in range(root.childCount()):
            collect_item(root.child(i), 0)
        
        return result

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 1 if delta > 0 else -1
            new_size = self._catalog_font_size + step
            new_size = max(self._font_min, min(self._font_max, new_size))
            self._catalog_font_size = new_size
            self._apply_catalog_font_zoom(new_size)
            event.accept()
            return
        super().wheelEvent(event)

    def _load_templates_to_combo(self):
        self.tpl_combo.clear()
        self._tpl_list = []  # [{'id':..., 'name':..., 'is_default':...}]
        try:
            tpls = list_catalog_templates()
            print(f"[catalog-entry] loaded templates: {len(tpls)}")
            for t in tpls:
                self._tpl_list.append({"id": t["id"], "name": t["name"], "is_default": t.get("is_default")})
                self.tpl_combo.addItem(t["name"], t["id"])
            # 增加“请选择模板”占位，不自动选中任何模板
            self.tpl_combo.insertItem(0, "请选择模板", None)
            # 按需求：默认停留在占位，不自动选择模板
            self.tpl_combo.setCurrentIndex(0)
            if not self._tpl_list:
                print("[catalog-entry] no templates found")
        except Exception as e:
            print(f"[catalog-entry] load templates failed: {e}")

    def _current_template_id(self):
        data = self.tpl_combo.currentData()
        return int(data) if data is not None else None

    def _on_tpl_changed(self, index):
        print(f"[catalog-entry] tpl changed idx={index} data={self.tpl_combo.currentData()}")
        # 占位项或无效索引时不加载
        if index <= 0:
            self.catalog_tree.clear()
            self.current_template_id = None
            self.current_entry_id = None
            return
        # 切换模板时重置当前 entry，确保后续写入绑定到新模板
        self.current_entry_id = None
        self.current_template_id = None
        self._populate_catalog_tree()

    def _autoselect_entry_template(self):
        """如果存在已录入的 entry，则自动选中其模板并加载目录；否则保持占位。"""
        tpl_id = None
        entry_id = None
        passed_entry_id = self.case_data.get("entry_id")
        emp_no = self.case_data.get("工号") or ""
        try:
            info = find_entry_for_autoselect(passed_entry_id, emp_no)
            if info:
                tpl_id = info.get("template_id")
                entry_id = info.get("id")
        except Exception as e:
            print(f"[catalog-entry] autoselect template failed: {e}")

        if not tpl_id:
            return

        # 在下拉列表中找到对应模板并选中，不触发信号
        target_idx = next((i + 1 for i, t in enumerate(self._tpl_list) if t["id"] == tpl_id), None)
        if target_idx is None:
            return
        self.tpl_combo.blockSignals(True)
        self.tpl_combo.setCurrentIndex(target_idx)
        self.tpl_combo.blockSignals(False)
        self.current_template_id = tpl_id
        self.current_entry_id = entry_id
        self._populate_catalog_tree()

    # === Entry/目录项数据辅助 ===
    def _ensure_entry_record(self):
        """确保当前录入对象有对应的 Entry 记录。简单按 emp_no + template_id 查找，不存在则创建。"""
        if self.current_entry_id:
            return
        tpl_id = self._current_template_id()
        if not tpl_id:
            return
        # 优先使用传入的 entry_id
        passed_entry_id = self.case_data.get("entry_id")

        emp_no = self.case_data.get("工号") or ""
        name = self.case_data.get("姓名") or ""
        role = self.case_data.get("岗位") or ""
        phone = self.case_data.get("电话") or ""
        status = self.case_data.get("状态") or ""
        try:
            self.current_entry_id = ensure_entry_record(
                passed_entry_id=passed_entry_id,
                owner_id=1,
                template_id=tpl_id,
                emp_no=emp_no,
                name=name,
                role_title=role,
                phone=phone,
                status=status,
            )
        except Exception as e:
            print(f"[catalog-entry] ensure entry failed: {e}")

    def _get_entry_catalog_item(self, template_item_id: int):
        """只读获取 entry_catalog_item，不会写入数据库，避免打开时产生写操作。"""
        self._ensure_entry_record()
        if not self.current_entry_id:
            return {
                "id": None,
                "serial": "",
                "name": "",
                "year": None,
                "month": None,
                "day": None,
                "pages": None,
                "remark": "",
            }
        try:
            return get_entry_catalog_item_readonly(
                entry_id=int(self.current_entry_id),
                template_item_id=template_item_id,
            )
        except Exception as e:
            print(f"[catalog-entry] get entry item failed: {e}")
            return {
                "id": None,
                "serial": "",
                "name": "",
                "year": None,
                "month": None,
                "day": None,
                "pages": None,
                "remark": "",
            }

    # === 目录录入增删改 ===
    def _create_item(self, data=None, tpl_serial="", tpl_name=""):
        """
        创建目录树节点。
        tpl_serial / tpl_name: 模板预设的编号/名称，用于判断是否锁定不可编辑。
        """
        data = data or {}
        # QTreeWidgetItem 期望字符串，统一转为字符串避免类型错误
        def _s(val):
            if val is None:
                return ""
            return str(val)
        item = QTreeWidgetItem([
            _s(data.get("serial", "")),
            _s(data.get("name", "")),
            _s(data.get("year", "")),
            _s(data.get("month", "")),
            _s(data.get("day", "")),
            _s(data.get("pages", "")),
            _s(data.get("desc", "")),
        ])
        # 允许直接编辑
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        # 存储模板原始值，用于判断是否锁定编辑
        item.setData(0, Qt.UserRole + 10, _s(tpl_serial))  # 模板预设的编号
        item.setData(1, Qt.UserRole + 10, _s(tpl_name))    # 模板预设的目录名称
        return item

    def _sibling_order_ids(self, parent_item):
        if parent_item is None:
            parent_item = self.catalog_tree.invisibleRootItem()
        ids = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            try:
                tpl_item_id = int(child.data(0, Qt.UserRole) or 0)
            except Exception:
                continue
            if tpl_item_id > 0:
                ids.append(tpl_item_id)
        return ids

    # === 目录树增删 ===
    def _current_tpl_required(self):
        tpl_id = self._current_template_id()
        if not tpl_id:
            StyledMessageBox.warning(self, "提示", "请先选择目录模板", self.current_theme)
            return None
        return tpl_id

    def _create_tpl_node(self, parent_item, prev_item=None):
        """
        创建空白模板节点并挂载到树，同时为当前 entry 建立 entry_catalog 记录。
        序号自动生成：同一父节点下从 1 递增。
        年份自动增加：如果前一行目录名称以年份开头，自动生成下一年的名称。
        """
        tpl_id = self._current_tpl_required()
        if not tpl_id:
            return None
        if parent_item is None:
            parent_item = self.catalog_tree.invisibleRootItem()
        parent_tpl_id = (
            parent_item.data(0, Qt.UserRole)
            if parent_item != self.catalog_tree.invisibleRootItem()
            else None
        )
        insert_index = parent_item.childCount()
        sort_order = insert_index + 1
        sibling_order_ids = self._sibling_order_ids(parent_item)
        # 自动生成序号：同一父节点下的子节点从 1 开始递增
        auto_serial = str(sort_order)
        
        # 年份自动增加逻辑
        auto_name = ""
        if prev_item is None:
            # 如果没有传入 prev_item，尝试获取前一个同级节点
            child_count = parent_item.childCount()
            if child_count > 0:
                prev_item = parent_item.child(child_count - 1)
        
        if prev_item:
            prev_name = prev_item.text(1).strip()
            auto_name = self._generate_next_year_name(prev_name)

        # 分配占位 id，立刻返回 UI；真实 id 后台创建完毕后迁移
        placeholder_id = self._alloc_placeholder_tpl_id()

        # 创建节点时自动填充序号和目录名称
        item = self._create_item(data={"serial": auto_serial, "name": auto_name})
        item.setData(0, Qt.UserRole, placeholder_id)
        # serial/name 初值加入 pending；占位 id 不写 WAL，迁移后一次性补写
        if self.current_entry_id:
            pending_fields = {"serial": auto_serial}
            if auto_name:
                pending_fields["name"] = auto_name
            self._stage_pending(placeholder_id, item, None, pending_fields)

        parent_item.addChild(item)
        parent_item.setExpanded(True)
        self.catalog_tree.setCurrentItem(item, 1)  # 设置到目录名称列
        item.setSelected(True)
        # 确保树控件获得焦点
        self.catalog_tree.setFocus()
        # 自动进入目录名称的编辑状态（列 1），使用默认参数捕获当前 item
        self._schedule_catalog_edit(item, 1)

        # 后台创建真实的 catalog_template_item
        self._async_create_template_item(
            placeholder_id, item,
            template_id=tpl_id,
            parent_id=parent_tpl_id,
            sort_order=sort_order,
            sibling_order_ids=sibling_order_ids,
            insert_index=insert_index,
        )
        return item

    def _generate_next_year_name(self, prev_name: str) -> str:
        """
        根据前一行的目录名称生成下一年的名称。
        - 如果前一行包含 4 位年份（如 "2024履历"、"2024年度考核"），则返回下一年的名称
        - 如果生成的年份超过当前年份，则不生成，返回空字符串
        """
        import re
        from datetime import datetime
        
        if not prev_name:
            return ""
        
        # 匹配名称中的 4 位数字（年份），支持开头或中间位置
        match = re.search(r'(\d{4})', prev_name)
        if not match:
            return ""
        
        year_str = match.group(1)
        try:
            year = int(year_str)
        except ValueError:
            return ""
        
        # 校验是否为合理的年份范围（1900-2100）
        if year < 1900 or year > 2100:
            return ""
        
        # 计算下一年
        next_year = year + 1
        
        # 获取当前年份
        current_year = datetime.now().year
        
        # 如果下一年超过当前年份，则不生成
        if next_year > current_year:
            return ""
        
        # 替换年份生成新名称
        new_name = prev_name.replace(year_str, str(next_year), 1)
        return new_name

    def _edit_new_item(self, item, column):
        """辅助方法：确保新增节点后能正常进入编辑状态。"""
        if getattr(self, "_is_closing", False):
            return
        try:
            if item and item.treeWidget() is self.catalog_tree and self.catalog_tree.currentItem() == item:
                if int(column) == 1:
                    self._show_catalog_name_editor(item)
                    return
                self.catalog_tree.editItem(item, column)
        except RuntimeError:
            return

    def _on_add_peer(self):
        current = self.catalog_tree.currentItem()
        parent_item = current.parent() if current else self.catalog_tree.invisibleRootItem()
        # 传入当前选中的节点作为 prev_item，用于年份自动增加
        self._create_tpl_node(parent_item, prev_item=current)

    def _on_insert_above(self):
        current = self.catalog_tree.currentItem()
        if not current:
            return
        parent = current.parent() or self.catalog_tree.invisibleRootItem()
        idx = parent.indexOfChild(current)
        prev = parent.child(idx - 1) if idx > 0 else None
        self._insert_peer_at(parent, insert_index=idx, prev_item=prev)

    def _on_insert_below(self):
        current = self.catalog_tree.currentItem()
        if not current:
            return
        parent = current.parent() or self.catalog_tree.invisibleRootItem()
        idx = parent.indexOfChild(current)
        self._insert_peer_at(parent, insert_index=idx + 1, prev_item=current)

    def _insert_peer_at(self, parent_item, insert_index: int, prev_item=None):
        """在 parent_item 的 insert_index 处插入一个新同级节点，然后重新排序序号。"""
        tpl_id = self._current_tpl_required()
        if not tpl_id:
            return None
        if parent_item is None:
            parent_item = self.catalog_tree.invisibleRootItem()
        parent_tpl_id = (
            parent_item.data(0, Qt.UserRole)
            if parent_item != self.catalog_tree.invisibleRootItem()
            else None
        )
        insert_index = max(0, min(int(insert_index), parent_item.childCount()))
        sort_order = insert_index + 1
        sibling_order_ids = self._sibling_order_ids(parent_item)
        auto_name = ""
        if prev_item:
            auto_name = self._generate_next_year_name(prev_item.text(1).strip())

        # 分配占位 id，立刻返回 UI；真实 id 后台创建完毕后迁移
        placeholder_id = self._alloc_placeholder_tpl_id()

        item = self._create_item(data={"serial": str(insert_index + 1), "name": auto_name})
        item.setData(0, Qt.UserRole, placeholder_id)
        # 初值走 pending；占位 id 不写 WAL，迁移后一次性补写
        if self.current_entry_id and auto_name:
            self._stage_pending(placeholder_id, item, None, {"name": auto_name})

        parent_item.insertChild(insert_index, item)
        parent_item.setExpanded(True)
        self.catalog_tree.setCurrentItem(item, 1)
        item.setSelected(True)
        self.catalog_tree.setFocus()
        self._update_siblings_serial(parent_item)
        self._schedule_catalog_edit(item, 1)

        # 后台创建真实的 catalog_template_item
        self._async_create_template_item(
            placeholder_id, item,
            template_id=tpl_id,
            parent_id=parent_tpl_id,
            sort_order=sort_order,
            sibling_order_ids=sibling_order_ids,
            insert_index=insert_index,
        )
        return item

    def _on_add_child(self):
        current = self.catalog_tree.currentItem() or self.catalog_tree.invisibleRootItem()
        self._create_tpl_node(current)

    def _collect_tpl_ids(self, node):
        ids = []
        def collect(item):
            tpl_item_id = item.data(0, Qt.UserRole)
            # 跳过占位 id（负数）：还没拿到真实 id，DB 里根本没有记录
            if tpl_item_id and int(tpl_item_id) > 0:
                ids.append(tpl_item_id)
            for i in range(item.childCount()):
                collect(item.child(i))
        collect(node)
        return ids

    def _on_delete_node(self):
        current = self.catalog_tree.currentItem()
        if not current:
            return
        if StyledMessageBox.question(self, "确认删除", "删除该节点及其所有子节点？", StyledMessageBox.Yes | StyledMessageBox.No, StyledMessageBox.No, self.current_theme) != StyledMessageBox.Yes:
            return
        ids = self._collect_tpl_ids(current)
        if ids and self.current_entry_id:
            try:
                # 方案A：删本 entry 的 EC 行，然后清理孤儿模板项
                removed = delete_entry_catalog_rows_only(
                    entry_id=int(self.current_entry_id),
                    template_item_ids=ids,
                )
                print(f"[catalog-entry] delete rows in entry={self.current_entry_id}: {removed}")
                # 清理孤儿模板项：删除后无 EC 引用的模板项一并删除
                for tpl_id in ids:
                    try:
                        delete_orphan_template_item_safely(tpl_id)
                    except Exception as e2:
                        print(f"[catalog-entry] orphan template cleanup for {tpl_id} failed: {e2}")
            except Exception as e:
                print(f"[catalog-entry] delete entry catalog rows failed: {e}")
        parent = current.parent() or self.catalog_tree.invisibleRootItem()
        parent.removeChild(current)
        # 删除后更新同级节点的序号
        self._update_siblings_serial(parent)

    def _ensure_entry_catalog_item(self, tpl_item_id: int, item_widget: QTreeWidgetItem):
        """确保当前 entry+tpl_item 有对应的 entry_catalog 记录，返回其 id。"""
        if not tpl_item_id:
            return None
        # 占位 id（负数）：真实模板项后台创建中，此刻还不能建 entry_catalog_item
        if int(tpl_item_id) < 0:
            return None
        self._ensure_entry_record()
        if not self.current_entry_id:
            return None
        ec_id = item_widget.data(1, Qt.UserRole)
        if ec_id:
            return ec_id
        try:
            ec_id = ensure_entry_catalog_item(entry_id=int(self.current_entry_id), template_item_id=int(tpl_item_id))
            item_widget.setData(1, Qt.UserRole, ec_id)
            return ec_id
        except Exception as e:
            print(f"[catalog-entry] ensure entry catalog failed: {e}")
            return None

    def _update_siblings_serial(self, parent_item):
        """更新同一父节点下所有子节点的序号（从1开始递增）。
        跳过模板固定序号的节点和完全空白的行。

        性能：UI 文本立即更新；DB 写通过 pending 队列批量异步完成，
        避免在一次插入/删除/移动后逐行同步写 N 次阻塞主线程。"""
        if not parent_item:
            parent_item = self.catalog_tree.invisibleRootItem()

        self._suppress_catalog_changed = True
        serial_counter = 0
        has_db_changes = False
        # 只在真正有变更时 ensure_entry_record 一次，避免 N 次 ensure 查询
        _entry_id_cached = self.current_entry_id

        for i in range(parent_item.childCount()):
            child = parent_item.child(i)

            # 检查是否有模板预设值，如果有则不修改
            tpl_serial = child.data(0, Qt.UserRole + 10) or ""
            if tpl_serial.strip():
                continue

            # 只跳过完全空白的占位行（无序号且无名称），有序号的行要重新编号
            current_serial = child.text(0).strip()
            has_name = bool(child.text(1).strip())
            if not current_serial and not has_name:
                continue

            serial_counter += 1
            new_serial = str(serial_counter)

            old_serial = child.text(0)
            if old_serial != new_serial:
                child.setText(0, new_serial)

                # 首次有 DB 变更时再确保 entry 存在
                if _entry_id_cached is None:
                    self._ensure_entry_record()
                    _entry_id_cached = self.current_entry_id

                if _entry_id_cached:
                    tpl_item_id = child.data(0, Qt.UserRole)
                    ec_item_id = child.data(1, Qt.UserRole)
                    if tpl_item_id:
                        # 写入 pending 队列 + WAL，一次 debounce 后由 worker 批量 upsert
                        self._stage_pending(tpl_item_id, child, ec_item_id, {"serial": new_serial})
                        has_db_changes = True

        if has_db_changes:
            self._catalog_save_timer.start()
        self._suppress_catalog_changed = False

    def _fix_serials_recursive(self, parent_item):
        """加载时递归修正序号：对每个节点调用 _update_siblings_serial，
        确保可见数据行按位置从 1 连续编号（跳过空白占位行）。"""
        self._update_siblings_serial(parent_item)
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.childCount() > 0:
                self._fix_serials_recursive(child)

    def _auto_assign_serials(self, root_item):
        """递归遍历树，为有内容但没有序号的子节点自动分配序号（加载时调用）。
        完全空白的行（无名称无数据）不分配序号。"""
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            if not child:
                continue
            # 跳过有模板固定序号的节点（如 "一", "4-1" 等）
            tpl_serial = child.data(0, Qt.UserRole + 10) or ""
            if not tpl_serial.strip():
                # 非模板固定序号，检查是否为空
                current_serial = child.text(0).strip()
                has_name = bool(child.text(1).strip())
                # 只给有名称内容的行自动分配序号，空白行不分配
                if not current_serial and has_name:
                    auto_serial = str(i + 1)
                    child.setText(0, auto_serial)
                    # 加载期的自动序号也走 pending + WAL
                    if self.current_entry_id:
                        tpl_item_id = child.data(0, Qt.UserRole)
                        ec_item_id = child.data(1, Qt.UserRole)
                        if tpl_item_id:
                            self._stage_pending(tpl_item_id, child, ec_item_id, {"serial": auto_serial})
            # 递归处理子节点
            if child.childCount() > 0:
                self._auto_assign_serials(child)

    # === 目录录入右键菜单（支持批量操作） ===
    def _on_catalog_context_menu(self, pos):
        """目录树右键菜单（支持多选批量操作）"""
        try:
            self._commit_active_catalog_editor()
        except Exception as e:
            print(f"[catalog-entry] commit before context menu failed: {e}")
        item = self.catalog_tree.itemAt(pos)
        if not item:
            return
        
        # 获取当前选中的所有项
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            return
        
        menu = QMenu(self)

        # 在上方 / 下方插入一行（只对单选有效）
        action_insert_above = menu.addAction("在上方插入一行")
        action_insert_above.triggered.connect(self._on_insert_above)
        action_insert_above.setEnabled(len(selected_items) == 1)

        action_insert_below = menu.addAction("在下方插入一行")
        action_insert_below.triggered.connect(self._on_insert_below)
        action_insert_below.setEnabled(len(selected_items) == 1)

        menu.addSeparator()

        # 上移
        action_move_up = menu.addAction(f"上移 ({len(selected_items)}项)" if len(selected_items) > 1 else "上移")
        action_move_up.triggered.connect(self._on_move_nodes_up)
        
        # 下移
        action_move_down = menu.addAction(f"下移 ({len(selected_items)}项)" if len(selected_items) > 1 else "下移")
        action_move_down.triggered.connect(self._on_move_nodes_down)
        
        menu.addSeparator()

        # 跨类别迁移
        can_cross, prev_cat_id, next_cat_id = self._check_can_cross_category_move(selected_items)
        if can_cross:
            prev_cat_name, next_cat_name = self._get_adjacent_category_names(selected_items)
            if prev_cat_name:
                label = "上移至 " + prev_cat_name
                if len(selected_items) > 1:
                    label += " (" + str(len(selected_items)) + "项)"
                action_move_to_prev = menu.addAction(label)
                action_move_to_prev.triggered.connect(self._on_move_to_prev_category)
            if next_cat_name:
                label = "下移至 " + next_cat_name
                if len(selected_items) > 1:
                    label += " (" + str(len(selected_items)) + "项)"
                action_move_to_next = menu.addAction(label)
                action_move_to_next.triggered.connect(self._on_move_to_next_category)
            if prev_cat_name or next_cat_name:
                menu.addSeparator()

        # 删除
        action_delete = menu.addAction(f"删除 ({len(selected_items)}项)" if len(selected_items) > 1 else "删除")
        action_delete.triggered.connect(self._on_delete_nodes)
        
        # 检查是否可以上移或下移（所有选中项必须是同级且连续）
        can_move = self._check_can_move_selected(selected_items)
        action_move_up.setEnabled(can_move and self._check_can_move_up(selected_items))
        action_move_down.setEnabled(can_move and self._check_can_move_down(selected_items))
        
        menu.exec_(self.catalog_tree.viewport().mapToGlobal(pos))
    
    def _check_can_move_selected(self, items):
        """检查选中项是否可以移动：必须是同级且连续"""
        if not items:
            return False
        
        # 检查是否同级
        first_parent = items[0].parent()
        for item in items:
            if item.parent() != first_parent:
                return False
        
        # 检查是否连续
        parent = first_parent or self.catalog_tree.invisibleRootItem()
        indices = sorted([parent.indexOfChild(item) for item in items])
        for i in range(len(indices) - 1):
            if indices[i+1] - indices[i] != 1:
                return False
        
        return True
    
    def _check_can_move_up(self, items):
        """检查选中项是否可以上移"""
        if not items:
            return False
        parent = items[0].parent() or self.catalog_tree.invisibleRootItem()
        min_index = min([parent.indexOfChild(item) for item in items])
        return min_index > 0
    
    def _check_can_move_down(self, items):
        """检查选中项是否可以下移"""
        if not items:
            return False
        parent = items[0].parent() or self.catalog_tree.invisibleRootItem()
        max_index = max([parent.indexOfChild(item) for item in items])
        return max_index < parent.childCount() - 1
    
    def _on_move_nodes_up(self):
        """批量上移选中的节点"""
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            StyledMessageBox.information(self, "提示", "请先选择要移动的节点", self.current_theme)
            return
        
        # 检查是否可以移动
        if not self._check_can_move_selected(selected_items):
            StyledMessageBox.warning(self, "提示", "只能移动同级且连续的节点", self.current_theme)
            return
        
        if not self._check_can_move_up(selected_items):
            return
        
        self._move_nodes_batch(selected_items, -1)
    
    def _on_move_nodes_down(self):
        """批量下移选中的节点"""
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            StyledMessageBox.information(self, "提示", "请先选择要移动的节点", self.current_theme)
            return
        
        # 检查是否可以移动
        if not self._check_can_move_selected(selected_items):
            StyledMessageBox.warning(self, "提示", "只能移动同级且连续的节点", self.current_theme)
            return
        
        if not self._check_can_move_down(selected_items):
            return
        
        self._move_nodes_batch(selected_items, 1)
    
    def _move_nodes_batch(self, items, direction):
        """批量移动节点：direction=-1上移，1下移"""
        if not items:
            return
        
        parent = items[0].parent() or self.catalog_tree.invisibleRootItem()
        
        # 按索引排序
        items_with_index = [(parent.indexOfChild(item), item) for item in items]
        if direction < 0:
            # 上移：从前往后处理
            items_with_index.sort()
        else:
            # 下移：从后往前处理
            items_with_index.sort(reverse=True)
        
        self._suppress_catalog_changed = True
        has_placeholder = False
        try:
            from .repo.inventory_entry_repo import swap_entry_catalog_item_order
            
            for index, item in items_with_index:
                new_index = index + direction
                if new_index < 0 or new_index >= parent.childCount():
                    continue
                
                # 获取要交换的两个节点
                sibling = parent.child(new_index)
                if not sibling:
                    continue
                
                current_id = item.data(0, Qt.UserRole)
                sibling_id = sibling.data(0, Qt.UserRole)
                
                if not current_id or not sibling_id:
                    continue
                
                # 占位 id（负数）：真实模板项后台创建中，跳过避免外键错误
                if int(current_id) <= 0 or int(sibling_id) <= 0:
                    has_placeholder = True
                    continue
                
                # 交换当前 entry 的 EC 行顺序
                success = swap_entry_catalog_item_order(
                    entry_id=int(self.current_entry_id),
                    template_item_id_a=current_id,
                    template_item_id_b=sibling_id,
                )
                if not success:
                    continue
                
                # 在UI中交换位置
                taken_item = parent.takeChild(index)
                parent.insertChild(new_index, taken_item)
            
            # 恢复选中状态
            for _, item in items_with_index:
                item.setSelected(True)
            
            # 移动后更新同级节点的序号
            self._update_siblings_serial(parent)
            
            if has_placeholder:
                StyledMessageBox.information(self, "提示", "部分目录正在保存中，请稍候再试", self.current_theme)
                
        except Exception as e:
            print(f"[catalog-entry] batch move failed: {e}")
            StyledMessageBox.warning(self, "提示", f"移动失败：{e}", self.current_theme)
        finally:
            self._suppress_catalog_changed = False
    
    # ------------------------------------------------------------------
    # 跨类别迁移：将选中的目录条目上移/下移至相邻类别
    # ------------------------------------------------------------------
    def _get_parent_category_id(self, item):
        """获取 item 所属的直接父类别的 template_item_id。
        支持多层子类：返回 item 的直接父节点 id，
        这样 4-1 下的条目可以迁移到 4-2（同一大类下的兄弟子类），
        也可以迁移到 3 或 5（大类别之间的迁移）。"""
        if not item:
            return None
        parent = item.parent()
        if parent is None or parent == self.catalog_tree.invisibleRootItem():
            return item.data(0, Qt.UserRole)
        return parent.data(0, Qt.UserRole)

    def _get_adjacent_category_names(self, items):
        """获取选中条目当前类别的上一个和下一个兄弟类别的名称。
        支持任意层级：在 item 父节点的同级兄弟中查找。
        Returns (prev_cat_name, next_cat_name)，无相邻方向时为 None。"""
        if not items:
            return (None, None)
        current_cat_id = self._get_parent_category_id(items[0])
        if not current_cat_id:
            return (None, None)
        # 找到当前类别节点在树中的位置
        cat_item = self._find_tree_item_by_tpl_id(current_cat_id)
        if not cat_item:
            return (None, None)
        parent_of_cat = cat_item.parent() or self.catalog_tree.invisibleRootItem()
        cat_idx = None
        for i in range(parent_of_cat.childCount()):
            if parent_of_cat.child(i).data(0, Qt.UserRole) == current_cat_id:
                cat_idx = i
                break
        if cat_idx is None:
            return (None, None)
        prev_name = None
        next_name = None
        if cat_idx > 0:
            prev_child = parent_of_cat.child(cat_idx - 1)
            prev_name = prev_child.text(1).strip() or prev_child.text(0).strip() or "未命名类别"
        if cat_idx < parent_of_cat.childCount() - 1:
            next_child = parent_of_cat.child(cat_idx + 1)
            next_name = next_child.text(1).strip() or next_child.text(0).strip() or "未命名类别"
        return (prev_name, next_name)

    def _check_can_cross_category_move(self, items):
        """检查选中的条目是否可以进行跨类别迁移。
        条件：1) 所有选中项属于同一类别  2) 该类别有相邻的兄弟类别
        支持任意层级：在父节点的同级兄弟中查找目标。
        Returns (can_move, prev_cat_id, next_cat_id)"""
        if not items:
            return (False, None, None)
        for item in items:
            if item.parent() is None:
                return (False, None, None)
        first_cat_id = self._get_parent_category_id(items[0])
        if not first_cat_id:
            return (False, None, None)
        for item in items:
            if self._get_parent_category_id(item) != first_cat_id:
                return (False, None, None)
        # 找到当前类别节点在树中的位置
        cat_item = self._find_tree_item_by_tpl_id(first_cat_id)
        if not cat_item:
            return (False, None, None)
        parent_of_cat = cat_item.parent() or self.catalog_tree.invisibleRootItem()
        cat_idx = None
        for i in range(parent_of_cat.childCount()):
            if parent_of_cat.child(i).data(0, Qt.UserRole) == first_cat_id:
                cat_idx = i
                break
        if cat_idx is None:
            return (False, None, None)
        prev_cat_id = parent_of_cat.child(cat_idx - 1).data(0, Qt.UserRole) if cat_idx > 0 else None
        next_cat_id = parent_of_cat.child(cat_idx + 1).data(0, Qt.UserRole) if cat_idx < parent_of_cat.childCount() - 1 else None
        can_move = prev_cat_id is not None or next_cat_id is not None
        return (can_move, prev_cat_id, next_cat_id)

    def _find_tree_item_by_tpl_id(self, tpl_id):
        """在目录树中查找指定 template_item_id 的节点。"""
        if not tpl_id:
            return None
        root = self.catalog_tree.invisibleRootItem()

        def _find(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, Qt.UserRole) == tpl_id:
                    return child
                result = _find(child)
                if result:
                    return result
            return None

        return _find(root)

    def _on_move_to_prev_category(self):
        """将选中的条目迁移到上一个类别"""
        self._cross_category_move(-1)

    def _on_move_to_next_category(self):
        """将选中的条目迁移到下一个类别"""
        self._cross_category_move(1)

    def _cross_category_move(self, direction):
        """跨类别迁移：direction=-1 上移至上一个类别, 1 下移至下一个类别。
        迁移后条目出现在目标类别的最后，然后刷新树并更新序号。"""
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            StyledMessageBox.information(self, "提示", "请先选择要迁移的条目", self.current_theme)
            return
        selected_ids = {id(item) for item in selected_items}
        selected_items = [
            item for item in selected_items
            if not any(id(parent) in selected_ids for parent in self._catalog_item_ancestors(item))
        ]
        if any(item.parent() is None for item in selected_items):
            StyledMessageBox.warning(self, "提示", "不能直接迁移根级类别，请选择类别下面的目录条目。", self.current_theme)
            return
        can_move, prev_cat_id, next_cat_id = self._check_can_cross_category_move(selected_items)
        if not can_move:
            StyledMessageBox.warning(self, "提示", "选中的条目无法跨类别迁移（类别不确定或无相邻类别）", self.current_theme)
            return
        target_cat_id = prev_cat_id if direction < 0 else next_cat_id
        if not target_cat_id:
            return
        prev_cat_name, next_cat_name = self._get_adjacent_category_names(selected_items)
        target_cat_name = prev_cat_name if direction < 0 else next_cat_name
        if StyledMessageBox.question(
            self,
            "确认迁移",
            f"确定将选中的 {len(selected_items)} 个目录条目迁移到「{target_cat_name or '目标类别'}」吗？\n\n此操作仅迁移当前人员的目录数据，不会影响其他档案。",
            StyledMessageBox.Yes | StyledMessageBox.No,
            StyledMessageBox.No,
            self.current_theme,
        ) != StyledMessageBox.Yes:
            return
        try:
            self._commit_active_catalog_editor()
        except Exception as e:
            StyledMessageBox.warning(self, "提示", f"迁移前保存当前目录失败：{e}", self.current_theme)
            return
        if self._placeholders_in_flight or self._catalog_save_in_flight or self._pending_catalog_saves:
            if not self._catalog_save_in_flight:
                try:
                    self._catalog_save_timer.start(500 if self._placeholders_in_flight else 50)
                except RuntimeError:
                    pass
            StyledMessageBox.warning(self, "提示", "当前目录仍有未保存内容，请稍后重试迁移。", self.current_theme)
            return
        all_ids = []
        for item in selected_items:
            tpl_item_id = item.data(0, Qt.UserRole)
            try:
                tpl_item_id = int(tpl_item_id)
            except Exception:
                tpl_item_id = 0
            if tpl_item_id > 0 and tpl_item_id not in all_ids:
                all_ids.append(tpl_item_id)
        if not all_ids:
            return
        # 调用 repo 层迁移（仅迁移当前 entry 的数据，不影响其他档案）
        try:
            updated = migrate_entry_catalog_items_to_parent(
                entry_id=int(self.current_entry_id),
                source_template_item_ids=all_ids,
                target_parent_id=int(target_cat_id),
            )
            print("[catalog-entry] per-entry migrate: {} items to parent_id={}".format(updated, target_cat_id))
        except Exception as e:
            print("[catalog-entry] cross-category move failed: {}".format(e))
            StyledMessageBox.warning(self, "提示", "跨类别迁移失败：{}".format(e), self.current_theme)
            return
        # 刷新整个目录树
        self._populate_catalog_tree()

    def _catalog_item_ancestors(self, item):
        parent = item.parent() if item else None
        while parent is not None:
            yield parent
            parent = parent.parent()

    def _shift_select_range(self, clicked_item):
        """Shift+click 范围选择：选中从锚点到 clicked_item 之间所有同层兄弟节点。

        Excel 风格：只在同一父节点下做连续选区，跨层级不匹配时回退为单选。
        """
        anchor = getattr(self, '_selection_anchor', None)
        if anchor is None or anchor == clicked_item:
            self._selection_anchor = clicked_item
            return
        # 获取双方所属的父节点
        anchor_parent = anchor.parent() or self.catalog_tree.invisibleRootItem()
        clicked_parent = clicked_item.parent() or self.catalog_tree.invisibleRootItem()
        if anchor_parent is not clicked_parent:
            # 不同父节点 → 回退单选
            self._selection_anchor = clicked_item
            return
        # 计算索引范围
        anchor_idx = anchor_parent.indexOfChild(anchor)
        clicked_idx = anchor_parent.indexOfChild(clicked_item)
        if anchor_idx < 0 or clicked_idx < 0:
            self._selection_anchor = clicked_item
            return
        start = min(anchor_idx, clicked_idx)
        end = max(anchor_idx, clicked_idx)
        # 构建新的选中集合
        self._suppress_catalog_changed = True
        self.catalog_tree.clearSelection()
        for i in range(start, end + 1):
            sibling = anchor_parent.child(i)
            if sibling:
                sibling.setSelected(True)
        self._suppress_catalog_changed = False

    def _on_delete_nodes(self):
        """批量删除选中的节点"""
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            StyledMessageBox.information(self, "提示", "请先选择要删除的节点", self.current_theme)
            return
        
        # 大类（根级类别）不可删除
        root_items = [item for item in selected_items
                      if item.parent() is None or item.parent() == self.catalog_tree.invisibleRootItem()]
        if root_items:
            StyledMessageBox.warning(self, "提示", "大类（根级类别）不可删除，请选择类别下的目录条目进行删除。", self.current_theme)
            return
        
        # 确认删除
        count = len(selected_items)
        if StyledMessageBox.question(self, "确认删除", f"确定要删除选中的 {count} 个节点及其所有子节点吗？", 
                                     StyledMessageBox.Yes | StyledMessageBox.No, 
                                     StyledMessageBox.No, self.current_theme) != StyledMessageBox.Yes:
            return
        
        # 收集所有要删除的节点ID（包括子节点），并记录受影响的父节点
        all_ids = []
        affected_parents = []  # 保存实际的父节点引用
        seen_parent_ids = set()
        
        for item in selected_items:
            ids = self._collect_tpl_ids(item)
            all_ids.extend(ids)
            parent = item.parent() or self.catalog_tree.invisibleRootItem()
            pid = id(parent)
            if pid not in seen_parent_ids:
                seen_parent_ids.add(pid)
                affected_parents.append(parent)
        
        # 删除数据库记录（方案A：删本 entry 的 EC 行，然后清理孤儿模板项）
        if all_ids and self.current_entry_id:
            try:
                removed = delete_entry_catalog_rows_only(
                    entry_id=int(self.current_entry_id),
                    template_item_ids=all_ids,
                )
                print(f"[catalog-entry] batch delete rows in entry={self.current_entry_id}: {removed}")
                # 清理孤儿模板项：如果删除后没有任何 EC 行引用该模板项，则一并删除模板项
                # 这样删除的条目不会在刷新后重新出现
                for tpl_id in all_ids:
                    try:
                        delete_orphan_template_item_safely(tpl_id)
                    except Exception as e2:
                        print(f"[catalog-entry] orphan template cleanup for {tpl_id} failed: {e2}")
            except Exception as e:
                print(f"[catalog-entry] batch delete entry catalog rows failed: {e}")
        
        # 从UI中删除
        self._suppress_catalog_changed = True
        for item in selected_items:
            parent = item.parent() or self.catalog_tree.invisibleRootItem()
            parent.removeChild(item)
        
        # 只更新受影响父节点下的序号，不影响其他类别
        for parent in affected_parents:
            self._update_siblings_serial(parent)
        self._suppress_catalog_changed = False
    
    def _update_all_siblings_serial(self):
        """更新整个树中所有节点的序号"""
        def update_node_and_children(parent_item):
            self._update_siblings_serial(parent_item)
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.childCount() > 0:
                    update_node_and_children(child)
        
        update_node_and_children(self.catalog_tree.invisibleRootItem())
    
    def _on_move_item(self, item, direction):
        """移动条目：direction=-1表示上移，1表示下移（单个项移动，保留用于兼容）"""
        if not item:
            return
        
        parent = item.parent() or self.catalog_tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        new_index = index + direction
        
        if new_index < 0 or new_index >= parent.childCount():
            return
        
        # 获取当前项和目标项的ID
        current_id = item.data(0, Qt.UserRole)
        sibling = parent.child(new_index)
        sibling_id = sibling.data(0, Qt.UserRole)
        
        if not current_id or not sibling_id:
            return
        
        # 占位 id（负数）：真实模板项后台创建中，DB 里还没有记录，交换会触发外键错误
        if int(current_id) <= 0 or int(sibling_id) <= 0:
            StyledMessageBox.information(self, "提示", "该目录正在保存中，请稍候再试", self.current_theme)
            return
        
        # 交换当前 entry 的 EC 行顺序
        try:
            from .repo.inventory_entry_repo import swap_entry_catalog_item_order
            success = swap_entry_catalog_item_order(
                entry_id=int(self.current_entry_id),
                template_item_id_a=current_id,
                template_item_id_b=sibling_id,
            )
            if not success:
                StyledMessageBox.warning(self, "提示", "移动失败", self.current_theme)
                return
        except Exception as e:
            print(f"[catalog-entry] swap sort order failed: {e}")
            StyledMessageBox.warning(self, "提示", f"移动失败：{e}", self.current_theme)
            return
        
        # 在UI中交换位置
        self._suppress_catalog_changed = True
        taken_item = parent.takeChild(index)
        parent.insertChild(new_index, taken_item)
        self.catalog_tree.setCurrentItem(taken_item)
        # 移动后更新同级节点的序号
        self._update_siblings_serial(parent)
        self._suppress_catalog_changed = False
    
    def _on_delete_node_from_menu(self, item):
        """从右键菜单删除节点（已弃用，使用批量删除）"""
        if not item:
            return
        # 设置当前项，然后调用批量删除方法
        self.catalog_tree.setCurrentItem(item)
        self._on_delete_nodes()

    # === 目录录入操作按钮（已移除） ===

    def _on_catalog_item_changed(self, item, column):
        if self._suppress_catalog_changed:
            return
        if column < 0 or column > 6:
            return

        # 编号(0) 和 目录名称(1)：大类（根级类别）不可修改
        if column in (0, 1):
            parent = item.parent()
            if parent is None or parent == self.catalog_tree.invisibleRootItem():
                # 大类节点：恢复原值
                tpl_value = item.data(column, Qt.UserRole + 10) or ""
                if tpl_value.strip() and item.text(column) != tpl_value:
                    self._suppress_catalog_changed = True
                    item.setText(column, tpl_value)
                    self._suppress_catalog_changed = False
                return

        raw = item.text(column).strip()

        # 任意非编号列(1-6)输入内容后自动生成序号
        if column >= 1 and raw:
            serial_str = item.text(0).strip()
            if not serial_str:  # 序号为空，自动生成
                parent_item = item.parent()
                if parent_item is None:
                    parent_item = self.catalog_tree.invisibleRootItem()
                # 计算序号：同一父节点下的当前索引 + 1
                current_index = parent_item.indexOfChild(item)
                auto_serial = str(current_index + 1)
                self._suppress_catalog_changed = True
                item.setText(0, auto_serial)
                self._suppress_catalog_changed = False
                # 自动序号走 pending + WAL，异步批量落盘
                self._ensure_entry_record()
                if self.current_entry_id:
                    tpl_item_id = item.data(0, Qt.UserRole)
                    ec_item_id = item.data(1, Qt.UserRole)
                    if tpl_item_id:
                        self._stage_pending(tpl_item_id, item, ec_item_id, {"serial": auto_serial})

        # 年月日输入校验（仅校验格式，不在单字段编辑时校验升序）
        if column == 2:  # 年
            valid, msg = self._validate_year(raw)
            if not valid:
                self._suppress_catalog_changed = True
                item.setText(column, "")
                self._suppress_catalog_changed = False
                self._validation_failed_reenter = True
                StyledMessageBox.warning(self, "输入错误", msg, self.current_theme)
                # 使用辅助方法重新进入编辑状态
                self._reenter_edit(item, column)
                return
        elif column == 3:  # 月
            valid, msg = self._validate_month(raw)
            if not valid:
                self._suppress_catalog_changed = True
                item.setText(column, "")
                self._suppress_catalog_changed = False
                self._validation_failed_reenter = True
                StyledMessageBox.warning(self, "输入错误", msg, self.current_theme)
                self._reenter_edit(item, column)
                return
        elif column == 4:  # 日
            valid, msg = self._validate_day(raw)
            if not valid:
                self._suppress_catalog_changed = True
                item.setText(column, "")
                self._suppress_catalog_changed = False
                self._validation_failed_reenter = True
                StyledMessageBox.warning(self, "输入错误", msg, self.current_theme)
                self._reenter_edit(item, column)
                return
        elif column == 5:  # 页数：必须是非负整数，防止写入汉字/字母 → DB Integer 列类型冲突
            valid, msg = self._validate_pages(raw)
            if not valid:
                self._suppress_catalog_changed = True
                item.setText(column, "")
                self._suppress_catalog_changed = False
                self._validation_failed_reenter = True
                StyledMessageBox.warning(self, "输入错误", msg, self.current_theme)
                self._reenter_edit(item, column)
                return

        # 确保 entry 已存在
        self._ensure_entry_record()
        if not self.current_entry_id:
            return
        tpl_item_id = item.data(0, Qt.UserRole)
        ec_item_id = item.data(1, Qt.UserRole)
        tpl_id = self._current_template_id()
        if not tpl_item_id or not tpl_id:
            return

        # 列类型调整为字符串，确保如 "01" 这类前导零文本原样保存
        field_map = {
            0: ("serial", "str"),
            1: ("name", "str"),
            2: ("year", "str"),
            3: ("month", "str"),
            4: ("day", "str"),
            5: ("pages", "str"),
            6: ("remark", "str"),
        }
        if column not in field_map:
            return

        field, typ = field_map[column]
        value = raw

        # 防抖：把本次字段更新加入 pending 队列（同步镜像到 WAL）
        # 延迟 350ms 后批量写入 DB；切换行时会立即 flush，保证数据不丢失
        self._stage_pending(tpl_item_id, item, ec_item_id, {field: value})

        # 目录名称列：异步记录到自动补全（放到下一个事件循环，不阻塞当前 Tab 切换）
        if column == 1 and value:
            QTimer.singleShot(0, lambda v=value, i=item: self._record_autocomplete_entry(i, v))

        # 目录名称或页数列变动时，刷新底部统计（键入热路径：不查图片数 DB，
        # 只防抖刷新基于树内容的页数/总条数，避免光标转圈）
        if column in (1, 5):
            self._update_total_pages_label(refresh_image_count=False)

    # ------------------------------------------------------------------
    # 本地 WAL 镜像：把 pending 同步到本地 SQLite，app 强杀后可恢复
    # ------------------------------------------------------------------
    def _wal_stage(self, tpl_item_id, fields: dict, ec_item_id=None):
        """把一批字段写入本地 WAL（任何错误都吞掉，WAL 只是安全网）。"""
        if not self.current_entry_id or not fields:
            return
        try:
            get_catalog_wal().write_fields(
                entry_id=int(self.current_entry_id),
                template_item_id=int(tpl_item_id),
                fields=fields,
                entry_catalog_item_id=int(ec_item_id) if ec_item_id else None,
            )
        except Exception as e:
            print(f"[catalog-wal] stage failed: {e}")

    def _wal_confirm(self, tpl_item_id, fields):
        """服务器 DB 写入成功后，从 WAL 中移除对应字段。"""
        if not self.current_entry_id:
            return
        try:
            get_catalog_wal().remove_fields(
                entry_id=int(self.current_entry_id),
                template_item_id=int(tpl_item_id),
                fields=list(fields or []),
            )
        except Exception as e:
            print(f"[catalog-wal] confirm failed: {e}")

    def _stage_pending(self, tpl_item_id, tree_item, ec_item_id, fields: dict):
        """统一的字段入队：更新内存 pending dict + 写入本地 WAL + 启动防抖定时器。

        这是所有字段落盘路径的唯一入口，确保 WAL 永远与内存 pending 同步。
        """
        if not tpl_item_id or not fields:
            return
        pending = self._pending_catalog_saves.setdefault(
            tpl_item_id, [tree_item, ec_item_id, {}]
        )
        pending[2].update(fields)
        if pending[1] is None and ec_item_id:
            pending[1] = ec_item_id
        # 立即把本次变更写入 WAL（INSERT OR REPLACE 保持最新值）
        # 占位 id（负数）不写 WAL——真实 id 到来后再一次性迁移
        if tpl_item_id > 0:
            self._wal_stage(tpl_item_id, fields, pending[1])
        # 对话框已开始关闭：sync flush 会把 pending 全部落盘，这里不再动定时器，
        # 避免晚到的 pending 把定时器重新拉起并在 C++ 对象销毁后触发。
        if getattr(self, "_is_closing", False):
            return
        try:
            self._catalog_save_timer.start()
        except RuntimeError:
            # QTimer C++ 已被销毁
            pass

    # ------------------------------------------------------------------
    # 占位 ID：异步新建模板项，不阻塞 UI
    # ------------------------------------------------------------------
    def _alloc_placeholder_tpl_id(self) -> int:
        """分配一个负数占位 id，真实 id 到来后会迁移。"""
        self._next_placeholder_id += 1
        pid = -self._next_placeholder_id
        self._placeholders_in_flight.add(pid)
        return pid

    def _async_create_template_item(
        self,
        placeholder_id,
        tree_item,
        *,
        template_id,
        parent_id,
        sort_order,
        sibling_order_ids=None,
        insert_index=None,
    ):
        """后台创建 catalog_template_item，拿到真实 id 后迁移占位 id。"""
        self._placeholders_in_flight.add(placeholder_id)

        try:
            if parent_id is not None and int(parent_id) < 0:
                def retry_after_parent_materialized():
                    if getattr(self, "_is_closing", False):
                        return
                    if placeholder_id not in self._pending_catalog_saves:
                        self._placeholders_in_flight.discard(placeholder_id)
                        return
                    try:
                        if tree_item is None or tree_item.treeWidget() is None:
                            self._pending_catalog_saves.pop(placeholder_id, None)
                            self._placeholders_in_flight.discard(placeholder_id)
                            return
                        parent_item = tree_item.parent()
                        if parent_item is None:
                            parent_real_id = None
                        else:
                            parent_real_id = parent_item.data(0, Qt.UserRole)
                            if parent_real_id is not None and int(parent_real_id) < 0:
                                QTimer.singleShot(500, retry_after_parent_materialized)
                                return
                        self._async_create_template_item(
                            placeholder_id,
                            tree_item,
                            template_id=template_id,
                            parent_id=parent_real_id,
                            sort_order=sort_order,
                            sibling_order_ids=sibling_order_ids,
                            insert_index=insert_index,
                        )
                    except RuntimeError:
                        self._pending_catalog_saves.pop(placeholder_id, None)
                        self._placeholders_in_flight.discard(placeholder_id)

                QTimer.singleShot(500, retry_after_parent_materialized)
                return
        except Exception:
            pass

        def do_create():
            return create_catalog_template_item(
                template_id=int(template_id),
                parent_id=int(parent_id) if parent_id else None,
                sort_order=int(sort_order),
                sibling_order_ids=list(sibling_order_ids or []),
                insert_index=insert_index,
            )

        def on_created(real_tpl_id):
            try:
                if not real_tpl_id:
                    self._placeholders_in_flight.discard(placeholder_id)
                    on_error("未返回模板项ID")
                    return
                # 如果 tree item 已被用户删除（或 widget 已关闭），刚创建的真实行会变成孤儿
                # 对话框已关闭 -> 视作 detached（tree 的 C++ 对象可能已销毁）
                detached = bool(getattr(self, "_is_closing", False))
                if not detached:
                    try:
                        detached = (tree_item is None) or (tree_item.treeWidget() is None)
                    except RuntimeError:
                        # QTreeWidgetItem 已被底层销毁
                        detached = True
                if detached:
                    # 孤儿清理（数据安全严格保护，杜绝历史 bug "每类第一条都没了"）
                    # ----------------------------------------------------------------
                    # 旧实现这里直接调 delete_catalog_template_items_and_entry_catalog_items，
                    # 但 CatalogTemplate 是**全局共享**的：在异步创建模板的窗口期内，
                    # 其他用户/客户端可能已经为这个新槽位创建了 EC 行（甚至填了数据）。
                    # 盲目级联删会跨 entry 把别人刚填的数据一起清掉，这与用户反馈
                    # "几类第一条都没了" 的现象完全吻合。
                    #
                    # 修复策略（最保守）：
                    # 1) 先删本 entry 自己的 EC 行（delete_entry_catalog_rows_only，安全）。
                    # 2) 仅当此模板条目**确认无任何 EC 行引用**时，才删模板条目本身
                    #    （delete_orphan_template_item_safely 内部做了原子性引用检查）。
                    # 3) 若仍有引用 → 保留模板，宁可留个孤儿槽位，也绝不跨 entry 删数据。
                    #
                    # ⚠️ 对话框已关闭场景（_is_closing=True）：我们 **不做** 孤儿清理。
                    # 原因：用户刚在新行里敲了数据，sync flush 已把这些字段 upsert 进了
                    # placeholder 对应的位置，但 placeholder 还没迁移到真实 tpl_id。
                    # 如果这里再走孤儿清理，会把用户刚录的 EC 行一起删掉。
                    # 正确做法是把真实 id 回填到 WAL，让下次启动回放接手。
                    if getattr(self, "_is_closing", False):
                        try:
                            wal = get_catalog_wal()
                            placeholder_entry = self._pending_catalog_saves.pop(placeholder_id, None)
                            if placeholder_entry and self.current_entry_id:
                                _, ec_id, fields = placeholder_entry
                                if fields:
                                    wal.write_fields(
                                        entry_id=int(self.current_entry_id),
                                        template_item_id=int(real_tpl_id),
                                        fields=fields,
                                        entry_catalog_item_id=int(ec_id) if ec_id else None,
                                    )
                        except Exception as e:
                            print(f"[catalog-entry] closing-time placeholder WAL migrate failed: {e}")
                        self._placeholders_in_flight.discard(placeholder_id)
                        return
                    try:
                        if self.current_entry_id:
                            delete_entry_catalog_rows_only(
                                entry_id=int(self.current_entry_id),
                                template_item_ids=[int(real_tpl_id)],
                            )
                        deleted = delete_orphan_template_item_safely(int(real_tpl_id))
                        if not deleted:
                            print(
                                f"[catalog-entry] orphan tpl {real_tpl_id} kept "
                                f"(referenced by other entries; left for admin cleanup)"
                            )
                    except Exception as de:
                        print(f"[catalog-entry] orphan cleanup failed: {de}")
                    self._pending_catalog_saves.pop(placeholder_id, None)
                    self._placeholders_in_flight.discard(placeholder_id)
                    return
                self._migrate_placeholder_id(placeholder_id, int(real_tpl_id), tree_item)
                # 迁移后立刻刷新一次 pending（真实 id 现在可以 upsert 了）
                if self._pending_catalog_saves.get(int(real_tpl_id)):
                    try:
                        self._catalog_save_timer.start(50)
                    except RuntimeError:
                        pass
            except Exception as e:
                print(f"[catalog-entry] placeholder migrate failed: {e}")
                self._placeholders_in_flight.discard(placeholder_id)

        def on_error(err):
            print(f"[catalog-entry] async create template item failed: {err}")
            self._placeholders_in_flight.discard(placeholder_id)
            if getattr(self, "_is_closing", False):
                return
            try:
                if tree_item is None or tree_item.treeWidget() is None:
                    self._pending_catalog_saves.pop(placeholder_id, None)
                    return
            except RuntimeError:
                self._pending_catalog_saves.pop(placeholder_id, None)
                return

            def retry_create():
                if getattr(self, "_is_closing", False):
                    return
                if placeholder_id not in self._pending_catalog_saves:
                    return
                try:
                    if tree_item is None or tree_item.treeWidget() is None:
                        self._pending_catalog_saves.pop(placeholder_id, None)
                        return
                except RuntimeError:
                    self._pending_catalog_saves.pop(placeholder_id, None)
                    return
                self._async_create_template_item(
                    placeholder_id,
                    tree_item,
                    template_id=template_id,
                    parent_id=parent_id,
                    sort_order=sort_order,
                    sibling_order_ids=sibling_order_ids,
                    insert_index=insert_index,
                )

            QTimer.singleShot(1500, retry_create)

        worker = Worker(do_create)
        worker.signals.finished.connect(on_created)
        worker.signals.error.connect(on_error)
        self._thread_pool.start(worker)

    def _migrate_placeholder_id(self, placeholder_id: int, real_tpl_id: int, tree_item):
        """把占位 id 换成真实 tpl_item_id：tree item + pending + WAL 三处同步更新。"""
        if not real_tpl_id:
            return
        # 1) tree item 的 UserRole 更新
        if tree_item:
            try:
                tree_item.setData(0, Qt.UserRole, int(real_tpl_id))
            except Exception:
                pass
        # 2) pending dict 迁移
        entry = self._pending_catalog_saves.pop(placeholder_id, None)
        if entry:
            existing = self._pending_catalog_saves.get(real_tpl_id)
            if existing:
                existing[2].update(entry[2])
                if existing[1] is None and entry[1]:
                    existing[1] = entry[1]
            else:
                self._pending_catalog_saves[real_tpl_id] = entry
        # 3) WAL：占位 id 没写过 WAL，只需把当前 pending 字段以真实 id 补写一次
        real_entry = self._pending_catalog_saves.get(real_tpl_id)
        if real_entry and real_entry[2]:
            self._wal_stage(real_tpl_id, real_entry[2], real_entry[1])
        # 4) 标记已完成
        self._placeholders_in_flight.discard(placeholder_id)

    def _materialize_placeholder_now(self, placeholder_id: int, tree_item):
        if not placeholder_id or int(placeholder_id) >= 0:
            return None
        try:
            if tree_item is None or tree_item.treeWidget() is not self.catalog_tree:
                return None
            parent_item = tree_item.parent() or self.catalog_tree.invisibleRootItem()
            insert_index = parent_item.indexOfChild(tree_item)
            if insert_index < 0:
                return None
            parent_tpl_id = None
            if parent_item != self.catalog_tree.invisibleRootItem():
                parent_tpl_id = parent_item.data(0, Qt.UserRole)
                if parent_tpl_id is None or int(parent_tpl_id) < 0:
                    return None
                parent_tpl_id = int(parent_tpl_id)
            tpl_id = self.current_template_id or self._current_template_id()
            if not tpl_id:
                return None
            real_tpl_id = create_catalog_template_item(
                template_id=int(tpl_id),
                parent_id=parent_tpl_id,
                sort_order=int(insert_index) + 1,
                sibling_order_ids=self._sibling_order_ids(parent_item),
                insert_index=int(insert_index),
            )
            if real_tpl_id:
                self._migrate_placeholder_id(int(placeholder_id), int(real_tpl_id), tree_item)
                return int(real_tpl_id)
        except Exception as e:
            print(f"[catalog-entry] sync create placeholder failed: {e}")
        return None

    def _flush_catalog_pending_saves(self):
        """将 pending 的目录字段变更在后台 Worker 线程批量写入 DB，不阻塞 UI。

        数据安全约束：
        1. pending 不预先清空；只在 worker 成功返回对应字段后才逐字段移除。
        2. worker 失败时字段保留在 pending 中，延迟后自动重试。
        3. 同一时刻只允许一个 worker 在跑（避免并发写同一字段乱序）。
        """
        if not self._pending_catalog_saves or not self.current_entry_id:
            return
        # 对话框已关闭：不再发起新的 DB 写入（sync flush 已把该写的都写了）
        if getattr(self, "_is_closing", False):
            return
        # 若上一批还在跑，等它完成后再触发新一轮
        if self._catalog_save_in_flight:
            try:
                self._catalog_save_timer.start()
            except RuntimeError:
                pass
            return

        # 快照：仅拷贝值，原 pending 保留，worker 返回后按结果精细清理
        # 跳过占位 id（负数）——真实 id 还没到，此时 upsert 会因 FK 失败
        snapshot = {
            int(tpl_item_id): (tree_item, ec_item_id, dict(fields))
            for tpl_item_id, (tree_item, ec_item_id, fields) in self._pending_catalog_saves.items()
            if fields and int(tpl_item_id) > 0
        }
        if not snapshot:
            # 如果还有占位项在排队，稍后再试
            if self._placeholders_in_flight:
                try:
                    self._catalog_save_timer.start(500)
                except RuntimeError:
                    pass
            return

        try:
            self._catalog_save_timer.stop()
        except RuntimeError:
            pass
        entry_id = int(self.current_entry_id)

        # 仅传可序列化数据给 Worker，不传 QTreeWidgetItem（跨线程不安全）
        # 同时捕获每个 tree_item 的 base_updated_at（乐观锁基线），worker 用它检测并发冲突
        def _read_base_ts(ti):
            if ti is None:
                return None
            try:
                return ti.data(1, Qt.UserRole + 20)
            except Exception:
                return None

        save_tasks = [
            (tpl_id, int(ec_id) if ec_id else None, dict(fields), _read_base_ts(tree_item))
            for tpl_id, (tree_item, ec_id, fields) in snapshot.items()
        ]
        tree_map = {tpl_id: tree_item for tpl_id, (tree_item, _, _) in snapshot.items()}
        # in-flight 快照（纯数据），供 worker 崩溃时回退
        self._catalog_save_in_flight_snapshot = {
            tpl_id: dict(fields) for tpl_id, (_, _, fields) in snapshot.items()
        }
        self._catalog_save_in_flight = True

        def do_save():
            results = []  # 每项: (tpl_item_id, status, payload, saved_fields, new_ts)
            for tpl_item_id, ec_item_id, fields, base_ts in save_tasks:
                try:
                    new_ec_id, new_ts = upsert_entry_catalog_item_fields(
                        entry_id=entry_id,
                        template_item_id=tpl_item_id,
                        entry_catalog_item_id=ec_item_id,
                        fields=fields,
                        base_updated_at=base_ts,
                    )
                    results.append((tpl_item_id, "ok", new_ec_id, fields, new_ts))
                except Exception as e:
                    print(f"[catalog-entry] async save failed tpl={tpl_item_id}: {e}")
                    results.append((tpl_item_id, "err", str(e), fields, None))
            return results

        worker = Worker(do_save)

        def on_done(results):
            # 对话框已关闭：in-flight 写已入 DB 成功（同步 flush 前已等它完成），
            # 但我们 **绝不能** 去触碰 C++ 对象（QTreeWidgetItem / QTimer）。
            # WAL 已在 _stage_pending 时写过，重放时会从 WAL 再补——数据不会丢。
            if getattr(self, "_is_closing", False):
                return
            had_failure = False
            for tpl_item_id, status, payload, saved_fields, new_ts in (results or []):
                if status == "ok":
                    new_ec_id = payload
                    # 更新 UI 节点的 ec_id 和乐观锁基线（首次保存会新建 ec_item）
                    ti = tree_map.get(tpl_item_id)
                    if ti:
                        try:
                            ti.setData(1, Qt.UserRole, new_ec_id)
                            if new_ts:
                                ti.setData(1, Qt.UserRole + 20, new_ts)
                        except (RuntimeError, Exception):
                            # RuntimeError: C++ QTreeWidgetItem 已销毁（dialog 关闭）
                            pass
                    # 从 pending 逐字段移除：仅移除"在飞行期间没被再次修改"的字段
                    confirmed_fields = []
                    pending_entry = self._pending_catalog_saves.get(tpl_item_id)
                    if pending_entry:
                        _, _, pending_fields = pending_entry
                        for f, saved_v in saved_fields.items():
                            if pending_fields.get(f) == saved_v:
                                pending_fields.pop(f, None)
                                confirmed_fields.append(f)
                        # 补全 ec_id，便于后续 upsert 直接定位
                        if pending_entry[1] is None:
                            pending_entry[1] = new_ec_id
                        if not pending_fields:
                            self._pending_catalog_saves.pop(tpl_item_id, None)
                    else:
                        # pending 里没有（已被更高版本的 flush 清空了），保守认为全部已落盘
                        confirmed_fields = list(saved_fields.keys())
                    # 从 WAL 中移除已成功落盘的字段
                    if confirmed_fields:
                        self._wal_confirm(tpl_item_id, confirmed_fields)
                else:
                    had_failure = True
                    # 失败：把字段回退合并到 pending（最新编辑优先，不覆盖新值）
                    pending_entry = self._pending_catalog_saves.get(tpl_item_id)
                    if pending_entry is None:
                        ti = tree_map.get(tpl_item_id)
                        self._pending_catalog_saves[tpl_item_id] = [ti, None, dict(saved_fields)]
                    else:
                        for f, v in saved_fields.items():
                            pending_entry[2].setdefault(f, v)

            self._catalog_save_in_flight_snapshot = {}
            self._catalog_save_in_flight = False

            # 还有剩余 pending（新编辑或失败项）→ 再次触发 flush
            if self._pending_catalog_saves:
                # 失败时用稍长间隔避免 DB 风暴；正常情况沿用 350ms
                try:
                    self._catalog_save_timer.start(1500 if had_failure else 350)
                except RuntimeError:
                    pass

        def on_error(err):
            """Worker 本体异常兜底（理论上 do_save 已吞异常，这里防御性回退）。"""
            if getattr(self, "_is_closing", False):
                # 关闭中：失败值已经在 WAL（stage 时写入），下次启动重放即可；不触 C++ 对象
                self._catalog_save_in_flight_snapshot = {}
                self._catalog_save_in_flight = False
                return
            print(f"[catalog-entry] async worker crashed: {err}")
            for tpl_item_id, fields in (self._catalog_save_in_flight_snapshot or {}).items():
                pending_entry = self._pending_catalog_saves.get(tpl_item_id)
                if pending_entry is None:
                    ti = tree_map.get(tpl_item_id)
                    self._pending_catalog_saves[tpl_item_id] = [ti, None, dict(fields)]
                else:
                    for f, v in fields.items():
                        pending_entry[2].setdefault(f, v)
            self._catalog_save_in_flight_snapshot = {}
            self._catalog_save_in_flight = False
            try:
                self._catalog_save_timer.start(1500)
            except RuntimeError:
                pass

        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        self._thread_pool.start(worker)

    @staticmethod
    def _is_ascii_digits(value: str) -> bool:
        """只允许 ASCII 数字。.isdigit() 会把全角 '１２３' / 孟加拉 '১২৩' 等也识别为数字，
        但写进 DB 的 Integer 列时 MySQL 不一定接受，直接在 UI 层禁掉。"""
        return bool(value) and value.isascii() and value.isdigit()

    def _validate_year(self, value: str) -> tuple:
        """校验年份输入：必须4位数字，范围1900-当前年度。"""
        if not value:
            return True, ""
        if not self._is_ascii_digits(value):
            return False, "年份必须为数字"
        if len(value) != 4:
            return False, "年份必须为4位数字"
        year_int = int(value)
        current_year = datetime.now().year
        if year_int < 1900:
            return False, "年份不能小于 1900"
        if year_int > current_year:
            return False, f"年份不能大于当前年度 {current_year}"
        return True, ""

    def _validate_month(self, value: str) -> tuple:
        """校验月份输入：最多2位数字，不能大于12。"""
        if not value:
            return True, ""
        if not self._is_ascii_digits(value):
            return False, "月份必须为半角数字（0-9）"
        if len(value) > 2:
            return False, "月份不能超过2位数字"
        month_int = int(value)
        if month_int < 1 or month_int > 12:
            return False, "月份必须在1-12之间"
        return True, ""

    def _validate_day(self, value: str) -> tuple:
        """校验日期输入：最多2位数字，不能大于31。"""
        if not value:
            return True, ""
        if not self._is_ascii_digits(value):
            return False, "日期必须为半角数字（0-9）"
        if len(value) > 2:
            return False, "日期不能超过2位数字"
        day_int = int(value)
        if day_int < 1 or day_int > 31:
            return False, "日期必须在1-31之间"
        return True, ""

    def _validate_pages(self, value: str) -> tuple:
        """校验页数输入：必须是非负 ASCII 整数（空值允许）。
        DB 字段类型是 Integer，写入汉字/字母/全角数字会触发 DataError，
        所以在 UI 层直接拦截，杠绝脏数据进入 WAL 和服务器库。"""
        if not value:
            return True, ""
        if not self._is_ascii_digits(value):
            return False, "页数必须为半角数字（0-9）"
        try:
            n = int(value)
        except ValueError:
            return False, "页数必须为数字"
        if n < 0:
            return False, "页数不能为负数"
        if n > 99999:
            return False, "页数不能超过 99999"
        return True, ""

    def _is_date_complete(self, item) -> bool:
        """检查节点的年月日是否都已填写。"""
        year_str = item.text(2).strip()
        month_str = item.text(3).strip()
        day_str = item.text(4).strip()
        return bool(year_str and month_str and day_str)

    def _check_date_ascending(self, item):
        """
        检查年月日是否满足升序要求（同一父节点下，序号越大日期越大）。
        返回 (True, None) 表示校验通过或无需校验。
        返回 (False, column) 表示校验失败，column 是需要编辑的列号。
        只有当前行和前一行的年月日都完整时才进行校验。
        """
        parent_item = item.parent()
        if parent_item is None:
            parent_item = self.catalog_tree.invisibleRootItem()
        # 获取当前节点在同级中的索引
        current_index = parent_item.indexOfChild(item)
        if current_index <= 0:
            # 第一个节点无需校验
            return True, None
        # 获取前一个兄弟节点
        prev_item = parent_item.child(current_index - 1)
        if prev_item is None:
            return True, None

        # 只有两行的年月日都完整时才进行比较
        if not self._is_date_complete(prev_item):
            return True, None
        if not self._is_date_complete(item):
            return True, None

        # 获取当前节点和前一节点的年月日
        def get_date_tuple(tree_item):
            year_str = tree_item.text(2).strip()
            month_str = tree_item.text(3).strip()
            day_str = tree_item.text(4).strip()
            year = int(year_str) if year_str.isdigit() else 0
            month = int(month_str) if month_str.isdigit() else 0
            day = int(day_str) if day_str.isdigit() else 0
            return (year, month, day)

        curr_date = get_date_tuple(item)
        prev_date = get_date_tuple(prev_item)

        # 比较日期元组（年, 月, 日）
        if curr_date < prev_date:
            # 日期不满足升序要求，弹出对话框（已禁用）
            # def format_date(d):
            #     return f"{d[0]}年{d[1]}月{d[2]}日"
            # msg = f"日期输入不符合升序要求\n\n前一序号日期：{format_date(prev_date)}\n当前输入日期：{format_date(curr_date)}"
            # result = StyledMessageBox.question(
            #     self, "日期校验", msg,
            #     StyledMessageBox.Yes | StyledMessageBox.No,
            #     StyledMessageBox.No,
            #     self.current_theme,
            #     yes_text="忽略",
            #     no_text="修改"
            # )
            # if result == StyledMessageBox.Yes:
            #     return True, None  # 忽略
            return True, None  # 静默忽略升序校验
            # if curr_date[0] < prev_date[0]:
            #     return False, 2
            # elif curr_date[0] == prev_date[0] and curr_date[1] < prev_date[1]:
            #     return False, 3
            # else:
            #     return False, 4
        return True, None

    # === 目录树键盘事件处理 ===
    def eventFilter(self, obj, event):
        """
        事件过滤器：监听 catalog_tree 的键盘事件。
        - Tab键：由 CatalogTreeDelegate 处理，在同一行内切换列
        - Enter键：校验当前行日期完整性和升序，新增行
        - 方向键：上下左右移动焦点
        """
        if obj == self.catalog_tree and event.type() == QEvent.KeyPress:
            key = event.key()
            delegate = getattr(self, "_catalog_delegate", None)
            if (
                    delegate is not None
                    and getattr(delegate, "_current_editor", None) is None
                    and self._is_plain_catalog_text_key(event)):
                current = self.catalog_tree.currentItem()
                current_col = self.catalog_tree.currentColumn()
                if current is not None and self._start_catalog_edit_with_initial_key(current, current_col, event):
                    return True

            # 方向键处理
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                current = self.catalog_tree.currentItem()
                if not current:
                    return False  # 没有选中项，不处理
                
                current_col = self.catalog_tree.currentColumn()
                if current_col < 0:
                    current_col = 0
                
                if key == Qt.Key_Left:
                    # 左键：切换到左边的列
                    new_col = current_col - 1
                    if new_col >= 0:
                        self.catalog_tree.setCurrentItem(current, new_col)
                        self._schedule_catalog_edit(current, new_col)
                    return True
                    
                elif key == Qt.Key_Right:
                    # 右键：切换到右边的列
                    col_count = self.catalog_tree.columnCount()
                    new_col = current_col + 1
                    if new_col < col_count:
                        self.catalog_tree.setCurrentItem(current, new_col)
                        self._schedule_catalog_edit(current, new_col)
                    return True
                    
                elif key == Qt.Key_Up:
                    # 上键：切换到上一行的同一列
                    parent_item = current.parent()
                    if parent_item is None:
                        parent_item = self.catalog_tree.invisibleRootItem()
                    current_index = parent_item.indexOfChild(current)
                    if current_index > 0:
                        prev_item = parent_item.child(current_index - 1)
                        if prev_item:
                            self.catalog_tree.setCurrentItem(prev_item, current_col)
                            self._schedule_catalog_edit(prev_item, current_col)
                    return True
                    
                elif key == Qt.Key_Down:
                    # 下键：切换到下一行的同一列
                    parent_item = current.parent()
                    if parent_item is None:
                        parent_item = self.catalog_tree.invisibleRootItem()
                    current_index = parent_item.indexOfChild(current)
                    sibling_count = parent_item.childCount()
                    if current_index < sibling_count - 1:
                        next_item = parent_item.child(current_index + 1)
                        if next_item:
                            self.catalog_tree.setCurrentItem(next_item, current_col)
                            self._schedule_catalog_edit(next_item, current_col)
                    return True

            # Enter 键：校验并换行
            if key in (Qt.Key_Return, Qt.Key_Enter):
                # 优先处理自动补全：弹窗可见时 Enter 只做"确认候选"，绝不换列。
                # 防止焦点竞速导致 Enter 没进 delegate eventFilter，而直接落到树层
                # 让列 1→列 2 的 fallback 把用户选中的候选词吃掉。
                if self._is_autocomplete_popup_visible():
                    self._on_autocomplete_confirm()
                    return True  # 拦截 Enter
                self._commit_active_catalog_editor()
                # 先让树控件获得焦点，关闭当前编辑器，确保数据被保存到 item 中
                self.catalog_tree.setFocus()

                current = self.catalog_tree.currentItem()
                if not current:
                    return True  # 拦截 Enter，避免传递到对话框按钮

                # 兜底：editor 失焦时 delegate 的 Enter 处理不会触发，在 tree 层
                # 也走一次同行列切换 (0→1→2→3→4→5)，与 delegate 保持一致，
                # 避免 "录完题名按回车直接跳到下一行" 的问题。
                _ENTER_NEXT_COL = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
                current_col = self.catalog_tree.currentColumn()
                if current_col in _ENTER_NEXT_COL:
                    next_col = _ENTER_NEXT_COL[current_col]
                    self.catalog_tree.setCurrentItem(current, next_col)
                    self._schedule_catalog_edit(current, next_col)
                    return True  # 拦截 Enter

                # 检查是否是模板原有条目（有预设名称的），模板原有条目不检查年月日
                tpl_name = current.data(1, Qt.UserRole + 10) or ""
                is_template_item = bool(tpl_name.strip())
                
                # 检查是否输入了目录名称
                name_str = current.text(1).strip()
                
                # 只要输入了目录名称，就必须填写年月日（模板原有条目除外）
                if name_str and not is_template_item:
                    # 检查当前行日期是否完整
                    year_str = current.text(2).strip()
                    month_str = current.text(3).strip()
                    day_str = current.text(4).strip()
                    has_any = bool(year_str or month_str or day_str)
                    is_complete = bool(year_str and month_str and day_str)

                    # 如果有输入但不完整，或者完全没输入，提示并阻止换行
                    # if not is_complete:
                    #     if not self._date_warning_suppressed:
                    #         missing = []
                    #         if not year_str: missing.append("年")
                    #         if not month_str: missing.append("月")
                    #         if not day_str: missing.append("日")
                    #         StyledMessageBox.warning(self, "提示", f"输入目录名称后必须填写年月日\n\n缺少：{'、'.join(missing)}")
                    #         self._date_warning_suppressed = True
                    #         if not year_str:
                    #             self._reenter_edit(current, 2)
                    #         elif not month_str:
                    #             self._reenter_edit(current, 3)
                    #         else:
                    #             self._reenter_edit(current, 4)
                    #         return True  # 拦截 Enter

                    # 如果日期完整，检查升序（这是提示，可以忽略）
                    if is_complete:
                        passed, edit_col = self._check_date_ascending(current)
                        if not passed:
                            # 用户选择修改，定位到对应字段
                            self._reenter_edit(current, edit_col or 2)
                            return True  # 拦截 Enter

                # 获取父节点
                parent_item = current.parent()
                if parent_item is None:
                    parent_item = self.catalog_tree.invisibleRootItem()
                
                # 检查当前行是否是最后一行（同级中的最后一个）
                child_count = parent_item.childCount()
                current_index = parent_item.indexOfChild(current)
                is_last_row = (current_index == child_count - 1)
                
                if is_last_row:
                    # 最后一行，创建新行
                    self._create_tpl_node(parent_item, prev_item=current)
                else:
                    # 不是最后一行，移动到下一行
                    next_item = parent_item.child(current_index + 1)
                    if next_item:
                        # 如果下一行序号为空且非模板固定序号，自动填充
                        next_serial = next_item.text(0).strip()
                        next_tpl_serial = next_item.data(0, Qt.UserRole + 10) or ""
                        if not next_serial and not next_tpl_serial.strip():
                            auto_serial = str(current_index + 2)
                            self._suppress_catalog_changed = True
                            next_item.setText(0, auto_serial)
                            self._suppress_catalog_changed = False
                            self._ensure_entry_record()
                            if self.current_entry_id:
                                tpl_item_id = next_item.data(0, Qt.UserRole)
                                ec_item_id = next_item.data(1, Qt.UserRole)
                                if tpl_item_id:
                                    self._stage_pending(tpl_item_id, next_item, ec_item_id, {"serial": auto_serial})
                        self.catalog_tree.setCurrentItem(next_item, 1)  # 设置到目录名称列
                        # 进入编辑状态，编辑目录名称列（使用默认参数捕获当前 next_item）
                        self._schedule_catalog_edit(next_item, 1)
                
                return True  # 始终拦截 Enter，避免传递到对话框按钮

        if obj == self.catalog_tree.viewport() and event.type() == QEvent.MouseButtonPress:
            try:
                item = self.catalog_tree.itemAt(event.pos())
                if item is not None:
                    column = self.catalog_tree.columnAt(event.pos().x())
                    if column >= 0:
                        if event.button() == Qt.RightButton:
                            if item.isSelected():
                                index = self.catalog_tree.indexFromItem(item, column)
                                if index.isValid():
                                    self.catalog_tree.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)
                            else:
                                self.catalog_tree.clearSelection()
                                self.catalog_tree.setCurrentItem(item, column)
                                item.setSelected(True)
                            self._selection_anchor = item
                            return True
                        modifiers = QApplication.keyboardModifiers()
                        if modifiers & Qt.ShiftModifier:
                            # Shift+click: Excel 风格 — 手动完成同层连续选区，
                            # 然后消费事件，防止 Qt ExtendedSelection 再次覆盖选区
                            self._shift_select_range(item)
                            self.catalog_tree.setCurrentItem(item, column)
                            self._schedule_catalog_edit(item, column)
                            return True
                        elif modifiers & Qt.ControlModifier:
                            # Ctrl+click: 仅预设当前项，不手动切换选区状态；
                            # 交由 Qt ExtendedSelection 原生处理 Ctrl+点击的切换逻辑
                            self.catalog_tree.setCurrentItem(item, column)
                        else:
                            # 普通点击：锚点更新为当前项，余下由 Qt 处理
                            self.catalog_tree.setCurrentItem(item, column)
                            self._selection_anchor = item
                        self._schedule_catalog_edit(item, column)
            except RuntimeError:
                pass

        if obj == self.catalog_tree.viewport() and event.type() in (QEvent.Resize, QEvent.Paint):
            try:
                if self._catalog_name_editor is not None and self._catalog_name_editor.isVisible():
                    item = self._catalog_name_editor_item
                    if item is not None:
                        x, y, w, h = self._catalog_cell_rect(item, 1)
                        self._catalog_name_editor.setGeometry(x + 1, y + 1, max(1, w - 2), max(1, h - 2))
            except RuntimeError:
                pass

        if obj == self._catalog_name_editor and event.type() == QEvent.KeyPress:
            key = event.key()
            if self._is_autocomplete_popup_visible():
                if key == Qt.Key_Up:
                    self._on_autocomplete_move(-1)
                    return True
                if key == Qt.Key_Down:
                    self._on_autocomplete_move(1)
                    return True
                if key == Qt.Key_Escape:
                    self._on_autocomplete_hide()
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                    self._on_autocomplete_confirm()
                    return True

            item = self._catalog_name_editor_item
            if key == Qt.Key_Tab and item is not None:
                self._sync_catalog_name_editor_to_item()
                self._hide_catalog_name_editor()
                self._on_request_edit_column(item, 2)
                return True
            if key == Qt.Key_Backtab and item is not None:
                self._sync_catalog_name_editor_to_item()
                self._hide_catalog_name_editor()
                self._on_request_edit_column(item, 0)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter) and item is not None:
                self._sync_catalog_name_editor_to_item()
                self._hide_catalog_name_editor()
                self._on_request_edit_column(item, 2)
                return True

        if obj == self._catalog_name_editor and event.type() == QEvent.FocusOut:
            if not self._is_autocomplete_popup_visible():
                self._hide_catalog_name_editor()
            return False

        return super().eventFilter(obj, event)

    def _flush_catalog_pending_saves_sync(self):
        """同步落盘 pending 目录保存（对话框关闭/确认时调用）。

        步骤：
        1. 停掉防抖定时器
        2. 等待飞行中的异步 worker 完成（最多 5 秒），它的 on_done 会把成功字段从 pending 中移除
        3. 同步重试所有剩余 pending 项；失败项保留在 pending（理论上调用侧会再次重试或提示）
        """
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QThread, QEventLoop
        self._catalog_save_timer.stop()

        # 1) 先等占位模板项后台创建完成（最多 3 秒），否则这些行无法 upsert
        waited_ms = 0
        while self._placeholders_in_flight and waited_ms < 3000:
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents, 50)
            QThread.msleep(20)
            waited_ms += 20

        # 2) 等待飞行中的 worker 完成，on_done 会回到 UI 线程并消化成功字段
        # 排除用户输入事件：关闭过程中不让用户再次点击/编辑
        waited_ms = 0
        while self._catalog_save_in_flight and waited_ms < 5000:
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents, 50)
            QThread.msleep(20)
            waited_ms += 20

        if not self._pending_catalog_saves or not self.current_entry_id:
            return
        for tpl_item_id, (tree_item, _ec_item_id, fields) in list(self._pending_catalog_saves.items()):
            if fields and int(tpl_item_id) < 0 and int(tpl_item_id) not in self._placeholders_in_flight:
                self._materialize_placeholder_now(int(tpl_item_id), tree_item)
        # 只处理真实 id（>0）；占位 id（负数）此时仍未拿到真实 id，
        # 必须继续留在 pending，等后台真实 id 回来后迁移到 WAL
        pending = {
            tpl_item_id: (tree_item, ec_item_id, dict(fields))
            for tpl_item_id, (tree_item, ec_item_id, fields) in self._pending_catalog_saves.items()
            if fields and int(tpl_item_id) > 0
        }
        if not pending:
            self._pending_catalog_saves = {
                tpl_item_id: value
                for tpl_item_id, value in self._pending_catalog_saves.items()
                if int(tpl_item_id) < 0
            }
            return

        entry_id = int(self.current_entry_id)
        failed = {}
        for tpl_id, (tree_item, ec_id, fields) in pending.items():
            # 捕获当前 tree item 的乐观锁基线
            base_ts = None
            if tree_item:
                try:
                    base_ts = tree_item.data(1, Qt.UserRole + 20)
                except Exception:
                    base_ts = None
            try:
                new_ec_id, new_ts = upsert_entry_catalog_item_fields(
                    entry_id=entry_id,
                    template_item_id=int(tpl_id),
                    entry_catalog_item_id=int(ec_id) if ec_id else None,
                    fields=fields,
                    base_updated_at=base_ts,
                )
                if tree_item:
                    try:
                        if not ec_id:
                            tree_item.setData(1, Qt.UserRole, new_ec_id)
                        if new_ts:
                            tree_item.setData(1, Qt.UserRole + 20, new_ts)
                    except Exception:
                        pass
                # 成功：从 WAL 中移除对应字段
                self._wal_confirm(int(tpl_id), list(fields.keys()))
            except Exception as e:
                print(f"[catalog-entry] sync-flush failed tpl_id={tpl_id}: {e}")
                failed[int(tpl_id)] = [tree_item, ec_id, dict(fields)]
                # 失败：字段仍在 WAL 里（stage 时写入且未被 confirm），下次启动会重放

        placeholder_pending = {
            tpl_item_id: value
            for tpl_item_id, value in self._pending_catalog_saves.items()
            if int(tpl_item_id) < 0
        }
        placeholder_pending.update(failed)
        self._pending_catalog_saves = placeholder_pending

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    # === 简单拖动支持（无边框窗口） ===
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
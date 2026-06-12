# -*- coding: utf-8 -*-
"""
回归测试：录入对话框的"防卡顿 + 防闪退 + 不丢数据"三大不变式。

对应用户反馈：
    - "录入过程中容易发生卡顿，并且闪退"
    - "要保证之前丢书数据的问题不能出现"

关键不变式（本测试用源码级静态检查验证；Qt 运行时测试在 `test_catalog_perf_benchmark.py`）：

1. 【防卡顿】键入热路径 `_on_catalog_item_changed` 不会同步调用 MySQL 查询
   - `_update_total_pages_label(refresh_image_count=False)` 走防抖 + 纯内存路径
   - `count_entry_total_images` 仅在异步 Worker 里被调用

2. 【防闪退】所有 Worker 回调都带 `_is_closing` 短路
   - `_flush_catalog_pending_saves.on_done` / `on_error` 两个闭包
   - `_async_create_template_item.on_created` 闭包
   - `_load_images_for_item._on_loaded` 闭包
   - `_schedule_image_count_refresh._on_loaded` 闭包

3. 【不丢数据】
   - `_stage_pending` 仍然无条件写 WAL（关闭中也写）
   - `closeEvent` 按「sync flush → 刷 autocomplete → 设 _is_closing → 停定时器」顺序执行
   - 关闭场景下 placeholder 孤儿不会被盲删（会写回 WAL 让下次重放接手）

运行：
    python tests/test_entry_dialog_no_lag_no_crash.py
"""
from __future__ import annotations

import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIALOG_PATH = os.path.join(
    ROOT, "main_ui", "pages", "inventory_ui", "inventory_entry_dialog.py"
)
POPUP_PATH = os.path.join(
    ROOT, "main_ui", "pages", "inventory_ui", "autocomplete_popup.py"
)
MODEL_PATH = os.path.join(ROOT, "common", "db", "models.py")
CATALOG_EXPORT_PATH = os.path.join(
    ROOT, "main_ui", "pages", "inventory_ui", "services", "catalog_export_service.py"
)
PERSON_EXPORT_PATH = os.path.join(
    ROOT, "main_ui", "pages", "inventory_ui", "services", "person_export_service.py"
)
AUTOCOMPLETE_MANAGER_PATH = os.path.join(
    ROOT, "main_ui", "pages", "inventory_ui", "autocomplete_manager.py"
)


def _read_dialog_source() -> str:
    with open(DIALOG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_popup_source() -> str:
    with open(POPUP_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _strip_docstrings(src: str) -> str:
    """去掉方法首个三引号字符串（docstring），避免误匹配提到函数名的说明文字。"""
    # 同时支持 """...""" 和 '''...'''
    for quote in ('"""', "'''"):
        # 非贪婪匹配最先出现的一个；我们循环直到剩下的 src 没有三引号包裹的大段文本
        pattern = re.compile(rf"{quote}.*?{quote}", re.DOTALL)
        src = pattern.sub("", src)
    # 同时去掉行注释（# 开头的部分）——避免注释里提到 count_entry_total_images 导致误判
    src = re.sub(r"#[^\n]*", "", src)
    return src


def _slice_method(source: str, name: str) -> str:
    """截取某个方法的源码（从 `def name(` 到下一个顶层/二层 def/class 为止），并剥离文档字符串。"""
    m = re.search(rf"\n    def {re.escape(name)}\s*\(", source)
    if not m:
        raise AssertionError(f"找不到方法：{name}")
    start = m.start()
    # 找下一个同级 def 或类边界
    tail = source[m.end():]
    nxt = re.search(r"\n    def \w+\s*\(|\nclass \w+", tail)
    end = m.end() + (nxt.start() if nxt else len(tail))
    return _strip_docstrings(source[start:end])


def _slice_nested(source: str, outer: str, inner: str) -> str:
    """截取嵌套在 outer 方法里的 inner 闭包函数源码。"""
    outer_src = _slice_method(source, outer)
    m = re.search(rf"\n        def {re.escape(inner)}\s*\(", outer_src)
    if not m:
        raise AssertionError(f"在 {outer} 里找不到嵌套函数 {inner}")
    start = m.start()
    tail = outer_src[m.end():]
    nxt = re.search(r"\n        def \w+\s*\(|\n    def \w+\s*\(|\nclass \w+", tail)
    end = m.end() + (nxt.start() if nxt else len(tail))
    return outer_src[start:end]


def _assert(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)
    # 避免 Windows GBK 控制台编码问题（CP936），只用 ASCII 字符
    print(f"  [OK] {msg}")


# ----------------------------------------------------------------------
# 【防卡顿】键入热路径不查 MySQL
# ----------------------------------------------------------------------
def test_hot_path_no_sync_mysql_query():
    src = _read_dialog_source()
    hot_path = _slice_method(src, "_on_catalog_item_changed")
    # 1) 键入列 1 或 5 时必须走 refresh_image_count=False 分支
    _assert(
        "_update_total_pages_label(refresh_image_count=False)" in hot_path,
        "hot path: _on_catalog_item_changed 走 refresh_image_count=False 防抖路径",
    )
    _assert(
        "count_entry_total_images(" not in hot_path,
        "hot path: _on_catalog_item_changed **不得** 直接调 count_entry_total_images",
    )

    # 2) _update_total_pages_label 本体只启定时器，不做 DB IO
    update_method = _slice_method(src, "_update_total_pages_label")
    _assert(
        "count_entry_total_images(" not in update_method,
        "_update_total_pages_label 本体不做同步 count_entry_total_images",
    )
    _assert(
        "_stats_refresh_timer.start" in update_method,
        "_update_total_pages_label 通过 _stats_refresh_timer 防抖",
    )

    # 3) _do_refresh_stats_ui（真正刷 UI 的地方）也不做 DB IO——图片数走异步 worker
    do_refresh = _slice_method(src, "_do_refresh_stats_ui")
    _assert(
        "count_entry_total_images(" not in do_refresh,
        "_do_refresh_stats_ui 不做同步 count_entry_total_images",
    )
    _assert(
        "_schedule_image_count_refresh()" in do_refresh,
        "_do_refresh_stats_ui 按需发起异步图片数刷新（_schedule_image_count_refresh）",
    )

    # 4) 异步图片数 worker 内部在 Worker._do_count 里调 count_entry_total_images
    sched = _slice_method(src, "_schedule_image_count_refresh")
    _assert(
        "count_entry_total_images(" in sched,
        "_schedule_image_count_refresh 把 count_entry_total_images 放到 Worker 里",
    )
    _assert(
        "Worker(_do_count)" in sched and "self._thread_pool.start(worker)" in sched,
        "_schedule_image_count_refresh 使用 QThreadPool 后台线程执行",
    )

    enter_new_row = _slice_method(src, "_on_request_enter_new_row")
    _assert(
        "processEvents(" not in enter_new_row,
        "Enter 换行热路径不再 processEvents，避免事件重入导致卡顿/闪退",
    )

    tree_event_filter = _slice_method(src, "eventFilter")
    _assert(
        "processEvents(" not in tree_event_filter,
        "catalog_tree 键盘事件热路径不再 processEvents",
    )

    schedule_edit = _slice_method(src, "_schedule_catalog_edit")
    _assert(
        'getattr(self, "_is_closing", False)' in schedule_edit and "tree.editItem(i, c)" in schedule_edit,
        "延迟进入编辑统一走 _schedule_catalog_edit，并带关闭/对象有效性检查",
    )
    _assert(
        "tree.currentItem() is not i or tree.currentColumn() != c" in schedule_edit,
        "延迟 editItem 执行前确认当前格未变化，避免旧回调打断 IME 首字母 composition",
    )
    _assert(
        "active_editor is not None and active_item is i and active_col == c" in schedule_edit,
        "同一格已有 editor 时不重复 editItem，避免 setEditorData 重入吞掉首字母",
    )
    _assert(
        "if int(delay_ms or 0) <= 0:" in schedule_edit and "_do_edit()" in schedule_edit,
        "0ms 切列立即创建 editor，避免用户首键先落到 QTreeWidget 被消费",
    )
    _assert(
        "setEditTriggers(QAbstractItemView.NoEditTriggers)" in src,
        "禁用 QTreeWidget 内置字母键启动编辑，避免快速输入时前几个拼音字母被树控件消费",
    )
    _assert(
        "itemClicked.connect(self._on_catalog_item_clicked)" in src,
        "点击目录格时由应用主动创建 editor，而不是依赖 Qt 内置 EditTrigger",
    )
    _assert(
        "self._catalog_name_editor = QLineEdit(self.catalog_tree.viewport())" in src
        and "_show_catalog_name_editor" in src,
        "目录名称列使用常驻 QLineEdit 覆盖编辑，绕开 QTreeWidget/delegate 临时 editor 的 IME 时序问题",
    )
    _assert(
        "itemPressed.connect(self._on_catalog_item_pressed)" in src
        and "self.catalog_tree.viewport().installEventFilter(self)" in src,
        "鼠标按下阶段就主动创建目录名称 editor，避免点完快速输入被树控件吞字",
    )
    _assert(
        "_sync_catalog_name_editor_to_item" in src
        and "_stage_pending(tpl_item_id, item, ec_item_id, fields)" in src,
        "常驻目录名称 editor 仍通过 pending/WAL 保存，避免修吞字时破坏数据安全",
    )
    _assert(
        "_is_plain_catalog_text_key(event)" in src
        and "_start_catalog_edit_with_initial_key(current, current_col, event)" in src,
        "无活动 editor 时普通首键由 tree 转发给新 editor，避免首字母被启动编辑吞掉",
    )
    initial_key = _slice_method(src, "_start_catalog_edit_with_initial_key")
    _assert(
        "QApplication.postEvent(" in initial_key and "QKeyEvent(QEvent.KeyPress" in initial_key,
        "首键转发使用 QKeyEvent 投递到新 editor",
    )
    _assert(
        "if int(column) == 1:" in initial_key
        and "post_initial_key_to_overlay" in initial_key
        and "self._show_catalog_name_editor(item)" in initial_key,
        "目录名称列首键启动也必须走常驻 overlay editor，避免回退到 delegate 临时 editor 吞字",
    )
    _assert(
        initial_key.index("if int(column) == 1:") < initial_key.index("self.catalog_tree.editItem(item, column)"),
        "目录名称列首键路径必须在调用 catalog_tree.editItem 前返回",
    )
    edit_new_item = _slice_method(src, "_edit_new_item")
    _assert(
        "if int(column) == 1:" in edit_new_item
        and "self._show_catalog_name_editor(item)" in edit_new_item,
        "新增目录节点进入目录名称列编辑时也必须走常驻 overlay editor",
    )
    _assert(
        edit_new_item.index("if int(column) == 1:") < edit_new_item.index("self.catalog_tree.editItem(item, column)"),
        "新增目录节点名称列必须在调用 catalog_tree.editItem 前返回",
    )


# ----------------------------------------------------------------------
# 【防闪退】所有 Worker 回调都带 _is_closing 短路
# ----------------------------------------------------------------------
def test_worker_callbacks_guarded_against_destroyed_dialog():
    src = _read_dialog_source()

    # 1) __init__ 设置 _is_closing = False
    init_src = _slice_method(src, "__init__") if False else src  # __init__ 是 QDialog 的，内嵌在 initUI 里定义了
    # 本文件 __init__ 里只是 self.initUI()；状态变量在 initUI 里建
    _assert(
        "self._is_closing = False" in src,
        "初始化阶段 self._is_closing 默认 False",
    )

    # 2) closeEvent / accept 按顺序调用 sync flush → 设置 _is_closing=True → 停定时器
    close_event = _slice_method(src, "closeEvent")
    _assert(
        "_flush_catalog_pending_saves_sync" in close_event,
        "closeEvent 先做 sync flush 保数据落盘",
    )
    _assert(
        "self._is_closing = True" in close_event,
        "closeEvent 标记 _is_closing=True 阻断晚到回调",
    )
    _assert(
        "_stop_ui_timers_safely" in close_event,
        "closeEvent 统一停 UI 定时器",
    )
    # sync flush 必须在 _is_closing=True 之前（否则 flush 内部 processEvents
    # 走到 on_done 会被标志挡掉，pending 就永远写不进 DB → 丢数据）
    order_ok = close_event.index("_flush_catalog_pending_saves_sync") < close_event.index(
        "self._is_closing = True"
    )
    _assert(order_ok, "closeEvent 顺序正确：sync flush 早于 _is_closing=True")

    accept = _slice_method(src, "accept")
    _assert(
        "self._is_closing = True" in accept and "_flush_catalog_pending_saves_sync" in accept,
        "accept 也按「先 flush 再置 _is_closing」顺序走",
    )
    order_ok2 = accept.index("_flush_catalog_pending_saves_sync") < accept.index(
        "self._is_closing = True"
    )
    _assert(order_ok2, "accept 顺序正确：sync flush 早于 _is_closing=True")
    _assert(
        "_has_unmaterialized_placeholders()" in close_event
        and "event.ignore()" in close_event
        and "_warn_unmaterialized_placeholders()" in close_event,
        "closeEvent 若仍有未物化新增目录行则阻止关闭，避免 DB 异常时丢行",
    )
    _assert(
        "_has_unmaterialized_placeholders()" in accept
        and "_warn_unmaterialized_placeholders()" in accept,
        "accept 若仍有未物化新增目录行则阻止保存关闭，避免 DB 异常时丢行",
    )
    _assert(
        accept.rindex("_has_unmaterialized_placeholders()") < accept.index("self._is_closing = True"),
        "accept 兜底占位检查必须在 _is_closing=True 前执行",
    )

    # 3) 所有 worker 回调闭包开头都有 _is_closing 短路
    for outer, inner in [
        ("_flush_catalog_pending_saves", "on_done"),
        ("_flush_catalog_pending_saves", "on_error"),
        ("_async_create_template_item", "on_created"),
        ("_load_images_for_item", "_on_loaded"),
        ("_schedule_image_count_refresh", "_on_loaded"),
        ("_schedule_image_count_refresh", "_on_error"),
    ]:
        cb = _slice_nested(src, outer, inner)
        _assert(
            'getattr(self, "_is_closing", False)' in cb or "self._is_closing" in cb,
            f"{outer}.{inner} 有 _is_closing 短路",
        )

    image_related = [
        ("_render_effective_preview", "on_done"),
        ("_on_trim_border", "on_done"),
        ("_on_trim_border_mm", "on_done"),
        ("_on_image_selected", "on_done"),
    ]
    for outer, inner in image_related:
        cb = _slice_nested(src, outer, inner)
        _assert(
            'getattr(self, "_is_closing", False)' in cb,
            f"{outer}.{inner} 晚到图片回调有 _is_closing 短路",
        )

    # 4) 所有定时器 start 都在 try/except RuntimeError 里
    #    (除了 initUI 里初始化 + timeout.connect 阶段，其他后继调用都要容错)
    # 粗略方法：检查 _stage_pending 和 _flush_catalog_pending_saves 里的 start 调用
    stage = _slice_method(src, "_stage_pending")
    _assert(
        "except RuntimeError" in stage or 'getattr(self, "_is_closing", False)' in stage,
        "_stage_pending 对 QTimer.start 做了 RuntimeError 容错 / 关闭短路",
    )


# ----------------------------------------------------------------------
# 【不丢数据】WAL 无条件写入；关闭时 placeholder 会迁移到真实 id 的 WAL
# ----------------------------------------------------------------------
def test_no_data_loss_on_close():
    src = _read_dialog_source()

    # 1) _stage_pending 无条件写 WAL（不受 _is_closing 控制）
    stage = _slice_method(src, "_stage_pending")
    # WAL 写入必须出现在 "if getattr(self, \"_is_closing\", False)" 之前
    wal_line = "self._wal_stage("
    closing_line = 'getattr(self, "_is_closing", False)'
    _assert(wal_line in stage, "_stage_pending 仍然调用 _wal_stage（本地持久化）")
    wal_idx = stage.index(wal_line)
    closing_idx = stage.index(closing_line) if closing_line in stage else len(stage)
    _assert(
        wal_idx < closing_idx,
        "_stage_pending 中 WAL 写入在 _is_closing 判断之前（关闭时仍保障落盘）",
    )

    # 2) _async_create_template_item 的 on_created 在关闭场景下 **不做** 孤儿盲删，
    #    而是把字段以真实 tpl_id 写回 WAL
    on_created = _slice_nested(src, "_async_create_template_item", "on_created")
    _assert(
        "wal.write_fields" in on_created,
        "关闭时 placeholder 会把字段以真实 tpl_id 迁写入 WAL（防丢）",
    )
    # 此分支必须出现在真正的 detach/orphan-cleanup 之前
    closing_branch = on_created.index(
        'if getattr(self, "_is_closing", False):'
    )
    orphan_branch = on_created.index("delete_entry_catalog_rows_only")
    _assert(
        closing_branch < orphan_branch,
        "关闭分支优先于孤儿清理分支，避免盲删刚录入的 EC 行",
    )
    on_error = _slice_nested(src, "_async_create_template_item", "on_error")
    _assert(
        "QTimer.singleShot(1500, retry_create)" in on_error
        and "placeholder_id not in self._pending_catalog_saves" in on_error,
        "模板项后台创建失败时保留占位 pending 并重试，避免临时 DB 异常丢新增目录行",
    )
    create_tpl = _slice_method(src, "_async_create_template_item")
    _assert(
        "int(parent_id) < 0" in create_tpl
        and "retry_after_parent_materialized" in create_tpl
        and "parent_id=parent_real_id" in create_tpl,
        "子目录父节点仍是占位 id 时必须等待父节点真实 id，避免负 parent_id 写库失败",
    )

    # 3) sync flush 本身仍然遍历 pending 并调 upsert_entry_catalog_item_fields
    sync_flush = _slice_method(src, "_flush_catalog_pending_saves_sync")
    _assert(
        "upsert_entry_catalog_item_fields(" in sync_flush,
        "sync flush 确实把 pending 字段逐条落盘到服务器 DB",
    )
    _assert(
        "_wal_confirm" in sync_flush,
        "sync flush 成功后从 WAL 中移除（对应「成功才 confirm」契约）",
    )
    _assert(
        "if int(tpl_item_id) < 0" in sync_flush
        and "placeholder_pending.update(failed)" in sync_flush
        and "self._pending_catalog_saves.clear()" not in sync_flush,
        "sync flush 等不到真实 tpl_id 时保留占位 pending，避免关闭窗口丢新增目录行",
    )
    _assert(
        "_materialize_placeholder_now" in sync_flush,
        "sync flush 会先尝试同步补建占位模板项，再落盘新增目录行",
    )
    _assert(
        "not in self._placeholders_in_flight" in sync_flush,
        "sync flush 只补建已失败/不在飞行中的占位项，避免和后台创建竞态生成重复模板项",
    )
    materialize = _slice_method(src, "_materialize_placeholder_now")
    _assert(
        "create_catalog_template_item(" in materialize
        and "_migrate_placeholder_id" in materialize,
        "同步补建占位模板项成功后必须迁移 pending/WAL 到真实 tpl_id",
    )


def test_autocomplete_first_selection_commits_to_item():
    src = _read_dialog_source()
    popup_src = _read_popup_source()

    popup_init = _slice_method(popup_src, "__init__")
    _assert(
        "WindowDoesNotAcceptFocus" in popup_init,
        "自动补全弹窗窗口本身不接受焦点，避免首字触发弹窗时打断 editor",
    )
    _assert(
        "self.setFocusPolicy(Qt.NoFocus)" in popup_init,
        "自动补全弹窗设置 NoFocus",
    )
    _assert(
        "self.list_widget.setFocusPolicy(Qt.NoFocus)" in popup_init,
        "自动补全列表设置 NoFocus",
    )

    text_changed = _slice_method(src, "_on_text_changed_for_autocomplete")
    # 关键反向不变式：textChanged 中**不能**直接 setText 回 item。
    # 否则会触发 itemChanged → _on_catalog_item_changed → _ensure_entry_record（同步 DB）
    # 以及 view 层 dataChanged → setEditorData 重入，导致首字被冲掉。
    _assert(
        "self._current_item.setText(1, text)" not in text_changed,
        "首字 textChanged 不再同步 setText 回 item，避免 itemChanged 级联冲掉首字",
    )
    _assert(
        "self.requestAutocomplete.emit" in text_changed,
        "首字 textChanged 仍然触发自动补全弹窗",
    )
    _assert(
        "QTimer.singleShot(50" in text_changed and "_autocomplete_request_seq" in text_changed,
        "自动补全请求延迟到 IME 提交事件结束后，避免候选词上屏时同步弹窗打断 editor",
    )
    _assert(
        "editor.text() != text" in text_changed,
        "延迟自动补全发出前校验 editor 当前文本仍匹配，避免旧请求覆盖 IME 上屏文本",
    )
    create_editor = _slice_method(src, "createEditor")
    _assert(
        "_autocomplete_request_seq += 1" in create_editor,
        "新建 editor 时取消旧自动补全延迟请求，避免跨 editor 触发",
    )

    # IME 反向不变式：setEditorData 不允许再用 QTimer 调 editor.end()。
    # 该 timer 在 0ms 后 fire，会发 cursorPositionChanged，恰好打断用户的拼音 IME
    # composition，导致首字母（如 "zhende" 的 "z"）被吃掉，IME 只看到 "hende"。
    # QLineEdit::setText 本身已把光标放到末尾，无需补这一刀。
    set_editor = _slice_method(src, "setEditorData")
    _assert(
        "editor.end" not in set_editor,
        "setEditorData 不再调 editor.end()，避免拼音 IME 首字母被 cursorPositionChanged 取消",
    )
    _assert(
        "QTimer.singleShot" not in set_editor,
        "setEditorData 不再用 QTimer 异步动光标，避免与 IME composition 起冲突",
    )

    set_model = _slice_method(src, "setModelData")
    _assert(
        "editor.text()" in set_model and "model.setData(index, editor.text(), Qt.EditRole)" in set_model,
        "setModelData 显式用 editor.text() 提交，避免 IME 候选上屏后按旧 model 值回写",
    )

    # 替代不变式：destroyEditor 在销毁前把 editor 当前文本兜底写回 item
    destroy = _slice_method(src, "destroyEditor")
    _assert(
        "editor.text()" in destroy and "self._current_item.setText(self._current_col" in destroy,
        "destroyEditor 销毁兜底：editor.text() 写回 item，保留所有未走 commitData 的输入",
    )
    _assert(
        "self._current_item.text(self._current_col) != text" in destroy,
        "destroyEditor 兜底前先比较，避免无谓刷新",
    )

    request_auto = _slice_method(src, "_on_request_autocomplete")
    _assert(
        "self._autocomplete_item = item" in request_auto,
        "自动补全请求保存当前 tree item，避免 editor 生命周期竞速丢目标",
    )
    _assert(
        "self._autocomplete_column = column" in request_auto,
        "自动补全请求保存当前列，确保只回写目录名称列",
    )

    selected = _slice_method(src, "_on_autocomplete_selected")
    _assert(
        "target_item.setText(1, candidate_text)" in selected,
        "自动补全选择立即写回 QTreeWidgetItem，不只写临时 editor",
    )

    commit = _slice_method(src, "_commit_active_catalog_editor")
    _assert(
        "delegate.commitData.emit(editor)" in commit and "delegate.closeEditor.emit(editor" in commit,
        "tree 层 Enter 兜底会显式 commit/close 当前 editor",
    )
    fallback_start = src.index("if self._is_autocomplete_popup_visible():")
    fallback_end = src.index("# 先让树控件获得焦点", fallback_start)
    fallback = src[fallback_start:fallback_end]
    _assert(
        "_commit_active_catalog_editor()" in fallback,
        "tree 层 Enter 兜底在换列/换行前先提交当前 editor",
    )

    # 关闭路径不变式：closeEvent / accept 在 sync flush 之前先 commit 活动 editor。
    # 这条线确保「编辑中没按 Enter/Tab 就保存/关闭」不会丢字段——因为 editor 文本
    # 必须先进 item → _on_catalog_item_changed → _stage_pending → WAL，sync flush
    # 才能把它落到服务器 DB。
    close_event = _slice_method(src, "closeEvent")
    _assert(
        "_commit_active_catalog_editor()" in close_event,
        "closeEvent 关闭前提交当前 editor，避免编辑中关对话框丢最后一字段",
    )
    _assert(
        close_event.index("_commit_active_catalog_editor()") < close_event.index("_flush_catalog_pending_saves_sync"),
        "closeEvent 顺序：先 commit editor，再 sync flush（否则 pending 里没有这条字段）",
    )

    accept_src = _slice_method(src, "accept")
    _assert(
        "_commit_active_catalog_editor()" in accept_src,
        "accept 保存前提交当前 editor，避免编辑中点保存丢最后一字段",
    )
    _assert(
        accept_src.index("_commit_active_catalog_editor()") < accept_src.index("_flush_catalog_pending_saves_sync"),
        "accept 顺序：先 commit editor，再 sync flush",
    )


def test_fixed_person_custom_fields_use_json_not_schema_columns():
    src = _read_dialog_source()
    models = _read_file(MODEL_PATH)
    catalog_export = _read_file(CATALOG_EXPORT_PATH)
    person_export = _read_file(PERSON_EXPORT_PATH)

    _assert(
        "custom_fields = Column(Text)" in models,
        "entries 仍使用 custom_fields TEXT 存储扩展字段",
    )
    _assert(
        "ethnicity" not in models and "native_place" not in models and "birth_date" not in models,
        "Entry 模型未新增民族/籍贯/出生日期数据库列",
    )

    fixed = src[src.index("FIXED_CUSTOM_FIELD_NAMES"):src.index("def _custom_fields_from_data")]
    _assert(
        '("民族", "籍贯", "出生日期")' in fixed,
        "民族/籍贯/出生日期 被声明为固定 custom_fields 字段",
    )
    options = src[src.index("CUSTOM_FIELD_OPTIONS ="):src.index("def _custom_fields_from_data")]
    _assert(
        '"民族"' not in options and '"籍贯"' not in options and '"出生日期"' not in options,
        "自定义字段下拉不再重复提供民族/籍贯/出生日期",
    )

    init_live = _slice_method(src, "_init_live_person_save")
    _assert(
        "self.le_ethnicity" in init_live and "self.le_native_place" in init_live and "self.le_birth_date" in init_live,
        "固定三字段接入人员信息防抖实时保存",
    )

    load_custom = _slice_method(src, "_load_custom_fields_from_data")
    _assert(
        "fn not in self.FIXED_CUSTOM_FIELD_NAMES" in load_custom,
        "加载旧 custom_fields 时固定三字段不会再显示到自定义字段区",
    )

    serialize = _slice_method(src, "_serialize_custom_fields")
    _assert(
        "le_ethnicity" in serialize and "le_native_place" in serialize and "le_birth_date" in serialize,
        "保存时固定三字段写入 entries.custom_fields JSON",
    )
    _assert(
        "fn not in self.FIXED_CUSTOM_FIELD_NAMES" in serialize,
        "保存时手输重复固定字段会被过滤，避免 JSON 里重复",
    )

    _assert(
        '"民族", "籍贯", "出生日期"' in catalog_export,
        "导出信息及目录 Excel 的基本信息表包含固定三字段",
    )
    _assert(
        '"ethnicity"' in person_export and '"native_place"' in person_export and '"birth_date"' in person_export,
        "人员包 XML 将固定三字段作为独立节点导出",
    )


def test_autocomplete_matching_uses_sorted_cache():
    manager_src = _read_file(AUTOCOMPLETE_MANAGER_PATH)
    _assert(
        "self._global_sorted_cache" in manager_src,
        "自动补全全局候选使用排序缓存，避免每个字符重复排序整套词库",
    )
    match_global = _slice_method(manager_src, "match_candidates_global")
    _assert(
        "self._global_sorted_cache.get(template_name)" in match_global,
        "match_candidates_global 先读取已排序缓存",
    )
    _assert(
        match_global.count("sorted(") <= 1,
        "match_candidates_global 最多在缓存缺失时排序一次",
    )
    warmup = _slice_method(manager_src, "warmup_template_async")
    _assert(
        "self._global_sorted_cache[template_name]" in warmup,
        "词库预热完成时同步构建排序缓存",
    )


def main():
    print("\n=== 回归测试：录入对话框防卡顿 + 防闪退 + 不丢数据 ===\n")
    print("【不变式 1】键入热路径不走同步 MySQL 查询")
    test_hot_path_no_sync_mysql_query()
    print("\n【不变式 2】Worker 回调全部带 _is_closing 短路，防闪退")
    test_worker_callbacks_guarded_against_destroyed_dialog()
    print("\n【不变式 3】关闭路径保数据，WAL 在任何时候都会写")
    test_no_data_loss_on_close()
    print("\n【不变式 4】自动补全/首遍输入会立即提交到目录节点")
    test_autocomplete_first_selection_commits_to_item()
    print("\n【不变式 5】民族/籍贯/出生日期固定展示但仍写 custom_fields")
    test_fixed_person_custom_fields_use_json_not_schema_columns()
    print("\n【不变式 6】自动补全匹配不在每次键入时重复排序整套词库")
    test_autocomplete_matching_uses_sorted_cache()
    print("\n=== 全部通过 ===\n")


if __name__ == "__main__":
    main()

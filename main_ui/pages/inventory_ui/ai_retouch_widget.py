# -*- coding: utf-8 -*-
"""
AI修图界面
左侧：机构树 + 人员列表
右侧：批量修图控制面板（去灰底、亮度、对比度、锐化、一键美化）+ 进度
"""

import os
import mimetypes
from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QPushButton, QLabel, QSplitter, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QToolButton, QCheckBox,
    QProgressBar, QApplication, QGroupBox, QSlider, QSpinBox,
    QGridLayout, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize, QThreadPool, QEvent
from PyQt5.QtGui import QFont, QWheelEvent, QBrush, QColor

from common.config import AppSettings
from common.services.crypto_service import CryptoService
from common.db.session import get_session
from common.db.models import Entry, EntryCatalogItem, EntryItemImage
from main_ui.config_pages import PagesConfig
from .style_inventory import InventoryReceiveStyle
from .repo.inventory_entry_repo import (
    list_entries_by_org_unit_id,
    count_entries_total_images,
)
from .repo.org_repo import list_all_org_units, count_entries_grouped_by_org
from .services.image_edit_service import (
    apply_enhance,
    remove_gray_background,
    adjust_brightness_contrast,
    sharpen_image,
    save_image_like_source,
    _open_pil_image,
)
from .utils.image_loading import resolve_image_path
from .widgets.qt_worker import Worker
from .styled_message_box import StyledMessageBox


ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icons'))


def _retouched_output_path(src_path: str):
    base_dir = os.path.dirname(src_path)
    base_name = os.path.basename(src_path)
    if base_name.lower().endswith(CryptoService.ENCRYPTED_EXT):
        base_name = base_name[:-len(CryptoService.ENCRYPTED_EXT)]
    stem, ext = os.path.splitext(base_name)
    out_name = f"{stem}_retouched{ext}{CryptoService.ENCRYPTED_EXT}"
    return os.path.join(base_dir, out_name), out_name


def _list_all_original_images_for_entry(entry_id: int) -> List[Dict[str, Any]]:
    """列出某人员下所有 original 图片（含 file_path、entry_catalog_item_id 等）。"""
    with get_session() as session:
        catalog_ids = [
            r[0] for r in
            session.query(EntryCatalogItem.id).filter(EntryCatalogItem.entry_id == int(entry_id)).all()
        ]
        if not catalog_ids:
            return []
        rows = (
            session.query(EntryItemImage, EntryCatalogItem.entry_id, EntryCatalogItem.template_item_id)
            .join(EntryCatalogItem, EntryCatalogItem.id == EntryItemImage.entry_catalog_item_id)
            .filter(
                EntryItemImage.entry_catalog_item_id.in_(catalog_ids),
                EntryItemImage.image_type == "original",
            )
            .order_by(EntryItemImage.sort_order, EntryItemImage.id)
            .all()
        )
        return [
            {
                "id": img.id,
                "entry_catalog_item_id": img.entry_catalog_item_id,
                "entry_id": int(entry_id) if entry_id is not None else None,
                "template_item_id": int(template_item_id) if template_item_id is not None else None,
                "file_path": img.file_path or "",
                "file_name": img.file_name or "",
                "sort_order": img.sort_order,
            }
            for img, entry_id, template_item_id in rows
        ]


def _upsert_retouched_for_original(orig_id: int, entry_catalog_item_id, orig_sort_order,
                                     out_path: str, out_name: str, mime_type: str, file_size):
    """写库：同一 original_id + image_type='retouched' 仅保留 1 条。"""
    with get_session() as session:
        rows = (
            session.query(EntryItemImage)
            .filter(
                EntryItemImage.original_id == orig_id,
                EntryItemImage.image_type == "retouched",
            )
            .order_by(EntryItemImage.id.asc())
            .all()
        )
        keep = rows[0] if rows else None
        extra = rows[1:] if rows else []

        if keep:
            old_path = keep.file_path or ""
            if entry_catalog_item_id is not None:
                keep.entry_catalog_item_id = entry_catalog_item_id
            keep.file_path = out_path
            keep.file_name = out_name
            keep.file_size = file_size
            keep.mime_type = mime_type or ""
            keep.original_id = orig_id
            keep.sort_order = orig_sort_order or keep.sort_order
            if old_path and old_path != out_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
        else:
            keep = EntryItemImage(
                entry_catalog_item_id=entry_catalog_item_id,
                image_type="retouched",
                file_path=out_path,
                file_name=out_name,
                file_size=file_size,
                mime_type=mime_type or "",
                original_id=orig_id,
                sort_order=orig_sort_order,
            )
            session.add(keep)

        for r in extra:
            old = r.file_path or ""
            try:
                session.delete(r)
            except Exception:
                pass
            if old and old != out_path and os.path.exists(old):
                try:
                    os.remove(old)
                except Exception:
                    pass

        session.commit()


class AIRetouchWidget(QWidget):
    """AI修图界面"""

    def __init__(self):
        super().__init__()
        self.config_manager = AppSettings()
        self.current_theme = self.config_manager.load_theme_preference()
        self._base_font: QFont = self.font()
        self._font_min = 9
        self._font_max = 20
        self._tree_font_size = self._base_font.pointSizeF()
        self._table_font_size = self._base_font.pointSizeF()
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(1)
        self._processing = False
        self._org_tree_load_token = 0
        self._person_load_token = 0
        self.initUI()
        self.apply_theme()

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 左右分割
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        # ── 左侧：机构树 + 人员列表 ──
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        left_layout.addWidget(QLabel("机构/人员"))

        self.org_tree = QTreeWidget()
        self.org_tree.setObjectName("org_tree_ai_retouch")
        self.org_tree.setHeaderHidden(True)
        self.org_tree.setIndentation(18)
        self.org_tree.itemClicked.connect(self._on_org_clicked)
        left_layout.addWidget(self.org_tree)

        # 人员表
        self.person_table = QTableWidget()
        self.person_table.setColumnCount(4)
        self.person_table.setHorizontalHeaderLabels(["选择", "姓名", "工号", "图片数"])
        self.person_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.person_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.person_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.person_table.setColumnWidth(0, 46)
        for c in range(1, self.person_table.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.Stretch)
        self.person_table.setAlternatingRowColors(True)
        self.person_table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.person_table)

        # 全选/反选
        sel_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setFixedHeight(28)
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._on_select_all)
        self.btn_deselect_all = QPushButton("取消全选")
        self.btn_deselect_all.setFixedHeight(28)
        self.btn_deselect_all.setCursor(Qt.PointingHandCursor)
        self.btn_deselect_all.clicked.connect(self._on_deselect_all)
        sel_row.addWidget(self.btn_select_all)
        sel_row.addWidget(self.btn_deselect_all)
        sel_row.addStretch()
        left_layout.addLayout(sel_row)

        # ── 右侧：修图控制面板 ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(12)

        title = QLabel("🎨 AI 批量修图")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px 0;")
        right_layout.addWidget(title)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #e0e0e0;")
        line.setFixedHeight(1)
        right_layout.addWidget(line)

        # === 修图参数区域 ===
        params_group = QGroupBox("修图参数")
        params_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        params_layout = QGridLayout(params_group)
        params_layout.setSpacing(10)

        row = 0
        # 去灰底
        params_layout.addWidget(QLabel("去灰底强度:"), row, 0)
        self.slider_gray = QSlider(Qt.Horizontal)
        self.slider_gray.setRange(0, 200)
        self.slider_gray.setValue(100)
        self.slider_gray.setTickInterval(20)
        self.slider_gray.setTickPosition(QSlider.TicksBelow)
        self.spin_gray = QSpinBox()
        self.spin_gray.setRange(0, 200)
        self.spin_gray.setValue(100)
        self.spin_gray.setSuffix("%")
        self.slider_gray.valueChanged.connect(self.spin_gray.setValue)
        self.spin_gray.valueChanged.connect(self.slider_gray.setValue)
        params_layout.addWidget(self.slider_gray, row, 1)
        params_layout.addWidget(self.spin_gray, row, 2)

        row += 1
        # 亮度
        params_layout.addWidget(QLabel("亮度:"), row, 0)
        self.slider_brightness = QSlider(Qt.Horizontal)
        self.slider_brightness.setRange(20, 300)
        self.slider_brightness.setValue(100)
        self.slider_brightness.setTickInterval(20)
        self.slider_brightness.setTickPosition(QSlider.TicksBelow)
        self.spin_brightness = QSpinBox()
        self.spin_brightness.setRange(20, 300)
        self.spin_brightness.setValue(100)
        self.spin_brightness.setSuffix("%")
        self.slider_brightness.valueChanged.connect(self.spin_brightness.setValue)
        self.spin_brightness.valueChanged.connect(self.slider_brightness.setValue)
        params_layout.addWidget(self.slider_brightness, row, 1)
        params_layout.addWidget(self.spin_brightness, row, 2)

        row += 1
        # 对比度
        params_layout.addWidget(QLabel("对比度:"), row, 0)
        self.slider_contrast = QSlider(Qt.Horizontal)
        self.slider_contrast.setRange(20, 300)
        self.slider_contrast.setValue(100)
        self.slider_contrast.setTickInterval(20)
        self.slider_contrast.setTickPosition(QSlider.TicksBelow)
        self.spin_contrast = QSpinBox()
        self.spin_contrast.setRange(20, 300)
        self.spin_contrast.setValue(100)
        self.spin_contrast.setSuffix("%")
        self.slider_contrast.valueChanged.connect(self.spin_contrast.setValue)
        self.spin_contrast.valueChanged.connect(self.slider_contrast.setValue)
        params_layout.addWidget(self.slider_contrast, row, 1)
        params_layout.addWidget(self.spin_contrast, row, 2)

        row += 1
        # 锐化
        params_layout.addWidget(QLabel("锐化:"), row, 0)
        self.slider_sharpen = QSlider(Qt.Horizontal)
        self.slider_sharpen.setRange(0, 200)
        self.slider_sharpen.setValue(0)
        self.slider_sharpen.setTickInterval(20)
        self.slider_sharpen.setTickPosition(QSlider.TicksBelow)
        self.spin_sharpen = QSpinBox()
        self.spin_sharpen.setRange(0, 200)
        self.spin_sharpen.setValue(0)
        self.spin_sharpen.setSuffix("%")
        self.slider_sharpen.valueChanged.connect(self.spin_sharpen.setValue)
        self.spin_sharpen.valueChanged.connect(self.slider_sharpen.setValue)
        params_layout.addWidget(self.slider_sharpen, row, 1)
        params_layout.addWidget(self.spin_sharpen, row, 2)

        right_layout.addWidget(params_group)

        # === 预设按钮 ===
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)

        self.btn_preset_auto = QPushButton("✨ 一键美化")
        self.btn_preset_auto.setFixedHeight(36)
        self.btn_preset_auto.setCursor(Qt.PointingHandCursor)
        self.btn_preset_auto.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_preset_auto.clicked.connect(self._on_preset_auto)

        self.btn_preset_gray = QPushButton("🌫 仅去灰底")
        self.btn_preset_gray.setFixedHeight(36)
        self.btn_preset_gray.setCursor(Qt.PointingHandCursor)
        self.btn_preset_gray.clicked.connect(self._on_preset_gray_only)

        self.btn_preset_reset = QPushButton("↩ 重置参数")
        self.btn_preset_reset.setFixedHeight(36)
        self.btn_preset_reset.setCursor(Qt.PointingHandCursor)
        self.btn_preset_reset.clicked.connect(self._on_preset_reset)

        preset_layout.addWidget(self.btn_preset_auto)
        preset_layout.addWidget(self.btn_preset_gray)
        preset_layout.addWidget(self.btn_preset_reset)
        preset_layout.addStretch()
        right_layout.addLayout(preset_layout)

        # === 进度条 ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("font-size: 12px; color: #666;")
        right_layout.addWidget(self.lbl_progress)

        # === 执行按钮 ===
        exec_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶  开始批量修图")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: bold; background-color: #2563eb; "
            "color: white; border-radius: 6px; padding: 0 24px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.btn_start.clicked.connect(self._on_start_batch)
        exec_layout.addStretch()
        exec_layout.addWidget(self.btn_start)
        exec_layout.addStretch()
        right_layout.addLayout(exec_layout)

        right_layout.addStretch()

        # 添加到分割器
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter)

        # 初始加载
        self._populate_org_tree()

    # ── 机构树 ──
    def _populate_org_tree(self):
        self._org_tree_load_token += 1
        self._person_load_token += 1
        token = self._org_tree_load_token
        self.org_tree.clear()
        self.person_table.setRowCount(0)

        def do_load():
            try:
                all_units = list_all_org_units()
                counts = count_entries_grouped_by_org()
                roots = [u for u in all_units if u.get("parent_id") is None]
                return {"token": token, "roots": roots, "all_units": all_units, "counts": counts, "error": ""}
            except Exception as e:
                return {"token": token, "roots": [], "all_units": [], "counts": {}, "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._org_tree_load_token:
                return
            if res.get("error"):
                print(f"[ai-retouch] load org tree failed: {res.get('error')}")
                return

            roots = res.get("roots") or []
            all_units = res.get("all_units") or []
            counts = res.get("counts") or {}
            children_map = {}
            for u in all_units:
                pid = u.get("parent_id")
                children_map.setdefault(pid, []).append(u)

            def build(parent_item, parent_id):
                for u in children_map.get(parent_id, []):
                    uid = u["id"]
                    cnt = counts.get(uid, 0)
                    label = f'{u["name"]}（{cnt}人）' if cnt else u["name"]
                    item = QTreeWidgetItem([label])
                    item.setData(0, Qt.UserRole, uid)
                    parent_item.addChild(item)
                    build(item, uid)

            self.org_tree.setUpdatesEnabled(False)
            try:
                self.org_tree.clear()
                for r in roots:
                    rid = r["id"]
                    cnt = counts.get(rid, 0)
                    label = f'{r["name"]}（{cnt}人）' if cnt else r["name"]
                    top = QTreeWidgetItem([label])
                    top.setData(0, Qt.UserRole, rid)
                    self.org_tree.addTopLevelItem(top)
                    build(top, rid)
                self.org_tree.expandAll()
            finally:
                self.org_tree.setUpdatesEnabled(True)

            if self.org_tree.topLevelItemCount() > 0:
                self.org_tree.setCurrentItem(self.org_tree.topLevelItem(0))
                self._on_org_clicked(self.org_tree.currentItem())

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

    def _on_org_clicked(self, item):
        if not item:
            return
        org_id = item.data(0, Qt.UserRole)
        self._load_persons(org_id)

    def _load_persons(self, org_unit_id):
        self._person_load_token += 1
        token = self._person_load_token
        self.person_table.setRowCount(0)

        def do_load():
            try:
                persons = list_entries_by_org_unit_id(org_unit_id)
                image_counts = count_entries_total_images([p.get("id") for p in persons])
                return {"token": token, "persons": persons, "image_counts": image_counts, "error": ""}
            except Exception as e:
                return {"token": token, "persons": [], "image_counts": {}, "error": str(e)}

        def on_loaded(res):
            if not isinstance(res, dict):
                return
            if res.get("token") != self._person_load_token:
                return
            if res.get("error"):
                print(f"[ai-retouch] load persons failed: {res.get('error')}")
                return
            self._render_person_rows(res.get("persons") or [], res.get("image_counts") or {})

        worker = Worker(do_load)
        worker.signals.finished.connect(on_loaded)
        self._thread_pool.start(worker)

    def _render_person_rows(self, persons, image_counts):
        self.person_table.setUpdatesEnabled(False)
        try:
            self.person_table.setRowCount(0)
            self.person_table.setRowCount(len(persons))
            for r, p in enumerate(persons):
                # 勾选框
                cb = QCheckBox()
                cb.setChecked(False)
                cb_widget = QWidget()
                cb_layout = QHBoxLayout(cb_widget)
                cb_layout.addWidget(cb)
                cb_layout.setAlignment(Qt.AlignCenter)
                cb_layout.setContentsMargins(0, 0, 0, 0)
                self.person_table.setCellWidget(r, 0, cb_widget)

                item0 = QTableWidgetItem("")
                item0.setData(Qt.UserRole, p["id"])
                self.person_table.setItem(r, 0, item0)

                self.person_table.setItem(r, 1, QTableWidgetItem(p.get("name") or ""))
                self.person_table.setItem(r, 2, QTableWidgetItem(p.get("emp_no") or ""))
                self.person_table.setItem(r, 3, QTableWidgetItem(str(image_counts.get(int(p["id"]), 0))))
        finally:
            self.person_table.setUpdatesEnabled(True)

    def _on_select_all(self):
        for r in range(self.person_table.rowCount()):
            w = self.person_table.cellWidget(r, 0)
            if w:
                cb = w.findChild(QCheckBox)
                if cb:
                    cb.setChecked(True)

    def _on_deselect_all(self):
        for r in range(self.person_table.rowCount()):
            w = self.person_table.cellWidget(r, 0)
            if w:
                cb = w.findChild(QCheckBox)
                if cb:
                    cb.setChecked(False)

    def _checked_entry_ids(self) -> List[int]:
        ids = []
        for r in range(self.person_table.rowCount()):
            w = self.person_table.cellWidget(r, 0)
            if not w:
                continue
            cb = w.findChild(QCheckBox)
            if cb and cb.isChecked():
                it = self.person_table.item(r, 0)
                if it:
                    eid = it.data(Qt.UserRole)
                    if eid is not None:
                        ids.append(int(eid))
        return ids

    # ── 预设 ──
    def _on_preset_auto(self):
        self.slider_gray.setValue(100)
        self.slider_brightness.setValue(110)
        self.slider_contrast.setValue(115)
        self.slider_sharpen.setValue(80)

    def _on_preset_gray_only(self):
        self.slider_gray.setValue(100)
        self.slider_brightness.setValue(100)
        self.slider_contrast.setValue(100)
        self.slider_sharpen.setValue(0)

    def _on_preset_reset(self):
        self.slider_gray.setValue(0)
        self.slider_brightness.setValue(100)
        self.slider_contrast.setValue(100)
        self.slider_sharpen.setValue(0)

    def _build_enhance_params(self) -> Dict[str, Any]:
        return {
            "gray_remove": self.slider_gray.value() / 100.0,
            "brightness": self.slider_brightness.value() / 100.0,
            "contrast": self.slider_contrast.value() / 100.0,
            "sharpen": self.slider_sharpen.value() / 100.0,
        }

    # ── 批量修图 ──
    def _on_start_batch(self):
        if self._processing:
            return
        entry_ids = self._checked_entry_ids()
        if not entry_ids:
            StyledMessageBox.information(self, "提示", "请先勾选要修图的人员", self.current_theme)
            return

        enh = self._build_enhance_params()
        # 检查是否有任何修改
        has_change = (
            enh["gray_remove"] > 0.01
            or abs(enh["brightness"] - 1.0) > 0.01
            or abs(enh["contrast"] - 1.0) > 0.01
            or enh["sharpen"] > 0.01
        )
        if not has_change:
            StyledMessageBox.information(self, "提示", "当前参数无修改，请调整修图参数后再执行", self.current_theme)
            return

        # 收集所有需要处理的图片
        all_images = []
        for eid in entry_ids:
            try:
                imgs = _list_all_original_images_for_entry(eid)
                for img in imgs:
                    fp = (img.get("file_path") or "").strip()
                    if fp and os.path.exists(fp):
                        all_images.append(img)
            except Exception:
                continue

        if not all_images:
            StyledMessageBox.information(self, "提示", "所选人员没有可处理的图片", self.current_theme)
            return

        total = len(all_images)
        self._processing = True
        self.btn_start.setEnabled(False)
        self.btn_start.setText("处理中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText(f"准备处理 {total} 张图片...")

        def do_batch():
            from PIL import Image  # type: ignore
            results = {"done": 0, "fail": 0}
            for idx, img_info in enumerate(all_images):
                try:
                    fp = resolve_image_path(
                        img_info.get("file_path") or "",
                        entry_id=img_info.get("entry_id"),
                        template_item_id=img_info.get("template_item_id"),
                        file_name=img_info.get("file_name") or "",
                    )
                    if not fp or not os.path.exists(fp):
                        raise FileNotFoundError(f"图片不存在：{img_info.get('file_name') or fp}")
                    im = _open_pil_image(fp)
                    im = apply_enhance(im, enh)

                    # 输出路径：在原图旁生成 _retouched 版本
                    out_path, out_name = _retouched_output_path(fp)

                    save_image_like_source(im, out_path, out_name)

                    mime, _ = mimetypes.guess_type(out_name[:-len(CryptoService.ENCRYPTED_EXT)])
                    fsize = os.path.getsize(out_path) if os.path.exists(out_path) else None

                    _upsert_retouched_for_original(
                        orig_id=int(img_info["id"]),
                        entry_catalog_item_id=img_info.get("entry_catalog_item_id"),
                        orig_sort_order=img_info.get("sort_order"),
                        out_path=out_path,
                        out_name=out_name,
                        mime_type=mime or "",
                        file_size=fsize,
                    )
                    results["done"] += 1
                except Exception as e:
                    print(f"[ai-retouch] process image failed: {e}")
                    results["fail"] += 1

                # 返回进度
                results["current"] = idx + 1
                results["total"] = total
            return results

        def on_progress_tick():
            """定时轮询更新进度（简化方案）。"""
            pass

        worker = Worker(do_batch)

        def on_done(res):
            self._processing = False
            self.btn_start.setEnabled(True)
            self.btn_start.setText("▶  开始批量修图")
            done = res.get("done", 0) if res else 0
            fail = res.get("fail", 0) if res else 0
            total_done = done + fail
            self.progress_bar.setValue(total_done)
            self.lbl_progress.setText(f"完成：成功 {done} 张，失败 {fail} 张（共 {total_done} 张）")
            # 刷新人员列表
            self._on_org_clicked(self.org_tree.currentItem())

        def on_error(err):
            self._processing = False
            self.btn_start.setEnabled(True)
            self.btn_start.setText("▶  开始批量修图")
            self.lbl_progress.setText(f"处理出错: {err}")

        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)

        # 使用线程池后台执行，UI 不阻塞
        # 但由于 Worker 是单次回调，进度条只能在完成后更新
        # 为了实时进度，改用 QApplication.processEvents 的阻塞方式
        self._run_batch_blocking(all_images, enh, total)

    def _run_batch_blocking(self, all_images, enh, total):
        """阻塞式批量处理（带实时进度更新）。"""
        from PIL import Image  # type: ignore

        done = 0
        fail = 0
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for idx, img_info in enumerate(all_images):
                try:
                    fp = resolve_image_path(
                        img_info.get("file_path") or "",
                        entry_id=img_info.get("entry_id"),
                        template_item_id=img_info.get("template_item_id"),
                        file_name=img_info.get("file_name") or "",
                    )
                    im = _open_pil_image(fp)
                    im = apply_enhance(im, enh)

                    out_path, out_name = _retouched_output_path(fp)

                    save_image_like_source(im, out_path, out_name)

                    mime, _ = mimetypes.guess_type(out_name[:-len(CryptoService.ENCRYPTED_EXT)])
                    fsize = os.path.getsize(out_path) if os.path.exists(out_path) else None

                    _upsert_retouched_for_original(
                        orig_id=int(img_info["id"]),
                        entry_catalog_item_id=img_info.get("entry_catalog_item_id"),
                        orig_sort_order=img_info.get("sort_order"),
                        out_path=out_path,
                        out_name=out_name,
                        mime_type=mime or "",
                        file_size=fsize,
                    )
                    done += 1
                except Exception as e:
                    print(f"[ai-retouch] process image failed: {e}")
                    fail += 1

                # 实时更新进度
                self.progress_bar.setValue(idx + 1)
                self.lbl_progress.setText(f"正在处理 {idx + 1}/{total}（成功 {done}，失败 {fail}）")
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        self._processing = False
        self.btn_start.setEnabled(True)
        self.btn_start.setText("▶  开始批量修图")
        self.lbl_progress.setText(f"完成：成功 {done} 张，失败 {fail} 张（共 {total} 张）")
        self._on_org_clicked(self.org_tree.currentItem())

    # ── 主题 ──
    def apply_theme(self):
        if self.current_theme == "light":
            self.setStyleSheet(InventoryReceiveStyle.LIGHT_STYLE)
        else:
            self.setStyleSheet(InventoryReceiveStyle.DARK_STYLE)

    def update_theme(self, theme_name):
        self.current_theme = theme_name
        self.apply_theme()

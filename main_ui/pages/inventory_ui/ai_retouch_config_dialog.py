# -*- coding: utf-8 -*-
"""
AI 修图配置对话框
提供 保护 / 移除 / 增强 / 其它 四组参数设置，配置持久化到 QSettings。
"""

import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QLabel, QLineEdit, QPushButton, QFrame, QGridLayout,
)
from PyQt5.QtCore import Qt, QPoint, QSettings


class AIRetouchConfigDialog(QDialog):
    """AI 修图配置对话框"""

    SETTINGS_KEY = "ai_retouch_config"

    DEFAULT_CONFIG = {
        # 保护
        "color_protect": True,
        "red_seal_protect": True,
        "blue_seal_protect": True,
        "photo_protect": True,
        "corner_protect": True,
        "stamp_protect": True,
        "stamp_threshold": 255,
        # 移除
        "remove_black_spots": True,
        "remove_shadow": True,
        "remove_staple": True,
        "remove_white_border": True,
        "remove_black_border": True,
        "remove_noise": True,
        "noise_size": 25,
        # 增强
        "enhance_image": True,
        "enhance_gamma": 1.05,
        "enhance_brightness": True,
        "brightness_alpha": 1,
        "brightness_beta": 20,
        "enhance_hd": True, 
        "hd_alpha": 1,
        "hd_beta": 175,
        # 其它
        "orientation_correct": True,
        "skew_correct": True,
        "fill": False,
        "center": False,
        "auto_crop": True,
        "crop_top": 0,
        "crop_right": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "enable_classify": True,
        "enable_recognize": True,
    }

    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        self.current_theme = theme
        self._config = dict(self.DEFAULT_CONFIG)
        self._load_config()
        self._drag_pos = None
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumWidth(520)
        self._init_ui()
        self._populate_ui()
        self._apply_style()

    # ── 持久化 ──────────────────────────────────────────────────

    def _load_config(self):
        try:
            settings = QSettings("Company", "ArchiveSystem")
            raw = settings.value(self.SETTINGS_KEY, "")
            if raw:
                data = json.loads(raw)
                self._config.update(data)
        except Exception:
            pass

    def _save_config(self):
        try:
            self._read_from_ui()
            settings = QSettings("Company", "ArchiveSystem")
            settings.setValue(self.SETTINGS_KEY, json.dumps(self._config, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    def load_config_static() -> dict:
        """静态方法：供外部直接读取当前保存的配置（不打开对话框）。"""
        cfg = dict(AIRetouchConfigDialog.DEFAULT_CONFIG)
        try:
            settings = QSettings("Company", "ArchiveSystem")
            raw = settings.value(AIRetouchConfigDialog.SETTINGS_KEY, "")
            if raw:
                cfg.update(json.loads(raw))
        except Exception:
            pass
        return cfg

    # ── UI 初始化 ─────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- 标题栏 ---
        self._header = QFrame()
        self._header.setObjectName("ai_cfg_header")
        self._header.setFixedHeight(40)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(14, 0, 8, 0)
        header_layout.setSpacing(8)

        title_lbl = QLabel("AI 修图配置")
        title_lbl.setObjectName("ai_cfg_title")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("ai_cfg_close_btn")
        close_btn.setFixedSize(32, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        layout.addWidget(self._header)

        # --- 内容区 ---
        content = QFrame()
        content.setObjectName("ai_cfg_content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 8)
        content_layout.setSpacing(10)

        # === 保护 ===
        protect_group = QGroupBox("保护")
        protect_group.setObjectName("ai_cfg_group")
        protect_layout = QGridLayout(protect_group)
        protect_layout.setContentsMargins(12, 14, 12, 10)
        protect_layout.setHorizontalSpacing(16)
        protect_layout.setVerticalSpacing(8)

        self.cb_color_protect = QCheckBox("颜色保护")
        self.cb_red_seal_protect = QCheckBox("红章保护")
        self.cb_blue_seal_protect = QCheckBox("蓝章保护")
        self.cb_photo_protect = QCheckBox("照片保护")
        self.cb_corner_protect = QCheckBox("角标保护")
        self.cb_stamp_protect = QCheckBox("图章保护")
        threshold_lbl = QLabel("阈值")
        self.le_stamp_threshold = QLineEdit()
        self.le_stamp_threshold.setFixedWidth(60)
        self.le_stamp_threshold.setObjectName("ai_cfg_input")

        protect_layout.addWidget(self.cb_color_protect, 0, 0)
        protect_layout.addWidget(self.cb_red_seal_protect, 0, 1)
        protect_layout.addWidget(self.cb_blue_seal_protect, 0, 2)
        protect_layout.addWidget(self.cb_photo_protect, 1, 0)
        protect_layout.addWidget(self.cb_corner_protect, 1, 1)
        protect_layout.addWidget(self.cb_stamp_protect, 1, 2)
        protect_layout.addWidget(threshold_lbl, 1, 3)
        protect_layout.addWidget(self.le_stamp_threshold, 1, 4)
        content_layout.addWidget(protect_group)

        # === 移除 ===
        remove_group = QGroupBox("移除")
        remove_group.setObjectName("ai_cfg_group")
        remove_layout = QGridLayout(remove_group)
        remove_layout.setContentsMargins(12, 14, 12, 10)
        remove_layout.setHorizontalSpacing(16)
        remove_layout.setVerticalSpacing(8)

        self.cb_remove_black_spots = QCheckBox("移除黑斑")
        self.cb_remove_shadow = QCheckBox("移除阴影")
        self.cb_remove_staple = QCheckBox("移除装订孔")
        self.cb_remove_white_border = QCheckBox("移除白边")
        self.cb_remove_black_border = QCheckBox("移除黑边")
        self.cb_remove_noise = QCheckBox("移除噪点")
        noise_size_lbl = QLabel("大小")
        self.le_noise_size = QLineEdit()
        self.le_noise_size.setFixedWidth(60)
        self.le_noise_size.setObjectName("ai_cfg_input")

        remove_layout.addWidget(self.cb_remove_black_spots, 0, 0)
        remove_layout.addWidget(self.cb_remove_shadow, 0, 1)
        remove_layout.addWidget(self.cb_remove_staple, 0, 2)
        remove_layout.addWidget(self.cb_remove_white_border, 1, 0)
        remove_layout.addWidget(self.cb_remove_black_border, 1, 1)
        remove_layout.addWidget(self.cb_remove_noise, 1, 2)
        remove_layout.addWidget(noise_size_lbl, 1, 3)
        remove_layout.addWidget(self.le_noise_size, 1, 4)
        content_layout.addWidget(remove_group)

        # === 增强 ===
        enhance_group = QGroupBox("增强")
        enhance_group.setObjectName("ai_cfg_group")
        enhance_layout = QGridLayout(enhance_group)
        enhance_layout.setContentsMargins(12, 14, 12, 10)
        enhance_layout.setHorizontalSpacing(16)
        enhance_layout.setVerticalSpacing(8)

        self.cb_enhance_image = QCheckBox("图像增强")
        gamma_lbl = QLabel("Gamma")
        self.le_enhance_gamma = QLineEdit()
        self.le_enhance_gamma.setFixedWidth(70)
        self.le_enhance_gamma.setObjectName("ai_cfg_input")

        self.cb_enhance_brightness = QCheckBox("明暗增强")
        alpha_lbl1 = QLabel("Alpha")
        self.le_brightness_alpha = QLineEdit()
        self.le_brightness_alpha.setFixedWidth(55)
        self.le_brightness_alpha.setObjectName("ai_cfg_input")
        beta_lbl1 = QLabel("Beta")
        self.le_brightness_beta = QLineEdit()
        self.le_brightness_beta.setFixedWidth(60)
        self.le_brightness_beta.setObjectName("ai_cfg_input")

        self.cb_enhance_hd = QCheckBox("转 高 清")
        alpha_lbl2 = QLabel("Alpha")
        self.le_hd_alpha = QLineEdit()
        self.le_hd_alpha.setFixedWidth(55)
        self.le_hd_alpha.setObjectName("ai_cfg_input")
        beta_lbl2 = QLabel("Beta")
        self.le_hd_beta = QLineEdit()
        self.le_hd_beta.setFixedWidth(60)
        self.le_hd_beta.setObjectName("ai_cfg_input")

        enhance_layout.addWidget(self.cb_enhance_image, 0, 0)
        enhance_layout.addWidget(gamma_lbl, 0, 1)
        enhance_layout.addWidget(self.le_enhance_gamma, 0, 2)
        enhance_layout.addWidget(self.cb_enhance_brightness, 1, 0)
        enhance_layout.addWidget(alpha_lbl1, 1, 1)
        enhance_layout.addWidget(self.le_brightness_alpha, 1, 2)
        enhance_layout.addWidget(beta_lbl1, 1, 3)
        enhance_layout.addWidget(self.le_brightness_beta, 1, 4)
        enhance_layout.addWidget(self.cb_enhance_hd, 2, 0)
        enhance_layout.addWidget(alpha_lbl2, 2, 1)
        enhance_layout.addWidget(self.le_hd_alpha, 2, 2)
        enhance_layout.addWidget(beta_lbl2, 2, 3)
        enhance_layout.addWidget(self.le_hd_beta, 2, 4)
        content_layout.addWidget(enhance_group)

        # === 其它 ===
        other_group = QGroupBox("其它")
        other_group.setObjectName("ai_cfg_group")
        other_layout = QGridLayout(other_group)
        other_layout.setContentsMargins(12, 14, 12, 10)
        other_layout.setHorizontalSpacing(16)
        other_layout.setVerticalSpacing(8)

        self.cb_orientation_correct = QCheckBox("方向校正")
        self.cb_skew_correct = QCheckBox("纠偏")
        self.cb_fill = QCheckBox("是否填充")
        self.cb_center = QCheckBox("是否居中")

        self.cb_auto_crop = QCheckBox("自动裁剪")
        crop_lbl = QLabel("四边裁剪")
        self.le_crop_top = QLineEdit()
        self.le_crop_right = QLineEdit()
        self.le_crop_bottom = QLineEdit()
        self.le_crop_left = QLineEdit()
        for le in (self.le_crop_top, self.le_crop_right, self.le_crop_bottom, self.le_crop_left):
            le.setFixedWidth(50)
            le.setObjectName("ai_cfg_input")

        self.cb_enable_classify = QCheckBox("启用分类")
        self.cb_enable_recognize = QCheckBox("启用识别")

        other_layout.addWidget(self.cb_orientation_correct, 0, 0)
        other_layout.addWidget(self.cb_skew_correct, 0, 1)
        other_layout.addWidget(self.cb_fill, 0, 2)
        other_layout.addWidget(self.cb_center, 0, 3)
        other_layout.addWidget(self.cb_auto_crop, 1, 0)
        other_layout.addWidget(crop_lbl, 1, 1)
        other_layout.addWidget(self.le_crop_top, 1, 2)
        other_layout.addWidget(self.le_crop_right, 1, 3)
        other_layout.addWidget(self.le_crop_bottom, 1, 4)
        other_layout.addWidget(self.le_crop_left, 1, 5)
        other_layout.addWidget(self.cb_enable_classify, 2, 0)
        other_layout.addWidget(self.cb_enable_recognize, 2, 1)
        content_layout.addWidget(other_group)

        # --- 底部按钮行 ---
        btn_frame = QFrame()
        btn_frame.setObjectName("ai_cfg_btn_frame")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 8, 0, 4)
        btn_layout.setSpacing(8)

        self.btn_reset = QPushButton("重置默认")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setObjectName("ai_cfg_reset_btn")
        self.btn_reset.clicked.connect(self._on_reset)

        self.btn_cancel = QPushButton("取 消")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setObjectName("ai_cfg_cancel_btn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("确 定")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setObjectName("ai_cfg_ok_btn")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_ok)

        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        content_layout.addWidget(btn_frame)

        layout.addWidget(content)

    # ── 数据双向绑定 ──────────────────────────────────────────

    def _populate_ui(self):
        cfg = self._config
        # 保护
        self.cb_color_protect.setChecked(cfg.get("color_protect", True))
        self.cb_red_seal_protect.setChecked(cfg.get("red_seal_protect", True))
        self.cb_blue_seal_protect.setChecked(cfg.get("blue_seal_protect", True))
        self.cb_photo_protect.setChecked(cfg.get("photo_protect", True))
        self.cb_corner_protect.setChecked(cfg.get("corner_protect", True))
        self.cb_stamp_protect.setChecked(cfg.get("stamp_protect", True))
        self.le_stamp_threshold.setText(str(cfg.get("stamp_threshold", 255)))
        # 移除
        self.cb_remove_black_spots.setChecked(cfg.get("remove_black_spots", True))
        self.cb_remove_shadow.setChecked(cfg.get("remove_shadow", True))
        self.cb_remove_staple.setChecked(cfg.get("remove_staple", True))
        self.cb_remove_white_border.setChecked(cfg.get("remove_white_border", True))
        self.cb_remove_black_border.setChecked(cfg.get("remove_black_border", True))
        self.cb_remove_noise.setChecked(cfg.get("remove_noise", True))
        self.le_noise_size.setText(str(cfg.get("noise_size", 25)))
        # 增强
        self.cb_enhance_image.setChecked(cfg.get("enhance_image", True))
        self.le_enhance_gamma.setText(str(cfg.get("enhance_gamma", 1.05)))
        self.cb_enhance_brightness.setChecked(cfg.get("enhance_brightness", True))
        self.le_brightness_alpha.setText(str(cfg.get("brightness_alpha", 1)))
        self.le_brightness_beta.setText(str(cfg.get("brightness_beta", 20)))
        self.cb_enhance_hd.setChecked(cfg.get("enhance_hd", True))
        self.le_hd_alpha.setText(str(cfg.get("hd_alpha", 1)))
        self.le_hd_beta.setText(str(cfg.get("hd_beta", 175)))
        # 其它
        self.cb_orientation_correct.setChecked(cfg.get("orientation_correct", True))
        self.cb_skew_correct.setChecked(cfg.get("skew_correct", True))
        self.cb_fill.setChecked(cfg.get("fill", False))
        self.cb_center.setChecked(cfg.get("center", False))
        self.cb_auto_crop.setChecked(cfg.get("auto_crop", True))
        self.le_crop_top.setText(str(cfg.get("crop_top", 0)))
        self.le_crop_right.setText(str(cfg.get("crop_right", 0)))
        self.le_crop_bottom.setText(str(cfg.get("crop_bottom", 0)))
        self.le_crop_left.setText(str(cfg.get("crop_left", 0)))
        self.cb_enable_classify.setChecked(cfg.get("enable_classify", True))
        self.cb_enable_recognize.setChecked(cfg.get("enable_recognize", True))

    def _read_from_ui(self):
        # 保护
        self._config["color_protect"] = self.cb_color_protect.isChecked()
        self._config["red_seal_protect"] = self.cb_red_seal_protect.isChecked()
        self._config["blue_seal_protect"] = self.cb_blue_seal_protect.isChecked()
        self._config["photo_protect"] = self.cb_photo_protect.isChecked()
        self._config["corner_protect"] = self.cb_corner_protect.isChecked()
        self._config["stamp_protect"] = self.cb_stamp_protect.isChecked()
        try:
            self._config["stamp_threshold"] = int(self.le_stamp_threshold.text())
        except ValueError:
            pass
        # 移除
        self._config["remove_black_spots"] = self.cb_remove_black_spots.isChecked()
        self._config["remove_shadow"] = self.cb_remove_shadow.isChecked()
        self._config["remove_staple"] = self.cb_remove_staple.isChecked()
        self._config["remove_white_border"] = self.cb_remove_white_border.isChecked()
        self._config["remove_black_border"] = self.cb_remove_black_border.isChecked()
        self._config["remove_noise"] = self.cb_remove_noise.isChecked()
        try:
            self._config["noise_size"] = int(self.le_noise_size.text())
        except ValueError:
            pass
        # 增强
        self._config["enhance_image"] = self.cb_enhance_image.isChecked()
        try:
            self._config["enhance_gamma"] = float(self.le_enhance_gamma.text())
        except ValueError:
            pass
        self._config["enhance_brightness"] = self.cb_enhance_brightness.isChecked()
        try:
            self._config["brightness_alpha"] = float(self.le_brightness_alpha.text())
            self._config["brightness_beta"] = float(self.le_brightness_beta.text())
        except ValueError:
            pass
        self._config["enhance_hd"] = self.cb_enhance_hd.isChecked()
        try:
            self._config["hd_alpha"] = float(self.le_hd_alpha.text())
            self._config["hd_beta"] = float(self.le_hd_beta.text())
        except ValueError:
            pass
        # 其它
        self._config["orientation_correct"] = self.cb_orientation_correct.isChecked()
        self._config["skew_correct"] = self.cb_skew_correct.isChecked()
        self._config["fill"] = self.cb_fill.isChecked()
        self._config["center"] = self.cb_center.isChecked()
        self._config["auto_crop"] = self.cb_auto_crop.isChecked()
        try:
            self._config["crop_top"] = int(self.le_crop_top.text())
            self._config["crop_right"] = int(self.le_crop_right.text())
            self._config["crop_bottom"] = int(self.le_crop_bottom.text())
            self._config["crop_left"] = int(self.le_crop_left.text())
        except ValueError:
            pass
        self._config["enable_classify"] = self.cb_enable_classify.isChecked()
        self._config["enable_recognize"] = self.cb_enable_recognize.isChecked()

    # ── 按钮事件 ──────────────────────────────────────────────

    def _on_reset(self):
        self._config = dict(self.DEFAULT_CONFIG)
        self._populate_ui()

    def _on_ok(self):
        self._save_config()
        self.accept()

    def get_config(self) -> dict:
        """返回当前（已保存）配置副本。"""
        return dict(self._config)

    # ── 无边框拖拽支持 ───────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._header.geometry().contains(event.pos()):
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── 样式 ──────────────────────────────────────────────────

    def _apply_style(self):
        if self.current_theme == "dark":
            bg = "#2d2d2d"
            text = "#e0e0e0"
            border = "#444444"
            header_bg = "#0f0f0f"
            input_bg = "#363636"
            group_bg = "#252525"
            btn_bg = "#3a3a3a"
            btn_hover = "#4a4a4a"
            ok_bg = "#2563eb"
            ok_hover = "#1d4ed8"
        else:
            bg = "#f5f5f5"
            text = "#1e2732"
            border = "#d0d0d0"
            header_bg = "#3498db"
            input_bg = "#ffffff"
            group_bg = "#ffffff"
            btn_bg = "#ffffff"
            btn_hover = "#e8f0fe"
            ok_bg = "#3498db"
            ok_hover = "#2980b9"

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QFrame#ai_cfg_header {{
                background: {header_bg};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QLabel#ai_cfg_title {{
                color: white;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            }}
            QPushButton#ai_cfg_close_btn {{
                border: none;
                color: white;
                background: transparent;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton#ai_cfg_close_btn:hover {{
                background: rgba(255,255,255,0.18);
                border-radius: 4px;
            }}
            QFrame#ai_cfg_content {{
                background: {bg};
            }}
            QGroupBox#ai_cfg_group {{
                background: {group_bg};
                border: 1px solid {border};
                border-radius: 6px;
                margin-top: 6px;
                color: {text};
                font-weight: 600;
                font-size: 13px;
            }}
            QGroupBox#ai_cfg_group::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
            }}
            QCheckBox {{
                color: {text};
                font-size: 13px;
                spacing: 5px;
            }}
            QLabel {{
                color: {text};
                font-size: 13px;
                background: transparent;
            }}
            QLineEdit#ai_cfg_input {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 3px 6px;
                color: {text};
                font-size: 13px;
            }}
            QPushButton#ai_cfg_reset_btn {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 14px;
                color: {text};
                font-size: 13px;
                min-height: 26px;
            }}
            QPushButton#ai_cfg_reset_btn:hover {{
                background: {btn_hover};
            }}
            QPushButton#ai_cfg_ok_btn {{
                background: {ok_bg};
                border: none;
                border-radius: 4px;
                padding: 4px 20px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                min-height: 26px;
            }}
            QPushButton#ai_cfg_ok_btn:hover {{
                background: {ok_hover};
            }}
            QPushButton#ai_cfg_cancel_btn {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 14px;
                color: {text};
                font-size: 13px;
                min-height: 26px;
            }}
            QPushButton#ai_cfg_cancel_btn:hover {{
                background: {btn_hover};
            }}
        """)

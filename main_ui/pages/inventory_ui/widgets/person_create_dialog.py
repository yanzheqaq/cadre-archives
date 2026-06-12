from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QGridLayout,
    QPushButton,
)
from PyQt5.QtCore import Qt

from common.repositories.field_option_repo import list_field_options


def _make_field_combo(field_name: str, placeholder: str = "", current_value: str = "") -> QComboBox:
    """
    根据 field_name 构建可编辑下拉框。
    - 若数据库有配置选项则填充下拉列表
    - 设置为可编辑，用户仍可自由输入
    """
    combo = QComboBox()
    combo.setEditable(True)
    combo.lineEdit().setPlaceholderText(placeholder)
    try:
        options = list_field_options(field_name)
    except Exception:
        options = []
    if options:
        combo.addItem("")  # 空默认项
        for opt in options:
            combo.addItem(opt)
    if current_value:
        # 如果当前值不在列表中，直接设置文本
        idx = combo.findText(current_value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(current_value)
    return combo


class PersonCreateDialog(QDialog):
    """
    新增人员/案件对话框（用于信息录入页的"新增"按钮）。
    - 允许选择所属机构（可为空）
    """

    def __init__(
        self,
        *,
        org_options: List[Tuple[Optional[int], str]],
        default_org_unit_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("新增人员")
        self.resize(520, 360)
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
            QLineEdit, QComboBox {
                font-size: 13px;
                padding: 8px 12px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: #fafafa;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4A90D9;
                background-color: #ffffff;
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
        title_label = QLabel("新增人员信息")
        title_label.setObjectName("title_label")
        layout.addWidget(title_label)

        # 卡片区域
        card = QFrame()
        card.setObjectName("card")
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setHorizontalSpacing(24)
        card_layout.setVerticalSpacing(12)

        # 第一行：姓名、工号
        lbl_name = QLabel("姓名")
        lbl_name.setProperty("class", "field_label")
        self.le_name = QLineEdit()
        self.le_name.setPlaceholderText("请输入姓名")
        card_layout.addWidget(lbl_name, 0, 0)
        card_layout.addWidget(self.le_name, 0, 1)

        lbl_emp_no = QLabel("工号")
        lbl_emp_no.setProperty("class", "field_label")
        self.le_emp_no = QLineEdit()
        self.le_emp_no.setPlaceholderText("请输入工号")
        card_layout.addWidget(lbl_emp_no, 0, 2)
        card_layout.addWidget(self.le_emp_no, 0, 3)

        # 第二行：岗位、电话
        lbl_role = QLabel("岗位")
        lbl_role.setProperty("class", "field_label")
        self.le_role = _make_field_combo("role_title", "请选择或输入岗位")
        card_layout.addWidget(lbl_role, 1, 0)
        card_layout.addWidget(self.le_role, 1, 1)

        lbl_phone = QLabel("电话")
        lbl_phone.setProperty("class", "field_label")
        self.le_phone = QLineEdit()
        self.le_phone.setPlaceholderText("请输入电话")
        card_layout.addWidget(lbl_phone, 1, 2)
        card_layout.addWidget(self.le_phone, 1, 3)

        # 第三行：身份证号、状态
        lbl_id_card = QLabel("身份证号")
        lbl_id_card.setProperty("class", "field_label")
        self.le_id_card = QLineEdit()
        self.le_id_card.setPlaceholderText("可选")
        card_layout.addWidget(lbl_id_card, 2, 0)
        card_layout.addWidget(self.le_id_card, 2, 1)

        lbl_status = QLabel("状态")
        lbl_status.setProperty("class", "field_label")
        self.le_status = _make_field_combo("status", "请选择或输入状态")
        card_layout.addWidget(lbl_status, 2, 2)
        card_layout.addWidget(self.le_status, 2, 3)

        # 第四行：所属机构（占满一行）
        lbl_org = QLabel("所属机构")
        lbl_org.setProperty("class", "field_label")
        self.cb_org = QComboBox()
        self._org_ids: List[Optional[int]] = []
        for oid, label in org_options:
            self.cb_org.addItem(label)
            self._org_ids.append(oid)

        # 默认值
        if default_org_unit_id in self._org_ids:
            self.cb_org.setCurrentIndex(self._org_ids.index(default_org_unit_id))
        else:
            if None in self._org_ids:
                self.cb_org.setCurrentIndex(self._org_ids.index(None))

        card_layout.addWidget(lbl_org, 3, 0)
        card_layout.addWidget(self.cb_org, 3, 1, 1, 3)

        # 设置列伸缩
        card_layout.setColumnStretch(1, 1)
        card_layout.setColumnStretch(3, 1)

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

    def get_data(self) -> Dict[str, Any]:
        idx = self.cb_org.currentIndex()
        org_unit_id = None
        if 0 <= idx < len(self._org_ids):
            org_unit_id = self._org_ids[idx]
        return {
            "name": self.le_name.text().strip(),
            "emp_no": self.le_emp_no.text().strip(),
            "role_title": self.le_role.currentText().strip(),
            "phone": self.le_phone.text().strip(),
            "status": self.le_status.currentText().strip(),
            "id_card": self.le_id_card.text().strip(),
            "org_unit_id": org_unit_id,
        }



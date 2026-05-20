from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import GroupConfig
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    style_text_editor,
)


class GroupForm(QWidget):
    add_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.default_group_enabled = True
        self.default_group_username_normalize = True
        self._current_group_id = ""

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：目标群 A")

        self.chat_id_edit = QLineEdit()
        self.chat_id_edit.setPlaceholderText("例如：-1001234567890")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("例如：@username 或 https://t.me/xxx")

        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("可选，用于记录这个群的用途")
        style_text_editor(self.remark_edit, 120)

        self.enabled_check = QCheckBox("启用")

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")

        self._build_ui()
        self.add_button.clicked.connect(self.add_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.clear_form()

    def _build_ui(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_labeled_widget(grid, 0, 0, "群组名称：", self.name_edit)
        grid.addWidget(self.enabled_check, 0, 2, 1, 2)

        self._add_labeled_widget(grid, 1, 0, "Chat ID：", self.chat_id_edit)
        self._add_labeled_widget(grid, 1, 2, "Username：", self.username_edit)

        label = QLabel("备注：")
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(label, 2, 0)
        grid.addWidget(self.remark_edit, 2, 1, 1, 3)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(grid)
        layout.addLayout(button_layout)
        layout.addStretch(1)

        apply_large_inputs(self)

    @staticmethod
    def _add_labeled_widget(
        grid: QGridLayout,
        row: int,
        label_column: int,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, label_column)
        grid.addWidget(widget, row, label_column + 1)

    def set_defaults(
        self,
        default_group_enabled: bool = True,
        default_group_username_normalize: bool = True,
    ) -> None:
        self.default_group_enabled = bool(default_group_enabled)
        self.default_group_username_normalize = bool(default_group_username_normalize)
        if not self._current_group_id:
            self.enabled_check.setChecked(self.default_group_enabled)

    def load_group(self, group: GroupConfig) -> None:
        self._current_group_id = str(group.group_id or "").strip()
        self.name_edit.setText(str(group.group_name or ""))
        self.chat_id_edit.setText(str(group.chat_id or ""))
        self.username_edit.setText(str(group.username or ""))
        self.remark_edit.setPlainText(str(group.remark or ""))
        self.enabled_check.setChecked(bool(group.enabled))

    def clear_form(self) -> None:
        self._current_group_id = ""
        self.name_edit.clear()
        self.chat_id_edit.clear()
        self.username_edit.clear()
        self.remark_edit.clear()
        self.enabled_check.setChecked(bool(self.default_group_enabled))

    def get_form_group(self) -> GroupConfig:
        group_id = self._current_group_id or uuid.uuid4().hex
        group_name = self.name_edit.text().strip()
        chat_id = self._parse_chat_id(self.chat_id_edit.text())

        if self.default_group_username_normalize:
            username = self._normalize_username(self.username_edit.text())
        else:
            username = self.username_edit.text().strip()

        return GroupConfig(
            group_id=group_id,
            group_name=group_name,
            chat_id=chat_id,
            username=username,
            remark=self.remark_edit.toPlainText().strip(),
            enabled=self.enabled_check.isChecked(),
        )

    @staticmethod
    def _parse_chat_id(value: Any) -> int:
        raw_text = str(value or "").strip()
        if not raw_text:
            raise ValueError("Chat ID 不能为空")

        try:
            chat_id = int(raw_text)
        except ValueError as exc:
            raise ValueError("Chat ID 必须是数字") from exc

        if chat_id == 0:
            raise ValueError("Chat ID 不能为 0")

        return chat_id

    @staticmethod
    def _normalize_username(value: Any) -> str:
        raw_text = str(value or "").strip()

        if not raw_text:
            return ""

        if raw_text.startswith("https://t.me/"):
            return raw_text

        if raw_text.startswith("http://t.me/"):
            return raw_text.replace("http://t.me/", "https://t.me/", 1)

        if raw_text.startswith("t.me/"):
            return "https://" + raw_text

        if raw_text.startswith("@"):
            return raw_text

        if "/" not in raw_text and " " not in raw_text:
            return "@" + raw_text

        return raw_text

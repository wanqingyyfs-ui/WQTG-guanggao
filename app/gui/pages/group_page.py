from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import GroupConfig
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_table,
    style_text_editor,
)


class GroupPage(QWidget):
    def __init__(self):
        super().__init__()

        self.groups: list[GroupConfig] = []
        self.default_group_enabled = True
        self.default_group_username_normalize = True

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["启用", "群组名称", "Chat ID", "Username/链接", "备注", "Group ID"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：目标群 A")

        self.chat_id_edit = QLineEdit()
        self.chat_id_edit.setPlaceholderText("例如：-1001234567890")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("例如：@username 或 https://t.me/xxx")

        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("可选，用于记录这个群的用途")
        style_text_editor(self.remark_edit, 170)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")
        self.delete_button = QPushButton("删除")

        form_group = QGroupBox("群组配置")
        style_group_box(form_group)

        form_layout = QFormLayout(form_group)
        style_form_layout(form_layout)
        form_layout.addRow("群组名称", self.name_edit)
        form_layout.addRow("Chat ID", self.chat_id_edit)
        form_layout.addRow("Username/链接", self.username_edit)
        form_layout.addRow("备注", self.remark_edit)
        form_layout.addRow("启用状态", self.enabled_check)

        apply_large_inputs(form_group)

        button_bar = QWidget()
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(14)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)

        table_group = QGroupBox("目标群列表")
        style_group_box(table_group)

        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(18, 20, 18, 18)
        table_layout.addWidget(self.table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        title_label = QLabel("群组管理")
        title_label.setObjectName("PageTitleLabel")
        top_layout.addWidget(title_label)
        top_layout.addWidget(make_scroll_area(table_group, minimum_height=240), 1)

        bottom_content = QWidget()
        bottom_layout = QVBoxLayout(bottom_content)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(form_group)
        bottom_layout.addWidget(button_bar)

        bottom_scroll = make_scroll_area(bottom_content, minimum_height=320)

        splitter = make_vertical_splitter(
            top_widget=top_widget,
            bottom_widget=bottom_scroll,
            sizes=[340, 520],
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self._update_action_buttons()

    def set_defaults(
        self,
        default_group_enabled: bool = True,
        default_group_username_normalize: bool = True,
    ) -> None:
        self.default_group_enabled = bool(default_group_enabled)
        self.default_group_username_normalize = bool(
            default_group_username_normalize
        )

    def set_groups(self, groups: list[GroupConfig]) -> None:
        self.groups = list(groups or [])
        self.refresh_table()
        self._update_action_buttons()

    def refresh_table(self) -> None:
        self.table.setRowCount(0)

        for group in self.groups:
            row = self.table.rowCount()
            self.table.insertRow(row)

            enabled_item = QTableWidgetItem("是" if group.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(group.group_name or "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(group.chat_id or "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(group.username or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(group.remark or "")))
            self.table.setItem(row, 5, QTableWidgetItem(str(group.group_id or "")))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()

        if not selected_rows:
            return -1

        return selected_rows[0].row()

    def get_form_group(self) -> GroupConfig:
        row = self.get_selected_row()

        if 0 <= row < len(self.groups):
            group_id = str(self.groups[row].group_id or "").strip()
        else:
            group_id = ""

        if not group_id:
            group_id = uuid.uuid4().hex

        group_name = self.name_edit.text().strip()
        chat_id = self._parse_chat_id(self.chat_id_edit.text())

        if self.default_group_username_normalize:
            username = self._normalize_username(self.username_edit.text())
        else:
            username = self.username_edit.text().strip()

        remark = self.remark_edit.toPlainText().strip()

        return GroupConfig(
            group_id=group_id,
            group_name=group_name,
            chat_id=chat_id,
            username=username,
            remark=remark,
            enabled=self.enabled_check.isChecked(),
        )

    def clear_form(self) -> None:
        self.table.clearSelection()
        self.name_edit.clear()
        self.chat_id_edit.clear()
        self.username_edit.clear()
        self.remark_edit.clear()
        self.enabled_check.setChecked(bool(self.default_group_enabled))
        self._update_action_buttons()

    def on_selection_changed(self) -> None:
        row = self.get_selected_row()

        if row < 0 or row >= len(self.groups):
            self._update_action_buttons()
            return

        group = self.groups[row]

        self.name_edit.setText(str(group.group_name or ""))
        self.chat_id_edit.setText(str(group.chat_id or ""))
        self.username_edit.setText(str(group.username or ""))
        self.remark_edit.setPlainText(str(group.remark or ""))
        self.enabled_check.setChecked(bool(group.enabled))
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_selection = 0 <= self.get_selected_row() < len(self.groups)
        self.delete_button.setEnabled(has_selection)

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
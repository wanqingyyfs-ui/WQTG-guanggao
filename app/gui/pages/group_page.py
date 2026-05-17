from __future__ import annotations

import uuid

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

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["启用", "群组名称", "Chat ID", "Username/链接", "备注"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.name_edit = QLineEdit()
        self.chat_id_edit = QLineEdit()
        self.username_edit = QLineEdit()
        self.remark_edit = QPlainTextEdit()
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
        top_layout.addWidget(QLabel("目标群管理"))
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

    def set_groups(self, groups: list[GroupConfig]) -> None:
        self.groups = list(groups)
        self.table.setRowCount(0)

        for group in self.groups:
            row = self.table.rowCount()
            self.table.insertRow(row)

            enabled_item = QTableWidgetItem("是" if group.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(group.group_name))
            self.table.setItem(row, 2, QTableWidgetItem(str(group.chat_id)))
            self.table.setItem(row, 3, QTableWidgetItem(group.username))
            self.table.setItem(row, 4, QTableWidgetItem(group.remark))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def get_form_group(self) -> GroupConfig:
        row = self.get_selected_row()

        if 0 <= row < len(self.groups):
            group_id = self.groups[row].group_id
        else:
            group_id = uuid.uuid4().hex

        chat_id_text = self.chat_id_edit.text().strip()
        if not chat_id_text:
            raise ValueError("Chat ID 不能为空")

        try:
            chat_id = int(chat_id_text)
        except ValueError as exc:
            raise ValueError("Chat ID 必须是数字") from exc

        return GroupConfig(
            group_id=group_id,
            group_name=self.name_edit.text().strip(),
            chat_id=chat_id,
            username=self.username_edit.text().strip(),
            remark=self.remark_edit.toPlainText().strip(),
            enabled=self.enabled_check.isChecked(),
        )

    def clear_form(self) -> None:
        self.table.clearSelection()
        self.name_edit.clear()
        self.chat_id_edit.clear()
        self.username_edit.clear()
        self.remark_edit.clear()
        self.enabled_check.setChecked(True)

    def on_selection_changed(self) -> None:
        row = self.get_selected_row()
        if row < 0 or row >= len(self.groups):
            return

        group = self.groups[row]
        self.name_edit.setText(group.group_name)
        self.chat_id_edit.setText(str(group.chat_id))
        self.username_edit.setText(group.username)
        self.remark_edit.setPlainText(group.remark)
        self.enabled_check.setChecked(group.enabled)
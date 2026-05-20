from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import GroupConfig
from app.gui.pages.layout_utils import style_table


class GroupPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.groups: list[GroupConfig] = []
        self.default_group_enabled = True
        self.default_group_username_normalize = True

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["启用", "群组名称", "Chat ID", "Username/链接", "备注"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.add_button = QPushButton("新增群组")
        self.config_button = QPushButton("配置群组")
        self.delete_button = QPushButton("删除群组")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")

        self._build_ui()
        self.table.itemSelectionChanged.connect(self.update_action_buttons)
        self.update_action_buttons()

    def _build_ui(self) -> None:
        title_label = QLabel("群组管理")
        title_label.setObjectName("PageTitleLabel")

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.config_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(button_layout)

    def set_defaults(
        self,
        default_group_enabled: bool = True,
        default_group_username_normalize: bool = True,
    ) -> None:
        self.default_group_enabled = bool(default_group_enabled)
        self.default_group_username_normalize = bool(default_group_username_normalize)

    def set_groups(self, groups: list[GroupConfig]) -> None:
        selected_group_id = self.get_selected_group_id()
        self.groups = list(groups or [])
        self.refresh_table()
        self.select_group_id(selected_group_id)
        self.update_action_buttons()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.groups))

        for row, group in enumerate(self.groups):
            enabled_item = QTableWidgetItem("是" if group.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(group.group_name or "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(group.chat_id or "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(group.username or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(group.remark or "")))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def get_selected_group_id(self) -> str:
        row = self.get_selected_row()
        if 0 <= row < len(self.groups):
            return str(self.groups[row].group_id or "").strip()
        return ""

    def select_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        else:
            self.table.clearSelection()
        self.update_action_buttons()

    def select_group_id(self, group_id: str) -> None:
        target = str(group_id or "").strip()
        if not target:
            return

        for row, group in enumerate(self.groups):
            if str(group.group_id or "").strip() == target:
                self.select_row(row)
                return

    def clear_selection(self) -> None:
        self.table.clearSelection()
        self.update_action_buttons()

    def update_action_buttons(self) -> None:
        row = self.get_selected_row()
        has_selection = 0 <= row < len(self.groups)

        self.config_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row < len(self.groups) - 1)

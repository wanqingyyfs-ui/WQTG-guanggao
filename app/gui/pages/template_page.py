from __future__ import annotations

from typing import Any

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

from app.core.models import (
    TEMPLATE_MESSAGE_TYPE_ALBUM,
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TemplateConfig,
)
from app.gui.pages.layout_utils import style_table


class TemplatePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.templates: list[TemplateConfig] = []

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["模板名称", "启用", "创建时间", "备注", "媒体数"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.config_button = QPushButton("配置模板")
        self.delete_button = QPushButton("删除模板")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.refresh_button = QPushButton("刷新列表")

        self._build_ui()
        self.table.itemSelectionChanged.connect(self.update_action_buttons)
        self.update_action_buttons()

    def _build_ui(self) -> None:
        title_label = QLabel("模板管理")
        title_label.setObjectName("PageTitleLabel")

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addWidget(self.config_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(button_layout)

    def set_templates(self, templates: list[TemplateConfig]) -> None:
        selected_template_id = self.get_selected_template_id()
        self.templates = list(templates or [])
        self.refresh_table()
        self.select_template_id(selected_template_id)
        self.update_action_buttons()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.templates))

        for row, template in enumerate(self.templates):
            enabled_item = QTableWidgetItem("是" if template.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, QTableWidgetItem(str(template.template_name or "")))
            self.table.setItem(row, 1, enabled_item)
            self.table.setItem(row, 2, QTableWidgetItem(str(template.created_at or "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(getattr(template, "remark", "") or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(self._template_media_count(template))))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def get_selected_template_id(self) -> str:
        row = self.get_selected_row()
        if 0 <= row < len(self.templates):
            return str(self.templates[row].template_id or "").strip()
        return ""

    def select_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        else:
            self.table.clearSelection()
        self.update_action_buttons()

    def select_template_id(self, template_id: str) -> None:
        target = str(template_id or "").strip()
        if not target:
            return

        for row, template in enumerate(self.templates):
            if str(template.template_id or "").strip() == target:
                self.select_row(row)
                return

    def clear_selection(self) -> None:
        self.table.clearSelection()
        self.update_action_buttons()

    def update_action_buttons(self) -> None:
        row = self.get_selected_row()
        has_selection = 0 <= row < len(self.templates)

        self.config_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row < len(self.templates) - 1)

    def _template_media_count(self, template: TemplateConfig) -> int:
        message_type = str(getattr(template, "message_type", TEMPLATE_MESSAGE_TYPE_TEXT) or "")
        if message_type == TEMPLATE_MESSAGE_TYPE_TEXT:
            return 0

        if message_type == TEMPLATE_MESSAGE_TYPE_PHOTO:
            return 1 if getattr(template, "source_message_ids", []) else 0

        if message_type == TEMPLATE_MESSAGE_TYPE_ALBUM:
            return len(getattr(template, "source_message_ids", []) or [])

        try:
            return max(0, int(getattr(template, "media_count", 0)))
        except (TypeError, ValueError):
            return 0

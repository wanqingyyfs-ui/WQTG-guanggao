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

from app.core.models import MESSAGE_MODE_TEMPLATE, MESSAGE_MODE_TEXT, SendTaskConfig
from app.gui.pages.layout_utils import style_table


class TaskPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.accounts = []
        self.groups = []
        self.templates = []
        self.tasks: list[SendTaskConfig] = []
        self.settings = None
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "启用", "任务名称", "账号组池", "群聊组池", "消息类型", "模板/文本", "账号延迟", "群组延迟", "任务间隔", "每日时间段",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)
        self.config_button = QPushButton("配置任务")
        self.delete_button = QPushButton("删除任务")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.start_task_button = QPushButton("启动任务")
        self.stop_task_button = QPushButton("停止任务")
        self._build_ui()
        self.table.itemSelectionChanged.connect(self.update_action_buttons)
        self.update_action_buttons()

    def _build_ui(self) -> None:
        title_label = QLabel("任务管理")
        title_label.setObjectName("PageTitleLabel")
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        for button in [self.config_button, self.delete_button, self.up_button, self.down_button]:
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.start_task_button)
        button_layout.addWidget(self.stop_task_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(button_layout)

    def set_context(self, accounts, groups, templates, settings=None) -> None:
        self.accounts = [item for item in list(accounts or []) if bool(getattr(item, "enabled", True))]
        self.groups = [item for item in list(groups or []) if bool(getattr(item, "enabled", True))]
        self.templates = [item for item in list(templates or []) if bool(getattr(item, "enabled", True))]
        if settings is not None:
            self.settings = settings

    def set_tasks(self, tasks: list[SendTaskConfig]) -> None:
        selected_task_id = self.get_selected_task_id()
        self.tasks = list(tasks or [])
        self.refresh_table()
        self.select_task_id(selected_task_id)
        self.update_action_buttons()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            enabled_item = QTableWidgetItem("是" if task.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(task.task_name or "")))
            self.table.setItem(row, 2, QTableWidgetItem(self._pool_label(getattr(task, "account_group_names", []), "账号组")))
            self.table.setItem(row, 3, QTableWidgetItem(self._pool_label(getattr(task, "group_group_names", []), "群聊组")))
            self.table.setItem(row, 4, QTableWidgetItem(self._message_mode_label(task.message_mode)))
            self.table.setItem(row, 5, QTableWidgetItem(self._message_target_label(task)))
            self.table.setItem(row, 6, QTableWidgetItem(self._delay_range_label(getattr(task, "account_delay_min_ms", 0), getattr(task, "account_delay_max_ms", 0))))
            self.table.setItem(row, 7, QTableWidgetItem(self._delay_range_label(getattr(task, "group_delay_min_ms", 0), getattr(task, "group_delay_max_ms", 0))))
            self.table.setItem(row, 8, QTableWidgetItem(self._interval_label(getattr(task, "interval_ms", 0))))
            self.table.setItem(row, 9, QTableWidgetItem(self._daily_window_label(task)))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        return -1 if not selected_rows else selected_rows[0].row()

    def get_selected_task_id(self) -> str:
        row = self.get_selected_row()
        if 0 <= row < len(self.tasks):
            return str(self.tasks[row].task_id or "").strip()
        return ""

    def select_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        else:
            self.table.clearSelection()
        self.update_action_buttons()

    def select_task_id(self, task_id: str) -> None:
        target = str(task_id or "").strip()
        if not target:
            return
        for row, task in enumerate(self.tasks):
            if str(task.task_id or "").strip() == target:
                self.select_row(row)
                return

    def clear_selection(self) -> None:
        self.table.clearSelection()
        self.update_action_buttons()

    def update_action_buttons(self) -> None:
        row = self.get_selected_row()
        has_selection = 0 <= row < len(self.tasks)
        self.config_button.setEnabled(True)
        self.delete_button.setEnabled(has_selection)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row < len(self.tasks) - 1)
        self.start_task_button.setEnabled(has_selection)
        self.stop_task_button.setEnabled(has_selection)

    @staticmethod
    def _pool_label(values: list[str], unit: str) -> str:
        items = [str(item or "").strip() for item in values or [] if str(item or "").strip()]
        if not items:
            return "未选择"
        return f"{len(items)} 个{unit}：" + "、".join(items[:3]) + ("..." if len(items) > 3 else "")

    def _message_target_label(self, task: SendTaskConfig) -> str:
        if task.message_mode == MESSAGE_MODE_TEXT:
            text = " ".join(str(task.text or "").split())
            return text[:30] + "..." if len(text) > 30 else text or "空文本"
        template_ids = self._task_template_ids(task)
        return f"{len(template_ids)} 个模板" if template_ids else "未选择模板"

    @staticmethod
    def _task_template_ids(task: SendTaskConfig) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "template_ids", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "template_id", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    @staticmethod
    def _message_mode_label(value: Any) -> str:
        if value == MESSAGE_MODE_TEXT:
            return "文本"
        if value == MESSAGE_MODE_TEMPLATE:
            return "模板"
        return str(value or "未知")

    @staticmethod
    def _delay_range_label(min_ms: Any, max_ms: Any) -> str:
        try:
            left = max(0, int(min_ms))
            right = max(0, int(max_ms))
        except (TypeError, ValueError):
            left = right = 0
        if right < left:
            right = left
        return f"{left / 1000:.3f}~{right / 1000:.3f} 秒"

    @staticmethod
    def _interval_label(interval_ms: Any) -> str:
        try:
            ms = max(0, int(interval_ms))
        except (TypeError, ValueError):
            ms = 0
        return f"{ms / 1000:.3f} 秒"

    @staticmethod
    def _daily_window_label(task: SendTaskConfig) -> str:
        if not bool(getattr(task, "daily_window_enabled", False)):
            return "未开启 / 24小时循环"
        return f"{getattr(task, 'daily_start_time', '09:00')} - {getattr(task, 'daily_end_time', '21:00')}"

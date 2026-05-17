from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    AccountConfig,
    GroupConfig,
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    SCHEDULE_MODE_MANUAL,
    SendTaskConfig,
    TemplateConfig,
)
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_table,
    style_text_editor,
)


class TaskPage(QWidget):
    def __init__(self):
        super().__init__()

        self.accounts: list[AccountConfig] = []
        self.groups: list[GroupConfig] = []
        self.templates: list[TemplateConfig] = []
        self.tasks: list[SendTaskConfig] = []

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["启用", "任务名称", "账号", "目标群", "消息类型", "调度模式", "下次运行"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.name_edit = QLineEdit()
        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)

        self.account_combo = QComboBox()
        self.group_combo = QComboBox()
        self.message_mode_combo = QComboBox()
        self.message_mode_combo.addItem("文本", MESSAGE_MODE_TEXT)
        self.message_mode_combo.addItem("模板", MESSAGE_MODE_TEMPLATE)

        self.text_edit = QPlainTextEdit()
        style_text_editor(self.text_edit, 180)

        self.template_combo = QComboBox()

        self.schedule_mode_combo = QComboBox()
        self.schedule_mode_combo.addItem("手动", SCHEDULE_MODE_MANUAL)
        self.schedule_mode_combo.addItem("间隔", SCHEDULE_MODE_INTERVAL)
        self.schedule_mode_combo.addItem("每日", SCHEDULE_MODE_DAILY)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 86400 * 30)
        self.interval_spin.setValue(3600)
        self.interval_spin.setSuffix(" 秒")

        self.daily_time_edit = QLineEdit("09:00")

        self.random_delay_min_spin = QSpinBox()
        self.random_delay_min_spin.setRange(0, 86400)
        self.random_delay_min_spin.setValue(0)
        self.random_delay_min_spin.setSuffix(" 秒")

        self.random_delay_max_spin = QSpinBox()
        self.random_delay_max_spin.setRange(0, 86400)
        self.random_delay_max_spin.setValue(0)
        self.random_delay_max_spin.setSuffix(" 秒")

        self.remark_edit = QPlainTextEdit()
        style_text_editor(self.remark_edit, 140)

        self.add_button = QPushButton("新增任务")
        self.save_button = QPushButton("保存任务")
        self.delete_button = QPushButton("删除任务")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.send_once_button = QPushButton("立即发送一次")

        form_group = QGroupBox("任务配置")
        style_group_box(form_group)

        form_layout = QFormLayout(form_group)
        style_form_layout(form_layout)
        form_layout.addRow("任务名称", self.name_edit)
        form_layout.addRow("启用状态", self.enabled_check)
        form_layout.addRow("发送账号", self.account_combo)
        form_layout.addRow("目标群组", self.group_combo)
        form_layout.addRow("消息类型", self.message_mode_combo)
        form_layout.addRow("文本内容", self.text_edit)
        form_layout.addRow("模板选择", self.template_combo)
        form_layout.addRow("调度模式", self.schedule_mode_combo)
        form_layout.addRow("间隔秒数", self.interval_spin)
        form_layout.addRow("每日时间 HH:MM", self.daily_time_edit)
        form_layout.addRow("随机延迟最小秒", self.random_delay_min_spin)
        form_layout.addRow("随机延迟最大秒", self.random_delay_max_spin)
        form_layout.addRow("备注", self.remark_edit)

        apply_large_inputs(form_group)

        button_bar = QWidget()
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(14)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.send_once_button)

        table_group = QGroupBox("群发任务列表")
        style_group_box(table_group)
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(18, 20, 18, 18)
        table_layout.addWidget(self.table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_layout.addWidget(QLabel("群发任务管理"))
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
            sizes=[330, 560],
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.message_mode_combo.currentIndexChanged.connect(self.on_message_mode_changed)

        self.on_message_mode_changed()

    def set_context(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        templates: list[TemplateConfig],
    ) -> None:
        self.accounts = list(accounts)
        self.groups = list(groups)
        self.templates = list(templates)

        current_account = self.account_combo.currentData()
        current_group = self.group_combo.currentData()
        current_template = self.template_combo.currentData()

        self.account_combo.clear()
        for account in self.accounts:
            self.account_combo.addItem(account.account_name, account.account_name)

        self.group_combo.clear()
        for group in self.groups:
            label = f"{group.group_name} ({group.chat_id})"
            self.group_combo.addItem(label, group.group_id)

        self.template_combo.clear()
        self.template_combo.addItem("请选择模板", "")
        for template in self.templates:
            self.template_combo.addItem(template.template_name, template.template_id)

        self._restore_combo_value(self.account_combo, current_account)
        self._restore_combo_value(self.group_combo, current_group)
        self._restore_combo_value(self.template_combo, current_template)

    def set_tasks(self, tasks: list[SendTaskConfig]) -> None:
        self.tasks = list(tasks)
        self.table.setRowCount(0)

        for task in self.tasks:
            row = self.table.rowCount()
            self.table.insertRow(row)

            enabled_item = QTableWidgetItem("是" if task.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(task.task_name))
            self.table.setItem(row, 2, QTableWidgetItem(task.account_name))
            self.table.setItem(row, 3, QTableWidgetItem(self._group_label(task.group_id)))
            self.table.setItem(row, 4, QTableWidgetItem(self._message_mode_label(task.message_mode)))
            self.table.setItem(row, 5, QTableWidgetItem(self._schedule_mode_label(task.schedule_mode)))
            self.table.setItem(row, 6, QTableWidgetItem(task.next_run_at))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def get_selected_task_id(self) -> str:
        row = self.get_selected_row()
        if row < 0 or row >= len(self.tasks):
            return ""
        return self.tasks[row].task_id

    def get_form_task(self) -> SendTaskConfig:
        row = self.get_selected_row()

        if 0 <= row < len(self.tasks):
            task_id = self.tasks[row].task_id
            last_run_at = self.tasks[row].last_run_at
            next_run_at = self.tasks[row].next_run_at
        else:
            task_id = uuid.uuid4().hex
            last_run_at = ""
            next_run_at = ""

        return SendTaskConfig(
            task_id=task_id,
            task_name=self.name_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
            account_name=str(self.account_combo.currentData() or ""),
            group_id=str(self.group_combo.currentData() or ""),
            message_mode=str(self.message_mode_combo.currentData() or MESSAGE_MODE_TEXT),
            text=self.text_edit.toPlainText().strip(),
            template_id=str(self.template_combo.currentData() or ""),
            schedule_mode=str(self.schedule_mode_combo.currentData() or SCHEDULE_MODE_MANUAL),
            interval_seconds=int(self.interval_spin.value()),
            daily_time=self.daily_time_edit.text().strip() or "09:00",
            random_delay_min=int(self.random_delay_min_spin.value()),
            random_delay_max=int(self.random_delay_max_spin.value()),
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            remark=self.remark_edit.toPlainText().strip(),
        )

    def clear_form(self) -> None:
        self.table.clearSelection()
        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self.account_combo.setCurrentIndex(0 if self.account_combo.count() else -1)
        self.group_combo.setCurrentIndex(0 if self.group_combo.count() else -1)
        self.message_mode_combo.setCurrentIndex(0)
        self.text_edit.clear()
        self.template_combo.setCurrentIndex(0 if self.template_combo.count() else -1)
        self.schedule_mode_combo.setCurrentIndex(0)
        self.interval_spin.setValue(3600)
        self.daily_time_edit.setText("09:00")
        self.random_delay_min_spin.setValue(0)
        self.random_delay_max_spin.setValue(0)
        self.remark_edit.clear()
        self.on_message_mode_changed()

    def on_selection_changed(self) -> None:
        row = self.get_selected_row()
        if row < 0 or row >= len(self.tasks):
            return

        task = self.tasks[row]
        self.name_edit.setText(task.task_name)
        self.enabled_check.setChecked(task.enabled)
        self._restore_combo_value(self.account_combo, task.account_name)
        self._restore_combo_value(self.group_combo, task.group_id)
        self._restore_combo_value(self.message_mode_combo, task.message_mode)
        self.text_edit.setPlainText(task.text)
        self._restore_combo_value(self.template_combo, task.template_id)
        self._restore_combo_value(self.schedule_mode_combo, task.schedule_mode)
        self.interval_spin.setValue(max(1, int(task.interval_seconds)))
        self.daily_time_edit.setText(task.daily_time or "09:00")
        self.random_delay_min_spin.setValue(max(0, int(task.random_delay_min)))
        self.random_delay_max_spin.setValue(max(0, int(task.random_delay_max)))
        self.remark_edit.setPlainText(task.remark)
        self.on_message_mode_changed()

    def on_message_mode_changed(self) -> None:
        mode = self.message_mode_combo.currentData()
        is_text = mode == MESSAGE_MODE_TEXT
        is_template = mode == MESSAGE_MODE_TEMPLATE

        self.text_edit.setEnabled(is_text)
        self.template_combo.setEnabled(is_template)

    @staticmethod
    def _restore_combo_value(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _group_label(self, group_id: str) -> str:
        group = next((item for item in self.groups if item.group_id == group_id), None)
        if group is None:
            return group_id
        return f"{group.group_name} ({group.chat_id})"

    @staticmethod
    def _message_mode_label(mode: str) -> str:
        if mode == MESSAGE_MODE_TEMPLATE:
            return "模板"
        return "文本"

    @staticmethod
    def _schedule_mode_label(mode: str) -> str:
        if mode == SCHEDULE_MODE_INTERVAL:
            return "间隔"
        if mode == SCHEDULE_MODE_DAILY:
            return "每日"
        return "手动"
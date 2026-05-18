from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_SINGLE,
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

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "启用",
                "任务名称",
                "账号池",
                "账号轮换",
                "目标群组",
                "群组轮换",
                "账号延迟",
                "群组延迟",
                "消息类型",
                "调度模式",
                "下次运行",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.name_edit = QLineEdit()
        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)

        self.account_list = QListWidget()
        self.account_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.account_list.setMinimumHeight(132)

        self.account_rotate_mode_combo = QComboBox()
        self.account_rotate_mode_combo.addItem(
            "单账号",
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        self.account_rotate_mode_combo.addItem(
            "顺序轮换",
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        )

        self.current_account_index_label = QLabel("未选择账号")
        self.current_account_index_label.setMinimumHeight(36)
        self.current_account_index_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.account_delay_spin = QSpinBox()
        self.account_delay_spin.setRange(0, 86400)
        self.account_delay_spin.setValue(0)
        self.account_delay_spin.setSuffix(" 秒")

        self.group_list = QListWidget()
        self.group_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.group_list.setMinimumHeight(132)

        self.group_rotate_mode_combo = QComboBox()
        self.group_rotate_mode_combo.addItem(
            "单群组",
            GROUP_ROTATE_MODE_SINGLE,
        )
        self.group_rotate_mode_combo.addItem(
            "顺序轮询",
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        )

        self.current_group_index_label = QLabel("未选择群组")
        self.current_group_index_label.setMinimumHeight(36)
        self.current_group_index_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.group_delay_spin = QSpinBox()
        self.group_delay_spin.setRange(0, 86400)
        self.group_delay_spin.setValue(0)
        self.group_delay_spin.setSuffix(" 秒")

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
        form_layout.addRow("发送账号池", self.account_list)
        form_layout.addRow("账号轮换模式", self.account_rotate_mode_combo)
        form_layout.addRow("当前账号序号", self.current_account_index_label)
        form_layout.addRow("账号延迟", self.account_delay_spin)
        form_layout.addRow("目标群组池", self.group_list)
        form_layout.addRow("群组轮询模式", self.group_rotate_mode_combo)
        form_layout.addRow("当前群组序号", self.current_group_index_label)
        form_layout.addRow("群组延迟", self.group_delay_spin)
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
        self.account_list.itemSelectionChanged.connect(
            self.update_current_account_index_label
        )
        self.account_rotate_mode_combo.currentIndexChanged.connect(
            self.update_current_account_index_label
        )
        self.group_list.itemSelectionChanged.connect(
            self.update_current_group_index_label
        )
        self.group_rotate_mode_combo.currentIndexChanged.connect(
            self.update_current_group_index_label
        )

        self.on_message_mode_changed()
        self.update_current_account_index_label()
        self.update_current_group_index_label()

    def set_context(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        templates: list[TemplateConfig],
    ) -> None:
        self.accounts = list(accounts)
        self.groups = list(groups)
        self.templates = list(templates)

        current_account_names = self._get_selected_account_names()
        current_group_ids = self._get_selected_group_ids()
        current_template = self.template_combo.currentData()

        self.account_list.blockSignals(True)
        self.account_list.clear()

        for account in self.accounts:
            item = QListWidgetItem(account.account_name)
            item.setData(Qt.ItemDataRole.UserRole, account.account_name)
            self.account_list.addItem(item)

        self.account_list.blockSignals(False)
        self._restore_account_selection(current_account_names)

        self.group_list.blockSignals(True)
        self.group_list.clear()

        for group in self.groups:
            label = f"{group.group_name} ({group.chat_id})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, group.group_id)
            self.group_list.addItem(item)

        self.group_list.blockSignals(False)
        self._restore_group_selection(current_group_ids)

        self.template_combo.clear()
        self.template_combo.addItem("请选择模板", "")

        for template in self.templates:
            self.template_combo.addItem(template.template_name, template.template_id)

        self._restore_combo_value(self.template_combo, current_template)
        self.update_current_account_index_label()
        self.update_current_group_index_label()

    def set_tasks(self, tasks: list[SendTaskConfig]) -> None:
        self.tasks = list(tasks)
        self.table.setRowCount(0)

        for task in self.tasks:
            row = self.table.rowCount()
            self.table.insertRow(row)

            enabled_item = QTableWidgetItem("是" if task.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, enabled_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(task.task_name or "")))
            self.table.setItem(row, 2, QTableWidgetItem(self._account_pool_label(task)))
            self.table.setItem(row, 3, QTableWidgetItem(self._account_rotate_mode_label(task)))
            self.table.setItem(row, 4, QTableWidgetItem(self._group_pool_label(task)))
            self.table.setItem(row, 5, QTableWidgetItem(self._group_rotate_mode_label(task)))
            self.table.setItem(
                row,
                6,
                QTableWidgetItem(f"{self._safe_int(getattr(task, 'account_delay_seconds', 0), 0)} 秒"),
            )
            self.table.setItem(
                row,
                7,
                QTableWidgetItem(f"{self._safe_int(getattr(task, 'group_delay_seconds', 0), 0)} 秒"),
            )
            self.table.setItem(
                row,
                8,
                QTableWidgetItem(self._message_mode_label(task.message_mode)),
            )
            self.table.setItem(
                row,
                9,
                QTableWidgetItem(self._schedule_mode_label(task.schedule_mode)),
            )
            self.table.setItem(row, 10, QTableWidgetItem(str(task.next_run_at or "")))

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
            existing_task = self.tasks[row]
            task_id = existing_task.task_id
            last_run_at = existing_task.last_run_at
            next_run_at = existing_task.next_run_at
            current_account_index = self._safe_non_negative_int(
                getattr(existing_task, "current_account_index", 0),
                0,
            )
            current_group_index = self._safe_non_negative_int(
                getattr(existing_task, "current_group_index", 0),
                0,
            )
        else:
            task_id = uuid.uuid4().hex
            last_run_at = ""
            next_run_at = ""
            current_account_index = 0
            current_group_index = 0

        account_names = self._get_selected_account_names()
        account_rotate_mode = str(
            self.account_rotate_mode_combo.currentData()
            or ACCOUNT_ROTATE_MODE_SINGLE
        )

        if account_rotate_mode == ACCOUNT_ROTATE_MODE_SINGLE and account_names:
            account_names = [account_names[0]]

        account_name = account_names[0] if account_names else ""

        if account_names:
            current_account_index = current_account_index % len(account_names)
        else:
            current_account_index = 0

        group_ids = self._get_selected_group_ids()
        group_rotate_mode = str(
            self.group_rotate_mode_combo.currentData()
            or GROUP_ROTATE_MODE_SINGLE
        )

        if group_rotate_mode == GROUP_ROTATE_MODE_SINGLE and group_ids:
            group_ids = [group_ids[0]]

        group_id = group_ids[0] if group_ids else ""

        if group_ids:
            current_group_index = current_group_index % len(group_ids)
        else:
            current_group_index = 0

        daily_time = self.daily_time_edit.text().strip() or "09:00"
        if self.schedule_mode_combo.currentData() == SCHEDULE_MODE_DAILY:
            self._validate_daily_time(daily_time)

        random_delay_min = int(self.random_delay_min_spin.value())
        random_delay_max = int(self.random_delay_max_spin.value())

        if random_delay_max < random_delay_min:
            raise ValueError("随机延迟最大秒不能小于随机延迟最小秒")

        return SendTaskConfig(
            task_id=task_id,
            task_name=self.name_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
            account_name=account_name,
            account_names=account_names,
            account_rotate_mode=account_rotate_mode,
            current_account_index=current_account_index,
            account_delay_seconds=int(self.account_delay_spin.value()),
            group_id=group_id,
            group_ids=group_ids,
            group_rotate_mode=group_rotate_mode,
            current_group_index=current_group_index,
            group_delay_seconds=int(self.group_delay_spin.value()),
            message_mode=str(self.message_mode_combo.currentData() or MESSAGE_MODE_TEXT),
            text=self.text_edit.toPlainText().strip(),
            template_id=str(self.template_combo.currentData() or ""),
            schedule_mode=str(
                self.schedule_mode_combo.currentData() or SCHEDULE_MODE_MANUAL
            ),
            interval_seconds=int(self.interval_spin.value()),
            daily_time=daily_time,
            random_delay_min=random_delay_min,
            random_delay_max=random_delay_max,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            remark=self.remark_edit.toPlainText().strip(),
        )

    def clear_form(self) -> None:
        self.table.clearSelection()

        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self._restore_account_selection([], select_first_when_empty=True)
        self.account_rotate_mode_combo.setCurrentIndex(0)
        self.account_delay_spin.setValue(0)
        self._restore_group_selection([], select_first_when_empty=True)
        self.group_rotate_mode_combo.setCurrentIndex(0)
        self.group_delay_spin.setValue(0)
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
        self.update_current_account_index_label()
        self.update_current_group_index_label()

    def on_selection_changed(self) -> None:
        row = self.get_selected_row()
        if row < 0 or row >= len(self.tasks):
            return

        task = self.tasks[row]
        account_names = self._task_account_names(task)
        group_ids = self._task_group_ids(task)

        self.name_edit.setText(str(task.task_name or ""))
        self.enabled_check.setChecked(bool(task.enabled))
        self._restore_account_selection(account_names)
        self._restore_combo_value(
            self.account_rotate_mode_combo,
            self._task_account_rotate_mode(task),
        )
        self.account_delay_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "account_delay_seconds", 0),
                0,
            )
        )

        self._restore_group_selection(group_ids)
        self._restore_combo_value(
            self.group_rotate_mode_combo,
            self._task_group_rotate_mode(task),
        )
        self.group_delay_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "group_delay_seconds", 0),
                0,
            )
        )

        self._restore_combo_value(self.message_mode_combo, task.message_mode)
        self.text_edit.setPlainText(str(task.text or ""))
        self._restore_combo_value(self.template_combo, task.template_id)
        self._restore_combo_value(self.schedule_mode_combo, task.schedule_mode)
        self.interval_spin.setValue(max(1, self._safe_int(task.interval_seconds, 3600)))
        self.daily_time_edit.setText(str(task.daily_time or "09:00"))
        self.random_delay_min_spin.setValue(
            self._safe_non_negative_int(task.random_delay_min, 0)
        )
        self.random_delay_max_spin.setValue(
            self._safe_non_negative_int(task.random_delay_max, 0)
        )
        self.remark_edit.setPlainText(str(task.remark or ""))

        self.on_message_mode_changed()
        self.update_current_account_index_label()
        self.update_current_group_index_label()

    def on_message_mode_changed(self) -> None:
        mode = self.message_mode_combo.currentData()
        is_text = mode == MESSAGE_MODE_TEXT
        is_template = mode == MESSAGE_MODE_TEMPLATE

        self.text_edit.setEnabled(is_text)
        self.template_combo.setEnabled(is_template)

    def update_current_account_index_label(self) -> None:
        account_names = self._get_selected_account_names()

        if not account_names:
            self.current_account_index_label.setText("未选择账号")
            return

        current_index = 0
        row = self.get_selected_row()

        if 0 <= row < len(self.tasks):
            current_index = self._safe_non_negative_int(
                getattr(self.tasks[row], "current_account_index", 0),
                0,
            )

        current_index = current_index % len(account_names)
        current_account_name = account_names[current_index]

        if self.account_rotate_mode_combo.currentData() == ACCOUNT_ROTATE_MODE_ROUND_ROBIN:
            text = (
                f"第 {current_index + 1} 个 / 共 {len(account_names)} 个"
                f"（当前：{current_account_name}）"
            )
        else:
            text = f"单账号：{account_names[0]}"

        self.current_account_index_label.setText(text)

    def update_current_group_index_label(self) -> None:
        group_ids = self._get_selected_group_ids()

        if not group_ids:
            self.current_group_index_label.setText("未选择群组")
            return

        current_index = 0
        row = self.get_selected_row()

        if 0 <= row < len(self.tasks):
            current_index = self._safe_non_negative_int(
                getattr(self.tasks[row], "current_group_index", 0),
                0,
            )

        current_index = current_index % len(group_ids)
        current_group_id = group_ids[current_index]
        current_group_label = self._group_label(current_group_id)

        if self.group_rotate_mode_combo.currentData() == GROUP_ROTATE_MODE_ROUND_ROBIN:
            text = (
                f"第 {current_index + 1} 个 / 共 {len(group_ids)} 个"
                f"（当前：{current_group_label}）"
            )
        else:
            text = f"单群组：{self._group_label(group_ids[0])}"

        self.current_group_index_label.setText(text)

    def _get_selected_account_names(self) -> list[str]:
        account_names: list[str] = []

        for item in self.account_list.selectedItems():
            account_name = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if account_name and account_name not in account_names:
                account_names.append(account_name)

        return account_names

    def _get_selected_group_ids(self) -> list[str]:
        group_ids: list[str] = []

        for item in self.group_list.selectedItems():
            group_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if group_id and group_id not in group_ids:
                group_ids.append(group_id)

        return group_ids

    def _restore_account_selection(
        self,
        account_names: list[str],
        select_first_when_empty: bool = False,
    ) -> None:
        wanted_names = {
            str(account_name or "").strip()
            for account_name in account_names
            if str(account_name or "").strip()
        }

        self.account_list.blockSignals(True)
        self.account_list.clearSelection()

        matched = False

        for row in range(self.account_list.count()):
            item = self.account_list.item(row)
            account_name = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if account_name in wanted_names:
                item.setSelected(True)
                matched = True

        if not matched and select_first_when_empty and self.account_list.count() > 0:
            self.account_list.item(0).setSelected(True)

        self.account_list.blockSignals(False)
        self.update_current_account_index_label()

    def _restore_group_selection(
        self,
        group_ids: list[str],
        select_first_when_empty: bool = False,
    ) -> None:
        wanted_group_ids = {
            str(group_id or "").strip()
            for group_id in group_ids
            if str(group_id or "").strip()
        }

        self.group_list.blockSignals(True)
        self.group_list.clearSelection()

        matched = False

        for row in range(self.group_list.count()):
            item = self.group_list.item(row)
            group_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if group_id in wanted_group_ids:
                item.setSelected(True)
                matched = True

        if not matched and select_first_when_empty and self.group_list.count() > 0:
            self.group_list.item(0).setSelected(True)

        self.group_list.blockSignals(False)
        self.update_current_group_index_label()

    @staticmethod
    def _restore_combo_value(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _task_account_names(self, task: SendTaskConfig) -> list[str]:
        account_names: list[str] = []

        for raw_account_name in getattr(task, "account_names", []) or []:
            account_name = str(raw_account_name or "").strip()

            if account_name and account_name not in account_names:
                account_names.append(account_name)

        legacy_account_name = str(getattr(task, "account_name", "") or "").strip()

        if legacy_account_name and legacy_account_name not in account_names:
            account_names.insert(0, legacy_account_name)

        return account_names

    def _task_group_ids(self, task: SendTaskConfig) -> list[str]:
        group_ids: list[str] = []

        for raw_group_id in getattr(task, "group_ids", []) or []:
            group_id = str(raw_group_id or "").strip()

            if group_id and group_id not in group_ids:
                group_ids.append(group_id)

        legacy_group_id = str(getattr(task, "group_id", "") or "").strip()

        if legacy_group_id and legacy_group_id not in group_ids:
            group_ids.insert(0, legacy_group_id)

        return group_ids

    @staticmethod
    def _task_account_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            ACCOUNT_ROTATE_MODE_SINGLE,
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        }:
            return ACCOUNT_ROTATE_MODE_SINGLE

        return rotate_mode

    @staticmethod
    def _task_group_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "group_rotate_mode", GROUP_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            GROUP_ROTATE_MODE_SINGLE,
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        }:
            return GROUP_ROTATE_MODE_SINGLE

        return rotate_mode

    def _account_pool_label(self, task: SendTaskConfig) -> str:
        account_names = self._task_account_names(task)

        if not account_names:
            return ""

        return "、".join(account_names)

    def _group_pool_label(self, task: SendTaskConfig) -> str:
        group_ids = self._task_group_ids(task)

        if not group_ids:
            return ""

        return "、".join(self._group_label(group_id) for group_id in group_ids)

    def _account_rotate_mode_label(self, task: SendTaskConfig) -> str:
        account_names = self._task_account_names(task)
        rotate_mode = self._task_account_rotate_mode(task)

        if rotate_mode == ACCOUNT_ROTATE_MODE_ROUND_ROBIN:
            account_count = max(1, len(account_names))
            current_index = self._safe_non_negative_int(
                getattr(task, "current_account_index", 0),
                0,
            )
            current_index = current_index % account_count
            return f"顺序轮换（{current_index + 1}/{account_count}）"

        return "单账号"

    def _group_rotate_mode_label(self, task: SendTaskConfig) -> str:
        group_ids = self._task_group_ids(task)
        rotate_mode = self._task_group_rotate_mode(task)

        if rotate_mode == GROUP_ROTATE_MODE_ROUND_ROBIN:
            group_count = max(1, len(group_ids))
            current_index = self._safe_non_negative_int(
                getattr(task, "current_group_index", 0),
                0,
            )
            current_index = current_index % group_count
            return f"顺序轮询（{current_index + 1}/{group_count}）"

        return "单群组"

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

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _safe_non_negative_int(cls, value: Any, default: int = 0) -> int:
        number = cls._safe_int(value, default)

        if number < 0:
            return 0

        return number

    @staticmethod
    def _validate_daily_time(value: str) -> None:
        raw_text = str(value or "").strip()

        try:
            hour_text, minute_text = raw_text.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except Exception as exc:
            raise ValueError("每日时间格式必须是 HH:MM，例如 09:30") from exc

        if hour < 0 or hour > 23:
            raise ValueError("每日时间小时必须在 00-23 之间")

        if minute < 0 or minute > 59:
            raise ValueError("每日时间分钟必须在 00-59 之间")
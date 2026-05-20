from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    AccountConfig,
    GroupConfig,
    SendTaskConfig,
    Settings,
    TemplateConfig,
)
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_list_widget,
    style_table,
    style_text_editor,
)
from app.gui.widgets.no_wheel import (
    NoWheelComboBox,
    NoWheelSpinBox,
    NoWheelTimeEdit,
)


class TaskPage(QWidget):
    def __init__(self, settings: Settings | None = None):
        super().__init__()

        self.accounts: list[AccountConfig] = []
        self.groups: list[GroupConfig] = []
        self.templates: list[TemplateConfig] = []
        self.tasks: list[SendTaskConfig] = []
        self.settings = settings or Settings()

        self.table = QTableWidget(0, 12)
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
                "模板池",
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
        style_list_widget(self.account_list, min_height=132)

        self.account_rotate_mode_combo = NoWheelComboBox()
        self.account_rotate_mode_combo.addItem(
            "单账号",
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        self.account_rotate_mode_combo.addItem(
            "多账号轮询",
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        )

        self.current_account_index_label = QLabel("未选择账号")
        self.current_account_index_label.setMinimumHeight(36)
        self.current_account_index_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.account_delay_min_ms_spin = NoWheelSpinBox()
        self.account_delay_min_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.account_delay_min_ms_spin.setSingleStep(100)
        self.account_delay_min_ms_spin.setSuffix(" 毫秒")

        self.account_delay_max_ms_spin = NoWheelSpinBox()
        self.account_delay_max_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.account_delay_max_ms_spin.setSingleStep(100)
        self.account_delay_max_ms_spin.setSuffix(" 毫秒")

        self.group_list = QListWidget()
        self.group_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        style_list_widget(self.group_list, min_height=132)

        self.group_rotate_mode_combo = NoWheelComboBox()
        self.group_rotate_mode_combo.addItem(
            "单群组",
            GROUP_ROTATE_MODE_SINGLE,
        )
        self.group_rotate_mode_combo.addItem(
            "多群组轮询",
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        )

        self.current_group_index_label = QLabel("未选择群组")
        self.current_group_index_label.setMinimumHeight(36)
        self.current_group_index_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.group_delay_min_ms_spin = NoWheelSpinBox()
        self.group_delay_min_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.group_delay_min_ms_spin.setSingleStep(100)
        self.group_delay_min_ms_spin.setSuffix(" 毫秒")

        self.group_delay_max_ms_spin = NoWheelSpinBox()
        self.group_delay_max_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.group_delay_max_ms_spin.setSingleStep(100)
        self.group_delay_max_ms_spin.setSuffix(" 毫秒")

        self.message_mode_combo = NoWheelComboBox()
        self.message_mode_combo.addItem("模板", MESSAGE_MODE_TEMPLATE)
        self.message_mode_combo.addItem("文本", MESSAGE_MODE_TEXT)

        self.text_edit = QPlainTextEdit()
        style_text_editor(self.text_edit, 180)

        self.template_list = QListWidget()
        self.template_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        style_list_widget(self.template_list, min_height=132)

        self.schedule_mode_combo = NoWheelComboBox()
        self.schedule_mode_combo.addItem("间隔", SCHEDULE_MODE_INTERVAL)
        self.schedule_mode_combo.addItem("每日", SCHEDULE_MODE_DAILY)

        self.interval_ms_spin = NoWheelSpinBox()
        self.interval_ms_spin.setRange(0, 365 * 24 * 60 * 60 * 1000)
        self.interval_ms_spin.setSingleStep(1000)
        self.interval_ms_spin.setSuffix(" 毫秒")
        self.interval_ms_spin.setToolTip(
            "0 表示任务结束后立即进入下一轮到期状态；调度扫描间隔仍由配置管理页控制"
        )

        self.daily_time_edit = NoWheelTimeEdit()
        self.daily_time_edit.setDisplayFormat("HH:mm")
        self.daily_time_edit.setTime(QTime(9, 0))

        self.remark_edit = QPlainTextEdit()
        style_text_editor(self.remark_edit, 140)

        self.add_button = QPushButton("新增任务")
        self.save_button = QPushButton("保存任务")
        self.delete_button = QPushButton("删除任务")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")

        form_group = QGroupBox("任务配置")
        style_group_box(form_group)

        form_layout = QFormLayout(form_group)
        style_form_layout(form_layout)
        form_layout.addRow("任务名称", self.name_edit)
        form_layout.addRow("启用状态", self.enabled_check)
        form_layout.addRow("发送账号池", self.account_list)
        form_layout.addRow("账号轮换模式", self.account_rotate_mode_combo)
        form_layout.addRow("当前账号序号", self.current_account_index_label)
        form_layout.addRow("账号延迟最小值", self.account_delay_min_ms_spin)
        form_layout.addRow("账号延迟最大值", self.account_delay_max_ms_spin)
        form_layout.addRow("目标群组池", self.group_list)
        form_layout.addRow("群组轮询模式", self.group_rotate_mode_combo)
        form_layout.addRow("当前群组序号", self.current_group_index_label)
        form_layout.addRow("群组延迟最小值", self.group_delay_min_ms_spin)
        form_layout.addRow("群组延迟最大值", self.group_delay_max_ms_spin)
        form_layout.addRow("消息类型", self.message_mode_combo)
        form_layout.addRow("文本内容", self.text_edit)
        form_layout.addRow("模板池", self.template_list)
        form_layout.addRow("调度模式", self.schedule_mode_combo)
        form_layout.addRow("间隔时间", self.interval_ms_spin)
        form_layout.addRow("每日时间", self.daily_time_edit)
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

        table_group = QGroupBox("群发任务列表")
        style_group_box(table_group)

        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(18, 20, 18, 18)
        table_layout.addWidget(self.table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        title_label = QLabel("群发任务管理")
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
        settings: Settings | None = None,
    ) -> None:
        self.accounts = list(accounts)
        self.groups = list(groups)
        self.templates = list(templates)

        if settings is not None:
            self.settings = settings

        current_account_names = self._get_selected_account_names()
        current_group_ids = self._get_selected_group_ids()
        current_template_ids = self._get_selected_template_ids()

        self.account_list.blockSignals(True)
        self.account_list.clear()

        for account in self.accounts:
            item = QListWidgetItem(account.account_name)
            item.setData(Qt.ItemDataRole.UserRole, account.account_name)
            if not account.enabled:
                item.setToolTip("账号未启用")
            self.account_list.addItem(item)

        self.account_list.blockSignals(False)
        self._restore_account_selection(current_account_names)

        self.group_list.blockSignals(True)
        self.group_list.clear()

        for group in self.groups:
            label = f"{group.group_name} ({group.chat_id})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, group.group_id)
            if not group.enabled:
                item.setToolTip("群组未启用")
            self.group_list.addItem(item)

        self.group_list.blockSignals(False)
        self._restore_group_selection(current_group_ids)

        self.template_list.blockSignals(True)
        self.template_list.clear()

        for template in self.templates:
            label = template.template_name
            if not template.enabled:
                label = f"{label}（未启用）"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            self.template_list.addItem(item)

        self.template_list.blockSignals(False)
        self._restore_template_selection(current_template_ids)

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
                QTableWidgetItem(self._delay_range_label(
                    getattr(task, "account_delay_min_ms", 0),
                    getattr(task, "account_delay_max_ms", 0),
                )),
            )
            self.table.setItem(
                row,
                7,
                QTableWidgetItem(self._delay_range_label(
                    getattr(task, "group_delay_min_ms", 0),
                    getattr(task, "group_delay_max_ms", 0),
                )),
            )
            self.table.setItem(
                row,
                8,
                QTableWidgetItem(self._message_mode_label(task.message_mode)),
            )
            self.table.setItem(
                row,
                9,
                QTableWidgetItem(self._template_pool_label(task)),
            )
            self.table.setItem(
                row,
                10,
                QTableWidgetItem(self._schedule_mode_label(task.schedule_mode)),
            )
            self.table.setItem(row, 11, QTableWidgetItem(str(task.next_run_at or "")))

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

        account_delay_min_ms = int(self.account_delay_min_ms_spin.value())
        account_delay_max_ms = int(self.account_delay_max_ms_spin.value())
        if account_delay_max_ms < account_delay_min_ms:
            raise ValueError("账号延迟最大值不能小于账号延迟最小值")

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

        group_delay_min_ms = int(self.group_delay_min_ms_spin.value())
        group_delay_max_ms = int(self.group_delay_max_ms_spin.value())
        if group_delay_max_ms < group_delay_min_ms:
            raise ValueError("群组延迟最大值不能小于群组延迟最小值")

        template_ids = self._get_selected_template_ids()
        template_id = template_ids[0] if template_ids else ""

        schedule_mode = str(
            self.schedule_mode_combo.currentData()
            or SCHEDULE_MODE_INTERVAL
        )

        daily_time = self.daily_time_edit.time().toString("HH:mm")
        if schedule_mode == SCHEDULE_MODE_DAILY:
            self._validate_daily_time(daily_time)

        interval_ms = int(self.interval_ms_spin.value())

        return SendTaskConfig(
            task_id=task_id,
            task_name=self.name_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
            account_name=account_name,
            account_names=account_names,
            account_rotate_mode=account_rotate_mode,
            current_account_index=current_account_index,
            account_delay_min_ms=account_delay_min_ms,
            account_delay_max_ms=account_delay_max_ms,
            account_delay_seconds=int(account_delay_min_ms // 1000),
            group_id=group_id,
            group_ids=group_ids,
            group_rotate_mode=group_rotate_mode,
            current_group_index=current_group_index,
            group_delay_min_ms=group_delay_min_ms,
            group_delay_max_ms=group_delay_max_ms,
            group_delay_seconds=int(group_delay_min_ms // 1000),
            message_mode=str(self.message_mode_combo.currentData() or MESSAGE_MODE_TEMPLATE),
            text=self.text_edit.toPlainText().strip(),
            template_ids=template_ids,
            template_id=template_id,
            schedule_mode=schedule_mode,
            interval_ms=interval_ms,
            interval_seconds=int(interval_ms // 1000),
            daily_time=daily_time,
            random_delay_min=0,
            random_delay_max=0,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            remark=self.remark_edit.toPlainText().strip(),
        )

    def clear_form(self) -> None:
        self.table.clearSelection()

        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self._restore_account_selection([], select_first_when_empty=True)
        self._restore_combo_value(
            self.account_rotate_mode_combo,
            str(getattr(self.settings, "default_task_account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE)),
        )
        self.account_delay_min_ms_spin.setValue(
            int(getattr(self.settings, "default_task_account_delay_min_ms", 0))
        )
        self.account_delay_max_ms_spin.setValue(
            int(getattr(self.settings, "default_task_account_delay_max_ms", 0))
        )
        self._restore_group_selection([], select_first_when_empty=True)
        self._restore_combo_value(
            self.group_rotate_mode_combo,
            str(getattr(self.settings, "default_task_group_rotate_mode", GROUP_ROTATE_MODE_SINGLE)),
        )
        self.group_delay_min_ms_spin.setValue(
            int(getattr(self.settings, "default_task_group_delay_min_ms", 0))
        )
        self.group_delay_max_ms_spin.setValue(
            int(getattr(self.settings, "default_task_group_delay_max_ms", 0))
        )
        self._restore_combo_value(
            self.message_mode_combo,
            str(getattr(self.settings, "default_task_message_mode", MESSAGE_MODE_TEMPLATE)),
        )
        self.text_edit.clear()
        self._restore_template_selection([])
        self._restore_combo_value(
            self.schedule_mode_combo,
            str(getattr(self.settings, "default_task_schedule_mode", SCHEDULE_MODE_INTERVAL)),
        )
        self.interval_ms_spin.setValue(
            int(getattr(self.settings, "default_task_interval_ms", 3600000))
        )
        self.daily_time_edit.setTime(
            self._time_from_text(str(getattr(self.settings, "default_task_daily_time", "09:00")))
        )
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
        template_ids = self._task_template_ids(task)

        self.name_edit.setText(str(task.task_name or ""))
        self.enabled_check.setChecked(bool(task.enabled))
        self._restore_account_selection(account_names)
        self._restore_combo_value(
            self.account_rotate_mode_combo,
            self._task_account_rotate_mode(task),
        )
        self.account_delay_min_ms_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "account_delay_min_ms", 0),
                0,
            )
        )
        self.account_delay_max_ms_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "account_delay_max_ms", 0),
                0,
            )
        )

        self._restore_group_selection(group_ids)
        self._restore_combo_value(
            self.group_rotate_mode_combo,
            self._task_group_rotate_mode(task),
        )
        self.group_delay_min_ms_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "group_delay_min_ms", 0),
                0,
            )
        )
        self.group_delay_max_ms_spin.setValue(
            self._safe_non_negative_int(
                getattr(task, "group_delay_max_ms", 0),
                0,
            )
        )

        self._restore_combo_value(self.message_mode_combo, task.message_mode)
        self.text_edit.setPlainText(str(task.text or ""))
        self._restore_template_selection(template_ids)
        self._restore_combo_value(self.schedule_mode_combo, task.schedule_mode)
        self.interval_ms_spin.setValue(
            self._safe_non_negative_int(getattr(task, "interval_ms", 3600000), 3600000)
        )
        self.daily_time_edit.setTime(self._time_from_text(str(task.daily_time or "09:00")))
        self.remark_edit.setPlainText(str(task.remark or ""))

        self.on_message_mode_changed()
        self.update_current_account_index_label()
        self.update_current_group_index_label()

    def on_message_mode_changed(self) -> None:
        mode = self.message_mode_combo.currentData()
        is_text = mode == MESSAGE_MODE_TEXT
        is_template = mode == MESSAGE_MODE_TEMPLATE

        self.text_edit.setEnabled(is_text)
        self.template_list.setEnabled(is_template)

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

    def _get_selected_template_ids(self) -> list[str]:
        template_ids: list[str] = []

        for item in self.template_list.selectedItems():
            template_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if template_id and template_id not in template_ids:
                template_ids.append(template_id)

        return template_ids

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

    def _restore_template_selection(
        self,
        template_ids: list[str],
        select_first_when_empty: bool = False,
    ) -> None:
        wanted_template_ids = {
            str(template_id or "").strip()
            for template_id in template_ids
            if str(template_id or "").strip()
        }

        self.template_list.blockSignals(True)
        self.template_list.clearSelection()

        matched = False

        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            template_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

            if template_id in wanted_template_ids:
                item.setSelected(True)
                matched = True

        if not matched and select_first_when_empty and self.template_list.count() > 0:
            self.template_list.item(0).setSelected(True)

        self.template_list.blockSignals(False)

    @staticmethod
    def _restore_combo_value(combo: NoWheelComboBox, value) -> None:
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

    def _task_template_ids(self, task: SendTaskConfig) -> list[str]:
        template_ids: list[str] = []

        for raw_template_id in getattr(task, "template_ids", []) or []:
            template_id = str(raw_template_id or "").strip()

            if template_id and template_id not in template_ids:
                template_ids.append(template_id)

        legacy_template_id = str(getattr(task, "template_id", "") or "").strip()

        if legacy_template_id and legacy_template_id not in template_ids:
            template_ids.insert(0, legacy_template_id)

        return template_ids

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

    def _template_pool_label(self, task: SendTaskConfig) -> str:
        template_ids = self._task_template_ids(task)

        if not template_ids:
            return ""

        return "、".join(self._template_label(template_id) for template_id in template_ids)

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
            return f"多账号轮询（{current_index + 1}/{account_count}）"

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
            return f"多群组轮询（{current_index + 1}/{group_count}）"

        return "单群组"

    def _group_label(self, group_id: str) -> str:
        group = next((item for item in self.groups if item.group_id == group_id), None)
        if group is None:
            return group_id
        return f"{group.group_name} ({group.chat_id})"

    def _template_label(self, template_id: str) -> str:
        template = next(
            (item for item in self.templates if item.template_id == template_id),
            None,
        )
        if template is None:
            return template_id
        return template.template_name

    @staticmethod
    def _message_mode_label(mode: str) -> str:
        if mode == MESSAGE_MODE_TEXT:
            return "文本"
        return "模板"

    @staticmethod
    def _schedule_mode_label(mode: str) -> str:
        if mode == SCHEDULE_MODE_DAILY:
            return "每日"
        return "间隔"

    @staticmethod
    def _delay_range_label(min_ms: Any, max_ms: Any) -> str:
        safe_min = TaskPage._safe_non_negative_int(min_ms, 0)
        safe_max = TaskPage._safe_non_negative_int(max_ms, safe_min)

        if safe_max < safe_min:
            safe_max = safe_min

        if safe_min == safe_max:
            return f"{safe_min} 毫秒"

        return f"{safe_min} - {safe_max} 毫秒"

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

    @staticmethod
    def _time_from_text(value: str) -> QTime:
        parsed = QTime.fromString(str(value or "09:00").strip(), "HH:mm")

        if parsed.isValid():
            return parsed

        return QTime(9, 0)
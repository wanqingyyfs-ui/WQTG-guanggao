from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import QTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    PAIRING_MODE_ROTATE,
    AccountConfig,
    GroupConfig,
    SendTaskConfig,
    Settings,
    TemplateConfig,
)
from app.gui.pages.layout_utils import apply_large_inputs, style_text_editor
from app.gui.widgets.check_combo_box import CheckComboBox
from app.gui.widgets.no_wheel import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelTimeEdit

MAX_SECONDS = 365 * 24 * 60 * 60


class TaskForm(QWidget):
    add_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accounts: list[AccountConfig] = []
        self.groups: list[GroupConfig] = []
        self.templates: list[TemplateConfig] = []
        self.tasks: list[SendTaskConfig] = []
        self.account_group_definitions: list[str] = []
        self.group_group_definitions: list[str] = []
        self.settings = Settings()
        self._current_task: SendTaskConfig | None = None
        self._current_task_id = ""

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("任务名称")
        self.enabled_check = QCheckBox("启用任务")

        self.account_group_combo = CheckComboBox()
        self.account_group_combo.lineEdit().setPlaceholderText("请选择账号组")
        self.group_group_combo = CheckComboBox()
        self.group_group_combo.lineEdit().setPlaceholderText("请选择群聊组")

        self.account_delay_min_seconds_spin = self._new_seconds_spin()
        self.account_delay_max_seconds_spin = self._new_seconds_spin()
        self.group_delay_min_seconds_spin = self._new_seconds_spin()
        self.group_delay_max_seconds_spin = self._new_seconds_spin()
        self.interval_seconds_spin = self._new_seconds_spin()
        self.interval_seconds_spin.setRange(0, MAX_SECONDS)
        self.interval_seconds_spin.setToolTip("0 表示当前账号组小轮询结束后立即进入下一小轮询")

        self.daily_window_enabled_check = QCheckBox("启用每日时间段")
        self.daily_start_time_edit = NoWheelTimeEdit()
        self.daily_start_time_edit.setDisplayFormat("HH:mm")
        self.daily_start_time_edit.setTime(QTime(9, 0))
        self.daily_end_time_edit = NoWheelTimeEdit()
        self.daily_end_time_edit.setDisplayFormat("HH:mm")
        self.daily_end_time_edit.setTime(QTime(21, 0))

        self.message_mode_combo = NoWheelComboBox()
        self.message_mode_combo.addItem("模板", MESSAGE_MODE_TEMPLATE)
        self.message_mode_combo.addItem("文本", MESSAGE_MODE_TEXT)
        self.template_combo = CheckComboBox()
        self.template_combo.lineEdit().setPlaceholderText("请选择模板")
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("纯文本消息内容")
        style_text_editor(self.text_edit, 58)
        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("备注")
        style_text_editor(self.remark_edit, 118)

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")
        self._style_action_button(self.add_button)
        self._style_action_button(self.save_button)
        self._build_ui()
        self._connect_signals()
        self.clear_form()

    def _build_ui(self) -> None:
        self.setMinimumSize(1060, 780)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        grid = QGridLayout()
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(16)
        grid.setColumnMinimumWidth(0, 112)
        grid.setColumnMinimumWidth(2, 112)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_labeled_widget(grid, 0, 0, "任务名称：", self.name_edit)
        grid.addWidget(self.enabled_check, 0, 2, 1, 2)
        self._add_labeled_widget(grid, 1, 0, "账号组池：", self.account_group_combo)
        self._add_labeled_widget(grid, 1, 2, "群聊组池：", self.group_group_combo)
        self._add_labeled_widget(grid, 2, 0, "账号延迟最小：", self.account_delay_min_seconds_spin)
        self._add_labeled_widget(grid, 2, 2, "账号延迟最大：", self.account_delay_max_seconds_spin)
        self._add_labeled_widget(grid, 3, 0, "群组延迟最小：", self.group_delay_min_seconds_spin)
        self._add_labeled_widget(grid, 3, 2, "群组延迟最大：", self.group_delay_max_seconds_spin)
        self._add_labeled_widget(grid, 4, 0, "任务间隔：", self.interval_seconds_spin)
        grid.addWidget(self.daily_window_enabled_check, 4, 2, 1, 2)
        self._add_labeled_widget(grid, 5, 0, "每日开始时间：", self.daily_start_time_edit)
        self._add_labeled_widget(grid, 5, 2, "每日结束时间：", self.daily_end_time_edit)
        self._add_labeled_widget(grid, 6, 0, "消息类型：", self.message_mode_combo)
        self._add_labeled_widget(grid, 6, 2, "模板池：", self.template_combo)

        text_label = QLabel("文本内容：")
        text_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(text_label, 7, 0)
        grid.addWidget(self.text_edit, 7, 1, 1, 3)
        remark_label = QLabel("备注：")
        remark_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(remark_label, 8, 0)
        grid.addWidget(self.remark_edit, 8, 1, 1, 3)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)
        button_layout.setSpacing(28)
        button_layout.addStretch(1)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(16)
        layout.addSpacing(12)
        layout.addLayout(grid)
        layout.addStretch(1)
        layout.addLayout(button_layout)
        apply_large_inputs(self)
        self.text_edit.setFixedHeight(58)
        self.remark_edit.setFixedHeight(118)

    @staticmethod
    def _style_action_button(button: QPushButton) -> None:
        button.setMinimumWidth(150)
        button.setMinimumHeight(44)

    @staticmethod
    def _add_labeled_widget(grid: QGridLayout, row: int, label_column: int, label_text: str, widget: QWidget) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, label_column)
        grid.addWidget(widget, row, label_column + 1)

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self.add_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.message_mode_combo.currentIndexChanged.connect(self._update_message_mode_state)
        self.daily_window_enabled_check.stateChanged.connect(self._update_daily_window_state)

    @staticmethod
    def _new_seconds_spin() -> NoWheelDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(0, 24 * 60 * 60)
        spin.setDecimals(3)
        spin.setSingleStep(0.100)
        spin.setSuffix(" 秒")
        return spin

    def set_context(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        templates: list[TemplateConfig],
        settings: Settings | None = None,
        tasks: list[SendTaskConfig] | None = None,
        current_task_id: str | None = None,
        account_group_definitions: list[str] | None = None,
        group_group_definitions: list[str] | None = None,
    ) -> None:
        self.accounts = [item for item in list(accounts or []) if bool(getattr(item, "enabled", True))]
        self.groups = [item for item in list(groups or []) if bool(getattr(item, "enabled", True))]
        self.templates = [item for item in list(templates or []) if bool(getattr(item, "enabled", True))]
        if settings is not None:
            self.settings = settings
        if tasks is not None:
            self.tasks = list(tasks or [])
        if current_task_id is not None:
            self._current_task_id = str(current_task_id or "").strip()
        if account_group_definitions is not None:
            self.account_group_definitions = self._normalize_text_values(account_group_definitions)
        if group_group_definitions is not None:
            self.group_group_definitions = self._normalize_text_values(group_group_definitions)

        selected_account_groups = self.account_group_combo.checked_data()
        selected_group_groups = self.group_group_combo.checked_data()
        selected_templates = self.template_combo.checked_data()
        self._populate_account_group_combo()
        self._populate_group_group_combo()
        self._populate_template_combo()
        self.account_group_combo.set_checked_data(self._normalize_text_values(selected_account_groups))
        self.group_group_combo.set_checked_data(self._normalize_text_values(selected_group_groups))
        self.template_combo.set_checked_data(self._normalize_text_values(selected_templates))

    def _populate_account_group_combo(self) -> None:
        used_by = self._account_group_used_by_other_enabled_tasks()
        self.account_group_combo.clear_items()
        for group_name in self._available_account_group_names():
            owner = used_by.get(group_name, "")
            enabled = not bool(owner)
            label = group_name if enabled else f"{group_name}（已被任务 {owner} 占用）"
            self.account_group_combo.add_check_item(label, group_name, enabled=enabled)

    def _populate_group_group_combo(self) -> None:
        self.group_group_combo.clear_items()
        for group_name in self._available_group_group_names():
            self.group_group_combo.add_check_item(group_name, group_name)

    def _populate_template_combo(self) -> None:
        self.template_combo.clear_items()
        for template in self.templates:
            template_id = str(template.template_id or "")
            label = str(template.template_name or template.template_id or "")
            self.template_combo.add_check_item(label, template_id)

    def _available_account_group_names(self) -> list[str]:
        result = self._normalize_text_values(self.account_group_definitions)
        for account in self.accounts:
            value = str(getattr(account, "account_group", "") or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    def _available_group_group_names(self) -> list[str]:
        result = self._normalize_text_values(self.group_group_definitions)
        for group in self.groups:
            for value in self._group_group_names(group):
                if value and value not in result:
                    result.append(value)
        return result

    @staticmethod
    def _group_group_names(group: GroupConfig) -> list[str]:
        result: list[str] = []
        for item in getattr(group, "group_group_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(group, "group_group", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    def _account_group_used_by_other_enabled_tasks(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for task in self.tasks:
            if not bool(getattr(task, "enabled", True)):
                continue
            task_id = str(getattr(task, "task_id", "") or "").strip()
            if task_id and task_id == self._current_task_id:
                continue
            task_name = str(getattr(task, "task_name", "") or task_id or "未知任务")
            for group_name in getattr(task, "account_group_names", []) or []:
                value = str(group_name or "").strip()
                if value and value not in result:
                    result[value] = task_name
        return result

    def load_task(self, task: SendTaskConfig) -> None:
        self._current_task = task
        self._current_task_id = str(getattr(task, "task_id", "") or "").strip()
        self.name_edit.setText(str(task.task_name or ""))
        self.enabled_check.setChecked(bool(task.enabled))
        self.set_context(
            self.accounts,
            self.groups,
            self.templates,
            self.settings,
            self.tasks,
            self._current_task_id,
            self.account_group_definitions,
            self.group_group_definitions,
        )
        self.account_group_combo.set_checked_data(self._task_account_group_names(task))
        self.group_group_combo.set_checked_data(self._task_group_group_names(task))
        self.account_delay_min_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "account_delay_min_ms", 0)))
        self.account_delay_max_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "account_delay_max_ms", 0)))
        self.group_delay_min_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "group_delay_min_ms", 0)))
        self.group_delay_max_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "group_delay_max_ms", 0)))
        self.interval_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "interval_ms", 3600000)))
        self.daily_window_enabled_check.setChecked(bool(getattr(task, "daily_window_enabled", False)))
        self.daily_start_time_edit.setTime(self._time_from_text(str(getattr(task, "daily_start_time", "09:00") or "09:00")))
        self.daily_end_time_edit.setTime(self._time_from_text(str(getattr(task, "daily_end_time", "21:00") or "21:00")))
        self._set_combo_value(self.message_mode_combo, str(task.message_mode or MESSAGE_MODE_TEMPLATE))
        self.text_edit.setPlainText(str(task.text or ""))
        self.template_combo.set_checked_data(self._task_template_ids(task))
        self.remark_edit.setPlainText(str(task.remark or ""))
        self._update_message_mode_state()
        self._update_daily_window_state()

    def clear_form(self) -> None:
        self._current_task = None
        self._current_task_id = ""
        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self.account_group_combo.set_checked_data([])
        self.group_group_combo.set_checked_data([])
        self.template_combo.set_checked_data([])
        self.account_delay_min_seconds_spin.setValue(self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_min_ms", 0)))
        self.account_delay_max_seconds_spin.setValue(self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_max_ms", 0)))
        self.group_delay_min_seconds_spin.setValue(self._ms_to_seconds(getattr(self.settings, "default_task_group_delay_min_ms", 0)))
        self.group_delay_max_seconds_spin.setValue(self._ms_to_seconds(getattr(self.settings, "default_task_group_delay_max_ms", 0)))
        self.interval_seconds_spin.setValue(self._ms_to_seconds(getattr(self.settings, "default_task_interval_ms", 3600000)))
        self.daily_window_enabled_check.setChecked(bool(getattr(self.settings, "default_task_daily_window_enabled", False)))
        self.daily_start_time_edit.setTime(self._time_from_text(str(getattr(self.settings, "default_task_daily_start_time", "09:00"))))
        self.daily_end_time_edit.setTime(self._time_from_text(str(getattr(self.settings, "default_task_daily_end_time", "21:00"))))
        self._set_combo_value(self.message_mode_combo, str(getattr(self.settings, "default_task_message_mode", MESSAGE_MODE_TEMPLATE)))
        self.text_edit.clear()
        self.remark_edit.clear()
        self._update_message_mode_state()
        self._update_daily_window_state()

    def get_form_task(self) -> SendTaskConfig:
        existing = self._current_task
        task_id = str(getattr(existing, "task_id", "") or "").strip() if existing else ""
        if not task_id:
            task_id = uuid.uuid4().hex
        account_group_names = self._normalize_text_values(self.account_group_combo.checked_data())
        group_group_names = self._normalize_text_values(self.group_group_combo.checked_data())
        account_delay_min_ms = self._seconds_to_ms(self.account_delay_min_seconds_spin.value())
        account_delay_max_ms = self._seconds_to_ms(self.account_delay_max_seconds_spin.value())
        if account_delay_max_ms < account_delay_min_ms:
            raise ValueError("账号延迟最大值不能小于账号延迟最小值")
        group_delay_min_ms = self._seconds_to_ms(self.group_delay_min_seconds_spin.value())
        group_delay_max_ms = self._seconds_to_ms(self.group_delay_max_seconds_spin.value())
        if group_delay_max_ms < group_delay_min_ms:
            raise ValueError("群组延迟最大值不能小于群组延迟最小值")
        interval_ms = self._seconds_to_ms(self.interval_seconds_spin.value())
        template_ids = self._normalize_text_values(self.template_combo.checked_data())
        daily_start_time = self.daily_start_time_edit.time().toString("HH:mm")
        daily_end_time = self.daily_end_time_edit.time().toString("HH:mm")
        return SendTaskConfig(
            task_id=task_id,
            task_name=self.name_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
            account_group_names=account_group_names,
            group_group_names=group_group_names,
            pairing_mode=PAIRING_MODE_ROTATE,
            account_delay_min_ms=account_delay_min_ms,
            account_delay_max_ms=account_delay_max_ms,
            account_delay_seconds=int(account_delay_min_ms // 1000),
            group_delay_min_ms=group_delay_min_ms,
            group_delay_max_ms=group_delay_max_ms,
            group_delay_seconds=int(group_delay_min_ms // 1000),
            interval_ms=interval_ms,
            interval_seconds=int(interval_ms // 1000),
            daily_window_enabled=self.daily_window_enabled_check.isChecked(),
            daily_start_time=daily_start_time,
            daily_end_time=daily_end_time,
            message_mode=str(self.message_mode_combo.currentData() or MESSAGE_MODE_TEMPLATE),
            text=self.text_edit.toPlainText().strip(),
            template_ids=template_ids,
            template_id=template_ids[0] if template_ids else "",
            last_run_at=str(getattr(existing, "last_run_at", "") or "") if existing else "",
            remark=self.remark_edit.toPlainText().strip(),
        )

    def _update_message_mode_state(self) -> None:
        mode = self.message_mode_combo.currentData()
        self.text_edit.setEnabled(mode == MESSAGE_MODE_TEXT)
        self.template_combo.setEnabled(mode == MESSAGE_MODE_TEMPLATE)

    def _update_daily_window_state(self) -> None:
        enabled = self.daily_window_enabled_check.isChecked()
        self.daily_start_time_edit.setEnabled(enabled)
        self.daily_end_time_edit.setEnabled(enabled)

    @staticmethod
    def _normalize_text_values(values: list[Any]) -> list[str]:
        result: list[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _set_combo_value(combo: NoWheelComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @staticmethod
    def _time_from_text(value: str) -> QTime:
        parsed = QTime.fromString(str(value or "09:00").strip(), "HH:mm")
        return parsed if parsed.isValid() else QTime(9, 0)

    @staticmethod
    def _seconds_to_ms(value: Any) -> int:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            seconds = 0.0
        return int(round(max(0.0, seconds) * 1000))

    @staticmethod
    def _ms_to_seconds(value: Any) -> float:
        try:
            ms = int(value)
        except (TypeError, ValueError):
            ms = 0
        return round(max(0, ms) / 1000.0, 3)

    @staticmethod
    def _task_account_group_names(task: SendTaskConfig) -> list[str]:
        return TaskForm._normalize_text_values(list(getattr(task, "account_group_names", []) or []))

    @staticmethod
    def _task_group_group_names(task: SendTaskConfig) -> list[str]:
        return TaskForm._normalize_text_values(list(getattr(task, "group_group_names", []) or []))

    @staticmethod
    def _task_template_ids(task: SendTaskConfig) -> list[str]:
        result = TaskForm._normalize_text_values(list(getattr(task, "template_ids", []) or []))
        legacy = str(getattr(task, "template_id", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

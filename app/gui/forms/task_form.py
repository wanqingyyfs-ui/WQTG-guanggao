from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import QTime, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
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
    style_form_layout,
    style_list_widget,
    style_text_editor,
)
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
        self.settings = Settings()
        self._current_task: SendTaskConfig | None = None

        self.name_edit = QPlainTextEdit()
        self.name_edit.setMaximumHeight(72)
        self.name_edit.setPlaceholderText("任务名称")
        style_text_editor(self.name_edit, 72)

        self.enabled_check = QCheckBox("启用任务")

        self.account_list = QListWidget()
        self.account_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        style_list_widget(self.account_list, 130)

        self.account_rotate_mode_combo = NoWheelComboBox()
        self.account_rotate_mode_combo.addItem("单账号", ACCOUNT_ROTATE_MODE_SINGLE)
        self.account_rotate_mode_combo.addItem("多账号轮询", ACCOUNT_ROTATE_MODE_ROUND_ROBIN)

        self.account_delay_min_seconds_spin = self._new_seconds_spin()
        self.account_delay_max_seconds_spin = self._new_seconds_spin()

        self.group_list = QListWidget()
        self.group_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        style_list_widget(self.group_list, 130)

        self.group_rotate_mode_combo = NoWheelComboBox()
        self.group_rotate_mode_combo.addItem("单群组", GROUP_ROTATE_MODE_SINGLE)
        self.group_rotate_mode_combo.addItem("多群组轮询", GROUP_ROTATE_MODE_ROUND_ROBIN)

        self.group_delay_min_seconds_spin = self._new_seconds_spin()
        self.group_delay_max_seconds_spin = self._new_seconds_spin()

        self.message_mode_combo = NoWheelComboBox()
        self.message_mode_combo.addItem("模板", MESSAGE_MODE_TEMPLATE)
        self.message_mode_combo.addItem("文本", MESSAGE_MODE_TEXT)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("纯文本消息内容")
        style_text_editor(self.text_edit, 150)

        self.template_list = QListWidget()
        self.template_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        style_list_widget(self.template_list, 130)

        self.schedule_mode_combo = NoWheelComboBox()
        self.schedule_mode_combo.addItem("间隔", SCHEDULE_MODE_INTERVAL)
        self.schedule_mode_combo.addItem("每日", SCHEDULE_MODE_DAILY)

        self.interval_seconds_spin = self._new_seconds_spin()
        self.interval_seconds_spin.setRange(0, MAX_SECONDS)
        self.interval_seconds_spin.setToolTip("0 表示任务完成后立即进入下一轮到期状态")

        self.daily_time_edit = NoWheelTimeEdit()
        self.daily_time_edit.setDisplayFormat("HH:mm")
        self.daily_time_edit.setTime(QTime(9, 0))

        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("备注")
        style_text_editor(self.remark_edit, 120)

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")

        self._build_ui()
        self._connect_signals()
        self.clear_form()

    def _build_ui(self) -> None:
        form = QFormLayout()
        style_form_layout(form)

        form.addRow("任务名称：", self.name_edit)
        form.addRow("启用状态：", self.enabled_check)
        form.addRow("发送账号池：", self.account_list)
        form.addRow("账号轮换：", self.account_rotate_mode_combo)
        form.addRow("账号延迟最小值：", self.account_delay_min_seconds_spin)
        form.addRow("账号延迟最大值：", self.account_delay_max_seconds_spin)
        form.addRow("目标群组池：", self.group_list)
        form.addRow("群组轮换：", self.group_rotate_mode_combo)
        form.addRow("群组延迟最小值：", self.group_delay_min_seconds_spin)
        form.addRow("群组延迟最大值：", self.group_delay_max_seconds_spin)
        form.addRow("消息类型：", self.message_mode_combo)
        form.addRow("文本内容：", self.text_edit)
        form.addRow("模板池：", self.template_list)
        form.addRow("调度模式：", self.schedule_mode_combo)
        form.addRow("间隔时间：", self.interval_seconds_spin)
        form.addRow("每日时间：", self.daily_time_edit)
        form.addRow("备注：", self.remark_edit)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addLayout(button_layout)
        layout.addStretch(1)

        apply_large_inputs(self)

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self.add_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.message_mode_combo.currentIndexChanged.connect(self._update_message_mode_state)

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
    ) -> None:
        self.accounts = [item for item in list(accounts or []) if bool(getattr(item, "enabled", True))]
        self.groups = [item for item in list(groups or []) if bool(getattr(item, "enabled", True))]
        self.templates = [item for item in list(templates or []) if bool(getattr(item, "enabled", True))]

        if settings is not None:
            self.settings = settings

        selected_accounts = self._selected_values(self.account_list)
        selected_groups = self._selected_values(self.group_list)
        selected_templates = self._selected_values(self.template_list)

        self._populate_account_list()
        self._populate_group_list()
        self._populate_template_list()

        self._restore_selection(self.account_list, selected_accounts)
        self._restore_selection(self.group_list, selected_groups)
        self._restore_selection(self.template_list, selected_templates)

    def _populate_account_list(self) -> None:
        self.account_list.clear()
        for account in self.accounts:
            item = QListWidgetItem(str(account.account_name or ""))
            item.setData(Qt.ItemDataRole.UserRole, str(account.account_name or ""))
            self.account_list.addItem(item)

    def _populate_group_list(self) -> None:
        self.group_list.clear()
        for group in self.groups:
            label = f"{group.group_name} ({group.chat_id})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(group.group_id or ""))
            self.group_list.addItem(item)

    def _populate_template_list(self) -> None:
        self.template_list.clear()
        for template in self.templates:
            item = QListWidgetItem(str(template.template_name or template.template_id or ""))
            item.setData(Qt.ItemDataRole.UserRole, str(template.template_id or ""))
            self.template_list.addItem(item)

    def load_task(self, task: SendTaskConfig) -> None:
        self._current_task = task

        self.name_edit.setPlainText(str(task.task_name or ""))
        self.enabled_check.setChecked(bool(task.enabled))
        self._restore_selection(self.account_list, self._task_account_names(task))
        self._set_combo_value(
            self.account_rotate_mode_combo,
            str(getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE)),
        )
        self.account_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "account_delay_min_ms", 0))
        )
        self.account_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "account_delay_max_ms", 0))
        )

        self._restore_selection(self.group_list, self._task_group_ids(task))
        self._set_combo_value(
            self.group_rotate_mode_combo,
            str(getattr(task, "group_rotate_mode", GROUP_ROTATE_MODE_SINGLE)),
        )
        self.group_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "group_delay_min_ms", 0))
        )
        self.group_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "group_delay_max_ms", 0))
        )

        self._set_combo_value(self.message_mode_combo, str(task.message_mode or MESSAGE_MODE_TEMPLATE))
        self.text_edit.setPlainText(str(task.text or ""))
        self._restore_selection(self.template_list, self._task_template_ids(task))
        self._set_combo_value(self.schedule_mode_combo, str(task.schedule_mode or SCHEDULE_MODE_INTERVAL))
        self.interval_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "interval_ms", 3600000)))
        self.daily_time_edit.setTime(self._time_from_text(str(task.daily_time or "09:00")))
        self.remark_edit.setPlainText(str(task.remark or ""))

        self._update_message_mode_state()

    def clear_form(self) -> None:
        self._current_task = None

        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self._clear_selection(self.account_list)
        self._clear_selection(self.group_list)
        self._clear_selection(self.template_list)

        self._set_combo_value(
            self.account_rotate_mode_combo,
            str(getattr(self.settings, "default_task_account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE)),
        )
        self.account_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_min_ms", 0))
        )
        self.account_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_max_ms", 0))
        )

        self._set_combo_value(
            self.group_rotate_mode_combo,
            str(getattr(self.settings, "default_task_group_rotate_mode", GROUP_ROTATE_MODE_SINGLE)),
        )
        self.group_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_group_delay_min_ms", 0))
        )
        self.group_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_group_delay_max_ms", 0))
        )

        self._set_combo_value(
            self.message_mode_combo,
            str(getattr(self.settings, "default_task_message_mode", MESSAGE_MODE_TEMPLATE)),
        )
        self.text_edit.clear()
        self._set_combo_value(
            self.schedule_mode_combo,
            str(getattr(self.settings, "default_task_schedule_mode", SCHEDULE_MODE_INTERVAL)),
        )
        self.interval_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_interval_ms", 3600000))
        )
        self.daily_time_edit.setTime(
            self._time_from_text(str(getattr(self.settings, "default_task_daily_time", "09:00")))
        )
        self.remark_edit.clear()
        self._update_message_mode_state()

    def get_form_task(self) -> SendTaskConfig:
        existing = self._current_task
        task_id = str(getattr(existing, "task_id", "") or "").strip() if existing else ""
        if not task_id:
            task_id = uuid.uuid4().hex

        last_run_at = str(getattr(existing, "last_run_at", "") or "") if existing else ""
        next_run_at = str(getattr(existing, "next_run_at", "") or "") if existing else ""
        current_account_index = self._safe_non_negative_int(
            getattr(existing, "current_account_index", 0) if existing else 0,
            0,
        )
        current_group_index = self._safe_non_negative_int(
            getattr(existing, "current_group_index", 0) if existing else 0,
            0,
        )

        account_names = self._selected_values(self.account_list)
        account_rotate_mode = str(self.account_rotate_mode_combo.currentData() or ACCOUNT_ROTATE_MODE_SINGLE)
        if account_rotate_mode == ACCOUNT_ROTATE_MODE_SINGLE and account_names:
            account_names = [account_names[0]]
        account_name = account_names[0] if account_names else ""
        current_account_index = current_account_index % len(account_names) if account_names else 0

        group_ids = self._selected_values(self.group_list)
        group_rotate_mode = str(self.group_rotate_mode_combo.currentData() or GROUP_ROTATE_MODE_SINGLE)
        if group_rotate_mode == GROUP_ROTATE_MODE_SINGLE and group_ids:
            group_ids = [group_ids[0]]
        group_id = group_ids[0] if group_ids else ""
        current_group_index = current_group_index % len(group_ids) if group_ids else 0

        account_delay_min_ms = self._seconds_to_ms(self.account_delay_min_seconds_spin.value())
        account_delay_max_ms = self._seconds_to_ms(self.account_delay_max_seconds_spin.value())
        if account_delay_max_ms < account_delay_min_ms:
            raise ValueError("账号延迟最大值不能小于账号延迟最小值")

        group_delay_min_ms = self._seconds_to_ms(self.group_delay_min_seconds_spin.value())
        group_delay_max_ms = self._seconds_to_ms(self.group_delay_max_seconds_spin.value())
        if group_delay_max_ms < group_delay_min_ms:
            raise ValueError("群组延迟最大值不能小于群组延迟最小值")

        template_ids = self._selected_values(self.template_list)
        template_id = template_ids[0] if template_ids else ""

        interval_ms = self._seconds_to_ms(self.interval_seconds_spin.value())
        daily_time = self.daily_time_edit.time().toString("HH:mm")

        return SendTaskConfig(
            task_id=task_id,
            task_name=self.name_edit.toPlainText().strip(),
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
            schedule_mode=str(self.schedule_mode_combo.currentData() or SCHEDULE_MODE_INTERVAL),
            interval_ms=interval_ms,
            interval_seconds=int(interval_ms // 1000),
            daily_time=daily_time,
            random_delay_min=0,
            random_delay_max=0,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            remark=self.remark_edit.toPlainText().strip(),
        )

    def _update_message_mode_state(self) -> None:
        mode = self.message_mode_combo.currentData()
        self.text_edit.setEnabled(mode == MESSAGE_MODE_TEXT)
        self.template_list.setEnabled(mode == MESSAGE_MODE_TEMPLATE)

    @staticmethod
    def _selected_values(list_widget: QListWidget) -> list[str]:
        result: list[str] = []
        for item in list_widget.selectedItems():
            value = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _restore_selection(list_widget: QListWidget, values: list[str]) -> None:
        wanted = {str(value or "").strip() for value in values if str(value or "").strip()}
        list_widget.clearSelection()
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            value = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            item.setSelected(value in wanted)

    @staticmethod
    def _clear_selection(list_widget: QListWidget) -> None:
        list_widget.clearSelection()

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
    def _safe_non_negative_int(value: Any, default: int = 0) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(0, number)

    @staticmethod
    def _task_account_names(task: SendTaskConfig) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "account_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "account_name", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    @staticmethod
    def _task_group_ids(task: SendTaskConfig) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "group_ids", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "group_id", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

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

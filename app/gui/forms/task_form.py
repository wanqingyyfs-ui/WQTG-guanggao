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
    style_text_editor,
)
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
        self.settings = Settings()
        self._current_task: SendTaskConfig | None = None

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("任务名称")

        self.enabled_check = QCheckBox("启用任务")

        self.account_combo = CheckComboBox()
        self.account_combo.lineEdit().setPlaceholderText("请选择发送账号")

        self.group_combo = CheckComboBox()
        self.group_combo.lineEdit().setPlaceholderText("请选择目标群组")

        self.account_delay_min_seconds_spin = self._new_seconds_spin()
        self.account_delay_max_seconds_spin = self._new_seconds_spin()

        self.group_delay_min_seconds_spin = self._new_seconds_spin()
        self.group_delay_max_seconds_spin = self._new_seconds_spin()

        self.message_mode_combo = NoWheelComboBox()
        self.message_mode_combo.addItem("模板", MESSAGE_MODE_TEMPLATE)
        self.message_mode_combo.addItem("文本", MESSAGE_MODE_TEXT)

        self.schedule_mode_combo = NoWheelComboBox()
        self.schedule_mode_combo.addItem("间隔", SCHEDULE_MODE_INTERVAL)
        self.schedule_mode_combo.addItem("每日", SCHEDULE_MODE_DAILY)

        self.interval_seconds_spin = self._new_seconds_spin()
        self.interval_seconds_spin.setRange(0, MAX_SECONDS)
        self.interval_seconds_spin.setToolTip("0 表示任务完成后立即进入下一轮到期状态")

        self.daily_time_edit = NoWheelTimeEdit()
        self.daily_time_edit.setDisplayFormat("HH:mm")
        self.daily_time_edit.setTime(QTime(9, 0))

        self.template_combo = CheckComboBox()
        self.template_combo.lineEdit().setPlaceholderText("请选择模板")

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("纯文本消息内容")
        style_text_editor(self.text_edit, 130)

        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("备注")
        style_text_editor(self.remark_edit, 110)

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")
        self._style_action_button(self.add_button)
        self._style_action_button(self.save_button)

        self._build_ui()
        self._connect_signals()
        self.clear_form()

    def _build_ui(self) -> None:
        self.setMinimumSize(720, 680)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )

        grid = QGridLayout()
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        grid.setColumnMinimumWidth(0, 98)
        grid.setColumnMinimumWidth(2, 98)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_labeled_widget(grid, 0, 0, "任务名称：", self.name_edit)
        grid.addWidget(self.enabled_check, 0, 2, 1, 2)

        self._add_labeled_widget(grid, 1, 0, "发送账号池：", self.account_combo)
        self._add_labeled_widget(grid, 1, 2, "目标群组池：", self.group_combo)

        self._add_labeled_widget(grid, 2, 0, "账号延迟最小：", self.account_delay_min_seconds_spin)
        self._add_labeled_widget(grid, 2, 2, "账号延迟最大：", self.account_delay_max_seconds_spin)

        self._add_labeled_widget(grid, 3, 0, "群组延迟最小：", self.group_delay_min_seconds_spin)
        self._add_labeled_widget(grid, 3, 2, "群组延迟最大：", self.group_delay_max_seconds_spin)

        self._add_labeled_widget(grid, 4, 0, "消息类型：", self.message_mode_combo)
        self._add_labeled_widget(grid, 4, 2, "调度模式：", self.schedule_mode_combo)

        self._add_labeled_widget(grid, 5, 0, "间隔时间：", self.interval_seconds_spin)
        self._add_labeled_widget(grid, 5, 2, "每日时间：", self.daily_time_edit)

        self._add_labeled_widget(grid, 6, 0, "模板池：", self.template_combo)

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
        button_layout.setSpacing(14)
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

    @staticmethod
    def _style_action_button(button: QPushButton) -> None:
        button.setMinimumWidth(120)
        button.setMinimumHeight(38)

    @staticmethod
    def _add_labeled_widget(
        grid: QGridLayout,
        row: int,
        label_column: int,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, label_column)
        grid.addWidget(widget, row, label_column + 1)

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

        selected_accounts = self.account_combo.checked_data()
        selected_groups = self.group_combo.checked_data()
        selected_templates = self.template_combo.checked_data()

        self._populate_account_combo()
        self._populate_group_combo()
        self._populate_template_combo()

        self.account_combo.set_checked_data(self._normalize_text_values(selected_accounts))
        self.group_combo.set_checked_data(self._normalize_text_values(selected_groups))
        self.template_combo.set_checked_data(self._normalize_text_values(selected_templates))

    def _populate_account_combo(self) -> None:
        self.account_combo.clear_items()
        for account in self.accounts:
            account_name = str(account.account_name or "")
            self.account_combo.add_check_item(account_name, account_name)

    def _populate_group_combo(self) -> None:
        self.group_combo.clear_items()
        for group in self.groups:
            group_id = str(group.group_id or "")
            label = f"{group.group_name} ({group.chat_id})"
            self.group_combo.add_check_item(label, group_id)

    def _populate_template_combo(self) -> None:
        self.template_combo.clear_items()
        for template in self.templates:
            template_id = str(template.template_id or "")
            label = str(template.template_name or template.template_id or "")
            self.template_combo.add_check_item(label, template_id)

    def load_task(self, task: SendTaskConfig) -> None:
        self._current_task = task

        self.name_edit.setText(str(task.task_name or ""))
        self.enabled_check.setChecked(bool(task.enabled))
        self.account_combo.set_checked_data(self._task_account_names(task))

        self.account_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "account_delay_min_ms", 0))
        )
        self.account_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "account_delay_max_ms", 0))
        )

        self.group_combo.set_checked_data(self._task_group_ids(task))
        self.group_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "group_delay_min_ms", 0))
        )
        self.group_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(task, "group_delay_max_ms", 0))
        )

        self._set_combo_value(self.message_mode_combo, str(task.message_mode or MESSAGE_MODE_TEMPLATE))
        self.text_edit.setPlainText(str(task.text or ""))
        self.template_combo.set_checked_data(self._task_template_ids(task))
        self._set_combo_value(self.schedule_mode_combo, str(task.schedule_mode or SCHEDULE_MODE_INTERVAL))
        self.interval_seconds_spin.setValue(self._ms_to_seconds(getattr(task, "interval_ms", 3600000)))
        self.daily_time_edit.setTime(self._time_from_text(str(task.daily_time or "09:00")))
        self.remark_edit.setPlainText(str(task.remark or ""))

        self._update_message_mode_state()

    def clear_form(self) -> None:
        self._current_task = None

        self.name_edit.clear()
        self.enabled_check.setChecked(True)
        self.account_combo.set_checked_data([])
        self.group_combo.set_checked_data([])
        self.template_combo.set_checked_data([])

        self.account_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_min_ms", 0))
        )
        self.account_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(getattr(self.settings, "default_task_account_delay_max_ms", 0))
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

        account_names = self._normalize_text_values(self.account_combo.checked_data())
        account_rotate_mode = (
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN
            if len(account_names) > 1
            else ACCOUNT_ROTATE_MODE_SINGLE
        )
        account_name = account_names[0] if account_names else ""
        current_account_index = current_account_index % len(account_names) if account_names else 0

        group_ids = self._normalize_text_values(self.group_combo.checked_data())
        group_rotate_mode = (
            GROUP_ROTATE_MODE_ROUND_ROBIN
            if len(group_ids) > 1
            else GROUP_ROTATE_MODE_SINGLE
        )
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

        template_ids = self._normalize_text_values(self.template_combo.checked_data())
        template_id = template_ids[0] if template_ids else ""

        interval_ms = self._seconds_to_ms(self.interval_seconds_spin.value())
        daily_time = self.daily_time_edit.time().toString("HH:mm")

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
        self.template_combo.setEnabled(mode == MESSAGE_MODE_TEMPLATE)

    @staticmethod
    def _style_action_button(button: QPushButton) -> None:
        button.setMinimumWidth(120)
        button.setMinimumHeight(38)

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

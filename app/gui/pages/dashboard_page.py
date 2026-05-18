from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    SCHEDULE_MODE_MANUAL,
)
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_table,
)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts_count_value = QLabel("0")
        self.enabled_accounts_count_value = QLabel("0")
        self.online_accounts_count_value = QLabel("0")
        self.groups_count_value = QLabel("0")
        self.enabled_groups_count_value = QLabel("0")
        self.tasks_count_value = QLabel("0")
        self.enabled_tasks_count_value = QLabel("0")
        self.manual_tasks_count_value = QLabel("0")
        self.interval_tasks_count_value = QLabel("0")
        self.daily_tasks_count_value = QLabel("0")
        self.scheduler_status_value = QLabel("stopped")

        self.summary_value_labels = [
            self.accounts_count_value,
            self.enabled_accounts_count_value,
            self.online_accounts_count_value,
            self.groups_count_value,
            self.enabled_groups_count_value,
            self.tasks_count_value,
            self.enabled_tasks_count_value,
            self.manual_tasks_count_value,
            self.interval_tasks_count_value,
            self.daily_tasks_count_value,
            self.scheduler_status_value,
        ]

        for label in self.summary_value_labels:
            label.setMinimumHeight(42)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.scheduler_tick_spin = QDoubleSpinBox()
        self.scheduler_tick_spin.setRange(0.2, 60.0)
        self.scheduler_tick_spin.setDecimals(1)
        self.scheduler_tick_spin.setSingleStep(0.5)
        self.scheduler_tick_spin.setSuffix(" 秒")

        self.max_concurrent_tasks_spin = QSpinBox()
        self.max_concurrent_tasks_spin.setRange(1, 20)
        self.max_concurrent_tasks_spin.setSuffix(" 个")

        self.default_send_interval_spin = QDoubleSpinBox()
        self.default_send_interval_spin.setRange(0.0, 86400.0)
        self.default_send_interval_spin.setDecimals(1)
        self.default_send_interval_spin.setSingleStep(1.0)
        self.default_send_interval_spin.setSuffix(" 秒")

        self.template_account_edit = QLineEdit()
        self.template_account_edit.setPlaceholderText("填写用于监听素材群的账号名称")

        self.template_chat_id_edit = QLineEdit()
        self.template_chat_id_edit.setPlaceholderText("例如：-1001234567890")

        self.log_file_edit = QLineEdit()
        self.log_file_edit.setReadOnly(True)

        self.sessions_dir_edit = QLineEdit()
        self.sessions_dir_edit.setReadOnly(True)

        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载配置")
        self.start_all_button = QPushButton("启动全部账号")
        self.stop_all_button = QPushButton("停止全部账号")
        self.start_scheduler_button = QPushButton("启动群发调度")
        self.stop_scheduler_button = QPushButton("停止群发调度")

        self.status_table = QTableWidget(0, 5)
        self.status_table.setHorizontalHeaderLabels(
            ["账号", "手机号", "启用", "状态", "说明"]
        )
        self.status_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.status_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.status_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.status_table)

        summary_group = QGroupBox("运行概览")
        style_group_box(summary_group)

        summary_layout = QGridLayout(summary_group)
        summary_layout.setContentsMargins(28, 28, 28, 26)
        summary_layout.setHorizontalSpacing(36)
        summary_layout.setVerticalSpacing(18)

        summary_layout.addWidget(QLabel("账号总数"), 0, 0)
        summary_layout.addWidget(self.accounts_count_value, 0, 1)
        summary_layout.addWidget(QLabel("启用账号"), 0, 2)
        summary_layout.addWidget(self.enabled_accounts_count_value, 0, 3)
        summary_layout.addWidget(QLabel("在线账号"), 0, 4)
        summary_layout.addWidget(self.online_accounts_count_value, 0, 5)

        summary_layout.addWidget(QLabel("目标群组"), 1, 0)
        summary_layout.addWidget(self.groups_count_value, 1, 1)
        summary_layout.addWidget(QLabel("启用群组"), 1, 2)
        summary_layout.addWidget(self.enabled_groups_count_value, 1, 3)
        summary_layout.addWidget(QLabel("任务总数"), 1, 4)
        summary_layout.addWidget(self.tasks_count_value, 1, 5)

        summary_layout.addWidget(QLabel("启用任务"), 2, 0)
        summary_layout.addWidget(self.enabled_tasks_count_value, 2, 1)
        summary_layout.addWidget(QLabel("手动任务"), 2, 2)
        summary_layout.addWidget(self.manual_tasks_count_value, 2, 3)
        summary_layout.addWidget(QLabel("间隔任务"), 2, 4)
        summary_layout.addWidget(self.interval_tasks_count_value, 2, 5)

        summary_layout.addWidget(QLabel("每日任务"), 3, 0)
        summary_layout.addWidget(self.daily_tasks_count_value, 3, 1)
        summary_layout.addWidget(QLabel("调度器状态"), 3, 2)
        summary_layout.addWidget(self.scheduler_status_value, 3, 3)

        runtime_group = QGroupBox("群发调度配置")
        style_group_box(runtime_group)

        runtime_form = QFormLayout(runtime_group)
        style_form_layout(runtime_form)
        runtime_form.addRow("任务扫描间隔", self.scheduler_tick_spin)
        runtime_form.addRow("最大并发任务数", self.max_concurrent_tasks_spin)
        runtime_form.addRow("默认发送间隔", self.default_send_interval_spin)

        template_group = QGroupBox("素材群监听配置")
        style_group_box(template_group)

        template_form = QFormLayout(template_group)
        style_form_layout(template_form)
        template_form.addRow("素材账号名", self.template_account_edit)
        template_form.addRow("素材群 Chat ID", self.template_chat_id_edit)

        path_group = QGroupBox("运行路径")
        style_group_box(path_group)

        path_form = QFormLayout(path_group)
        style_form_layout(path_form)
        path_form.addRow("日志文件", self.log_file_edit)
        path_form.addRow("Session 目录", self.sessions_dir_edit)

        apply_large_inputs(runtime_group)
        apply_large_inputs(template_group)
        apply_large_inputs(path_group)

        config_button_bar = QWidget()
        config_button_layout = QHBoxLayout(config_button_bar)
        config_button_layout.setContentsMargins(12, 12, 12, 12)
        config_button_layout.setSpacing(14)
        config_button_layout.addWidget(self.save_button)
        config_button_layout.addWidget(self.reload_button)
        config_button_layout.addStretch(1)

        runtime_button_bar = QWidget()
        runtime_button_layout = QHBoxLayout(runtime_button_bar)
        runtime_button_layout.setContentsMargins(12, 12, 12, 12)
        runtime_button_layout.setSpacing(14)
        runtime_button_layout.addWidget(self.start_all_button)
        runtime_button_layout.addWidget(self.stop_all_button)
        runtime_button_layout.addStretch(1)
        runtime_button_layout.addWidget(self.start_scheduler_button)
        runtime_button_layout.addWidget(self.stop_scheduler_button)

        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)
        config_layout.addWidget(summary_group)
        config_layout.addWidget(runtime_group)
        config_layout.addWidget(template_group)
        config_layout.addWidget(path_group)
        config_layout.addWidget(config_button_bar)
        config_layout.addWidget(runtime_button_bar)
        config_layout.addStretch(1)

        status_group = QGroupBox("账号运行状态")
        style_group_box(status_group)

        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(18, 20, 18, 18)
        status_layout.addWidget(self.status_table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_layout.addWidget(QLabel("运行总控"))
        top_layout.addWidget(make_scroll_area(config_content, minimum_height=360), 1)

        bottom_widget = make_scroll_area(status_group, minimum_height=260)

        splitter = make_vertical_splitter(
            top_widget=top_widget,
            bottom_widget=bottom_widget,
            sizes=[560, 330],
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

    def update_summary(
        self,
        accounts,
        groups,
        tasks,
        settings,
        scheduler_status: str = "stopped",
    ) -> None:
        accounts_list = list(accounts or [])
        groups_list = list(groups or [])
        tasks_list = list(tasks or [])

        self.accounts_count_value.setText(str(len(accounts_list)))
        self.enabled_accounts_count_value.setText(
            str(sum(1 for item in accounts_list if bool(getattr(item, "enabled", True))))
        )
        self.groups_count_value.setText(str(len(groups_list)))
        self.enabled_groups_count_value.setText(
            str(sum(1 for item in groups_list if bool(getattr(item, "enabled", True))))
        )
        self.tasks_count_value.setText(str(len(tasks_list)))
        self.enabled_tasks_count_value.setText(
            str(sum(1 for item in tasks_list if bool(getattr(item, "enabled", True))))
        )

        self.manual_tasks_count_value.setText(
            str(
                sum(
                    1
                    for item in tasks_list
                    if getattr(item, "schedule_mode", SCHEDULE_MODE_MANUAL)
                    == SCHEDULE_MODE_MANUAL
                )
            )
        )
        self.interval_tasks_count_value.setText(
            str(
                sum(
                    1
                    for item in tasks_list
                    if getattr(item, "schedule_mode", "") == SCHEDULE_MODE_INTERVAL
                )
            )
        )
        self.daily_tasks_count_value.setText(
            str(
                sum(
                    1
                    for item in tasks_list
                    if getattr(item, "schedule_mode", "") == SCHEDULE_MODE_DAILY
                )
            )
        )

        self.scheduler_status_value.setText(
            self._scheduler_status_label(scheduler_status)
        )
        self._update_scheduler_buttons(scheduler_status)

        self.scheduler_tick_spin.setValue(
            self._safe_float(getattr(settings, "scheduler_tick_seconds", 1.0), 1.0)
        )
        self.max_concurrent_tasks_spin.setValue(
            self._safe_int(getattr(settings, "max_concurrent_tasks", 1), 1)
        )
        self.default_send_interval_spin.setValue(
            self._safe_float(
                getattr(settings, "default_send_interval_seconds", 1.0),
                1.0,
            )
        )

        self.template_account_edit.setText(
            str(getattr(settings, "template_source_account_name", "") or "")
        )

        template_source_chat_id = self._safe_int(
            getattr(settings, "template_source_chat_id", 0),
            0,
        )
        self.template_chat_id_edit.setText(
            str(template_source_chat_id) if template_source_chat_id else ""
        )

        self.log_file_edit.setText(str(getattr(settings, "log_file", "") or ""))
        self.sessions_dir_edit.setText(str(getattr(settings, "sessions_dir", "") or ""))

    def update_status_table(self, accounts, status_map) -> None:
        accounts_list = list(accounts or [])
        safe_status_map = dict(status_map or {})

        self.status_table.setRowCount(len(accounts_list))

        online_count = 0

        for row, account in enumerate(accounts_list):
            account_name = str(getattr(account, "account_name", "") or "")
            phone = str(getattr(account, "phone", "") or "")
            enabled = bool(getattr(account, "enabled", True))
            status, detail = safe_status_map.get(account_name, ("stopped", "未启动"))

            if self._is_online_status(status):
                online_count += 1

            enabled_item = QTableWidgetItem("是" if enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.status_table.setItem(row, 0, QTableWidgetItem(account_name))
            self.status_table.setItem(row, 1, QTableWidgetItem(phone))
            self.status_table.setItem(row, 2, enabled_item)
            self.status_table.setItem(row, 3, QTableWidgetItem(self._status_label(status)))
            self.status_table.setItem(row, 4, QTableWidgetItem(str(detail or "")))

        self.online_accounts_count_value.setText(str(online_count))

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_online_status(status: str) -> bool:
        normalized = str(status or "").strip().lower()

        return normalized in {
            "running",
            "logged_in",
            "online",
            "运行中",
            "已登录",
        }

    @staticmethod
    def _status_label(status: str) -> str:
        normalized = str(status or "").strip()

        status_map = {
            "idle": "空闲",
            "starting": "启动中",
            "running": "运行中",
            "logged_in": "已登录",
            "logging_in": "登录中",
            "stopped": "已停止",
            "disabled": "未启用",
            "error": "错误",
            "online": "在线",
        }

        return status_map.get(normalized, normalized or "未知")

    @staticmethod
    def _scheduler_status_label(status: str) -> str:
        normalized = str(status or "").strip()

        status_map = {
            "running": "运行中",
            "stopped": "已停止",
            "error": "错误",
            "starting": "启动中",
            "stopping": "停止中",
        }

        return status_map.get(normalized, normalized or "未知")

    def _update_scheduler_buttons(self, scheduler_status: str) -> None:
        normalized = str(scheduler_status or "").strip().lower()
        is_running = normalized == "running"

        self.start_scheduler_button.setEnabled(not is_running)
        self.stop_scheduler_button.setEnabled(is_running)
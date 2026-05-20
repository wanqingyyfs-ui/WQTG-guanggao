from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
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
        self.interval_tasks_count_value = QLabel("0")
        self.daily_tasks_count_value = QLabel("0")
        self.scheduler_status_value = QLabel("stopped")

        self.ad_probability_value = QLabel("75%")
        self.noise_probability_value = QLabel("22%")
        self.skip_probability_value = QLabel("3%")
        self.max_concurrent_tasks_value = QLabel("不限制")
        self.scheduler_tick_value = QLabel("1.0 秒")
        self.default_task_interval_value = QLabel("3600000 毫秒")

        self.log_file_edit = QLineEdit()
        self.log_file_edit.setReadOnly(True)

        self.sessions_dir_edit = QLineEdit()
        self.sessions_dir_edit.setReadOnly(True)

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

        self._build_ui()

    def _build_ui(self) -> None:
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
        summary_layout.addWidget(QLabel("间隔任务"), 2, 2)
        summary_layout.addWidget(self.interval_tasks_count_value, 2, 3)
        summary_layout.addWidget(QLabel("每日任务"), 2, 4)
        summary_layout.addWidget(self.daily_tasks_count_value, 2, 5)

        summary_layout.addWidget(QLabel("调度器状态"), 3, 0)
        summary_layout.addWidget(self.scheduler_status_value, 3, 1)

        strategy_group = QGroupBox("当前发送策略摘要")
        style_group_box(strategy_group)

        strategy_layout = QGridLayout(strategy_group)
        strategy_layout.setContentsMargins(28, 28, 28, 26)
        strategy_layout.setHorizontalSpacing(36)
        strategy_layout.setVerticalSpacing(18)

        strategy_layout.addWidget(QLabel("广告概率"), 0, 0)
        strategy_layout.addWidget(self.ad_probability_value, 0, 1)
        strategy_layout.addWidget(QLabel("噪音概率"), 0, 2)
        strategy_layout.addWidget(self.noise_probability_value, 0, 3)
        strategy_layout.addWidget(QLabel("跳过概率"), 0, 4)
        strategy_layout.addWidget(self.skip_probability_value, 0, 5)

        strategy_layout.addWidget(QLabel("最大并发任务"), 1, 0)
        strategy_layout.addWidget(self.max_concurrent_tasks_value, 1, 1)
        strategy_layout.addWidget(QLabel("调度扫描间隔"), 1, 2)
        strategy_layout.addWidget(self.scheduler_tick_value, 1, 3)
        strategy_layout.addWidget(QLabel("默认任务间隔"), 1, 4)
        strategy_layout.addWidget(self.default_task_interval_value, 1, 5)

        path_group = QGroupBox("运行路径")
        style_group_box(path_group)

        path_form = QFormLayout(path_group)
        style_form_layout(path_form)
        path_form.addRow("日志文件", self.log_file_edit)
        path_form.addRow("Session 目录", self.sessions_dir_edit)

        apply_large_inputs(path_group)

        runtime_button_bar = QWidget()
        runtime_button_layout = QHBoxLayout(runtime_button_bar)
        runtime_button_layout.setContentsMargins(12, 12, 12, 12)
        runtime_button_layout.setSpacing(14)
        runtime_button_layout.addWidget(self.reload_button)
        runtime_button_layout.addStretch(1)
        runtime_button_layout.addWidget(self.start_all_button)
        runtime_button_layout.addWidget(self.stop_all_button)
        runtime_button_layout.addStretch(1)
        runtime_button_layout.addWidget(self.start_scheduler_button)
        runtime_button_layout.addWidget(self.stop_scheduler_button)

        dashboard_content = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_content)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(12)
        dashboard_layout.addWidget(summary_group)
        dashboard_layout.addWidget(strategy_group)
        dashboard_layout.addWidget(path_group)
        dashboard_layout.addWidget(runtime_button_bar)
        dashboard_layout.addStretch(1)

        status_group = QGroupBox("账号运行状态")
        style_group_box(status_group)

        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(18, 20, 18, 18)
        status_layout.addWidget(self.status_table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        title_label = QLabel("运行总控")
        title_label.setObjectName("PageTitleLabel")
        top_layout.addWidget(title_label)
        top_layout.addWidget(make_scroll_area(dashboard_content, minimum_height=360), 1)

        bottom_widget = make_scroll_area(status_group, minimum_height=260)

        splitter = make_vertical_splitter(
            top_widget=top_widget,
            bottom_widget=bottom_widget,
            sizes=[520, 360],
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

        self.ad_probability_value.setText(
            f"{self._safe_int(getattr(settings, 'ad_probability', 75), 75)}%"
        )
        self.noise_probability_value.setText(
            f"{self._safe_int(getattr(settings, 'noise_probability', 22), 22)}%"
        )
        self.skip_probability_value.setText(
            f"{self._safe_int(getattr(settings, 'skip_probability', 3), 3)}%"
        )

        max_concurrent_tasks = self._safe_int(
            getattr(settings, "max_concurrent_tasks", 0),
            0,
        )
        if max_concurrent_tasks <= 0:
            self.max_concurrent_tasks_value.setText("不限制")
        else:
            self.max_concurrent_tasks_value.setText(f"{max_concurrent_tasks} 个")

        self.scheduler_tick_value.setText(
            f"{self._safe_float(getattr(settings, 'scheduler_tick_seconds', 1.0), 1.0):.2f} 秒"
        )
        self.default_task_interval_value.setText(
            f"{self._safe_int(getattr(settings, 'default_task_interval_ms', 3600000), 3600000)} 毫秒"
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
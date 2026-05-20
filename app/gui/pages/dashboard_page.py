from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class DashboardPage(QWidget):
    """
    运行总控页。

    最终版总控页只负责运行控制：
    - 启动全部账号
    - 停止全部账号
    - 启动群发
    - 停止群发

    配置、运行路径、策略摘要、账号状态表都不再放在总控页。
    为了兼容当前 MainWindow，仍保留 update_summary() 和 update_status_table()。
    """

    start_all_requested = Signal()
    stop_all_requested = Signal()
    start_scheduler_requested = Signal()
    stop_scheduler_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title_label = QLabel("运行总控")
        self.title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("群发调度：已停止")
        self.status_label.setObjectName("DashboardStatusLabel")

        self.online_label = QLabel("在线账号：0")
        self.online_label.setObjectName("DashboardStatusLabel")

        self.hint_label = QLabel("发送数据修改前，请先停止群发功能。")
        self.hint_label.setObjectName("DashboardHintLabel")
        self.hint_label.setWordWrap(True)

        self.start_all_button = QPushButton("启动全部账号")
        self.stop_all_button = QPushButton("停止全部账号")
        self.start_scheduler_button = QPushButton("启动群发")
        self.stop_scheduler_button = QPushButton("停止群发")

        self._build_ui()
        self._connect_signals()
        self._update_scheduler_buttons("stopped")

    def _build_ui(self) -> None:
        card = QFrame()
        card.setObjectName("DashboardCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 32, 34, 32)
        card_layout.setSpacing(22)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(18)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.online_label)
        status_layout.addStretch(1)

        button_layout = QGridLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setHorizontalSpacing(18)
        button_layout.setVerticalSpacing(16)
        button_layout.setColumnStretch(0, 1)
        button_layout.setColumnStretch(1, 1)

        button_layout.addWidget(self.start_all_button, 0, 0)
        button_layout.addWidget(self.stop_all_button, 0, 1)
        button_layout.addWidget(self.start_scheduler_button, 1, 0)
        button_layout.addWidget(self.stop_scheduler_button, 1, 1)

        card_layout.addLayout(status_layout)
        card_layout.addLayout(button_layout)
        card_layout.addWidget(self.hint_label)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)
        page_layout.addWidget(self.title_label)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addStretch(1)

    def _connect_signals(self) -> None:
        self.start_all_button.clicked.connect(self.start_all_requested.emit)
        self.stop_all_button.clicked.connect(self.stop_all_requested.emit)
        self.start_scheduler_button.clicked.connect(
            self.start_scheduler_requested.emit
        )
        self.stop_scheduler_button.clicked.connect(
            self.stop_scheduler_requested.emit
        )

    def update_summary(
        self,
        accounts,
        groups,
        tasks,
        settings,
        scheduler_status: str = "stopped",
    ) -> None:
        del groups, tasks, settings

        accounts_list = list(accounts or [])
        self._update_scheduler_buttons(scheduler_status)
        self.status_label.setText(
            f"群发调度：{self._scheduler_status_label(scheduler_status)}"
        )

        enabled_accounts = sum(
            1 for item in accounts_list if bool(getattr(item, "enabled", True))
        )
        self.online_label.setToolTip(f"启用账号：{enabled_accounts}")

    def update_status_table(self, accounts, status_map) -> None:
        accounts_list = list(accounts or [])
        safe_status_map = dict(status_map or {})

        online_count = 0

        for account in accounts_list:
            account_name = str(getattr(account, "account_name", "") or "")
            status, _detail = safe_status_map.get(account_name, ("stopped", "未启动"))

            if self._is_online_status(status):
                online_count += 1

        self.online_label.setText(f"在线账号：{online_count}")

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
        normalized = str(status or "").strip().lower()

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

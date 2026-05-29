from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui.pages.layout_utils import style_text_editor


class DashboardPage(QWidget):
    """运行总控页。

    上半部分负责运行控制；下半部分直接显示实时运行日志，替代原来的独立“日志查看”页面。
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

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(3000)
        self.log_text.setPlaceholderText("运行日志会显示在这里。")
        style_text_editor(self.log_text, min_height=320)

        self.clear_log_button = QPushButton("清空界面日志")

        self._build_ui()
        self._connect_signals()
        self._update_scheduler_buttons("stopped")

    def _build_ui(self) -> None:
        card = QFrame()
        card.setObjectName("DashboardCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 28, 34, 28)
        card_layout.setSpacing(20)

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

        log_card = QFrame()
        log_card.setObjectName("DashboardCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 18, 18, 18)
        log_layout.setSpacing(12)

        log_header_layout = QHBoxLayout()
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_title = QLabel("运行日志")
        log_title.setObjectName("DashboardStatusLabel")
        log_header_layout.addWidget(log_title)
        log_header_layout.addStretch(1)
        log_header_layout.addWidget(self.clear_log_button)

        log_layout.addLayout(log_header_layout)
        log_layout.addWidget(self.log_text, 1)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)
        page_layout.addWidget(self.title_label)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addWidget(log_card, 1)

    def _connect_signals(self) -> None:
        self.start_all_button.clicked.connect(self.start_all_requested.emit)
        self.stop_all_button.clicked.connect(self.stop_all_requested.emit)
        self.start_scheduler_button.clicked.connect(self.start_scheduler_requested.emit)
        self.stop_scheduler_button.clicked.connect(self.stop_scheduler_requested.emit)
        self.clear_log_button.clicked.connect(self.clear_logs)

    def update_summary(self, accounts, groups, tasks, settings, scheduler_status: str = "stopped") -> None:
        del groups, tasks, settings
        accounts_list = list(accounts or [])
        self._update_scheduler_buttons(scheduler_status)
        self.status_label.setText(f"群发调度：{self._scheduler_status_label(scheduler_status)}")
        enabled_accounts = sum(1 for item in accounts_list if bool(getattr(item, "enabled", True)))
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

    def append_log(self, level: str, message: str) -> None:
        now_text = datetime.now().strftime("%H:%M:%S")
        self.append_log_lines([f"{now_text} [{str(level or 'INFO').upper()}] {message}"])

    def append_log_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        self.log_text.appendPlainText("\n".join(str(line or "") for line in lines))
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_logs(self) -> None:
        self.log_text.clear()

    @staticmethod
    def _is_online_status(status: str) -> bool:
        return str(status or "").strip().lower() in {"running", "logged_in", "online", "运行中", "已登录"}

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

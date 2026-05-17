from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts_count_value = QLabel("0")
        self.online_accounts_count_value = QLabel("0")
        self.groups_count_value = QLabel("0")
        self.enabled_tasks_count_value = QLabel("0")
        self.scheduler_status_value = QLabel("stopped")

        self.scheduler_tick_spin = QDoubleSpinBox()
        self.scheduler_tick_spin.setRange(0.2, 60.0)
        self.scheduler_tick_spin.setDecimals(1)
        self.scheduler_tick_spin.setSingleStep(0.5)
        self.scheduler_tick_spin.setMinimumWidth(360)
        self.scheduler_tick_spin.setMinimumHeight(42)

        self.max_concurrent_tasks_spin = QSpinBox()
        self.max_concurrent_tasks_spin.setRange(1, 20)
        self.max_concurrent_tasks_spin.setMinimumWidth(360)
        self.max_concurrent_tasks_spin.setMinimumHeight(42)

        self.default_send_interval_spin = QDoubleSpinBox()
        self.default_send_interval_spin.setRange(0.0, 86400.0)
        self.default_send_interval_spin.setDecimals(1)
        self.default_send_interval_spin.setSingleStep(1.0)
        self.default_send_interval_spin.setMinimumWidth(360)
        self.default_send_interval_spin.setMinimumHeight(42)

        self.template_account_edit = QLineEdit()
        self.template_chat_id_edit = QLineEdit()
        self.template_account_edit.setMinimumHeight(40)
        self.template_chat_id_edit.setMinimumHeight(40)

        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载配置")
        self.start_all_button = QPushButton("启动全部账号")
        self.stop_all_button = QPushButton("停止全部账号")
        self.start_scheduler_button = QPushButton("启动群发调度")
        self.stop_scheduler_button = QPushButton("停止群发调度")

        self.status_table = QTableWidget(0, 4)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setMinimumHeight(220)
        self.status_table.setMaximumHeight(16777215)
        self.status_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.status_table.setHorizontalHeaderLabels(["账号", "手机号", "状态", "说明"])
        self.status_table.horizontalHeader().setStretchLastSection(True)

        summary_group = QGroupBox("运行概览")
        summary_layout = QGridLayout(summary_group)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(16)
        summary_layout.addWidget(QLabel("账号总数"), 0, 0)
        summary_layout.addWidget(self.accounts_count_value, 0, 1)
        summary_layout.addWidget(QLabel("在线账号"), 0, 2)
        summary_layout.addWidget(self.online_accounts_count_value, 0, 3)
        summary_layout.addWidget(QLabel("目标群组"), 1, 0)
        summary_layout.addWidget(self.groups_count_value, 1, 1)
        summary_layout.addWidget(QLabel("启用任务"), 1, 2)
        summary_layout.addWidget(self.enabled_tasks_count_value, 1, 3)
        summary_layout.addWidget(QLabel("调度器状态"), 2, 0)
        summary_layout.addWidget(self.scheduler_status_value, 2, 1)

        runtime_group = QGroupBox("群发调度配置")
        runtime_form = QFormLayout(runtime_group)
        runtime_form.setHorizontalSpacing(18)
        runtime_form.setVerticalSpacing(14)
        runtime_form.addRow("任务扫描间隔（秒）：", self.scheduler_tick_spin)
        runtime_form.addRow("最大并发任务数：", self.max_concurrent_tasks_spin)
        runtime_form.addRow("默认发送间隔（秒）：", self.default_send_interval_spin)

        template_group = QGroupBox("素材群监听配置")
        template_form = QFormLayout(template_group)
        template_form.setHorizontalSpacing(18)
        template_form.setVerticalSpacing(14)
        template_form.addRow("素材账号名：", self.template_account_edit)
        template_form.addRow("素材群 Chat ID：", self.template_chat_id_edit)

        config_button_layout = QHBoxLayout()
        config_button_layout.setSpacing(12)
        config_button_layout.addWidget(self.save_button)
        config_button_layout.addWidget(self.reload_button)
        config_button_layout.addStretch()

        runtime_button_layout = QHBoxLayout()
        runtime_button_layout.setSpacing(12)
        runtime_button_layout.addWidget(self.start_all_button)
        runtime_button_layout.addWidget(self.stop_all_button)
        runtime_button_layout.addStretch()
        runtime_button_layout.addWidget(self.start_scheduler_button)
        runtime_button_layout.addWidget(self.stop_scheduler_button)

        status_scroll = QScrollArea()
        status_scroll.setWidgetResizable(True)
        status_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        status_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        status_scroll.setWidget(self.status_table)

        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.addWidget(summary_group)
        layout.addWidget(runtime_group)
        layout.addWidget(template_group)
        layout.addLayout(config_button_layout)
        layout.addLayout(runtime_button_layout)
        layout.addWidget(status_scroll, 1)

    def update_summary(
        self,
        accounts,
        groups,
        tasks,
        settings,
        scheduler_status: str = "stopped",
    ) -> None:
        self.accounts_count_value.setText(str(len(accounts)))

        online_count = 0
        for account in accounts:
            status = getattr(account, "runtime_status", "")
            if status in {"running", "logged_in", "online"}:
                online_count += 1

        self.online_accounts_count_value.setText(str(online_count))
        self.groups_count_value.setText(str(len(groups)))
        self.enabled_tasks_count_value.setText(str(sum(1 for item in tasks if item.enabled)))
        self.scheduler_status_value.setText(scheduler_status)

        self.scheduler_tick_spin.setValue(float(settings.scheduler_tick_seconds or 1.0))
        self.max_concurrent_tasks_spin.setValue(int(settings.max_concurrent_tasks or 1))
        self.default_send_interval_spin.setValue(
            float(settings.default_send_interval_seconds or 1.0)
        )
        self.template_account_edit.setText(settings.template_source_account_name or "")
        self.template_chat_id_edit.setText(str(settings.template_source_chat_id or ""))

    def update_status_table(self, accounts, status_map) -> None:
        self.status_table.setRowCount(len(accounts))

        for row, account in enumerate(accounts):
            status, detail = status_map.get(account.account_name, ("未启动", ""))

            self.status_table.setItem(row, 0, QTableWidgetItem(account.account_name))
            self.status_table.setItem(row, 1, QTableWidgetItem(account.phone))
            self.status_table.setItem(row, 2, QTableWidgetItem(status))
            self.status_table.setItem(row, 3, QTableWidgetItem(detail))
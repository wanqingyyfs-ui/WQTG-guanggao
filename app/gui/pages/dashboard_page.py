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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
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
        self.online_accounts_count_value = QLabel("0")
        self.groups_count_value = QLabel("0")
        self.enabled_tasks_count_value = QLabel("0")
        self.scheduler_status_value = QLabel("stopped")

        for label in [
            self.accounts_count_value,
            self.online_accounts_count_value,
            self.groups_count_value,
            self.enabled_tasks_count_value,
            self.scheduler_status_value,
        ]:
            label.setMinimumHeight(42)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.scheduler_tick_spin = QDoubleSpinBox()
        self.scheduler_tick_spin.setRange(0.2, 60.0)
        self.scheduler_tick_spin.setDecimals(1)
        self.scheduler_tick_spin.setSingleStep(0.5)

        self.max_concurrent_tasks_spin = QSpinBox()
        self.max_concurrent_tasks_spin.setRange(1, 20)

        self.default_send_interval_spin = QDoubleSpinBox()
        self.default_send_interval_spin.setRange(0.0, 86400.0)
        self.default_send_interval_spin.setDecimals(1)
        self.default_send_interval_spin.setSingleStep(1.0)

        self.template_account_edit = QLineEdit()
        self.template_chat_id_edit = QLineEdit()

        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载配置")
        self.start_all_button = QPushButton("启动全部账号")
        self.stop_all_button = QPushButton("停止全部账号")
        self.start_scheduler_button = QPushButton("启动群发调度")
        self.stop_scheduler_button = QPushButton("停止群发调度")

        self.status_table = QTableWidget(0, 4)
        self.status_table.setHorizontalHeaderLabels(["账号", "手机号", "状态", "说明"])
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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
        summary_layout.addWidget(QLabel("在线账号"), 0, 2)
        summary_layout.addWidget(self.online_accounts_count_value, 0, 3)
        summary_layout.addWidget(QLabel("目标群组"), 1, 0)
        summary_layout.addWidget(self.groups_count_value, 1, 1)
        summary_layout.addWidget(QLabel("启用任务"), 1, 2)
        summary_layout.addWidget(self.enabled_tasks_count_value, 1, 3)
        summary_layout.addWidget(QLabel("调度器状态"), 2, 0)
        summary_layout.addWidget(self.scheduler_status_value, 2, 1)

        runtime_group = QGroupBox("群发调度配置")
        style_group_box(runtime_group)

        runtime_form = QFormLayout(runtime_group)
        style_form_layout(runtime_form)
        runtime_form.addRow("任务扫描间隔（秒）", self.scheduler_tick_spin)
        runtime_form.addRow("最大并发任务数", self.max_concurrent_tasks_spin)
        runtime_form.addRow("默认发送间隔（秒）", self.default_send_interval_spin)

        template_group = QGroupBox("素材群监听配置")
        style_group_box(template_group)

        template_form = QFormLayout(template_group)
        style_form_layout(template_form)
        template_form.addRow("素材账号名", self.template_account_edit)
        template_form.addRow("素材群 Chat ID", self.template_chat_id_edit)

        apply_large_inputs(runtime_group)
        apply_large_inputs(template_group)

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
            sizes=[520, 330],
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
        self.accounts_count_value.setText(str(len(accounts)))

        self.groups_count_value.setText(str(len(groups)))
        self.enabled_tasks_count_value.setText(
            str(sum(1 for item in tasks if item.enabled))
        )
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

        online_count = 0

        for row, account in enumerate(accounts):
            status, detail = status_map.get(account.account_name, ("未启动", ""))

            if status in {"running", "logged_in", "online", "运行中", "已登录"}:
                online_count += 1

            self.status_table.setItem(row, 0, QTableWidgetItem(account.account_name))
            self.status_table.setItem(row, 1, QTableWidgetItem(account.phone))
            self.status_table.setItem(row, 2, QTableWidgetItem(status))
            self.status_table.setItem(row, 3, QTableWidgetItem(detail))

        self.online_accounts_count_value.setText(str(online_count))
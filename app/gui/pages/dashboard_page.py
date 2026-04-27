from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts_count_value = QLabel("0")
        self.enabled_accounts_count_value = QLabel("0")
        self.rules_count_value = QLabel("0")
        self.enabled_rules_count_value = QLabel("0")

        self.reply_interval_spin = QDoubleSpinBox()
        self.reply_interval_spin.setRange(0, 60)
        self.reply_interval_spin.setDecimals(1)
        self.reply_interval_spin.setSingleStep(0.5)
        self.reply_interval_spin.setMinimumWidth(360)
        self.reply_interval_spin.setMinimumHeight(42)

        self.template_account_edit = QLineEdit()
        self.template_chat_id_edit = QLineEdit()

        self.template_account_edit.setMinimumHeight(40)
        self.template_chat_id_edit.setMinimumHeight(40)

        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载配置")
        self.start_all_button = QPushButton("启动全部账号")
        self.stop_all_button = QPushButton("停止全部账号")

        self.status_table = QTableWidget(0, 4)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setMinimumHeight(220)
        self.status_table.setMaximumHeight(16777215)
        self.status_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.status_table.setHorizontalHeaderLabels(["账号", "手机号", "状态", "说明"])
        self.status_table.horizontalHeader().setStretchLastSection(True)

        summary_group = QGroupBox("运行概览")
        summary_layout = QGridLayout(summary_group)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(16)
        summary_layout.addWidget(QLabel("账号总数"), 0, 0)
        summary_layout.addWidget(self.accounts_count_value, 0, 1)
        summary_layout.addWidget(QLabel("启用账号"), 0, 2)
        summary_layout.addWidget(self.enabled_accounts_count_value, 0, 3)
        summary_layout.addWidget(QLabel("规则总数"), 1, 0)
        summary_layout.addWidget(self.rules_count_value, 1, 1)
        summary_layout.addWidget(QLabel("启用规则"), 1, 2)
        summary_layout.addWidget(self.enabled_rules_count_value, 1, 3)

        runtime_group = QGroupBox("基础运行配置")
        runtime_form = QFormLayout(runtime_group)
        runtime_form.setHorizontalSpacing(18)
        runtime_form.setVerticalSpacing(14)
        runtime_form.addRow("回复间隔（秒）：", self.reply_interval_spin)

        template_group = QGroupBox("素材群监听配置")
        template_form = QFormLayout(template_group)
        template_form.setHorizontalSpacing(18)
        template_form.setVerticalSpacing(14)
        template_form.addRow("监听账号名：", self.template_account_edit)
        template_form.addRow("素材群 Chat ID：", self.template_chat_id_edit)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.reload_button)
        button_layout.addStretch()
        button_layout.addWidget(self.start_all_button)
        button_layout.addWidget(self.stop_all_button)

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
        layout.addLayout(button_layout)
        layout.addWidget(status_scroll, 1)

    def update_summary(self, accounts, rules, settings):
        self.accounts_count_value.setText(str(len(accounts)))
        self.enabled_accounts_count_value.setText(str(sum(1 for x in accounts if x.enabled)))
        self.rules_count_value.setText(str(len(rules)))
        self.enabled_rules_count_value.setText(str(sum(1 for x in rules if x.enabled)))

        self.reply_interval_spin.setValue(float(settings.reply_interval_seconds or 0))
        self.template_account_edit.setText(settings.template_source_account_name or "")
        self.template_chat_id_edit.setText(str(settings.template_source_chat_id or ""))

    def update_status_table(self, accounts, status_map):
        self.status_table.setRowCount(len(accounts))

        for row, acc in enumerate(accounts):
            status, detail = status_map.get(acc.account_name, ("未启动", ""))
            self.status_table.setItem(row, 0, QTableWidgetItem(acc.account_name))
            self.status_table.setItem(row, 1, QTableWidgetItem(acc.phone))
            self.status_table.setItem(row, 2, QTableWidgetItem(status))
            self.status_table.setItem(row, 3, QTableWidgetItem(detail))
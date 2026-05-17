from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
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

from app.core.models import AccountConfig
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_table,
)


class AccountPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts: list[AccountConfig] = []
        self.status_map: dict[str, tuple[str, str]] = {}

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["账号名", "手机号", "启用", "状态", "详情"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        style_table(self.table)

        self.account_name_edit = QLineEdit()
        self.api_id_edit = QLineEdit()
        self.api_hash_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.session_name_edit = QLineEdit()

        self.enabled_checkbox = QCheckBox("启用此账号")
        self.enabled_checkbox.setChecked(True)

        form_group = QGroupBox("账号配置")
        style_group_box(form_group)

        form_layout = QFormLayout(form_group)
        style_form_layout(form_layout)

        form_layout.addRow("账号名称", self.account_name_edit)
        form_layout.addRow("API ID", self.api_id_edit)
        form_layout.addRow("API Hash", self.api_hash_edit)
        form_layout.addRow("手机号", self.phone_edit)
        form_layout.addRow("Session 名称", self.session_name_edit)
        form_layout.addRow("启用状态", self.enabled_checkbox)

        apply_large_inputs(form_group)

        self.add_button = QPushButton("新增账号")
        self.save_button = QPushButton("保存账号")
        self.delete_button = QPushButton("删除账号")
        self.login_button = QPushButton("登录账号")
        self.start_button = QPushButton("启动该账号")
        self.stop_button = QPushButton("停止该账号")

        button_bar = QWidget()
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(14)

        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)

        button_layout.addStretch(1)

        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        table_group = QGroupBox("账号列表")
        style_group_box(table_group)

        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(18, 20, 18, 18)
        table_layout.addWidget(self.table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_layout.addWidget(QLabel("账号管理"))
        top_layout.addWidget(
            make_scroll_area(table_group, minimum_height=240),
            1,
        )

        bottom_content = QWidget()
        bottom_layout = QVBoxLayout(bottom_content)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(form_group)
        bottom_layout.addWidget(button_bar)

        bottom_scroll = make_scroll_area(
            bottom_content,
            minimum_height=340,
        )

        splitter = make_vertical_splitter(
            top_widget=top_widget,
            bottom_widget=bottom_scroll,
            sizes=[320, 560],
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(
            self.load_selected_account
        )

    def set_accounts(
        self,
        accounts: list[AccountConfig],
        status_map: dict[str, tuple[str, str]],
    ) -> None:
        self.accounts = list(accounts)
        self.status_map = dict(status_map)
        self.refresh_table()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.accounts))

        for row, account in enumerate(self.accounts):
            status, detail = self.status_map.get(
                account.account_name,
                ("idle", "未启动"),
            )

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(account.account_name),
            )

            self.table.setItem(
                row,
                1,
                QTableWidgetItem(account.phone),
            )

            self.table.setItem(
                row,
                2,
                QTableWidgetItem("是" if account.enabled else "否"),
            )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(status),
            )

            self.table.setItem(
                row,
                4,
                QTableWidgetItem(detail),
            )

    def load_selected_account(self) -> None:
        row = self.table.currentRow()

        if row < 0 or row >= len(self.accounts):
            return

        account = self.accounts[row]

        self.account_name_edit.setText(account.account_name)
        self.api_id_edit.setText(str(account.api_id))
        self.api_hash_edit.setText(account.api_hash)
        self.phone_edit.setText(account.phone)
        self.session_name_edit.setText(account.session_name)
        self.enabled_checkbox.setChecked(account.enabled)

    def clear_form(self) -> None:
        self.table.clearSelection()

        self.account_name_edit.clear()
        self.api_id_edit.clear()
        self.api_hash_edit.clear()
        self.phone_edit.clear()
        self.session_name_edit.clear()

        self.enabled_checkbox.setChecked(True)

    def get_form_account(self) -> AccountConfig:
        api_id_text = self.api_id_edit.text().strip()

        if not api_id_text:
            raise ValueError("API ID 不能为空")

        try:
            api_id = int(api_id_text)
        except ValueError as exc:
            raise ValueError("API ID 必须是数字") from exc

        return AccountConfig(
            account_name=self.account_name_edit.text().strip(),
            api_id=api_id,
            api_hash=self.api_hash_edit.text().strip(),
            phone=self.phone_edit.text().strip(),
            session_name=self.session_name_edit.text().strip(),
            enabled=self.enabled_checkbox.isChecked(),
        )

    def get_selected_account_name(self) -> str:
        return self.account_name_edit.text().strip()
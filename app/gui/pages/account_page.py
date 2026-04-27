from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from app.core.models import AccountConfig


class AccountPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.accounts: list[AccountConfig] = []
        self.status_map: dict[str, tuple[str, str]] = {}

        self.table = QTableWidget(0, 5)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        self.table.setMaximumHeight(16777215)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setHorizontalHeaderLabels(["账号名", "手机号", "启用", "状态", "详情"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.account_name_edit = QLineEdit()
        self.api_id_edit = QLineEdit()
        self.api_hash_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.session_name_edit = QLineEdit()
        self.enabled_checkbox = QCheckBox("启用此账号")
        for widget in [
            self.account_name_edit,
            self.api_id_edit,
            self.api_hash_edit,
            self.phone_edit,
            self.session_name_edit,
        ]:
            widget.setMinimumWidth(420)
            widget.setMinimumHeight(42)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        form_group = QGroupBox("账号编辑")
        form_group.setObjectName("accountFormGroup")
        groupbox_title_style = """
        QGroupBox#templateFormGroup,
        QGroupBox#accountFormGroup {
            margin-top: 28px;
            padding-top: 22px;
        }

        QGroupBox#templateFormGroup::title,
        QGroupBox#accountFormGroup::title {
            subcontrol-origin: margin;
            left: 16px;
            padding: 2px 10px 2px 10px;
        }
        """

        form_group.setStyleSheet(groupbox_title_style)
        form_group.setMinimumHeight(520)
        form_group.setMinimumWidth(1180)
        form_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )

        form_layout = QFormLayout(form_group)
        form_layout.setContentsMargins(26, 24, 26, 24)
        form_layout.setHorizontalSpacing(24)
        form_layout.setVerticalSpacing(16)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        form_layout.addRow("账号名称：", self.account_name_edit)
        form_layout.addRow("API ID：", self.api_id_edit)
        form_layout.addRow("API Hash：", self.api_hash_edit)
        form_layout.addRow("手机号：", self.phone_edit)
        form_layout.addRow("Session 名称：", self.session_name_edit)
        form_layout.addRow("", self.enabled_checkbox)

        self.add_button = QPushButton("新增账号")
        self.save_button = QPushButton("保存账号")
        self.delete_button = QPushButton("删除账号")
        self.login_button = QPushButton("登录账号")
        self.start_button = QPushButton("启动该账号")
        self.stop_button = QPushButton("停止该账号")

        button_bar = QWidget()
        button_bar.setMinimumHeight(72)
        button_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 10, 12, 10)
        button_layout.setSpacing(12)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 4, 0, 0)
        top_layout.setSpacing(18)
        top_layout.addWidget(QLabel("账号列表"))

        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setMinimumHeight(180)
        table_scroll.setWidget(self.table)

        top_layout.addWidget(table_scroll)

        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_scroll.setMinimumHeight(380)
        form_scroll.setWidget(form_group)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)
        bottom_layout.addWidget(form_scroll, 1)
        bottom_layout.addWidget(button_bar, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([240, 520])
        splitter.setStyleSheet("""
        QSplitter::handle {
            background-color: #d0d0d0;
        }
        QSplitter::handle:hover {
            background-color: #b0b0b0;
        }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(self.load_selected_account)

    def set_accounts(self, accounts: list[AccountConfig], status_map: dict[str, tuple[str, str]]) -> None:
        self.accounts = accounts
        self.status_map = status_map
        self.refresh_table()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.accounts))
        for row, account in enumerate(self.accounts):
            status, detail = self.status_map.get(account.account_name, ("idle", "未启动"))
            self.table.setItem(row, 0, QTableWidgetItem(account.account_name))
            self.table.setItem(row, 1, QTableWidgetItem(account.phone))
            self.table.setItem(row, 2, QTableWidgetItem("是" if account.enabled else "否"))
            self.table.setItem(row, 3, QTableWidgetItem(status))
            self.table.setItem(row, 4, QTableWidgetItem(detail))

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
        self.account_name_edit.clear()
        self.api_id_edit.clear()
        self.api_hash_edit.clear()
        self.phone_edit.clear()
        self.session_name_edit.clear()
        self.enabled_checkbox.setChecked(True)

    def get_form_account(self) -> AccountConfig:
        return AccountConfig(
            account_name=self.account_name_edit.text().strip(),
            api_id=int(self.api_id_edit.text().strip()),
            api_hash=self.api_hash_edit.text().strip(),
            phone=self.phone_edit.text().strip(),
            session_name=self.session_name_edit.text().strip(),
            enabled=self.enabled_checkbox.isChecked(),
        )

    def get_selected_account_name(self) -> str:
        return self.account_name_edit.text().strip()
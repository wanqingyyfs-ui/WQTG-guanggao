from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import AccountConfig
from app.gui.pages.layout_utils import style_table


class AccountPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts: list[AccountConfig] = []
        self.status_map: dict[str, tuple[str, str]] = {}
        self.default_account_enabled = True
        self.default_session_name_follow_account = True

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["账号名", "手机号", "API ID", "Session", "启用", "状态", "详情"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)

        self.add_button = QPushButton("新增账号")
        self.config_button = QPushButton("配置账号")
        self.delete_button = QPushButton("删除账号")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.login_button = QPushButton("登录账号")
        self.start_button = QPushButton("启动该账号")
        self.stop_button = QPushButton("停止该账号")

        self._build_ui()
        self.table.itemSelectionChanged.connect(self.update_action_buttons)
        self.update_action_buttons()

    def _build_ui(self) -> None:
        title_label = QLabel("账号管理")
        title_label.setObjectName("PageTitleLabel")

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.config_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(button_layout)

    def set_defaults(
        self,
        default_account_enabled: bool = True,
        default_session_name_follow_account: bool = True,
    ) -> None:
        self.default_account_enabled = bool(default_account_enabled)
        self.default_session_name_follow_account = bool(default_session_name_follow_account)

    def set_accounts(
        self,
        accounts: list[AccountConfig],
        status_map: dict[str, tuple[str, str]],
    ) -> None:
        selected_name = self.get_selected_account_name()
        self.accounts = list(accounts or [])
        self.status_map = dict(status_map or {})
        self.refresh_table()
        self.select_account_name(selected_name)
        self.update_action_buttons()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.accounts))

        for row, account in enumerate(self.accounts):
            status, detail = self.status_map.get(account.account_name, ("stopped", "未启动"))

            enabled_item = QTableWidgetItem("是" if account.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, QTableWidgetItem(str(account.account_name)))
            self.table.setItem(row, 1, QTableWidgetItem(str(account.phone)))
            self.table.setItem(row, 2, QTableWidgetItem(str(account.api_id)))
            self.table.setItem(row, 3, QTableWidgetItem(str(account.session_name)))
            self.table.setItem(row, 4, enabled_item)
            self.table.setItem(row, 5, QTableWidgetItem(self._status_label(status)))
            self.table.setItem(row, 6, QTableWidgetItem(str(detail or "")))

    def get_selected_row(self) -> int:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def get_selected_account_name(self) -> str:
        row = self.get_selected_row()
        if 0 <= row < len(self.accounts):
            return str(self.accounts[row].account_name or "").strip()
        return ""

    def select_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        else:
            self.table.clearSelection()
        self.update_action_buttons()

    def select_account_name(self, account_name: str) -> None:
        target = str(account_name or "").strip()
        if not target:
            return

        for row, account in enumerate(self.accounts):
            if str(account.account_name or "").strip() == target:
                self.select_row(row)
                return

    def clear_selection(self) -> None:
        self.table.clearSelection()
        self.update_action_buttons()

    def update_action_buttons(self) -> None:
        row = self.get_selected_row()
        has_selection = 0 <= row < len(self.accounts)

        self.config_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(has_selection and row < len(self.accounts) - 1)
        self.login_button.setEnabled(has_selection)
        self.start_button.setEnabled(has_selection)
        self.stop_button.setEnabled(has_selection)

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

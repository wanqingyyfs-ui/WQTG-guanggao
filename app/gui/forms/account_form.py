from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.models import AccountConfig
from app.gui.pages.layout_utils import apply_large_inputs


class AccountForm(QWidget):
    add_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.default_account_enabled = True
        self.default_session_name_follow_account = True
        self._loading = False

        self.account_name_edit = QLineEdit()
        self.account_name_edit.setPlaceholderText("例如：account_01")

        self.api_id_edit = QLineEdit()
        self.api_id_edit.setPlaceholderText("Telegram API ID，只能填写数字")

        self.api_hash_edit = QLineEdit()
        self.api_hash_edit.setPlaceholderText("Telegram API Hash")
        self.api_hash_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("例如：+8613800000000")

        self.session_name_edit = QLineEdit()
        self.session_name_edit.setPlaceholderText("留空时默认使用账号名称")

        self.enabled_checkbox = QCheckBox("启用此账号")

        self.add_button = QPushButton("新增")
        self.save_button = QPushButton("保存")
        self._style_action_button(self.add_button)
        self._style_action_button(self.save_button)

        self._build_ui()
        self.account_name_edit.textChanged.connect(self._on_account_name_changed)
        self.add_button.clicked.connect(self.add_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.clear_form()

    def _build_ui(self) -> None:
        self.setMinimumSize(560, 420)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )

        grid = QGridLayout()
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        grid.setColumnMinimumWidth(0, 88)
        grid.setColumnMinimumWidth(2, 76)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_labeled_widget(grid, 0, 0, "账号名称：", self.account_name_edit)
        grid.addWidget(self.enabled_checkbox, 0, 2, 1, 2)

        self._add_labeled_widget(grid, 1, 0, "API ID：", self.api_id_edit)
        self._add_labeled_widget(grid, 1, 2, "手机号：", self.phone_edit)

        self._add_labeled_widget(grid, 2, 0, "API Hash：", self.api_hash_edit)
        self._add_labeled_widget(grid, 2, 2, "Session：", self.session_name_edit)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)
        button_layout.setSpacing(14)
        button_layout.addStretch(1)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(16)
        layout.addSpacing(18)
        layout.addLayout(grid)
        layout.addStretch(1)
        layout.addLayout(button_layout)

        apply_large_inputs(self)

    @staticmethod
    def _style_action_button(button: QPushButton) -> None:
        button.setMinimumWidth(120)
        button.setMinimumHeight(38)

    @staticmethod
    def _add_labeled_widget(
        grid: QGridLayout,
        row: int,
        label_column: int,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, label_column)
        grid.addWidget(widget, row, label_column + 1)

    def set_defaults(
        self,
        default_account_enabled: bool = True,
        default_session_name_follow_account: bool = True,
    ) -> None:
        self.default_account_enabled = bool(default_account_enabled)
        self.default_session_name_follow_account = bool(default_session_name_follow_account)

        if not self.account_name_edit.text().strip():
            self.enabled_checkbox.setChecked(self.default_account_enabled)

    def load_account(self, account: AccountConfig) -> None:
        self._loading = True
        try:
            self.account_name_edit.setText(str(account.account_name or ""))
            self.api_id_edit.setText(str(account.api_id or ""))
            self.api_hash_edit.setText(str(account.api_hash or ""))
            self.phone_edit.setText(str(account.phone or ""))
            self.session_name_edit.setText(str(account.session_name or ""))
            self.enabled_checkbox.setChecked(bool(account.enabled))
        finally:
            self._loading = False

    def clear_form(self) -> None:
        self._loading = True
        try:
            self.account_name_edit.clear()
            self.api_id_edit.clear()
            self.api_hash_edit.clear()
            self.phone_edit.clear()
            self.session_name_edit.clear()
            self.enabled_checkbox.setChecked(bool(self.default_account_enabled))
        finally:
            self._loading = False

    def get_form_account(self) -> AccountConfig:
        account_name = self.account_name_edit.text().strip()
        api_id = self._parse_api_id(self.api_id_edit.text())
        api_hash = self.api_hash_edit.text().strip()
        phone = self.phone_edit.text().strip()
        session_name = self.session_name_edit.text().strip()

        if not session_name and account_name and self.default_session_name_follow_account:
            session_name = account_name

        return AccountConfig(
            account_name=account_name,
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            session_name=session_name,
            enabled=self.enabled_checkbox.isChecked(),
        )

    def _on_account_name_changed(self, value: str) -> None:
        if self._loading or not self.default_session_name_follow_account:
            return

        if self.session_name_edit.text().strip():
            return

        self.session_name_edit.setText(str(value or "").strip())

    @staticmethod
    def _parse_api_id(value: Any) -> int:
        raw_text = str(value or "").strip()
        if not raw_text:
            raise ValueError("API ID 不能为空")

        try:
            api_id = int(raw_text)
        except ValueError as exc:
            raise ValueError("API ID 必须是数字") from exc

        if api_id <= 0:
            raise ValueError("API ID 必须是大于 0 的数字")

        return api_id

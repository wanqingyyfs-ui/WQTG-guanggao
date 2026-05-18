from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class LoginConfirmDialog(QDialog):
    def __init__(self, account_name: str, phone: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle("确认登录")
        self.setModal(True)
        self.resize(430, 170)

        safe_account_name = str(account_name or "").strip()
        safe_phone = str(phone or "").strip()

        label = QLabel(
            "即将开始 Telegram 用户号登录流程。\n\n"
            f"账号：{safe_account_name or '未填写'}\n"
            f"手机号：{safe_phone or '未填写'}\n\n"
            "继续后可能会向该手机号或 Telegram 客户端发送验证码。"
        )
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

        if ok_button is not None:
            ok_button.setText("继续登录")

        if cancel_button is not None:
            cancel_button.setText("取消")

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(label)
        layout.addWidget(button_box)
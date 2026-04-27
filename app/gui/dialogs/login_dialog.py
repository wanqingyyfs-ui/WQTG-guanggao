from __future__ import annotations

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
        self.resize(360, 120)

        label = QLabel(f"准备登录账号：{account_name}\n手机号：{phone}\n\n是否继续？")
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(button_box)
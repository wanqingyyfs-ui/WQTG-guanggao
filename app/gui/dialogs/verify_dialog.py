from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class VerifyInputDialog(QDialog):
    def __init__(
        self,
        title: str,
        label_text: str,
        password_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle(str(title or "输入验证信息"))
        self.setModal(True)
        self.resize(460, 180)

        self.label = QLabel(str(label_text or "请输入验证信息："))
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.input_edit = QLineEdit()
        self.input_edit.setMinimumHeight(42)
        self.input_edit.setClearButtonEnabled(True)

        if password_mode:
            self.input_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.input_edit.setPlaceholderText("请输入二步验证密码")
        else:
            self.input_edit.setPlaceholderText("请输入 Telegram 验证码")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(self.label)
        layout.addWidget(self.input_edit)
        layout.addWidget(self.button_box)

        self.input_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def get_value(self) -> str:
        return self.input_edit.text().strip()
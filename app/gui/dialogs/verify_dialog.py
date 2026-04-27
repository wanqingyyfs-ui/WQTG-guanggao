from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class VerifyInputDialog(QDialog):
    def __init__(self, title: str, label_text: str, password_mode: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 140)

        self.label = QLabel(label_text)
        self.input_edit = QLineEdit()

        if password_mode:
            self.input_edit.setEchoMode(QLineEdit.Password)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.input_edit)
        layout.addWidget(self.button_box)

    def get_value(self) -> str:
        return self.input_edit.text().strip()
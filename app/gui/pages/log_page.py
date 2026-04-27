from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogPage(QWidget):
    def __init__(self, logs_dir: str, parent=None):
        super().__init__(parent)
        self.logs_dir = logs_dir

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        self.clear_button = QPushButton("清空界面日志")
        self.open_dir_button = QPushButton("打开日志目录")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.open_dir_button)
        button_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addLayout(button_layout)
        layout.addWidget(self.log_text)

        self.clear_button.clicked.connect(self.log_text.clear)
        self.open_dir_button.clicked.connect(self.open_logs_dir)

    def append_log(self, level: str, message: str) -> None:
        self.log_text.append(f"[{level}] {message}")

    def open_logs_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.logs_dir))
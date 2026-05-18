from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPage(QWidget):
    def __init__(self, logs_dir: str, parent=None):
        super().__init__(parent)

        self.logs_dir = str(Path(logs_dir).expanduser())

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(3000)
        self.log_text.setPlaceholderText("运行日志会显示在这里。")

        self.clear_button = QPushButton("清空界面日志")
        self.open_dir_button = QPushButton("打开日志目录")
        self.open_app_log_button = QPushButton("打开 app.log")
        self.open_task_log_button = QPushButton("打开 task_send.jsonl")

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.open_dir_button)
        button_layout.addWidget(self.open_app_log_button)
        button_layout.addWidget(self.open_task_log_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(button_layout)
        layout.addWidget(self.log_text)

        self.clear_button.clicked.connect(self.clear_logs)
        self.open_dir_button.clicked.connect(self.open_logs_dir)
        self.open_app_log_button.clicked.connect(self.open_app_log)
        self.open_task_log_button.clicked.connect(self.open_task_log)

    def append_log(self, level: str, message: str) -> None:
        now_text = datetime.now().strftime("%H:%M:%S")
        safe_level = str(level or "INFO").upper()
        safe_message = str(message or "")

        self.log_text.appendPlainText(
            f"{now_text} [{safe_level}] {safe_message}"
        )

        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_logs(self) -> None:
        self.log_text.clear()

    def open_logs_dir(self) -> None:
        logs_dir = self._logs_path()
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(logs_dir)

    def open_app_log(self) -> None:
        self._open_log_file("app.log")

    def open_task_log(self) -> None:
        self._open_log_file("task_send.jsonl")

    def _open_log_file(self, filename: str) -> None:
        logs_dir = self._logs_path()
        logs_dir.mkdir(parents=True, exist_ok=True)

        file_path = logs_dir / filename

        if not file_path.exists():
            QMessageBox.information(
                self,
                "提示",
                f"日志文件暂不存在：{file_path}",
            )
            return

        self._open_path(file_path)

    def _logs_path(self) -> Path:
        return Path(str(self.logs_dir or "")).expanduser()

    def _open_path(self, path: Path) -> None:
        safe_path = Path(path).expanduser()
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(safe_path)))

        if not ok:
            QMessageBox.warning(
                self,
                "打开失败",
                f"无法打开路径：{safe_path}",
            )

    def set_logs_dir(self, logs_dir: Any) -> None:
        self.logs_dir = str(Path(str(logs_dir or "")).expanduser())
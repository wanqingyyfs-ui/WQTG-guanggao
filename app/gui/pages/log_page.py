from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.gui.pages.layout_utils import style_table, style_text_editor
from app.gui.widgets.no_wheel import NoWheelSpinBox


class LogPage(QWidget):
    def __init__(self, logs_dir: str, parent=None):
        super().__init__(parent)

        self.logs_dir = str(Path(logs_dir).expanduser())

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(3000)
        self.log_text.setPlaceholderText("运行日志会显示在这里。")
        style_text_editor(self.log_text, min_height=360)

        self.clear_button = QPushButton("清空界面日志")
        self.open_dir_button = QPushButton("打开日志目录")
        self.open_app_log_button = QPushButton("打开 app.log")
        self.open_task_log_button = QPushButton("打开 task_send.jsonl")

        self.task_record_limit_spin = NoWheelSpinBox()
        self.task_record_limit_spin.setRange(50, 5000)
        self.task_record_limit_spin.setSingleStep(50)
        self.task_record_limit_spin.setValue(300)
        self.task_record_limit_spin.setSuffix(" 条")

        self.refresh_task_records_button = QPushButton("刷新任务记录")
        self.clear_task_records_button = QPushButton("清空任务记录文件")

        self.task_table = QTableWidget(0, 10)
        self.task_table.setHorizontalHeaderLabels(
            [
                "时间",
                "状态",
                "判定",
                "消息模式",
                "任务",
                "账号",
                "群组",
                "模板",
                "噪音预览",
                "错误",
            ]
        )
        self.task_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        style_table(self.task_table)

        self.task_record_status_label = QLabel("尚未加载任务发送记录")
        self.task_record_status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_runtime_log_tab(), "运行日志")
        self.tabs.addTab(self._build_task_record_tab(), "任务发送记录")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title_label = QLabel("日志查看")
        title_label.setObjectName("PageTitleLabel")

        layout.addWidget(title_label)
        layout.addWidget(self.tabs, 1)

        self.clear_button.clicked.connect(self.clear_logs)
        self.open_dir_button.clicked.connect(self.open_logs_dir)
        self.open_app_log_button.clicked.connect(self.open_app_log)
        self.open_task_log_button.clicked.connect(self.open_task_log)
        self.refresh_task_records_button.clicked.connect(self.refresh_task_records)
        self.clear_task_records_button.clicked.connect(self.clear_task_records_file)

        self.refresh_task_records()

    def _build_runtime_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.open_dir_button)
        button_layout.addWidget(self.open_app_log_button)
        button_layout.addWidget(self.open_task_log_button)
        button_layout.addStretch(1)

        layout.addLayout(button_layout)
        layout.addWidget(self.log_text, 1)

        return widget

    def _build_task_record_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.addWidget(QLabel("读取最近："))
        button_layout.addWidget(self.task_record_limit_spin)
        button_layout.addWidget(self.refresh_task_records_button)
        button_layout.addWidget(self.clear_task_records_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.task_record_status_label)

        layout.addLayout(button_layout)
        layout.addWidget(self.task_table, 1)

        return widget

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

    def refresh_task_records(self) -> None:
        records = self._read_task_records(self.task_record_limit_spin.value())
        self.task_table.setRowCount(0)

        for record in records:
            row = self.task_table.rowCount()
            self.task_table.insertRow(row)

            values = [
                self._record_time(record),
                self._status_label(record.get("status", "")),
                self._decision_label(record.get("decision", "")),
                self._message_mode_label(record.get("message_mode", "")),
                str(record.get("task_name", "") or record.get("task_id", "") or ""),
                str(record.get("account_name", "") or record.get("selected_account_name", "") or ""),
                self._record_group_text(record),
                self._record_template_text(record),
                str(record.get("noise_text_preview", "") or ""),
                str(record.get("error", "") or ""),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.task_table.setItem(row, column, item)

        self.task_record_status_label.setText(f"已加载 {len(records)} 条任务记录")

    def clear_task_records_file(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空 task_send.jsonl 任务发送记录文件吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            task_log_path = self._task_log_path()
            task_log_path.parent.mkdir(parents=True, exist_ok=True)
            task_log_path.write_text("", encoding="utf-8")
            self.refresh_task_records()
            QMessageBox.information(self, "已清空", "任务发送记录文件已清空")
        except Exception as exc:
            QMessageBox.warning(self, "清空失败", str(exc))

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

    def _read_task_records(self, limit: int) -> list[dict[str, Any]]:
        task_log_path = self._task_log_path()

        if not task_log_path.exists():
            return []

        try:
            lines = self._read_tail_lines(task_log_path, limit)
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", f"读取任务发送记录失败：{exc}")
            return []

        records: list[dict[str, Any]] = []

        for line in lines:
            text = line.strip()

            if not text:
                continue

            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                records.append(
                    {
                        "status": "invalid",
                        "error": "日志行不是有效 JSON",
                        "raw_line": text[:500],
                    }
                )
                continue

            if isinstance(record, Mapping):
                records.append(dict(record))
            else:
                records.append(
                    {
                        "status": "invalid",
                        "error": f"日志记录不是对象: {type(record).__name__}",
                        "raw_record": str(record)[:500],
                    }
                )

        return records

    @staticmethod
    def _read_tail_lines(path: Path, limit: int) -> list[str]:
        safe_limit = max(1, int(limit or 300))

        try:
            with path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        return lines[-safe_limit:]

    @staticmethod
    def _record_time(record: Mapping[str, Any]) -> str:
        for key in ("logged_at", "finished_at", "started_at", "created_at"):
            value = str(record.get(key, "") or "").strip()
            if value:
                return value

        return ""

    @staticmethod
    def _record_group_text(record: Mapping[str, Any]) -> str:
        group_name = str(record.get("selected_group_name", "") or "").strip()
        group_id = str(record.get("selected_group_id", "") or record.get("group_id", "") or "").strip()
        chat_id = str(record.get("chat_id", "") or "").strip()

        if group_name and chat_id:
            return f"{group_name} ({chat_id})"

        if group_name:
            return group_name

        if chat_id:
            return chat_id

        return group_id

    @staticmethod
    def _record_template_text(record: Mapping[str, Any]) -> str:
        selected_template_id = str(record.get("selected_template_id", "") or "").strip()
        template_id = str(record.get("template_id", "") or "").strip()

        if selected_template_id:
            return selected_template_id

        return template_id

    @staticmethod
    def _status_label(status: Any) -> str:
        normalized = str(status or "").strip().lower()

        label_map = {
            "success": "成功",
            "failed": "失败",
            "skipped": "跳过",
            "invalid": "无效",
            "unknown": "未知",
        }

        return label_map.get(normalized, str(status or ""))

    @staticmethod
    def _decision_label(decision: Any) -> str:
        normalized = str(decision or "").strip().lower()

        label_map = {
            "ad": "广告",
            "noise": "噪音",
            "skip": "跳过",
        }

        return label_map.get(normalized, str(decision or ""))

    @staticmethod
    def _message_mode_label(mode: Any) -> str:
        normalized = str(mode or "").strip().lower()

        label_map = {
            "template": "模板",
            "text": "文本",
            "noise": "噪音",
            "skip": "跳过",
        }

        return label_map.get(normalized, str(mode or ""))

    def _logs_path(self) -> Path:
        return Path(str(self.logs_dir or "")).expanduser()

    def _task_log_path(self) -> Path:
        return self._logs_path() / "task_send.jsonl"

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
        self.refresh_task_records()
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.gui.pages.layout_utils import style_table


class TaskProgressPage(QWidget):
    STATUS_LABELS = {
        "success": "成功",
        "flood_wait": "FloodWait",
        "blocked": "被屏蔽/限制",
        "not_participant": "未加入群组",
        "unavailable": "群组不可访问",
        "invalid_target": "目标无效",
        "telegram_busy": "Telegram繁忙",
        "skipped": "跳过",
        "failed": "失败",
        "invalid": "日志异常",
        "unknown": "未知",
    }
    DECISION_LABELS = {"ad": "广告模板", "noise": "噪音", "skip": "跳过"}

    def __init__(self, task_log_service, parent=None):
        super().__init__(parent)
        self.task_log_service = task_log_service
        self._records: list[dict] = []
        self._last_signature = None

        self.summary_label = QLabel("尚无任务记录")
        self.summary_label.setWordWrap(True)
        self.cooldown_label = QLabel("")
        self.cooldown_label.setWordWrap(True)

        self.status_filter = QComboBox()
        self.status_filter.addItem("全部结果", "")
        for status in (
            "success", "flood_wait", "blocked", "not_participant",
            "unavailable", "invalid_target", "telegram_busy", "skipped", "failed",
        ):
            self.status_filter.addItem(self.STATUS_LABELS[status], status)

        self.limit_combo = QComboBox()
        for limit in (300, 1000, 3000, 5000):
            self.limit_combo.addItem(f"最近 {limit} 条", limit)
        self.limit_combo.setCurrentIndex(1)

        self.refresh_button = QPushButton("立即刷新")
        self.clear_button = QPushButton("清空记录")

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels([
            "记录时间", "任务", "账号", "群组", "Chat ID", "概率判定",
            "消息模式", "模板", "结果", "FloodWait", "冷却截止", "具体原因", "完成时间",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        style_table(self.table)

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择一条记录后显示完整字段")
        self.detail_text.setMaximumHeight(190)

        self._build_ui()
        self.status_filter.currentIndexChanged.connect(lambda: self.refresh_records(force=True))
        self.limit_combo.currentIndexChanged.connect(lambda: self.refresh_records(force=True))
        self.refresh_button.clicked.connect(lambda: self.refresh_records(force=True))
        self.clear_button.clicked.connect(self._clear_records)
        self.table.itemSelectionChanged.connect(self._show_selected_detail)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_records)
        self.timer.start()
        self.refresh_records(force=True)

    def _build_ui(self) -> None:
        title = QLabel("任务进度与逐条结果")
        title.setObjectName("PageTitleLabel")

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)
        tools.addWidget(QLabel("结果筛选："))
        tools.addWidget(self.status_filter)
        tools.addWidget(self.limit_combo)
        tools.addWidget(self.refresh_button)
        tools.addStretch(1)
        tools.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.cooldown_label)
        layout.addLayout(tools)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("所选记录完整详情："))
        layout.addWidget(self.detail_text)

    def refresh_records(self, force: bool = False) -> None:
        log_file = Path(self.task_log_service.get_log_file())
        try:
            stat = log_file.stat() if log_file.exists() else None
            signature = (
                stat.st_mtime_ns if stat else 0,
                stat.st_size if stat else 0,
                self.status_filter.currentData(),
                self.limit_combo.currentData(),
            )
        except OSError:
            signature = None
        if not force and signature == self._last_signature:
            self._refresh_cooldown_label()
            return
        self._last_signature = signature

        selected_attempt = self._selected_attempt_id()
        limit = int(self.limit_combo.currentData() or 1000)
        records = list(self.task_log_service.read_recent_records(limit))
        records.reverse()
        status_filter = str(self.status_filter.currentData() or "")
        if status_filter:
            records = [r for r in records if str(r.get("status") or "") == status_filter]
        self._records = records
        self._populate_table()
        self._update_summary()
        self._refresh_cooldown_label()
        self._restore_selection(selected_attempt)

    def _populate_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            probability = self._probability_label(record)
            values = [
                record.get("logged_at", ""),
                record.get("task_name", ""),
                record.get("account_name", ""),
                record.get("selected_group_name") or record.get("group_id", ""),
                record.get("chat_id", ""),
                probability,
                self._message_mode_label(record),
                record.get("template_name") or record.get("selected_template_id", ""),
                self.STATUS_LABELS.get(str(record.get("status") or ""), str(record.get("status") or "未知")),
                self._flood_wait_label(record),
                record.get("cooldown_until", ""),
                record.get("reason_detail") or record.get("error") or record.get("skip_reason", ""),
                record.get("finished_at", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.ItemDataRole.UserRole, str(record.get("attempt_id") or ""))
                if column in {4, 8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(False)

    def _update_summary(self) -> None:
        counts: dict[str, int] = {}
        for record in self._records:
            status = str(record.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        parts = [f"当前显示 {len(self._records)} 条"]
        for status in (
            "success", "flood_wait", "blocked", "not_participant",
            "unavailable", "invalid_target", "telegram_busy", "skipped", "failed",
        ):
            if counts.get(status):
                parts.append(f"{self.STATUS_LABELS[status]} {counts[status]}")
        self.summary_label.setText("｜".join(parts))

    def _refresh_cooldown_label(self) -> None:
        loader = getattr(self.task_log_service, "load_active_flood_waits", None)
        active = dict(loader()) if callable(loader) else {}
        if not active:
            self.cooldown_label.setText("当前没有仍在生效的账号 FloodWait 冷却")
            return
        text = "；".join(
            f"{account} 冷却至 {until.isoformat(timespec='seconds')}"
            for account, until in sorted(active.items())
        )
        self.cooldown_label.setText("当前 FloodWait：" + text)

    def _show_selected_detail(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._records)):
            self.detail_text.clear()
            return
        self.detail_text.setPlainText(
            json.dumps(self._records[row], ensure_ascii=False, indent=2, default=str)
        )

    def _clear_records(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空任务记录",
            "确定清空任务发送记录吗？此操作不会停止正在运行的任务。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.task_log_service.clear()
        self._last_signature = None
        self.refresh_records(force=True)

    def _selected_attempt_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def _restore_selection(self, attempt_id: str) -> None:
        if not attempt_id:
            return
        for row, record in enumerate(self._records):
            if str(record.get("attempt_id") or "") == attempt_id:
                self.table.selectRow(row)
                return

    @classmethod
    def _probability_label(cls, record: dict) -> str:
        decision = cls.DECISION_LABELS.get(
            str(record.get("decision") or ""),
            str(record.get("decision") or "未判定"),
        )
        roll = record.get("probability_roll", -1)
        total = record.get("probability_total", 100)
        try:
            if float(roll) >= 0:
                return f"{decision}（抽样 {float(roll):.3f}/{int(total)}）"
        except (TypeError, ValueError):
            pass
        return decision

    @staticmethod
    def _message_mode_label(record: dict) -> str:
        mode = str(record.get("message_mode") or "")
        return {
            "template": "模板转发",
            "noise": "噪音文本",
            "text": "纯文本",
            "skip": "跳过",
        }.get(mode, mode or "未知")

    @staticmethod
    def _flood_wait_label(record: dict) -> str:
        seconds = int(record.get("flood_wait_seconds") or 0)
        return f"{seconds} 秒" if seconds > 0 else ""

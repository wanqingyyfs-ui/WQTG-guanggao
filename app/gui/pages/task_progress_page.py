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
        "entity_unresolved": "群实体未解析",
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
            "unavailable", "invalid_target", "entity_unresolved", "telegram_busy",
            "skipped", "failed",
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
        controls = QHBoxLayout()
        controls.addWidget(QLabel("结果筛选"))
        controls.addWidget(self.status_filter)
        controls.addWidget(self.limit_combo)
        controls.addStretch(1)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.cooldown_label)
        layout.addLayout(controls)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("完整记录"))
        layout.addWidget(self.detail_text)

    @staticmethod
    def _safe_int(value, default=0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _short_text(value, limit: int = 140) -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def refresh_records(self, force: bool = False) -> None:
        limit = int(self.limit_combo.currentData() or 1000)
        records = list(self.task_log_service.read_recent_records(limit))
        signature = (
            len(records),
            str(records[-1].get("logged_at") or records[-1].get("finished_at") or "") if records else "",
            str(self.status_filter.currentData() or ""),
            limit,
        )
        if not force and signature == self._last_signature:
            self._refresh_cooldown_label()
            return
        self._last_signature = signature

        status_filter = str(self.status_filter.currentData() or "")
        filtered = [
            record for record in reversed(records)
            if not status_filter or str(record.get("status") or "unknown") == status_filter
        ]
        self._records = filtered
        self.table.setRowCount(len(filtered))

        counts: dict[str, int] = {}
        for record in records:
            status = str(record.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        count_text = "，".join(
            f"{self.STATUS_LABELS.get(key, key)} {value}"
            for key, value in sorted(counts.items())
        ) or "尚无任务记录"
        self.summary_label.setText(f"最近 {len(records)} 条：{count_text}")

        for row, record in enumerate(filtered):
            decision = str(record.get("decision") or "")
            roll = record.get("probability_roll", "")
            probability_text = self.DECISION_LABELS.get(decision, decision or "-")
            if roll not in (None, "", -1, -1.0):
                probability_text += f" / {roll}"
            values = [
                record.get("logged_at") or "",
                record.get("task_name") or record.get("task_id") or "",
                record.get("account_name") or "",
                record.get("selected_group_name") or record.get("group_id") or "",
                record.get("chat_id") or "",
                probability_text,
                record.get("message_mode") or "",
                record.get("template_name") or record.get("selected_template_id") or "",
                self.STATUS_LABELS.get(str(record.get("status") or "unknown"), str(record.get("status") or "unknown")),
                record.get("flood_wait_seconds") or "",
                record.get("cooldown_until") or "",
                record.get("reason_detail") or record.get("error") or record.get("skip_reason") or "",
                record.get("finished_at") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(self._short_text(value, 240 if column == 11 else 100))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, item)

        self._refresh_cooldown_label()
        self._show_selected_detail()

    def _refresh_cooldown_label(self) -> None:
        try:
            active = self.task_log_service.load_active_flood_waits()
        except Exception:
            active = {}
        if not active:
            self.cooldown_label.setText("当前没有账号处于 FloodWait 冷却。")
            return
        items = [f"{name} → {deadline.isoformat(timespec='seconds')}" for name, deadline in sorted(active.items())]
        self.cooldown_label.setText("账号冷却：" + "；".join(items))

    def _show_selected_detail(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.detail_text.clear()
            return
        row_index = selected[0].data(Qt.ItemDataRole.UserRole)
        try:
            record = self._records[int(row_index)]
        except (TypeError, ValueError, IndexError):
            self.detail_text.clear()
            return
        self.detail_text.setPlainText(json.dumps(record, ensure_ascii=False, indent=2))

    def _clear_records(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空任务记录",
            "确定清空任务进度页面中的全部发送记录吗？\n此操作不会删除账号、任务或模板。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.task_log_service.clear_records()
        except Exception as exc:
            QMessageBox.critical(self, "清空失败", str(exc))
            return
        self._last_signature = None
        self.refresh_records(force=True)

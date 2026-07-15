from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QMessageBox, QTableWidget, QTableWidgetItem, QWidget,
)

def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def info(parent: QWidget, text: str) -> None:
    QMessageBox.information(parent, "WQTG", text)


def error(parent: QWidget, text: str) -> None:
    QMessageBox.critical(parent, "WQTG", text)


def selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    return int(item.text()) if item else None


class DataTable(QTableWidget):
    def __init__(self, headers: list[str], parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)

    def set_rows(self, rows: list[list[Any]]) -> None:
        self.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for col_index, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                self.setItem(row_index, col_index, item)



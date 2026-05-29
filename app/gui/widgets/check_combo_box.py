from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QListView

from app.gui.widgets.no_wheel import NoWheelComboBox


class CheckComboBox(NoWheelComboBox):
    """可勾选多选下拉框，保留用户勾选顺序。"""

    checked_items_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._popup_should_stay_open = False
        self._checked_order: list[str] = []
        self.setModel(self._model)
        self.setView(QListView(self))
        self.setEditable(True)
        self.setMaxVisibleItems(16)
        self.setMinimumWidth(180)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("请选择")
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)
        self.view().pressed.connect(self._on_item_pressed)

    def clear_items(self) -> None:
        self._model.clear()
        self._checked_order.clear()
        self._update_display_text()

    def add_check_item(
        self,
        text: str,
        data: Any = None,
        checked: bool = False,
        enabled: bool = True,
    ) -> None:
        item = QStandardItem(str(text or ""))
        item.setData(data, Qt.ItemDataRole.UserRole)
        flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
        if enabled:
            flags |= Qt.ItemFlag.ItemIsEnabled
        item.setFlags(flags)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._model.appendRow(item)
        key = self._key(data)
        if checked and key and key not in self._checked_order:
            self._checked_order.append(key)
        self._cleanup_checked_order()
        self._update_display_text()

    def checked_data(self) -> list[Any]:
        self._cleanup_checked_order()
        key_to_data: dict[str, Any] = {}
        checked_keys: list[str] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            key = self._key(data)
            if key:
                key_to_data[key] = data
                if key not in checked_keys:
                    checked_keys.append(key)
        ordered_keys = [key for key in self._checked_order if key in key_to_data]
        for key in checked_keys:
            if key not in ordered_keys:
                ordered_keys.append(key)
        self._checked_order = ordered_keys
        return [key_to_data[key] for key in ordered_keys]

    def checked_texts(self) -> list[str]:
        self._cleanup_checked_order()
        key_to_text: dict[str, str] = {}
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            key = self._key(item.data(Qt.ItemDataRole.UserRole))
            if key:
                key_to_text[key] = item.text()
        return [key_to_text[key] for key in self._checked_order if key in key_to_text]

    def set_checked_data(self, values: list[Any]) -> None:
        wanted_order: list[str] = []
        for value in values or []:
            key = self._key(value)
            if key and key not in wanted_order:
                wanted_order.append(key)
        available_keys: set[str] = set()
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue
            key = self._key(item.data(Qt.ItemDataRole.UserRole))
            if key:
                available_keys.add(key)
            item.setCheckState(Qt.CheckState.Checked if key in wanted_order else Qt.CheckState.Unchecked)
        self._checked_order = [key for key in wanted_order if key in available_keys]
        self._cleanup_checked_order()
        self._update_display_text()
        self.checked_items_changed.emit()

    def selected_count(self) -> int:
        return len(self.checked_data())

    def showPopup(self) -> None:  # noqa: N802
        popup_width = max(self.width(), 360)
        self.view().setMinimumWidth(popup_width)
        self.view().setMinimumHeight(min(360, max(160, self._model.rowCount() * 32)))
        super().showPopup()

    def hidePopup(self) -> None:  # noqa: N802
        if self._popup_should_stay_open:
            self._popup_should_stay_open = False
            return
        super().hidePopup()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            self.showPopup()
            return True
        if watched is self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            return True
        return super().eventFilter(watched, event)

    def _on_item_pressed(self, index) -> None:
        item = self._model.itemFromIndex(index)
        if item is None or not item.isEnabled():
            return
        self._popup_should_stay_open = True
        key = self._key(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
            self._checked_order = [value for value in self._checked_order if value != key]
        else:
            item.setCheckState(Qt.CheckState.Checked)
            if key and key not in self._checked_order:
                self._checked_order.append(key)
        self._cleanup_checked_order()
        self._update_display_text()
        self.checked_items_changed.emit()

    @staticmethod
    def _key(value: Any) -> str:
        return str(value or "").strip()

    def _cleanup_checked_order(self) -> None:
        checked_keys: set[str] = set()
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                key = self._key(item.data(Qt.ItemDataRole.UserRole))
                if key:
                    checked_keys.add(key)
        self._checked_order = [key for key in self._checked_order if key in checked_keys]
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            key = self._key(item.data(Qt.ItemDataRole.UserRole))
            if key and key not in self._checked_order:
                self._checked_order.append(key)

    def _update_display_text(self) -> None:
        texts = self.checked_texts()
        if not texts:
            self.lineEdit().setText("未选择")
            return
        if len(texts) <= 2:
            self.lineEdit().setText("、".join(texts))
            return
        self.lineEdit().setText(f"已选择 {len(texts)} 项")

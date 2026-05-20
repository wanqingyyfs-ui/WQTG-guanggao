from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QListView

from app.gui.widgets.no_wheel import NoWheelComboBox


class CheckComboBox(NoWheelComboBox):
    """
    基于 Qt Model/View 的可勾选多选下拉框。

    修复点：
    - 点击输入框区域也会弹出下拉，不只依赖右侧箭头。
    - 点击选项时只切换勾选状态，不立即关闭下拉。
    - 下拉视图给足宽度和高度，避免用户看不到可选项。
    """

    checked_items_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._model = QStandardItemModel(self)
        self._popup_should_stay_open = False

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
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
        )
        if not enabled:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self._model.appendRow(item)
        self._update_display_text()

    def checked_data(self) -> list[Any]:
        values: list[Any] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                values.append(item.data(Qt.ItemDataRole.UserRole))
        return values

    def checked_texts(self) -> list[str]:
        texts: list[str] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                texts.append(item.text())
        return texts

    def set_checked_data(self, values: list[Any]) -> None:
        wanted = {str(value or "").strip() for value in values if str(value or "").strip()}

        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue

            item_value = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            item.setCheckState(
                Qt.CheckState.Checked
                if item_value in wanted
                else Qt.CheckState.Unchecked
            )

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
        if item is None:
            return

        if not item.isEnabled():
            return

        self._popup_should_stay_open = True
        item.setCheckState(
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        self._update_display_text()
        self.checked_items_changed.emit()

    def _update_display_text(self) -> None:
        texts = self.checked_texts()
        if not texts:
            self.lineEdit().setText("未选择")
            return

        if len(texts) <= 2:
            self.lineEdit().setText("、".join(texts))
            return

        self.lineEdit().setText(f"已选择 {len(texts)} 项")

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QSpinBox,
    QTimeEdit,
)


class NoWheelMixin:
    """
    禁止鼠标滚轮直接修改控件值。

    说明：
    - 鼠标滚轮经常会误改概率、延迟、字号等关键数值。
    - 这里不吞掉页面滚动，把滚轮事件 ignore，让父级滚动区域继续处理。
    - 键盘上下键、手动输入、点击下拉框仍然正常。
    """

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class NoWheelSpinBox(NoWheelMixin, QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoWheelDoubleSpinBox(NoWheelMixin, QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoWheelComboBox(NoWheelMixin, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoWheelTimeEdit(NoWheelMixin, QTimeEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoWheelDateEdit(NoWheelMixin, QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoWheelDateTimeEdit(NoWheelMixin, QDateTimeEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
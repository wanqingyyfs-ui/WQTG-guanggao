from __future__ import annotations

import base64

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel


class BrowserCanvas(QLabel):
    browser_click = Signal(float, float)
    browser_key = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(640, 360)
        self.setText("选择并启动账号后，这里显示当前浏览器页面")
        self._source_width = 1
        self._source_height = 1
        self._pixmap_size = None

    def set_frame(self, image_base64: str, width: int, height: int) -> None:
        data = base64.b64decode(image_base64)
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "PNG"):
            return
        self._source_width = max(1, int(width))
        self._source_height = max(1, int(height))
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap_size = scaled.size()
        self.setPixmap(scaled)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.pixmap() is None or self._pixmap_size is None:
            return super().mousePressEvent(event)
        display_w = self._pixmap_size.width()
        display_h = self._pixmap_size.height()
        offset_x = (self.width() - display_w) / 2
        offset_y = (self.height() - display_h) / 2
        x = event.position().x() - offset_x
        y = event.position().y() - offset_y
        if 0 <= x <= display_w and 0 <= y <= display_h:
            self.browser_click.emit(
                x * self._source_width / display_w,
                y * self._source_height / display_h,
            )
            self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        special = {
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Backspace: "Backspace",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Escape: "Escape",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_Left: "ArrowLeft",
            Qt.Key.Key_Right: "ArrowRight",
            Qt.Key.Key_Up: "ArrowUp",
            Qt.Key.Key_Down: "ArrowDown",
        }
        if event.key() in special:
            self.browser_key.emit(special[event.key()])
        elif event.text():
            self.browser_key.emit("text:" + event.text())
        else:
            super().keyPressEvent(event)

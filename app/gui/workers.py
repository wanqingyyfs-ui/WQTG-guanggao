from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal


class FunctionThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.func = func

    def run(self) -> None:
        try:
            self.succeeded.emit(self.func())
        except Exception as exc:
            self.failed.emit(str(exc))

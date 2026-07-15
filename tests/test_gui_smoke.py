from __future__ import annotations

import os

import pytest


def test_main_window_constructs_and_closes(tmp_path, monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    monkeypatch.setenv("WQTG_HOME", str(tmp_path / "runtime"))
    from PySide6.QtWidgets import QApplication

    from app.core.context import AppContext
    from app.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    context = AppContext.create()
    window = MainWindow(context)
    assert window.stack.count() == 11
    window.show()
    app.processEvents()
    window.close()
    context.close()

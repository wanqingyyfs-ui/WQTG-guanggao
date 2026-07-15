from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication

    from app.core.context import AppContext
    from app.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("WQTG 浏览器原生工作台")
    context = AppContext.create()
    window = MainWindow(context)
    window.show()
    rc = app.exec()
    context.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    app.setApplicationName("Telegram 用户号群发任务面板")
    app.setOrganizationName("wanqingyyfs")

    icon_path = Path(__file__).resolve().parent / "app.ico"

    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
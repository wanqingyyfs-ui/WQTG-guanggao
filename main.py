from __future__ import annotations

import ctypes
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.gui.main_window import MainWindow


APP_NAME = "Telegram 用户号群发任务面板"
ORGANIZATION_NAME = "wanqingyyfs"
WINDOW_ICON_NAME = "app.ico"


def resource_path(relative_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path

    return Path(__file__).resolve().parent / relative_path


def setup_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    try:
        app_id = f"{ORGANIZATION_NAME}.{APP_NAME}".replace(" ", "_")
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def install_exception_hook() -> None:
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            original_hook(exc_type, exc_value, exc_traceback)
            return

        error_text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )

        print(error_text, file=sys.stderr)

        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "程序异常",
                f"程序发生未处理异常：\n\n{exc_value}",
            )

    sys.excepthook = handle_exception


def create_application() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setQuitOnLastWindowClosed(True)

    icon_path = resource_path(WINDOW_ICON_NAME)
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    return app


def main() -> int:
    setup_windows_app_id()
    install_exception_hook()

    app = create_application()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
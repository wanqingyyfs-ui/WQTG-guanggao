from __future__ import annotations

import ctypes
import faulthandler
import multiprocessing
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.gui.main_window import MainWindow

APP_NAME = "Telegram 用户号群发任务面板"
ORGANIZATION_NAME = "wanqingyyfs"
RUNTIME_DATA_APP_NAME = "万青TG群发任务"
WINDOW_ICON_NAME = "app.ico"
LOGS_DIR_NAME = "logs"
STARTUP_ERROR_LOG_NAME = "startup_error.log"


def project_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    return project_root() / relative_path


def local_appdata_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser()
    return Path.home() / "AppData" / "Local"


def runtime_logs_dir() -> Path:
    if getattr(sys, "frozen", False):
        return local_appdata_dir() / RUNTIME_DATA_APP_NAME / LOGS_DIR_NAME
    return project_root() / LOGS_DIR_NAME


def startup_error_log_path() -> Path:
    return runtime_logs_dir() / STARTUP_ERROR_LOG_NAME


def setup_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        app_id = "wanqingyyfs.WQTGGuanggao.TelegramUserGroupSender"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def enable_fault_handler() -> None:
    try:
        logs_dir = runtime_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        fault_log_file = (logs_dir / "fatal_error.log").open("a", encoding="utf-8")
        faulthandler.enable(file=fault_log_file, all_threads=True)
    except Exception:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass


def write_startup_error(error_text: str) -> None:
    try:
        logs_dir = runtime_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        now_text = datetime.now().isoformat(timespec="seconds")
        with startup_error_log_path().open("a", encoding="utf-8") as file:
            file.write(f"\n===== {now_text} =====\n")
            file.write(error_text)
            if not error_text.endswith("\n"):
                file.write("\n")
    except Exception:
        pass


def install_exception_hook() -> None:
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            original_hook(exc_type, exc_value, exc_traceback)
            return
        error_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(error_text, file=sys.stderr)
        write_startup_error(error_text)
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "程序异常",
                f"程序发生未处理异常：\n\n{exc_value}\n\n详细日志已写入：{startup_error_log_path()}",
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
    enable_fault_handler()
    install_exception_hook()
    try:
        app = create_application()
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:
        error_text = traceback.format_exc()
        print(error_text, file=sys.stderr)
        write_startup_error(error_text)
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "启动失败",
                f"程序启动失败：\n\n{error_text}\n\n详细日志已写入：{startup_error_log_path()}",
            )
        return 1


if __name__ == "__main__":
    # Python and PyInstaller both require this before starting spawned workers.
    multiprocessing.freeze_support()
    raise SystemExit(main())

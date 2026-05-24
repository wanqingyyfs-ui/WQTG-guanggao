from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


def install_tgapipldc_panel() -> None:
    """给 MainWindow 动态安装 tgapipldc 工作台，避免大范围改 main_window.py。"""
    from app.gui.main_window import MainWindow
    from app.gui.pages.tgapipldc_page import TgapipldcPage

    if getattr(MainWindow, "_tgapipldc_panel_installed", False):
        return

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _setup_tgapipldc_page(self, TgapipldcPage)

    MainWindow.__init__ = patched_init
    MainWindow._tgapipldc_panel_installed = True


def _setup_tgapipldc_page(window, page_class) -> None:
    if hasattr(window, "tgapipldc_page"):
        return

    page = page_class()
    window.tgapipldc_page = page
    window.tabs.addTab(page, "API 批量工作台")

    runtime = window.runtime_service

    runtime.tgapipldc_log_received.connect(page.append_log)
    runtime.tgapipldc_process_status_changed.connect(page.set_process_running)

    page.reload_csv_requested.connect(lambda: _reload_csv(window))
    page.overwrite_accounts_requested.connect(lambda text: _call(window, lambda: runtime.overwrite_tgapipldc_accounts_csv(text), "覆盖 accounts.csv 成功"))
    page.overwrite_proxies_requested.connect(lambda text: _call(window, lambda: runtime.overwrite_tgapipldc_proxies_csv(text), "覆盖 proxies.csv 成功"))

    page.test_proxies_requested.connect(lambda: _call(window, runtime.run_tgapipldc_test_proxies, "已开始检测代理"))
    page.build_proxy_pool_requested.connect(lambda: _call(window, runtime.run_tgapipldc_build_proxy_pool, "已开始构建可用代理池"))
    page.assign_proxies_requested.connect(lambda: _call(window, runtime.run_tgapipldc_assign_proxies, "已开始绑定账号和代理"))
    page.export_api_requested.connect(lambda: _call(window, runtime.run_tgapipldc_export_api, "已开始批量获取 API"))
    page.stop_process_requested.connect(lambda: _call(window, runtime.stop_tgapipldc_process, "已请求停止当前流程"))

    page.import_api_requested.connect(lambda: _call_and_refresh(window, runtime.run_tgapipldc_import_api_to_wqtg, "API 已导入 WQTG 账号"))
    page.login_wqtg_accounts_requested.connect(lambda: _call(window, runtime.run_tgapipldc_login_wqtg_accounts, "已开始 WQTG 批量登录"))

    _reload_csv(window)
    page.set_process_running(False)


def _reload_csv(window) -> None:
    page = window.tgapipldc_page
    runtime = window.runtime_service
    try:
        page.set_accounts_text(runtime.read_tgapipldc_accounts_csv_text())
        page.set_proxies_text(runtime.read_tgapipldc_proxies_csv_text())
        page.append_log("CSV 内容已刷新")
    except Exception as exc:
        _show_error(window, f"刷新 CSV 失败：{exc}")


def _call(window, func, success_message: str) -> None:
    try:
        func()
        if success_message:
            window.tgapipldc_page.append_log(success_message)
            window.statusBar().showMessage(success_message, 3000)
    except Exception as exc:
        _show_error(window, str(exc))


def _call_and_refresh(window, func, success_message: str) -> None:
    _call(window, func, success_message)
    try:
        if hasattr(window.runtime_service, "reload_config_cache"):
            window.runtime_service.reload_config_cache()
        if hasattr(window, "_sync_state_from_runtime"):
            window._sync_state_from_runtime()
        if hasattr(window, "refresh_all_views"):
            window.refresh_all_views()
    except Exception as exc:
        window.tgapipldc_page.append_log(f"刷新 WQTG 页面状态失败：{exc}")


def _show_error(window, message: str) -> None:
    safe_message = str(message or "")
    try:
        window.tgapipldc_page.append_log(f"错误：{safe_message}")
    except Exception:
        pass

    if hasattr(window, "_show_error"):
        window._show_error(safe_message)
    else:
        QMessageBox.critical(window, "错误", safe_message)

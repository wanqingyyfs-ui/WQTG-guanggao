from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from app.services.tgapipldc_locator_service import TgapipldcLocatorService


PROFILE_MAINTENANCE_ACTION_NAMES = {
    "status": "检测资料状态",
    "photo": "修改头像",
    "name": "修改昵称",
    "username": "修改用户名",
    "bio": "修改签名",
    "folder": "添加分组文件夹",
    "all": "修改全部选项",
}


def install_tgapipldc_panel() -> None:
    """Historical compatibility entry; MainWindow now installs pages explicitly."""
    return None


def setup_tgapipldc_pages(window) -> None:
    from app.gui.pages.tgapipldc_locator_page import TgapipldcLocatorPage
    from app.gui.pages.tgapipldc_page import TgapipldcPage
    from app.gui.pages.tgapipldc_profile_maintenance_page import TgapipldcProfileMaintenancePage

    _setup_tgapipldc_pages(
        window,
        TgapipldcPage,
        TgapipldcProfileMaintenancePage,
        TgapipldcLocatorPage,
    )


def _setup_tgapipldc_pages(window, api_page_class, profile_page_class, locator_page_class) -> None:
    if hasattr(window, "tgapipldc_page"):
        return

    api_page = api_page_class()
    profile_page = profile_page_class()
    locator_page = locator_page_class()

    window.tgapipldc_page = api_page
    window.tgapipldc_profile_maintenance_page = profile_page
    window.tgapipldc_locator_page = locator_page
    window._tgapipldc_active_channel = "api"

    window.tabs.addTab(api_page, "API 批量工作台")
    window.tabs.addTab(profile_page, "账号资料维护")
    window.tabs.addTab(locator_page, "自动化定位设置")

    runtime = window.runtime_service
    window.tgapipldc_locator_service = TgapipldcLocatorService(
        runtime.tgapipldc_workspace_service
    )

    runtime.tgapipldc_log_received.connect(
        lambda message: _dispatch_tgapipldc_log(window, message)
    )
    runtime.tgapipldc_process_status_changed.connect(
        lambda running: _dispatch_process_status(window, running)
    )

    api_page.reload_csv_requested.connect(lambda: _reload_csv(window))
    api_page.overwrite_accounts_requested.connect(
        lambda text: _api_call(
            window,
            lambda: runtime.overwrite_tgapipldc_accounts_csv(text),
            "覆盖 accounts.csv 成功",
        )
    )
    api_page.overwrite_proxies_requested.connect(
        lambda text: _api_call(
            window,
            lambda: runtime.overwrite_tgapipldc_proxies_csv(text),
            "保存动态代理成功",
        )
    )
    api_page.test_proxies_requested.connect(
        lambda: _api_call(window, runtime.run_tgapipldc_test_proxies, "已开始检测代理")
    )
    api_page.build_proxy_pool_requested.connect(
        lambda: _api_call(window, runtime.run_tgapipldc_build_proxy_pool, "已开始构建可用代理池")
    )
    api_page.assign_proxies_requested.connect(
        lambda: _api_call(window, runtime.run_tgapipldc_assign_proxies, "已开始生成运行表")
    )
    api_page.export_api_requested.connect(
        lambda: _api_call(window, runtime.run_tgapipldc_export_api, "已开始批量获取 API")
    )
    api_page.stop_process_requested.connect(
        lambda: _stop_call(window, "api")
    )
    api_page.import_api_requested.connect(
        lambda: _api_call_and_refresh(
            window,
            runtime.run_tgapipldc_import_api_to_wqtg,
            "API 已导入 WQTG 账号",
        )
    )
    api_page.login_wqtg_accounts_requested.connect(
        lambda: _api_call(
            window,
            runtime.run_tgapipldc_login_wqtg_accounts,
            "已开始 WQTG 批量登录",
        )
    )

    profile_page.upload_profile_photos_requested.connect(
        lambda paths: _upload_profile_photos(window, paths)
    )
    profile_page.open_profile_photo_library_requested.connect(
        lambda: _open_profile_photo_library(window)
    )
    profile_page.clear_profile_maintenance_results_requested.connect(
        lambda: _clear_profile_maintenance_results(window)
    )
    profile_page.profile_maintenance_requested.connect(
        lambda action, config: _run_profile_maintenance(window, action, config)
    )
    profile_page.stop_process_requested.connect(
        lambda: _stop_call(window, "profile")
    )

    locator_page.reload_requested.connect(lambda: _reload_locator_config(window))
    locator_page.save_target_requested.connect(
        lambda target_id, raw_json: _save_locator_target(window, target_id, raw_json)
    )
    locator_page.reset_target_requested.connect(
        lambda target_id: _reset_locator_target(window, target_id)
    )
    locator_page.calibrate_requested.connect(
        lambda target_id, profile_dir, url: _run_locator_calibration(
            window, target_id, profile_dir, url
        )
    )
    locator_page.open_config_directory_requested.connect(
        lambda: _open_locator_config_directory(window)
    )
    locator_page.stop_process_requested.connect(
        lambda: _stop_call(window, "locator")
    )

    _reload_csv(window)
    _reload_profile_maintenance_config(window)
    _reload_locator_config(window)
    _dispatch_process_status(window, False)


def _active_page(window):
    channel = str(getattr(window, "_tgapipldc_active_channel", "api") or "api")
    if channel == "profile":
        return window.tgapipldc_profile_maintenance_page
    if channel == "locator":
        return window.tgapipldc_locator_page
    return window.tgapipldc_page


def _set_channel(window, channel: str) -> None:
    window._tgapipldc_active_channel = str(channel or "api")


def _dispatch_tgapipldc_log(window, message: str) -> None:
    _active_page(window).append_log(message)


def _dispatch_process_status(window, running: bool) -> None:
    is_running = bool(running)
    for page in (
        window.tgapipldc_page,
        window.tgapipldc_profile_maintenance_page,
        window.tgapipldc_locator_page,
    ):
        page.set_process_running(is_running)
    if not is_running and getattr(window, "_tgapipldc_active_channel", "") == "locator":
        _reload_locator_config(window, silent=True)


def _profile_page(window):
    return getattr(window, "tgapipldc_profile_maintenance_page", window.tgapipldc_page)


def _reload_csv(window) -> None:
    page = window.tgapipldc_page
    runtime = window.runtime_service
    try:
        page.set_accounts_text(runtime.read_tgapipldc_accounts_csv_text())
        page.set_proxies_text(runtime.read_tgapipldc_proxies_csv_text())
        page.append_log("CSV 内容已刷新")
    except Exception as exc:
        _show_error(window, f"刷新 CSV 失败：{exc}")


def _reload_profile_maintenance_config(window) -> None:
    page = _profile_page(window)
    runtime = window.runtime_service
    try:
        config = runtime.tgapipldc_workspace_service.read_profile_maintenance_config()
        page.set_profile_maintenance_config(config)
        page.append_log("账号资料维护配置已加载")
    except Exception as exc:
        _show_error(window, f"加载账号资料维护配置失败：{exc}")


def _reload_locator_config(window, silent: bool = False) -> None:
    page = window.tgapipldc_locator_page
    service = window.tgapipldc_locator_service
    try:
        page.set_targets(service.load_targets())
        page.set_profiles(service.list_profiles())
        if not silent:
            page.append_log(f"定位配置已加载：{service.config_path}")
    except Exception as exc:
        _show_error(window, f"加载定位配置失败：{exc}")


def _save_locator_target(window, target_id: str, raw_json: str) -> None:
    service = window.tgapipldc_locator_service
    page = window.tgapipldc_locator_page
    try:
        target = service.validate_target_json(target_id, raw_json)
        service.save_target(target_id, target)
        _reload_locator_config(window, silent=True)
        page.append_log(f"定位目标已保存：{target_id}")
        window.statusBar().showMessage("定位目标已保存", 3000)
    except Exception as exc:
        _show_error(window, f"保存定位目标失败：{exc}")


def _reset_locator_target(window, target_id: str) -> None:
    service = window.tgapipldc_locator_service
    try:
        service.reset_target(target_id)
        _reload_locator_config(window, silent=True)
        window.tgapipldc_locator_page.append_log(f"已恢复默认定位参数：{target_id}")
    except Exception as exc:
        _show_error(window, f"恢复默认定位参数失败：{exc}")


def _run_locator_calibration(window, target_id: str, profile_dir: str, url: str) -> None:
    runtime = window.runtime_service
    locator_service = window.tgapipldc_locator_service
    _set_channel(window, "locator")

    def task() -> None:
        result = runtime.tgapipldc_runner_service.run_locator_calibration(
            target_id=target_id,
            profile_dir=profile_dir,
            url=url,
            raw_proxy=locator_service.proxy_for_profile(profile_dir),
            log_callback=runtime._emit_tgapipldc_log,
        )
        if not result.success:
            raise RuntimeError(
                f"定位校准未完成，退出码：{result.return_code}；关闭浏览器属于主动取消"
            )

    try:
        runtime._run_tgapipldc_background(f"定位校准-{target_id}", task)
        page = window.tgapipldc_locator_page
        page.append_log(f"已打开定位校准：{target_id}")
        page.append_log("请在浏览器中按住 Ctrl + Shift 点击目标元素。")
    except Exception as exc:
        _show_error(window, str(exc))


def _open_locator_config_directory(window) -> None:
    try:
        directory = window.tgapipldc_locator_service.open_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        window.tgapipldc_locator_page.append_log(f"已打开定位配置目录：{directory}")
    except Exception as exc:
        _show_error(window, f"打开定位配置目录失败：{exc}")


def _upload_profile_photos(window, file_paths) -> None:
    runtime = window.runtime_service
    page = _profile_page(window)
    try:
        result = runtime.tgapipldc_workspace_service.copy_profile_photo_files(file_paths or [])
        message = (
            f"图片上传完成：复制 {result.copied_count} 张，"
            f"跳过 {result.skipped_count} 个，目录：{result.library_dir}"
        )
        page.append_log(message)
        window.statusBar().showMessage(message, 3000)
    except Exception as exc:
        _show_error(window, f"上传图片失败：{exc}")


def _open_profile_photo_library(window) -> None:
    runtime = window.runtime_service
    page = _profile_page(window)
    try:
        runtime.tgapipldc_workspace_service.ensure_structure()
        directory = runtime.tgapipldc_workspace_service.profile_photos_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        page.append_log(f"已打开图片库：{directory}")
    except Exception as exc:
        _show_error(window, f"打开图片库失败：{exc}")


def _clear_profile_maintenance_results(window) -> None:
    runtime = window.runtime_service
    page = _profile_page(window)
    try:
        runtime.tgapipldc_workspace_service.clear_profile_maintenance_results()
        message = "账号资料维护结果已清空"
        page.append_log(message)
        window.statusBar().showMessage(message, 3000)
    except Exception as exc:
        _show_error(window, f"清空账号资料维护结果失败：{exc}")


def _run_profile_maintenance(window, action: str, config: dict) -> None:
    runtime = window.runtime_service
    page = _profile_page(window)
    safe_action = str(action or "status").strip().lower() or "status"
    action_name = PROFILE_MAINTENANCE_ACTION_NAMES.get(safe_action, safe_action)
    _set_channel(window, "profile")

    def task() -> None:
        result = runtime.tgapipldc_runner_service.run_profile_maintenance(
            action=safe_action,
            log_callback=runtime._emit_tgapipldc_log,
        )
        if not result.success:
            status = str(result.details.get("status") or "failed")
            raise RuntimeError(
                f"账号资料维护未完全成功，状态：{status}，退出码：{result.return_code}"
            )

    try:
        normalized_config = runtime.tgapipldc_workspace_service.save_profile_maintenance_config(config or {})
        page.set_profile_maintenance_config(normalized_config)
        runtime._run_tgapipldc_background(action_name, task)
        message = f"已开始账号资料维护：{action_name}"
        page.append_log(message)
        window.statusBar().showMessage(message, 3000)
    except Exception as exc:
        _show_error(window, str(exc))


def _api_call(window, func, success_message: str) -> None:
    _set_channel(window, "api")
    _call(window, func, success_message)


def _api_call_and_refresh(window, func, success_message: str) -> None:
    _set_channel(window, "api")
    _call_and_refresh(window, func, success_message)


def _stop_call(window, channel: str) -> None:
    _set_channel(window, channel)
    _call(window, window.runtime_service.stop_tgapipldc_process, "已请求停止当前流程")


def _call(window, func, success_message: str) -> None:
    try:
        func()
        if success_message:
            _active_page(window).append_log(success_message)
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
        _active_page(window).append_log(f"刷新 WQTG 页面状态失败：{exc}")


def _show_error(window, message: str) -> None:
    safe_message = str(message or "")
    try:
        _active_page(window).append_log(f"错误：{safe_message}")
    except Exception:
        pass
    if hasattr(window, "_show_error"):
        window._show_error(safe_message)
    else:
        QMessageBox.critical(window, "错误", safe_message)

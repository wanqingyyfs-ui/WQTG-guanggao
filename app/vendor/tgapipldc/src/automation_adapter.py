from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from automation_atomic_io import append_csv_row_locked, atomic_write_csv, read_csv_rows
from automation_locator_engine import LocatorEngine
from profile_lock import ProfileLock


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
PROFILE_LOCK_ROOT = DATA_DIR / "profile_locks"


def _engine() -> LocatorEngine:
    config_path = Path(os.environ.get("WQTG_LOCATOR_CONFIG") or DATA_DIR / "automation_locators.json")
    diagnostics_dir = Path(os.environ.get("WQTG_LOCATOR_DIAGNOSTICS") or LOG_DIR / "automation_failures")
    return LocatorEngine(config_path, diagnostics_dir, log_func=lambda message: print(message, flush=True))


def _patch(module, name: str, wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
    original = getattr(module, name, None)
    if not callable(original) or getattr(original, "_wqtg_wrapped", False):
        return
    wrapped = wrapper_factory(original)
    setattr(wrapped, "_wqtg_wrapped", True)
    setattr(module, name, wrapped)


def _click_wrapper(target_id: str, *, page_index: int = 0):
    def factory(original):
        def wrapped(*args, **kwargs):
            page = args[page_index] if len(args) > page_index else kwargs.get("page")
            if page is not None:
                try:
                    if _engine().click(page, target_id, diagnose_on_failure=False):
                        return True
                except Exception as exc:
                    print(f"定位器 {target_id} 异常，回退原逻辑：{exc}", flush=True)
            return original(*args, **kwargs)

        return wrapped

    return factory


def install_login_adapter(module) -> dict[str, Any]:
    state: dict[str, Any] = {"results": []}

    for function_name, target_id in (
        ("click_login_by_phone", "telegram.login.use_phone"),
        ("click_next_after_phone", "telegram.login.next"),
        ("click_phone_confirm_modal_if_present", "telegram.login.phone_confirm"),
        ("click_api_development_tools_link", "mytelegram.api_tools"),
    ):
        _patch(module, function_name, _click_wrapper(target_id))

    original_open = getattr(module, "open_telegram_web_for_login", None)
    if callable(original_open) and not getattr(original_open, "_wqtg_wrapped", False):
        def open_wrapped(account: dict[str, str]):
            profile_dir = Path(getattr(module, "BASE_DIR", BASE_DIR)) / str(account.get("profile_dir") or "")
            with ProfileLock(profile_dir, PROFILE_LOCK_ROOT, job_id=os.environ.get("WQTG_JOB_ID", "login")):
                result = original_open(account)
                state["results"].append(bool(result[0] if isinstance(result, tuple) else result))
                return result
        setattr(open_wrapped, "_wqtg_wrapped", True)
        module.open_telegram_web_for_login = open_wrapped

    status_file = getattr(module, "TELEGRAM_LOGIN_STATUS_FILE", None)
    if status_file is not None and callable(getattr(module, "append_login_status", None)):
        fields = ["phone", "profile_dir", "proxy", "exit_ip", "telegram_status", "note", "updated_at"]
        def append_status(row: dict[str, Any]):
            append_csv_row_locked(status_file, fields, row)
        module.append_login_status = append_status

    map_file = getattr(module, "ACCOUNT_PROXY_MAP_FILE", None)
    if map_file is not None and callable(getattr(module, "update_account_proxy_map_exit_ip", None)):
        def update_map(phone: str, new_exit_ip: str):
            fieldnames, rows = read_csv_rows(map_file)
            if "phone" not in fieldnames or "exit_ip" not in fieldnames:
                raise ValueError("account_proxy_map.csv 缺少 phone 或 exit_ip 字段")
            for row in rows:
                if str(row.get("phone") or "").strip() == str(phone or "").strip():
                    row["exit_ip"] = str(new_exit_ip or "")
                    if "status" in fieldnames:
                        row["status"] = "telegram_proxy_verified"
                    if "note" in fieldnames:
                        row["note"] = "exit_ip_updated_before_telegram_login"
                    break
            atomic_write_csv(map_file, fieldnames, rows)
        module.update_account_proxy_map_exit_ip = update_map

    return state


def install_profile_adapter(module) -> dict[str, Any]:
    state: dict[str, Any] = {"rows": []}

    for function_name, target_id in (
        ("open_settings", "telegram.settings.open"),
        ("click_profile_edit_icon_button", "telegram.profile.edit"),
        ("click_photo_editor_finish_button", "telegram.photo.editor_save"),
        ("click_profile_save_button_multi", "telegram.profile.save"),
    ):
        _patch(module, function_name, _click_wrapper(target_id))

    original_add_folder = getattr(module, "_v16_click_add_folder_button", None)
    if callable(original_add_folder) and not getattr(original_add_folder, "_wqtg_wrapped", False):
        def add_folder_wrapped(page):
            try:
                if _engine().click(page, "telegram.folder.add", diagnose_on_failure=False):
                    return "success"
            except Exception as exc:
                print(f"文件夹定位器异常，回退原逻辑：{exc}", flush=True)
            return original_add_folder(page)
        setattr(add_folder_wrapped, "_wqtg_wrapped", True)
        module._v16_click_add_folder_button = add_folder_wrapped

    original_process = getattr(module, "process_account", None)
    if callable(original_process) and not getattr(original_process, "_wqtg_wrapped", False):
        def process_wrapped(action, config, account, account_index, total, used_photos):
            profile_dir = Path(getattr(module, "BASE_DIR", BASE_DIR)) / str(account.get("profile_dir") or "")
            with ProfileLock(profile_dir, PROFILE_LOCK_ROOT, job_id=os.environ.get("WQTG_JOB_ID", "profile")):
                return original_process(action, config, account, account_index, total, used_photos)
        setattr(process_wrapped, "_wqtg_wrapped", True)
        module.process_account = process_wrapped

    original_write_result = getattr(module, "write_result", None)
    if callable(original_write_result):
        def write_result_wrapped(row):
            state["rows"].append(dict(row or {}))
            return original_write_result(row)
        module.write_result = write_result_wrapped

    return state

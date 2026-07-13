from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from automation_locator_engine import LocatorEngine

CONFIG_KEY = "profile_behaviors"
BUILTIN_IDS = {"status", "photo", "name", "username", "bio", "folder", "all"}
ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SUCCESS = {"success", "already_added", "logged_in"}
STEP_TYPES = {
    "status.check": "检查 Telegram 登录状态",
    "photo.select_upload": "进入编辑页并上传头像",
    "photo.crop_confirm": "确认头像裁剪",
    "profile.save": "点击资料保存按钮",
    "photo.wait_settled": "等待头像上传与页面稳定",
    "name.update": "修改昵称",
    "username.update": "修改用户名",
    "bio.update": "修改签名",
    "folder.add": "添加分组文件夹",
    "behavior.run": "运行另一个行为",
    "navigation.home": "返回 Telegram 初始页面",
    "wait": "等待指定毫秒",
}


def step(step_id: str, step_type: str, name: str, **extra) -> dict[str, Any]:
    value = {
        "id": step_id, "name": name, "type": step_type, "enabled": True,
        "required": True, "retries": 1, "wait_after_ms": 0, "params": {},
    }
    value.update(extra)
    return value


def default_behaviors(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = dict(config or {})
    builtins = [
        ("status", "检测资料状态", True, [step("check", "status.check", "检查登录状态")]),
        ("photo", "修改头像", cfg.get("update_photo", True), [
            step("upload", "photo.select_upload", "进入资料编辑并上传头像", retries=2),
            step("crop", "photo.crop_confirm", "确认头像裁剪", retries=2, wait_after_ms=3000),
            step("save", "profile.save", "点击资料页保存按钮", retries=3),
            step("settle", "photo.wait_settled", "等待头像上传与页面稳定",
                 params={"sync_wait_ms": 15000, "settle_timeout_ms": 15000}),
        ]),
        ("name", "修改昵称", cfg.get("update_name", True), [step("update", "name.update", "修改昵称", retries=2)]),
        ("username", "修改用户名", cfg.get("update_username", True), [step("update", "username.update", "修改用户名", retries=2)]),
        ("bio", "修改签名", cfg.get("update_bio", True), [step("update", "bio.update", "修改签名", retries=2)]),
        ("folder", "添加分组文件夹", cfg.get("add_chat_folder", True), [step("add", "folder.add", "添加分组文件夹", retries=2)]),
    ]
    result = [{"id": i, "name": n, "enabled": bool(e), "builtin": True,
               "failure_mode": "strict", "steps": s} for i, n, e, s in builtins]
    all_steps = []
    for behavior_id, name in (("photo", "头像"), ("name", "昵称"), ("username", "用户名"), ("bio", "签名"), ("folder", "分组文件夹")):
        all_steps.append(step(f"run_{behavior_id}", "behavior.run", f"运行{name}", params={"behavior_id": behavior_id}))
        if behavior_id != "folder":
            all_steps.append(step(f"home_{behavior_id}", "navigation.home", f"{name}后返回初始页", wait_after_ms=3000))
    result.append({"id": "all", "name": "修改全部选项", "enabled": True,
                   "builtin": True, "failure_mode": "strict", "steps": all_steps})
    return result


def normalize_step(raw: dict[str, Any] | None, index: int = 0) -> dict[str, Any]:
    data = dict(raw or {})
    kind = str(data.get("type") or "wait")
    if kind not in STEP_TYPES:
        kind = "wait"
    step_id = str(data.get("id") or f"step_{index + 1}").strip().lower()
    if not ID_RE.fullmatch(step_id):
        step_id = f"step_{index + 1}"
    try:
        retries = max(1, min(5, int(data.get("retries") or 1)))
    except Exception:
        retries = 1
    try:
        wait_ms = max(0, min(600000, int(data.get("wait_after_ms") or 0)))
    except Exception:
        wait_ms = 0
    return {
        "id": step_id,
        "name": str(data.get("name") or STEP_TYPES[kind]).strip() or STEP_TYPES[kind],
        "type": kind,
        "enabled": bool(data.get("enabled", True)),
        "required": bool(data.get("required", True)),
        "retries": retries,
        "wait_after_ms": wait_ms,
        "params": deepcopy(data.get("params") if isinstance(data.get("params"), dict) else {}),
    }


def normalize_behavior(raw: dict[str, Any] | None, index: int = 0) -> dict[str, Any]:
    data = dict(raw or {})
    behavior_id = str(data.get("id") or f"custom_{index + 1}").strip().lower()
    if not ID_RE.fullmatch(behavior_id):
        behavior_id = f"custom_{index + 1}"
    raw_steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    return {
        "id": behavior_id,
        "name": str(data.get("name") or behavior_id).strip() or behavior_id,
        "enabled": bool(data.get("enabled", True)),
        "builtin": bool(data.get("builtin", behavior_id in BUILTIN_IDS)),
        "failure_mode": "continue" if data.get("failure_mode") == "continue" else "strict",
        "steps": [normalize_step(item, idx) for idx, item in enumerate(raw_steps) if isinstance(item, dict)],
    }


def normalize_behaviors(raw: Any, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    defaults = default_behaviors(config)
    if not isinstance(raw, list):
        return defaults
    result, seen = [], set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        behavior = normalize_behavior(item, index)
        if behavior["id"] not in seen:
            result.append(behavior)
            seen.add(behavior["id"])
    for behavior in defaults:
        if behavior["id"] not in seen:
            result.append(behavior)
    return result


def normalize_config(config: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(config or {})
    result["workflow_schema_version"] = 1
    result[CONFIG_KEY] = normalize_behaviors(result.get(CONFIG_KEY), result)
    flags = {"photo": "update_photo", "name": "update_name", "username": "update_username", "bio": "update_bio", "folder": "add_chat_folder"}
    for behavior in result[CONFIG_KEY]:
        flag = flags.get(behavior["id"])
        if flag in result:
            behavior["enabled"] = bool(result[flag])
    return result


def behavior_map(config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in normalize_config(config)[CONFIG_KEY]}


def sleep(page, milliseconds: int) -> None:
    milliseconds = max(0, int(milliseconds or 0))
    if not milliseconds:
        return
    try:
        page.wait_for_timeout(milliseconds)
    except Exception:
        time.sleep(milliseconds / 1000)


def engine(module) -> LocatorEngine:
    base = Path(getattr(module, "BASE_DIR", Path(__file__).resolve().parent.parent))
    data = Path(getattr(module, "DATA_DIR", base / "data"))
    logs = Path(getattr(module, "LOG_DIR", base / "logs"))
    return LocatorEngine(
        Path(os.environ.get("WQTG_LOCATOR_CONFIG") or data / "automation_locators.json"),
        Path(os.environ.get("WQTG_LOCATOR_DIAGNOSTICS") or logs / "automation_failures"),
        log_func=module.log,
    )


def locator_click(module, page, target_id: str) -> bool:
    try:
        return bool(_locator_engine(module).click(page, target_id, diagnose_on_failure=False))
    except Exception as exc:
        module.log(f"定位器 {target_id} 失败：{exc}")
        return False


def execute_step(module, page, item: dict[str, Any], state: dict[str, Any], config: dict[str, Any], stack: tuple[str, ...]) -> str:
    kind, params = item["type"], dict(item.get("params") or {})
    account, index, used = state["account"], state["account_index"], state["used_photos"]
    if kind == "status.check":
        return "logged_in"
    if kind == "photo.select_upload":
        path = state.get("photo_path") or module.select_photo(config, index, used)
        state["photo_path"] = path
        if path is None or not Path(path).exists():
            return "skipped_no_photo"
        used.add(Path(path))
        if not module.open_settings(page) or not module.click_profile_edit_icon_button(page):
            raise RuntimeError("未能进入头像编辑页")
        sleep(page, 1200)
        module.click_profile_avatar_for_upload(page, Path(path))
        return "success"
    if kind == "photo.crop_confirm":
        if not locator_click(module, page, "telegram.photo.editor_save"):
            if not module.click_media_editor_finish(page, timeout=15000):
                raise RuntimeError("未找到头像裁剪确认按钮")
        if hasattr(module, "wait_media_editor_closed") and not module.wait_media_editor_closed(page, timeout=30000):
            raise RuntimeError("头像裁剪确认后媒体编辑器没有关闭")
        return "success"
    if kind == "profile.save":
        if locator_click(module, page, "telegram.profile.save"):
            return "success"
        max_clicks = max(1, min(5, int(params.get("max_clicks") or 1)))
        if module.click_profile_save_button_multi(page, "资料保存按钮", max_clicks=max_clicks, max_wait_seconds=15):
            return "success"
        raise RuntimeError("头像裁剪确认后未找到资料页保存按钮")
    if kind == "photo.wait_settled":
        sleep(page, int(params.get("sync_wait_ms") or 15000))
        if not module.wait_photo_save_ui_settled(page, timeout_ms=int(params.get("settle_timeout_ms") or 15000)):
            raise RuntimeError("头像保存后页面没有稳定")
        return "success"
    if kind in {"name.update", "username.update", "bio.update", "folder.add"}:
        domain = kind.split(".", 1)[0]
        return str(module.execute_step(page, domain, config, account, index, used))
    if kind == "navigation.home":
        if hasattr(module, "_v17_return_to_initial_telegram_page"):
            module._v17_return_to_initial_telegram_page(page, account, item.get("name") or "返回初始页")
        else:
            page.goto(getattr(module, "TELEGRAM_WEB_URL", "https://web.telegram.org/k/"), wait_until="commit", timeout=20000)
        return "success"
    if kind == "wait":
        sleep(page, int(params.get("milliseconds") or item.get("wait_after_ms") or 1000))
        return "success"
    if kind == "behavior.run":
        target = str(params.get("behavior_id") or "").strip().lower()
        if not target:
            raise RuntimeError("behavior.run 缺少 behavior_id")
        return execute_behavior(module, page, target, state, config, stack)
    raise RuntimeError(f"不支持的步骤类型：{kind}")


def status_ok(value: str) -> bool:
    value = str(value or "").lower()
    return value in SUCCESS or value.startswith("skipped")


def domain_for(item: dict[str, Any]) -> str | None:
    kind = item["type"]
    if kind.startswith("photo.") or kind == "profile.save":
        return "photo"
    if kind.endswith(".update") or kind == "folder.add":
        return kind.split(".", 1)[0]
    if kind == "behavior.run":
        target = str((item.get("params") or {}).get("behavior_id") or "")
        return target if target in {"photo", "name", "username", "bio", "folder"} else None
    return None


def execute_behavior(module, page, behavior_id: str, state: dict[str, Any], config: dict[str, Any], stack: tuple[str, ...] = ()) -> str:
    behavior_id = str(behavior_id).lower()
    if behavior_id in stack:
        raise RuntimeError("行为循环引用：" + " -> ".join((*stack, behavior_id)))
    behavior = behavior_map(config).get(behavior_id)
    if behavior is None:
        raise KeyError(f"未知行为：{behavior_id}")
    if not behavior.get("enabled", True):
        return "skipped_disabled"
    active = [item for item in behavior["steps"] if item.get("enabled", True)]
    module.log(f"开始行为 {behavior_id}（{behavior['name']}），启用步骤 {len(active)} 个。")
    failures = []
    for position, item in enumerate(active, 1):
        status, error = "", ""
        attempts = int(item.get("retries") or 1)
        for attempt in range(1, attempts + 1):
            try:
                module.log(f"步骤 {position}/{len(active)} {item['name']}，尝试 {attempt}/{attempts}")
                status = str(execute_step(module, page, item, state, config, (*stack, behavior_id)) or "success")
                if status_ok(status):
                    error = ""
                    break
                error = f"返回状态：{status}"
            except Exception as exc:
                error = str(exc)
            if attempt < attempts:
                sleep(page, 1500)
        ok = status_ok(status) and not error
        state["step_results"].append({"behavior": behavior_id, "step_id": item["id"], "type": item["type"], "status": status or "failed", "success": ok, "error": error})
        domain = domain_for(item)
        if domain:
            domains = state.setdefault("domains", state.get("domain_statuses", {}))
            domains.setdefault(domain, []).append(status if ok else f"failed: {error or status}")
        if not ok:
            failures.append(f"{behavior_id}.{item['id']}: {error or status}")
            if item.get("required", True) and behavior.get("failure_mode") == "strict":
                raise RuntimeError(failures[-1])
        sleep(page, int(item.get("wait_after_ms") or 0))
    return "partial_failed" if failures else "success"


def aggregate(values: list[str]) -> str:
    if not values:
        return "skipped"
    failed = [value for value in values if str(value).startswith("failed")]
    if failed:
        return failed[-1]
    normal = [value for value in values if not str(value).startswith("skipped")]
    return normal[-1] if normal else values[-1]


def build_process_account(module):
    def process_account(action, config, account, account_index, total, used_photos):
        config, action = normalize_config(config), str(action or "status").strip().lower()
        result = module.safe_status_row(account, action)
        behavior = behavior_map(config).get(action)
        if behavior is None:
            result.update(final_status="failed", note=f"未知资料维护行为：{action}")
            return result
        parsed = module.parse_raw_proxy(account["raw_proxy"])
        result["masked_proxy"] = parsed.masked_raw_proxy
        ok, realtime_ip, error = module.verify_proxy_before_browser(account, parsed)
        if not ok:
            result.update(final_status="failed", note=error)
            return result
        state = {"account": account, "account_index": account_index, "used_photos": used_photos,
                 "photo_path": None, "step_results": [], "domains": {}}
        context = None
        try:
            with module.sync_playwright() as playwright:
                context, _ = module.launch_context_for_account(playwright, account)
                ok, browser_ip, error = module.verify_browser_proxy(context, account, realtime_ip)
                if not ok:
                    result.update(final_status="failed", note=error)
                    return result
                page = context.new_page()
                if not module.ensure_logged_in_without_mytelegram(page, account):
                    result.update(final_status="not_logged_in", note="Telegram Web 未登录，自动登录失败")
                    return result
                status = execute_behavior(module, page, action, state, config)
                result["final_status"] = "success" if status_ok(status) else status
                result["note"] = f"行为 {behavior['name']} 完成；步骤结果={json.dumps(state['step_results'], ensure_ascii=False)}"
                if action == "status":
                    result["note"] = f"logged_in，browser_ip={browser_ip}"
        except Exception as exc:
            result.update(final_status="failed", note=f"行为 {behavior['name']} 失败：{exc}；步骤结果={json.dumps(state['step_results'], ensure_ascii=False)}")
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
        for domain, field in module.STEP_STATUS_FIELDS.items():
            result[field] = aggregate(state["domains"].get(domain, []))
        result["_workflow_failed_steps"] = [f"{x['behavior']}.{x['step_id']}" for x in state["step_results"] if not x["success"]]
        return result
    process_account._wqtg_behavior_workflow = True
    return process_account


def install_profile_behavior_workflow(module) -> None:
    if getattr(module, "_wqtg_behavior_workflow_installed", False):
        return
    old_normalize = module.normalize_config
    module.DEFAULT_CONFIG = normalize_config(module.DEFAULT_CONFIG)
    module.normalize_config = lambda raw: normalize_config(old_normalize(raw))
    module.action_steps = lambda action, config: [x["type"] for x in (behavior_map(config).get(str(action), {}).get("steps") or []) if x.get("enabled", True)]
    module.failed_steps_from_result = lambda row: list(row.get("_workflow_failed_steps") or [])
    module.unfinished_steps_from_result = lambda row, steps: []
    module.process_account = build_process_account(module)
    module._wqtg_behavior_workflow_installed = True


BUILTIN_BEHAVIOR_IDS = BUILTIN_IDS
STEP_TYPE_LABELS = STEP_TYPES
normalize_workflow_config = normalize_config
_execute_behavior = execute_behavior
_locator_engine = engine


def behavior_name(config: dict[str, Any] | None, behavior_id: str) -> str:
    item = behavior_map(config).get(str(behavior_id or "").strip().lower())
    return str((item or {}).get("name") or behavior_id)

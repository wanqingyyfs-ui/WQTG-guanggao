from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

LOCATOR_CLICK_TYPE = "locator.click"
LOCATOR_FILL_TYPE = "locator.fill"
LOCATOR_UPLOAD_TYPE = "locator.upload"
PAGE_STEP_TYPES = {LOCATOR_CLICK_TYPE, LOCATOR_FILL_TYPE, LOCATOR_UPLOAD_TYPE}

DATA_PREPARE_PHOTO = "data.prepare_photo"
DATA_PREPARE_NAME = "data.prepare_name"
DATA_PREPARE_USERNAME = "data.prepare_username"
DATA_PREPARE_BIO = "data.prepare_bio"
DATA_PREPARE_FOLDER = "data.prepare_folder"
NAVIGATE_STATE_URL = "navigation.goto_state_url"
KEYBOARD_PRESS_TYPE = "keyboard.press"
VERIFY_PHOTO = "verify.photo"
VERIFY_NAME = "verify.name"
VERIFY_USERNAME = "verify.username"
VERIFY_BIO = "verify.bio"
VERIFY_FOLDER = "verify.folder"

MANAGED_TARGET_PREFIX = "workflow."
MANAGED_BY = "profile_behavior_step"
ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")

STEP_LABELS = {
    LOCATOR_CLICK_TYPE: "点击已配置定位目标",
    LOCATOR_FILL_TYPE: "向已配置输入目标写入内容",
    LOCATOR_UPLOAD_TYPE: "向已配置上传目标上传头像",
    DATA_PREPARE_PHOTO: "读取账号资料维护中的头像配置",
    DATA_PREPARE_NAME: "读取账号资料维护中的昵称配置",
    DATA_PREPARE_USERNAME: "生成当前账号的用户名",
    DATA_PREPARE_BIO: "读取账号资料维护中的签名配置",
    DATA_PREPARE_FOLDER: "读取账号资料维护中的分组文件夹配置",
    NAVIGATE_STATE_URL: "打开已准备的配置链接",
    KEYBOARD_PRESS_TYPE: "按下指定键盘按键",
    VERIFY_PHOTO: "校验头像修改结果",
    VERIFY_NAME: "校验昵称修改结果",
    VERIFY_USERNAME: "校验用户名修改结果",
    VERIFY_BIO: "校验签名修改结果",
    VERIFY_FOLDER: "校验分组文件夹添加结果",
}

LEGACY_COMPOSITE_TYPES = {
    "photo.select_upload",
    "photo.crop_confirm",
    "profile.save",
    "photo.wait_settled",
    "name.update",
    "username.update",
    "bio.update",
    "folder.add",
}


def normalize_id(value: str, label: str) -> str:
    clean = str(value or "").strip().lower()
    if not ID_RE.fullmatch(clean):
        raise ValueError(
            f"{label} ID 只能使用小写字母、数字、点、下划线和连字符，并且必须以字母开头：{value}"
        )
    return clean


def managed_target_id(behavior_id: str, step_id: str) -> str:
    return (
        f"{MANAGED_TARGET_PREFIX}"
        f"{normalize_id(behavior_id, '行为')}."
        f"{normalize_id(step_id, '步骤')}"
    )


def page_step(
    behavior_id: str,
    step_id: str,
    name: str,
    step_type: str = LOCATOR_CLICK_TYPE,
    *,
    domain: str = "",
    retries: int = 2,
    wait_after_ms: int = 800,
    required: bool = True,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if step_type not in PAGE_STEP_TYPES:
        raise ValueError(f"不是页面定位步骤类型：{step_type}")
    payload = dict(params or {})
    payload["target_id"] = managed_target_id(behavior_id, step_id)
    if domain:
        payload["domain"] = domain
    return {
        "id": normalize_id(step_id, "步骤"),
        "name": str(name or step_id).strip() or step_id,
        "type": step_type,
        "enabled": True,
        "required": bool(required),
        "retries": max(1, int(retries or 1)),
        "wait_after_ms": max(0, int(wait_after_ms or 0)),
        "params": payload,
    }


def function_step(
    step_id: str,
    step_type: str,
    name: str,
    *,
    domain: str = "",
    retries: int = 1,
    wait_after_ms: int = 0,
    required: bool = True,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(params or {})
    if domain:
        payload["domain"] = domain
    return {
        "id": normalize_id(step_id, "步骤"),
        "name": str(name or step_id).strip() or step_id,
        "type": step_type,
        "enabled": True,
        "required": bool(required),
        "retries": max(1, int(retries or 1)),
        "wait_after_ms": max(0, int(wait_after_ms or 0)),
        "params": payload,
    }


def make_custom_page_step(
    behavior_id: str,
    step_id: str,
    name: str,
    step_type: str = LOCATOR_CLICK_TYPE,
    *,
    value_source: str = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if step_type == LOCATOR_FILL_TYPE:
        params["value_source"] = str(value_source or "literal:")
        params["allow_empty"] = False
    elif step_type == LOCATOR_UPLOAD_TYPE:
        params["value_source"] = str(value_source or "state.photo_path")
    return page_step(
        behavior_id,
        step_id,
        name,
        step_type,
        retries=1,
        wait_after_ms=800,
        params=params,
    )


def make_custom_click_step(behavior_id: str, step_id: str, name: str) -> dict[str, Any]:
    return make_custom_page_step(behavior_id, step_id, name, LOCATOR_CLICK_TYPE)


def locator_target_for_step(behavior_id: str, step: dict[str, Any] | None) -> str:
    item = dict(step or {})
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    explicit = str(params.get("target_id") or item.get("locator_target_id") or "").strip()
    if explicit:
        return explicit
    if str(item.get("type") or "") in PAGE_STEP_TYPES:
        return managed_target_id(behavior_id, str(item.get("id") or "step"))
    return ""


def _css(value: str) -> dict[str, Any]:
    return {"type": "css", "value": value, "enabled": True}


def _role(role: str, regex: str) -> dict[str, Any]:
    return {"type": "role", "role": role, "name_regex": regex, "enabled": True}


def _text(regex: str) -> dict[str, Any]:
    return {"type": "text", "value_regex": regex, "enabled": True}


def default_strategies(behavior_id: str, step_id: str, step_type: str) -> list[dict[str, Any]]:
    key = f"{behavior_id}.{step_id}".lower()
    if "open_main_menu" in key:
        return [
            _role("button", "menu|菜单"),
            _css("button.btn-menu,.sidebar-header button.btn-icon,button[aria-label*='menu' i]"),
        ]
    if "open_settings" in key:
        return [
            _role("menuitem", "settings|设置"),
            _text("^settings$|^设置$"),
            _css("[data-menu-id='settings'],.btn-menu-item"),
        ]
    if "open_profile_edit" in key:
        return [
            _role("button", "edit|编辑"),
            _css("button.btn-icon.rp,button[aria-label*='edit' i]"),
        ]
    if "upload_photo" in key:
        return [
            _css("input[type='file'][accept*='image']"),
            _css(".avatar.avatar-120,.avatar-120,.profile-change-avatar"),
            _role("button", "photo|avatar|头像|照片"),
        ]
    if "confirm_crop" in key:
        return [
            _role("button", "done|save|apply|完成|保存|确定"),
            _css(".media-editor__finish-button,.media-editor button.btn-primary"),
        ]
    if "save" in key:
        return [
            _role("button", "save|done|保存|完成"),
            _css("button.btn-circle.btn-corner.rp.is-visible,button.btn-primary"),
        ]
    if "first_name" in key:
        return [
            _css("input[name='first_name'],input[name='firstName']"),
            _css(".input-field input.input-field-input"),
        ]
    if "last_name" in key:
        return [
            _css("input[name='last_name'],input[name='lastName']"),
            _css(".input-field input.input-field-input"),
        ]
    if "username" in key and step_type == LOCATOR_FILL_TYPE:
        return [
            _css("input[name='username']"),
            _css("input.input-field-input[autocomplete='off']"),
        ]
    if "bio" in key and step_type == LOCATOR_FILL_TYPE:
        return [
            _css("textarea[name='bio'],textarea[name='about'],input[name='bio'],input[name='about']"),
            _css(".input-field-input[contenteditable='true'][data-no-linebreaks='1']"),
        ]
    if "open_saved_messages" in key:
        return [
            _role("link", "saved messages|saved|收藏夹|已保存的消息|保存的消息"),
            _text("^saved messages$|^saved$|^收藏夹$|^已保存的消息$|^保存的消息$"),
        ]
    if "input_folder_link" in key:
        return [
            _css("[contenteditable='true'][data-peer-id],.input-message-input"),
            _css("[contenteditable='true']"),
        ]
    if "click_folder_link" in key:
        return [
            _css("a[href*='addlist'],.message a,.bubble a"),
            _text(r"t\.me/addlist|telegram\.me/addlist"),
        ]
    if "add_folder" in key or ("folder" in key and step_type == LOCATOR_CLICK_TYPE):
        return [
            _role("button", "add folder|add|join|apply|save|done|ok|添加文件夹|添加|加入|保存|完成|确定"),
            _css(".popup button.btn-primary,.modal button.btn-primary,button.btn-primary"),
        ]
    return [_css(f"[data-wqtg-unconfigured-target='{managed_target_id(behavior_id, step_id)}']")]


def blank_managed_target(
    target_id: str,
    behavior_id: str,
    behavior_name: str,
    step_id: str,
    step_name: str,
    previous: dict[str, Any] | None = None,
    *,
    step_type: str = LOCATOR_CLICK_TYPE,
) -> dict[str, Any]:
    old = deepcopy(previous or {})
    strategies = old.get("strategies") if isinstance(old.get("strategies"), list) else []
    if not strategies:
        strategies = default_strategies(behavior_id, step_id, step_type)
    absolute = old.get("absolute_position") if isinstance(old.get("absolute_position"), dict) else {
        "x": 0.0,
        "y": 0.0,
        "viewport_width": 1200,
        "viewport_height": 900,
        "captured": False,
    }
    return {
        "category": f"行为：{str(behavior_name or behavior_id)}",
        "description": str(step_name or step_id),
        "timeout_ms": int(old.get("timeout_ms") or 15000),
        "locator_mode": str(old.get("locator_mode") or "strategies"),
        "absolute_position": absolute,
        "strategies": strategies,
        "managed_by": MANAGED_BY,
        "behavior_id": str(behavior_id),
        "step_id": str(step_id),
        "step_type": str(step_type),
    }


def _behavior(behavior_id: str, name: str, enabled: bool, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": behavior_id,
        "name": name,
        "enabled": bool(enabled),
        "builtin": True,
        "failure_mode": "strict",
        "steps": steps,
    }


def atomic_default_behaviors(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = dict(config or {})
    photo = [
        function_step("step01_prepare_photo", DATA_PREPARE_PHOTO, "修改头像1：读取头像配置", domain="photo"),
        page_step("photo", "step02_open_main_menu", "修改头像2：点击主菜单", domain="photo"),
        page_step("photo", "step03_open_settings", "修改头像3：点击设置", domain="photo"),
        page_step("photo", "step04_open_profile_edit", "修改头像4：点击编辑资料", domain="photo"),
        page_step(
            "photo", "step05_upload_photo", "修改头像5：选择并上传头像",
            LOCATOR_UPLOAD_TYPE, domain="photo",
            params={"value_source": "state.photo_path"},
        ),
        page_step("photo", "step06_confirm_crop", "修改头像6：确认头像裁剪", domain="photo"),
        page_step("photo", "step07_save_profile", "修改头像7：点击资料保存", domain="photo", retries=3),
        function_step(
            "step08_verify_photo", VERIFY_PHOTO, "修改头像8：等待并校验头像",
            domain="photo",
            params={"sync_wait_ms": 15000, "settle_timeout_ms": 15000},
        ),
    ]
    name = [
        function_step("step01_prepare_name", DATA_PREPARE_NAME, "修改昵称1：读取昵称配置", domain="name"),
        page_step("name", "step02_open_main_menu", "修改昵称2：点击主菜单", domain="name"),
        page_step("name", "step03_open_settings", "修改昵称3：点击设置", domain="name"),
        page_step("name", "step04_open_profile_edit", "修改昵称4：点击编辑资料", domain="name"),
        page_step(
            "name", "step05_input_first_name", "修改昵称5：输入 First Name",
            LOCATOR_FILL_TYPE, domain="name",
            params={"value_source": "state.first_name"},
        ),
        page_step(
            "name", "step06_input_last_name", "修改昵称6：输入 Last Name",
            LOCATOR_FILL_TYPE, domain="name", required=False,
            params={"value_source": "state.last_name", "allow_empty": True},
        ),
        page_step("name", "step07_save_name", "修改昵称7：点击保存", domain="name"),
        function_step(
            "step08_verify_name", VERIFY_NAME, "修改昵称8：等待并校验昵称",
            domain="name", params={"wait_before_ms": 15000},
        ),
    ]
    username = [
        function_step("step01_prepare_username", DATA_PREPARE_USERNAME, "修改用户名1：生成账号用户名", domain="username"),
        page_step("username", "step02_open_main_menu", "修改用户名2：点击主菜单", domain="username"),
        page_step("username", "step03_open_settings", "修改用户名3：点击设置", domain="username"),
        page_step("username", "step04_open_profile_edit", "修改用户名4：点击编辑资料", domain="username"),
        page_step(
            "username", "step05_input_username", "修改用户名5：输入用户名",
            LOCATOR_FILL_TYPE, domain="username",
            params={"value_source": "state.username"},
        ),
        page_step("username", "step06_save_username", "修改用户名6：点击保存", domain="username"),
        function_step(
            "step07_verify_username", VERIFY_USERNAME, "修改用户名7：等待并校验用户名",
            domain="username", params={"wait_before_ms": 20000},
        ),
    ]
    bio = [
        function_step("step01_prepare_bio", DATA_PREPARE_BIO, "修改签名1：读取签名配置", domain="bio"),
        page_step("bio", "step02_open_main_menu", "修改签名2：点击主菜单", domain="bio"),
        page_step("bio", "step03_open_settings", "修改签名3：点击设置", domain="bio"),
        page_step("bio", "step04_open_profile_edit", "修改签名4：点击编辑资料", domain="bio"),
        page_step(
            "bio", "step05_input_bio", "修改签名5：输入签名",
            LOCATOR_FILL_TYPE, domain="bio",
            params={"value_source": "state.bio_text"},
        ),
        page_step("bio", "step06_save_bio", "修改签名6：点击保存", domain="bio"),
        function_step(
            "step07_verify_bio", VERIFY_BIO, "修改签名7：等待并校验签名",
            domain="bio", params={"wait_before_ms": 20000},
        ),
    ]
    folder = [
        function_step("step01_prepare_folder", DATA_PREPARE_FOLDER, "添加分组文件夹1：读取文件夹链接", domain="folder"),
        page_step("folder", "step02_open_saved_messages", "添加分组文件夹2：点击收藏夹", domain="folder"),
        page_step(
            "folder", "step03_input_folder_link", "添加分组文件夹3：输入文件夹链接",
            LOCATOR_FILL_TYPE, domain="folder",
            params={"value_source": "state.folder_link"},
        ),
        function_step(
            "step04_send_folder_link", KEYBOARD_PRESS_TYPE, "添加分组文件夹4：发送文件夹链接",
            domain="folder", params={"key": "Enter"}, wait_after_ms=2500,
        ),
        page_step("folder", "step05_click_folder_link", "添加分组文件夹5：点击已发送链接", domain="folder", wait_after_ms=3000),
        page_step("folder", "step06_add_folder", "添加分组文件夹6：点击添加文件夹", domain="folder", retries=2),
        function_step("step07_verify_folder", VERIFY_FOLDER, "添加分组文件夹7：校验添加结果", domain="folder"),
    ]
    result = [
        _behavior("status", "检测资料状态", True, [
            function_step("step01_check_login", "status.check", "检测状态1：检查 Telegram 登录状态")
        ]),
        _behavior("photo", "修改头像", cfg.get("update_photo", True), photo),
        _behavior("name", "修改昵称", cfg.get("update_name", True), name),
        _behavior("username", "修改用户名", cfg.get("update_username", True), username),
        _behavior("bio", "修改签名", cfg.get("update_bio", True), bio),
        _behavior("folder", "添加分组文件夹", cfg.get("add_chat_folder", True), folder),
    ]
    all_steps: list[dict[str, Any]] = []
    for number, (behavior_id, label) in enumerate((
        ("photo", "头像"), ("name", "昵称"), ("username", "用户名"),
        ("bio", "签名"), ("folder", "分组文件夹"),
    ), 1):
        all_steps.append(function_step(
            f"step{number:02d}_run_{behavior_id}",
            "behavior.run",
            f"修改全部{number}：运行{label}行为",
            params={"behavior_id": behavior_id},
        ))
        if behavior_id != "folder":
            all_steps.append(function_step(
                f"step{number:02d}_home_{behavior_id}",
                "navigation.home",
                f"修改全部{number}：{label}后返回初始页",
                wait_after_ms=3000,
            ))
    result.append(_behavior("all", "修改全部选项", True, all_steps))
    return result


def _legacy_expansion(behavior_id: str, item_type: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = {item["id"]: item for item in atomic_default_behaviors(config)}
    steps = deepcopy(defaults.get(behavior_id, {}).get("steps") or [])
    if item_type in {"name.update", "username.update", "bio.update", "folder.add"}:
        return steps
    if behavior_id != "photo":
        return []
    mapping = {
        "photo.select_upload": {
            "step01_prepare_photo", "step02_open_main_menu", "step03_open_settings",
            "step04_open_profile_edit", "step05_upload_photo",
        },
        "photo.crop_confirm": {"step06_confirm_crop"},
        "profile.save": {"step07_save_profile"},
        "photo.wait_settled": {"step08_verify_photo"},
    }
    wanted = mapping.get(item_type, set())
    return [item for item in steps if item["id"] in wanted]


def migrate_legacy_behaviors(
    behaviors: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    migrated: list[dict[str, Any]] = []
    for behavior in behaviors:
        current = deepcopy(behavior)
        behavior_id = str(current.get("id") or "")
        new_steps: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for item in current.get("steps") or []:
            item_type = str(item.get("type") or "")
            replacements = (
                _legacy_expansion(behavior_id, item_type, config)
                if item_type in LEGACY_COMPOSITE_TYPES
                else [deepcopy(item)]
            )
            for replacement in replacements:
                step_id = str(replacement.get("id") or "")
                if step_id and step_id not in used_ids:
                    new_steps.append(replacement)
                    used_ids.add(step_id)
        if behavior_id in {"photo", "name", "username", "bio", "folder"} and not new_steps:
            default_map = {item["id"]: item for item in atomic_default_behaviors(config)}
            new_steps = deepcopy(default_map[behavior_id]["steps"])
        current["steps"] = new_steps
        migrated.append(current)
    return migrated


def _read_source(source: str, state: dict[str, Any], config: dict[str, Any]) -> Any:
    clean = str(source or "").strip()
    if clean.startswith("state."):
        return state.get(clean.split(".", 1)[1], "")
    if clean.startswith("config."):
        return config.get(clean.split(".", 1)[1], "")
    if clean.startswith("account."):
        return state.get("account", {}).get(clean.split(".", 1)[1], "")
    if clean.startswith("literal:"):
        return clean.split(":", 1)[1]
    return clean


def _target_mode(engine, target_id: str) -> str:
    try:
        target = engine.store.load().get("targets", {}).get(target_id) or {}
        return str(target.get("locator_mode") or "strategies")
    except Exception:
        return "strategies"


def _generic_fill(module, page, locator, value: str, label: str) -> None:
    if hasattr(module, "_fill_profile_text_field"):
        module._fill_profile_text_field(page, locator, value, label)
        return
    locator.wait_for(state="visible", timeout=10000)
    locator.scroll_into_view_if_needed(timeout=5000)
    locator.click(timeout=5000, force=True)
    try:
        locator.fill("", timeout=3000)
        locator.fill(value, timeout=8000)
    except Exception:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        if value:
            page.keyboard.insert_text(value)


def _execute_fill(workflow, module, page, target_id: str, value: str, label: str) -> None:
    engine = workflow._locator_engine(module)
    if _target_mode(engine, target_id) == "absolute_position":
        if not engine.click(page, target_id, diagnose_on_failure=False):
            raise RuntimeError(f"未能点击输入位置：{target_id}")
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        if value:
            page.keyboard.insert_text(value)
        return
    locator = engine.resolve(page, target_id)
    if locator is None:
        raise RuntimeError(f"未能定位输入目标：{target_id}")
    _generic_fill(module, page, locator, value, label)


def _execute_upload(workflow, module, page, target_id: str, path: Path) -> None:
    engine = workflow._locator_engine(module)
    if _target_mode(engine, target_id) == "absolute_position":
        try:
            with page.expect_file_chooser(timeout=10000) as chooser_info:
                if not engine.click(page, target_id, diagnose_on_failure=False):
                    raise RuntimeError(f"未能点击头像上传位置：{target_id}")
            chooser_info.value.set_files(str(path))
            return
        except Exception as exc:
            raise RuntimeError(f"绝对位置头像上传失败：{target_id}: {exc}") from exc

    locator = engine.resolve(page, target_id)
    if locator is None:
        raise RuntimeError(f"未能定位头像上传目标：{target_id}")
    try:
        tag_info = locator.evaluate(
            "(el) => ({tag:(el.tagName||'').toLowerCase(), type:el.getAttribute('type')||''})"
        ) or {}
    except Exception:
        tag_info = {}
    if str(tag_info.get("tag")) == "input" and str(tag_info.get("type")).lower() == "file":
        locator.set_input_files(str(path))
        return
    try:
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            locator.click(timeout=5000, force=True)
        chooser_info.value.set_files(str(path))
    except Exception as exc:
        raise RuntimeError(f"头像上传目标没有打开文件选择器：{target_id}: {exc}") from exc


def _skip_domain(state: dict[str, Any], domain: str, status: str) -> str:
    state.setdefault("skip_domains", {})[domain] = status
    return status


def _verify_folder(module, page) -> str:
    try:
        text = str(module.safe_page_text(page, limit=4000) or "").lower()
    except Exception:
        text = ""
    if (
        ("already" in text and ("added" in text or "joined" in text))
        or "已添加" in text
        or "已经添加" in text
    ):
        return "already_added"
    return "success"


def ensure_locator_click_support() -> None:
    import profile_behavior_workflow as workflow

    for key, label in STEP_LABELS.items():
        workflow.STEP_TYPES.setdefault(key, label)
    workflow.STEP_TYPE_LABELS = workflow.STEP_TYPES

    if getattr(workflow, "_wqtg_atomic_steps_installed", False):
        return

    original_normalize_config = workflow.normalize_config
    original_execute_step = workflow.execute_step
    original_domain_for = workflow.domain_for

    workflow.default_behaviors = atomic_default_behaviors

    def normalize_config(config):
        result = original_normalize_config(config)
        result["workflow_schema_version"] = 3
        result[workflow.CONFIG_KEY] = migrate_legacy_behaviors(
            result.get(workflow.CONFIG_KEY) or [],
            result,
        )
        return result

    def execute_step(module, page, item, state, config, stack):
        kind = str(item.get("type") or "")
        params = dict(item.get("params") or {})
        domain = str(params.get("domain") or "")
        skipped = state.get("skip_domains", {}).get(domain) if domain else None
        if skipped and kind not in {
            DATA_PREPARE_PHOTO,
            DATA_PREPARE_NAME,
            DATA_PREPARE_USERNAME,
            DATA_PREPARE_BIO,
            DATA_PREPARE_FOLDER,
        }:
            return skipped

        if kind == DATA_PREPARE_PHOTO:
            path = module.select_photo(config, state["account_index"], state["used_photos"])
            if path is None or not Path(path).exists():
                return _skip_domain(state, "photo", "skipped_no_photo")
            path = Path(path)
            state["photo_path"] = path
            state["used_photos"].add(path)
            return "success"

        if kind == DATA_PREPARE_NAME:
            selected = module.select_name(config)
            if selected is None:
                return _skip_domain(state, "name", "skipped_empty")
            state["first_name"], state["last_name"] = selected
            return "success"

        if kind == DATA_PREPARE_USERNAME:
            username = str(module.username_for_account(config, state["account_index"]) or "")
            if not username:
                return _skip_domain(state, "username", "skipped_empty")
            if hasattr(module, "validate_username") and not module.validate_username(username):
                return "invalid_username"
            state["username"] = username
            return "success"

        if kind == DATA_PREPARE_BIO:
            value = str(config.get("bio_text") or "")
            if not value.strip():
                return _skip_domain(state, "bio", "skipped_empty")
            state["bio_text"] = value
            return "success"

        if kind == DATA_PREPARE_FOLDER:
            value = str(config.get("chat_folder_link") or "").strip()
            if not value:
                return _skip_domain(state, "folder", "skipped_empty")
            if "t.me/addlist" not in value and "telegram.me/addlist" not in value:
                return "failed_invalid_link"
            state["folder_link"] = value
            return "success"

        if kind == LOCATOR_CLICK_TYPE:
            target_id = locator_target_for_step(str(stack[-1] if stack else "custom"), item)
            if not target_id or not workflow.locator_click(module, page, target_id):
                raise RuntimeError(f"未能点击定位目标：{target_id or item.get('id')}")
            return "success"

        if kind == LOCATOR_FILL_TYPE:
            target_id = locator_target_for_step(str(stack[-1] if stack else "custom"), item)
            value = _read_source(str(params.get("value_source") or ""), state, config)
            value = "" if value is None else str(value)
            if not value and bool(params.get("allow_empty", False)):
                return "skipped_empty"
            if not value:
                return _skip_domain(state, domain, "skipped_empty") if domain else "skipped_empty"
            _execute_fill(workflow, module, page, target_id, value, str(item.get("name") or "输入内容"))
            return "success"

        if kind == LOCATOR_UPLOAD_TYPE:
            target_id = locator_target_for_step(str(stack[-1] if stack else "custom"), item)
            value = _read_source(str(params.get("value_source") or "state.photo_path"), state, config)
            path = Path(value) if value else None
            if path is None or not path.exists():
                return _skip_domain(state, domain or "photo", "skipped_no_photo")
            _execute_upload(workflow, module, page, target_id, path)
            return "success"

        if kind == KEYBOARD_PRESS_TYPE:
            page.keyboard.press(str(params.get("key") or "Enter"))
            return "success"

        if kind == NAVIGATE_STATE_URL:
            url = str(_read_source(str(params.get("value_source") or ""), state, config) or "")
            if not url:
                return _skip_domain(state, domain, "skipped_empty") if domain else "skipped_empty"
            page.goto(url, wait_until="commit", timeout=20000)
            return "success"

        if kind == VERIFY_PHOTO:
            workflow.sleep(page, int(params.get("sync_wait_ms") or 15000))
            if hasattr(module, "wait_photo_save_ui_settled") and not module.wait_photo_save_ui_settled(
                page, timeout_ms=int(params.get("settle_timeout_ms") or 15000)
            ):
                raise RuntimeError("头像保存后页面没有稳定")
            return "success"

        if kind == VERIFY_NAME:
            workflow.sleep(page, int(params.get("wait_before_ms") or 15000))
            if hasattr(module, "wait_for_profile_name_applied") and not module.wait_for_profile_name_applied(
                page,
                str(state.get("first_name") or ""),
                str(state.get("last_name") or ""),
                timeout=int(params.get("timeout_ms") or 30000),
            ):
                raise RuntimeError("昵称保存后未检测到页面昵称变化")
            return "success"

        if kind == VERIFY_USERNAME:
            workflow.sleep(page, int(params.get("wait_before_ms") or 20000))
            if hasattr(module, "_profile_username_error_status"):
                error = module._profile_username_error_status(page)
                if error:
                    return str(error)
            if hasattr(module, "wait_for_username_applied") and not module.wait_for_username_applied(
                page,
                str(state.get("username") or ""),
                timeout=int(params.get("timeout_ms") or 15000),
            ):
                raise RuntimeError("用户名保存后未检测到页面用户名变化")
            return "success"

        if kind == VERIFY_BIO:
            workflow.sleep(page, int(params.get("wait_before_ms") or 20000))
            if hasattr(module, "wait_for_bio_applied") and not module.wait_for_bio_applied(
                page,
                str(state.get("bio_text") or ""),
                timeout=int(params.get("timeout_ms") or 15000),
            ):
                raise RuntimeError("签名保存后未检测到页面签名变化")
            return "success"

        if kind == VERIFY_FOLDER:
            return _verify_folder(module, page)

        return original_execute_step(module, page, item, state, config, stack)

    def domain_for(item):
        params = item.get("params") if isinstance(item, dict) and isinstance(item.get("params"), dict) else {}
        domain = str(params.get("domain") or "")
        return domain or original_domain_for(item)

    workflow.normalize_config = normalize_config
    workflow.execute_step = execute_step
    workflow.domain_for = domain_for
    workflow.normalize_workflow_config = normalize_config
    workflow._wqtg_atomic_steps_installed = True


STEP_TYPE_LABELS = STEP_LABELS
ensure_atomic_workflow_support = ensure_locator_click_support

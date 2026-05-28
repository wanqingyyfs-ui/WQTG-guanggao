from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from login_telegram_web import (
    detect_exit_ip_by_browser,
    detect_exit_ip_by_requests,
    dump_debug_html,
    get_telegram_page_state,
    is_telegram_logged_in_page,
    now_text,
    open_telegram_web_until_ready,
    read_account_proxy_map,
    restart_telegram_page_from_scratch,
    safe_page_text,
    split_phone_for_telegram,
    update_account_proxy_map_exit_ip,
    click_login_by_phone,
    fill_phone_number,
    click_next_after_phone,
    click_phone_confirm_modal_if_present,
    wait_after_phone_submit_transition,
    fill_current_code_page,
    fill_current_password_page,
)
from proxy_utils import parse_raw_proxy


SCRIPT_VERSION = "profile-maintenance-017-all-strict-retry"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = DATA_DIR / "profile_maintenance_config.json"
RESULTS_FILE = DATA_DIR / "profile_maintenance_results.csv"
FAILED_FILE = DATA_DIR / "profile_maintenance_failed.csv"

TELEGRAM_WEB_URL = "https://web.telegram.org/k/"

ACTIONS = {"status", "photo", "name", "username", "bio", "folder", "all"}
RESULT_HEADER = [
    "phone",
    "profile_dir",
    "masked_proxy",
    "action",
    "photo_status",
    "name_status",
    "username_status",
    "bio_status",
    "folder_status",
    "final_status",
    "note",
    "updated_at",
]
FAILED_HEADER = [
    "phone",
    "profile_dir",
    "masked_proxy",
    "action",
    "failed_steps",
    "unfinished_steps",
    "error_message",
    "updated_at",
]

DEFAULT_CONFIG = {
    "update_photo": True,
    "photo_mode": "random",
    "photo_library_dir": "assets/profile_photos",
    "update_name": True,
    "name_pool": [],
    "update_username": True,
    "username_keyword": "",
    "username_start_index": 1,
    "update_bio": True,
    "bio_text": "",
    "add_chat_folder": True,
    "chat_folder_link": "",
    "account_delay_ms": 3000,
    "stop_on_error": False,
}

STEP_STATUS_FIELDS = {
    "photo": "photo_status",
    "name": "name_status",
    "username": "username_status",
    "bio": "bio_status",
    "folder": "folder_status",
}

ADD_FOLDER_BUTTON_REGEX = re.compile(
    r"^(add|add folder|join|apply|save|done|ok|添加|添加文件夹|加入|保存|完成|确定)$",
    re.IGNORECASE,
)
SAVE_BUTTON_REGEX = re.compile(r"^(save|done|ok|confirm|保存|完成|确定|确认)$", re.IGNORECASE)
SETTINGS_TEXT_REGEX = re.compile(r"^(settings|设置)$", re.IGNORECASE)
EDIT_PROFILE_TEXT_REGEX = re.compile(r"^(edit profile|edit|编辑资料|编辑|修改资料)$", re.IGNORECASE)
SAVED_MESSAGES_REGEX = re.compile(r"^(saved messages|saved|收藏夹|已保存的消息|保存的消息)$", re.IGNORECASE)
PHOTO_TEXT_REGEX = re.compile(r"(change photo|set photo|upload photo|更换头像|上传头像|头像)", re.IGNORECASE)
MEDIA_EDITOR_FINISH_REGEX = re.compile(r"^(crop|apply|save|done|ok|确定|保存|完成|应用)$", re.IGNORECASE)
PHOTO_SYNC_WAIT_MS = 30000
PHOTO_VERIFY_TIMEOUT_MS = 60000
PHOTO_UPLOAD_MAX_ATTEMPTS = 2
NAME_SYNC_WAIT_MS = 15000
NAME_VERIFY_TIMEOUT_MS = 30000
PROFILE_FORM_SYNC_WAIT_MS = 20000
PROFILE_FORM_VERIFY_TIMEOUT_MS = 15000
PROFILE_FORM_MAX_ATTEMPTS = 2


def log(message: str) -> None:
    print(str(message or ""), flush=True)


def load_config() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        raw_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw_config = {}
    return normalize_config(raw_config)


def normalize_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config.update(dict(raw_config or {}))

    config["update_photo"] = bool(config.get("update_photo"))
    config["photo_mode"] = str(config.get("photo_mode") or "random").strip() or "random"
    if config["photo_mode"] not in {"random", "sequential", "unique_random"}:
        config["photo_mode"] = "random"
    config["photo_library_dir"] = str(config.get("photo_library_dir") or "assets/profile_photos").strip() or "assets/profile_photos"

    config["update_name"] = bool(config.get("update_name"))
    name_pool = config.get("name_pool") or []
    if isinstance(name_pool, str):
        name_pool = [line.strip() for line in normalize_newlines(name_pool).split("\n") if line.strip()]
    elif isinstance(name_pool, list | tuple):
        name_pool = [str(item or "").strip() for item in name_pool if str(item or "").strip()]
    else:
        name_pool = []
    config["name_pool"] = name_pool

    config["update_username"] = bool(config.get("update_username"))
    config["username_keyword"] = str(config.get("username_keyword") or "").strip()
    try:
        config["username_start_index"] = max(1, int(config.get("username_start_index") or 1))
    except Exception:
        config["username_start_index"] = 1

    config["update_bio"] = bool(config.get("update_bio"))
    config["bio_text"] = str(config.get("bio_text") or "")

    config["add_chat_folder"] = bool(config.get("add_chat_folder"))
    config["chat_folder_link"] = str(config.get("chat_folder_link") or "").strip()

    try:
        config["account_delay_ms"] = max(0, int(config.get("account_delay_ms") or 3000))
    except Exception:
        config["account_delay_ms"] = 3000
    config["stop_on_error"] = bool(config.get("stop_on_error"))
    return config


def normalize_newlines(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def append_csv_row(file_path: Path, header: list[str], row: dict[str, Any]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = file_path.exists() and file_path.stat().st_size > 0
    with file_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow({field: str(row.get(field, "") or "") for field in header})


def write_result(row: dict[str, Any]) -> None:
    append_csv_row(RESULTS_FILE, RESULT_HEADER, row)


def write_failed(row: dict[str, Any]) -> None:
    append_csv_row(FAILED_FILE, FAILED_HEADER, row)


def action_steps(action: str, config: dict[str, Any]) -> list[str]:
    if action == "status":
        return []
    if action in STEP_STATUS_FIELDS:
        return [action]

    steps: list[str] = []
    if config.get("update_photo"):
        steps.append("photo")
    if config.get("update_name"):
        steps.append("name")
    if config.get("update_username"):
        steps.append("username")
    if config.get("update_bio"):
        steps.append("bio")
    if config.get("add_chat_folder"):
        steps.append("folder")
    return steps


def safe_status_row(account: dict[str, str], action: str) -> dict[str, Any]:
    return {
        "phone": account.get("phone", ""),
        "profile_dir": account.get("profile_dir", ""),
        "masked_proxy": account.get("masked_proxy", ""),
        "action": action,
        "photo_status": "skipped",
        "name_status": "skipped",
        "username_status": "skipped",
        "bio_status": "skipped",
        "folder_status": "skipped",
        "final_status": "pending",
        "note": "",
        "updated_at": now_text(),
    }


def failed_steps_from_result(result_row: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for step, field in STEP_STATUS_FIELDS.items():
        value = str(result_row.get(field) or "")
        if value.startswith("failed") or value in {"username_taken", "invalid_username", "not_logged_in"}:
            failed.append(step)
    return failed


def unfinished_steps_from_result(result_row: dict[str, Any], steps: list[str]) -> list[str]:
    unfinished: list[str] = []
    for step in steps:
        field = STEP_STATUS_FIELDS[step]
        value = str(result_row.get(field) or "")
        if value in {"", "pending", "skipped"} or value.startswith("failed"):
            unfinished.append(step)
    return unfinished


def get_photo_files(config: dict[str, Any]) -> list[Path]:
    raw_dir = Path(str(config.get("photo_library_dir") or "assets/profile_photos"))
    photo_dir = raw_dir if raw_dir.is_absolute() else BASE_DIR / raw_dir
    if not photo_dir.exists():
        return []
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return [item for item in sorted(photo_dir.iterdir()) if item.is_file() and item.suffix.lower() in allowed]


def select_photo(config: dict[str, Any], account_index: int, used_photos: set[Path]) -> Path | None:
    photos = get_photo_files(config)
    if not photos:
        return None
    mode = str(config.get("photo_mode") or "random")
    if mode == "sequential":
        return photos[(account_index - 1) % len(photos)]
    if mode == "unique_random":
        available = [path for path in photos if path not in used_photos]
        if not available:
            available = photos
        return random.choice(available)
    return random.choice(photos)


def parse_name_line(line: str) -> tuple[str, str]:
    clean_line = str(line or "").strip()
    if "," in clean_line:
        first_name, last_name = clean_line.split(",", 1)
        return first_name.strip(), last_name.strip()
    if "，" in clean_line:
        first_name, last_name = clean_line.split("，", 1)
        return first_name.strip(), last_name.strip()
    return clean_line, ""


def select_name(config: dict[str, Any]) -> tuple[str, str] | None:
    name_pool = config.get("name_pool") or []
    clean_pool = [str(item or "").strip() for item in name_pool if str(item or "").strip()]
    if not clean_pool:
        return None
    return parse_name_line(random.choice(clean_pool))


def username_for_account(config: dict[str, Any], account_index: int) -> str:
    keyword = str(config.get("username_keyword") or "").strip()
    if not keyword:
        return ""
    start_index = int(config.get("username_start_index") or 1)
    return f"{keyword}{start_index + account_index - 1}"


def validate_username(username: str) -> bool:
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]{4,31}$", username or ""):
        return False
    if username.endswith("_"):
        return False
    return True


def click_first_visible(locators: list[Any], timeout: int = 3000, force: bool = False) -> bool:
    for locator in locators:
        try:
            count = locator.count()
        except Exception:
            count = 1
        for index in range(max(1, count)):
            try:
                item = locator.nth(index) if count > 1 else locator
                if not item.is_visible(timeout=timeout):
                    continue
                item.scroll_into_view_if_needed(timeout=timeout)
                item.click(timeout=timeout, force=force)
                return True
            except Exception:
                continue
    return False


def click_by_text(page, regex: re.Pattern, timeout: int = 3000) -> bool:
    return click_first_visible(
        [
            page.get_by_role("button", name=regex),
            page.get_by_role("link", name=regex),
            page.locator("button").filter(has_text=regex),
            page.locator("a").filter(has_text=regex),
            page.get_by_text(regex),
            page.locator(".btn-primary").filter(has_text=regex),
            page.locator(".MenuItem").filter(has_text=regex),
            page.locator(".row").filter(has_text=regex),
        ],
        timeout=timeout,
        force=True,
    )


def wait_after_click(page, ms: int = 1000) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def open_main_menu(page) -> bool:
    candidates = [
        page.locator("button[aria-label*='menu' i]"),
        page.locator("button[title*='menu' i]"),
        page.locator(".btn-menu"),
        page.locator("button.btn-icon"),
        page.locator(".sidebar-header button"),
        page.locator("#column-left button").first,
    ]
    if click_first_visible(candidates, timeout=2500, force=True):
        wait_after_click(page, 800)
        return True
    return False


def open_settings(page) -> bool:
    for attempt in range(1, 4):
        log(f"打开 Telegram 设置页尝试 {attempt}/3")
        if click_by_text(page, SETTINGS_TEXT_REGEX, timeout=2000):
            wait_after_click(page, 1200)
            return True
        open_main_menu(page)
        if click_by_text(page, SETTINGS_TEXT_REGEX, timeout=3000):
            wait_after_click(page, 1200)
            return True
        page.keyboard.press("Escape")
        wait_after_click(page, 700)
    dump_debug_html(page, "profile_open_settings_failed")
    return False


def open_edit_profile(page) -> bool:
    if click_by_text(page, EDIT_PROFILE_TEXT_REGEX, timeout=3000):
        wait_after_click(page, 1200)
        return True
    # 有些版本点击头像/资料区域会进入编辑资料
    if click_first_visible([
        page.locator(".profile-card"),
        page.locator(".settings-content .row").first,
        page.locator(".sidebar-content .row").first,
    ], timeout=2000, force=True):
        wait_after_click(page, 1000)
        if click_by_text(page, EDIT_PROFILE_TEXT_REGEX, timeout=2000):
            wait_after_click(page, 1000)
        return True
    return False


def open_profile_editor(page) -> None:
    if not open_settings(page):
        raise RuntimeError("未能打开 Telegram 设置页")
    open_edit_profile(page)


def field_score(info: dict[str, Any], labels: list[str]) -> int:
    text = " ".join(str(info.get(key) or "") for key in [
        "aria", "placeholder", "name", "id", "label_text", "wrapper_text", "parent_text", "outer_html"
    ]).lower()
    score = 0
    for label in labels:
        if label.lower() in text:
            score += 200
    if info.get("visible"):
        score += 50
    if str(info.get("contenteditable") or "").lower() == "true":
        score += 30
    tag = str(info.get("tag") or "").lower()
    if tag in {"input", "textarea"}:
        score += 30
    if "search" in text:
        score -= 300
    if "message" in text:
        score -= 200
    if "password" in text:
        score -= 500
    return score


def find_text_field(page, labels: list[str], timeout: int = 5000):
    deadline = time.time() + timeout / 1000
    selectors = [
        "input:not([type='hidden']):not([type='password'])",
        "textarea",
        "[contenteditable='true']",
        ".input-field-input",
    ]
    while time.time() < deadline:
        best = None
        best_score = -9999
        best_info = {}
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    visible = item.is_visible(timeout=300)
                    if not visible:
                        continue
                    info = item.evaluate(
                        """
                        (el) => {
                            const inputField = el.closest('.input-field');
                            const row = el.closest('.row');
                            const parent = el.parentElement;
                            const label = inputField ? inputField.querySelector('.input-field-label, label, [class*="label"]') : null;
                            return {
                                tag: (el.tagName || '').toLowerCase(),
                                type: el.getAttribute('type') || '',
                                id: el.getAttribute('id') || '',
                                name: el.getAttribute('name') || '',
                                aria: el.getAttribute('aria-label') || '',
                                placeholder: el.getAttribute('placeholder') || '',
                                contenteditable: el.getAttribute('contenteditable') || '',
                                className: el.getAttribute('class') || '',
                                label_text: label ? (label.innerText || label.textContent || '') : '',
                                wrapper_text: inputField ? (inputField.innerText || inputField.textContent || '') : '',
                                row_text: row ? (row.innerText || row.textContent || '') : '',
                                parent_text: parent ? (parent.innerText || parent.textContent || '') : '',
                                outer_html: el.outerHTML || '',
                                visible: true
                            };
                        }
                        """
                    ) or {}
                    score = field_score(info, labels)
                    if score > best_score:
                        best = item
                        best_score = score
                        best_info = info
                except Exception:
                    continue
        if best is not None and best_score > 0:
            log(f"已定位输入框：labels={labels} score={best_score} info={str(best_info)[:200]}")
            return best
        wait_after_click(page, 500)
    return None


def fill_text_field(page, locator, value: str, label: str) -> None:
    if locator is None:
        raise RuntimeError(f"未找到输入框：{label}")
    locator.wait_for(state="visible", timeout=10000)
    locator.scroll_into_view_if_needed(timeout=5000)
    locator.click(timeout=5000)
    wait_after_click(page, 200)
    try:
        locator.fill("", timeout=4000)
        locator.fill(value, timeout=8000)
    except Exception:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(value)
    wait_after_click(page, 500)
    try:
        current = locator.input_value(timeout=1000)
    except Exception:
        try:
            current = locator.evaluate("el => el.innerText || el.textContent || el.value || ''")
        except Exception:
            current = ""
    if str(value or "") and str(value or "") not in str(current or ""):
        locator.evaluate(
            """
            (el, value) => {
                el.focus();
                if (el.getAttribute('contenteditable') === 'true') {
                    el.innerText = value;
                    el.textContent = value;
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return;
                }
                const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                if (descriptor && descriptor.set) descriptor.set.call(el, value);
                else el.value = value;
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            value,
        )
        wait_after_click(page, 500)


def click_profile_save_button_multi(
    page,
    label: str = "资料保存按钮",
    max_clicks: int = 3,
    max_wait_seconds: int = 15,
) -> bool:
    """
    资料页保存按钮统一按“修改头像第二个保存按钮”的方式处理。

    只认这个固定按钮：
    button.btn-circle.btn-corner.z-depth-1.rp.is-visible

    并且按钮 HTML 里必须包含图标：
    

    不用 JS，不用文本模糊识别，不用坐标猜测。
    使用 Playwright 的 locator.click(force=True) 直接点这个按钮。
    """
    selectors = [
        "button.btn-circle.btn-corner.z-depth-1.rp.is-visible",
        "button.btn-circle.btn-corner.rp.is-visible",
        "button[class*='btn-circle'][class*='btn-corner'][class*='is-visible']",
    ]

    deadline = time.time() + max_wait_seconds
    clicked_count = 0
    last_error = ""

    while time.time() < deadline and clicked_count < max_clicks:
        clicked_this_round = False

        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception as e:
                last_error = str(e)
                continue

            for index in range(count):
                item = locator.nth(index)
                try:
                    box = item.bounding_box(timeout=800)
                    if not box:
                        continue

                    html = item.evaluate("(el) => el.outerHTML || ''") or ""
                    if "" not in str(html):
                        continue

                    try:
                        item.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass

                    item.click(timeout=5000, force=True)
                    clicked_count += 1
                    clicked_this_round = True
                    log(f"已点击{label}：selector={selector}, index={index}, click={clicked_count}/{max_clicks}")
                    wait_after_click(page, 1000)
                    break
                except Exception as e:
                    last_error = str(e)
                    continue

            if clicked_this_round:
                break

        if clicked_this_round:
            continue

        if clicked_count > 0:
            log(f"{label} 已点击过，当前保存按钮已消失，停止继续点击。")
            break

        wait_after_click(page, 800)

    if clicked_count > 0:
        log(f"{label} 多点确认完成，共点击 {clicked_count} 次。")
        return True

    log(f"15 秒内未找到{label}：button.btn-circle.btn-corner.z-depth-1.rp.is-visible / 图标 ，最后错误：{last_error}")
    return False


def click_save(page) -> bool:
    return click_profile_save_button_multi(
        page,
        label="资料保存按钮",
        max_clicks=3,
        max_wait_seconds=15,
    )


def update_name(page, first_name: str, last_name: str) -> str:
    fields = open_name_editor(page)
    first_field = fields[0] if fields else None
    if first_field is None:
        raise RuntimeError("未找到输入框：First Name")

    fill_profile_name_field(page, first_field, first_name, "First Name")

    if len(fields) >= 2:
        fill_profile_name_field(page, fields[1], last_name, "Last Name")
    elif str(last_name or "").strip():
        log("未找到 Last Name 输入框，本次只写入 First Name。")

    if not click_profile_name_save(page, timeout=12000):
        dump_debug_html(page, "profile_name_save_button_not_found")
        raise RuntimeError("修改昵称后未找到保存按钮")

    log(f"昵称保存后等待 {NAME_SYNC_WAIT_MS} 毫秒，让 Telegram Web 完成同步。")
    wait_after_click(page, NAME_SYNC_WAIT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    if wait_for_profile_name_applied(page, first_name, last_name, timeout=NAME_VERIFY_TIMEOUT_MS):
        log("已检测到昵称修改生效。")
        return "success"

    dump_debug_html(page, "profile_name_not_changed_after_save")
    raise RuntimeError("昵称保存后未检测到页面昵称变化")


def click_profile_form_save(page, action_label: str, timeout: int = 12000) -> bool:
    """点击 Telegram Web 资料编辑页右下角圆形保存按钮。"""
    deadline = time.time() + timeout / 1000
    save_icon_text = re.compile(r"()")
    while time.time() < deadline:
        save_buttons = [
            page.locator("button.btn-circle.btn-corner.z-depth-1.rp.is-visible:not(.profile-change-avatar)"),
            page.locator("button.btn-circle.btn-corner.z-depth-1.is-visible:not(.profile-change-avatar)"),
            page.locator(".settings-content button.btn-circle.btn-corner.z-depth-1.rp.is-visible").filter(has_text=save_icon_text),
            page.locator(".sidebar-content button.btn-circle.btn-corner.z-depth-1.rp.is-visible").filter(has_text=save_icon_text),
            page.locator("button[aria-label*='save' i]"),
            page.locator("button[aria-label*='done' i]"),
            page.locator("button[title*='save' i]"),
            page.locator("button[title*='done' i]"),
        ]
        if click_first_visible(save_buttons, timeout=1200, force=True):
            wait_after_click(page, 2500)
            log(f"已点击{action_label}保存按钮。")
            return True
        if click_by_text(page, SAVE_BUTTON_REGEX, timeout=1200):
            wait_after_click(page, 2500)
            log(f"已通过文字按钮保存{action_label}。")
            return True
        wait_after_click(page, 500)
    return False


def _visible_field_info(locator) -> dict[str, Any]:
    try:
        return locator.evaluate(
            """
            (el) => {
                const inputField = el.closest('.input-field');
                const inputWrapper = el.closest('.input-wrapper');
                const row = el.closest('.row');
                const parent = el.parentElement;
                const label = inputField ? inputField.querySelector('.input-field-label, label, [class*="label"]') : null;
                const rect = el.getBoundingClientRect();
                return {
                    tag: (el.tagName || '').toLowerCase(),
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    aria: el.getAttribute('aria-label') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    autocomplete: el.getAttribute('autocomplete') || '',
                    required: el.hasAttribute('required') ? '1' : '',
                    contenteditable: el.getAttribute('contenteditable') || '',
                    data_no_linebreaks: el.getAttribute('data-no-linebreaks') || '',
                    className: el.getAttribute('class') || '',
                    label_text: label ? (label.innerText || label.textContent || '') : '',
                    wrapper_text: inputWrapper ? (inputWrapper.innerText || inputWrapper.textContent || '') : '',
                    field_text: inputField ? (inputField.innerText || inputField.textContent || '') : '',
                    row_text: row ? (row.innerText || row.textContent || '') : '',
                    parent_text: parent ? (parent.innerText || parent.textContent || '') : '',
                    outer_html: (el.outerHTML || '').slice(0, 700),
                    visible: true,
                    top: rect.top || 0,
                    left: rect.left || 0,
                    width: rect.width || 0,
                    height: rect.height || 0
                };
            }
            """
        ) or {}
    except Exception:
        return {}


def _field_text_value(locator) -> str:
    try:
        return str(locator.input_value(timeout=1000) or "")
    except Exception:
        pass
    try:
        return str(locator.evaluate(
            """
            (el) => {
                if ('value' in el) return el.value || '';
                const parts = [];
                const walk = (node) => {
                    if (!node) return;
                    if (node.nodeType === Node.TEXT_NODE) {
                        parts.push(node.textContent || '');
                        return;
                    }
                    if (node.nodeType !== Node.ELEMENT_NODE) return;
                    const tag = String(node.tagName || '').toLowerCase();
                    if (tag === 'br') {
                        parts.push('\n');
                        return;
                    }
                    if (tag === 'img') {
                        parts.push(node.getAttribute('alt') || '');
                        return;
                    }
                    for (const child of node.childNodes) walk(child);
                };
                walk(el);
                return parts.join('').trim() || (el.innerText || el.textContent || '').trim();
            }
            """
        ) or "")
    except Exception:
        return ""


def _fill_profile_text_field(page, locator, value: str, label: str) -> None:
    clean_value = str(value or "")
    locator.wait_for(state="visible", timeout=10000)
    locator.scroll_into_view_if_needed(timeout=5000)
    locator.click(timeout=5000, force=True)
    wait_after_click(page, 300)
    try:
        locator.fill("", timeout=3000)
        locator.fill(clean_value, timeout=8000)
    except Exception:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        wait_after_click(page, 200)
        if clean_value:
            page.keyboard.insert_text(clean_value)
    wait_after_click(page, 500)

    current = _field_text_value(locator)
    if current.strip() != clean_value.strip():
        locator.evaluate(
            """
            (el, value) => {
                el.focus();
                if (el.getAttribute('contenteditable') === 'true') {
                    while (el.firstChild) el.removeChild(el.firstChild);
                    const lines = String(value || '').split('\n');
                    lines.forEach((line, index) => {
                        if (index > 0) el.appendChild(document.createElement('br'));
                        if (line) el.appendChild(document.createTextNode(line));
                    });
                    el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, inputType: 'insertText', data: value}));
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                    return;
                }
                const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                if (descriptor && descriptor.set) descriptor.set.call(el, value);
                else el.value = value;
                el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, inputType: 'insertText', data: value}));
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
            }
            """,
            clean_value,
        )
        wait_after_click(page, 500)

    current = _field_text_value(locator)
    if current.strip() != clean_value.strip():
        raise RuntimeError(f"{label} 输入后校验失败：期望={clean_value!r}，当前={current!r}")
    log(f"{label} 已写入：{clean_value!r}")


def _score_profile_field(info: dict[str, Any], target: str) -> int:
    text = " ".join(str(info.get(key) or "") for key in [
        "name", "id", "aria", "placeholder", "label_text", "wrapper_text", "field_text", "row_text", "parent_text", "outer_html"
    ]).lower()
    score = 0
    if info.get("visible"):
        score += 40
    tag = str(info.get("tag") or "").lower()
    if tag in {"input", "textarea"}:
        score += 50
    if str(info.get("contenteditable") or "").lower() == "true":
        score += 45
    if "input-field-input" in str(info.get("className") or ""):
        score += 45

    if target == "username":
        if str(info.get("name") or "").lower() == "username":
            score += 500
        for label in ("username", "user name", "用户名"):
            if label in text:
                score += 160
        for bad in ("first name", "last name", "bio", "about", "phone", "search", "message", "签名", "简介", "名字", "昵称"):
            if bad in text:
                score -= 300
    elif target == "bio":
        for label in ("bio", "about", "简介", "签名", "个人简介"):
            if label in text:
                score += 170
        for bad in ("username", "user name", "first name", "last name", "phone", "search", "message", "用户名", "名字", "昵称"):
            if bad in text:
                score -= 300
    return score


def find_profile_username_field(page, timeout: int = 6000):
    deadline = time.time() + timeout / 1000
    selectors = [
        "input[name='username']",
        ".input-field input[name='username']",
        "input.input-field-input[name='username']",
        "input.input-field-input[autocomplete='off']",
        "input[type='text'].input-field-input",
    ]
    while time.time() < deadline:
        best = None
        best_score = -9999
        best_info: dict[str, Any] = {}
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=300):
                        continue
                    info = _visible_field_info(item)
                    if float(info.get("width") or 0) < 20 or float(info.get("height") or 0) < 10:
                        continue
                    score = _score_profile_field(info, "username")
                    if score > best_score:
                        best = item
                        best_score = score
                        best_info = info
                except Exception:
                    continue
        if best is not None and best_score > 0:
            log(f"已定位用户名输入框：score={best_score} info={str(best_info)[:220]}")
            return best
        wait_after_click(page, 500)
    return None


def find_profile_bio_field(page, timeout: int = 6000):
    """定位 Telegram Web 资料编辑页里的签名 / Bio 输入框。

    现在 Telegram Web 的签名框在点击资料编辑按钮后，通常表现为：
        <div class="input-field-input" contenteditable="true" data-no-linebreaks="1">...</div>
    它不一定带明显的 Bio / About 文案，所以这里先找显式 bio/about 字段；找不到时，
    在资料编辑区域内优先选择位置更靠下的 contenteditable 输入框，避开 First Name / Username。
    """
    deadline = time.time() + timeout / 1000
    selectors = [
        "textarea[name='bio']",
        "textarea[name='about']",
        "input[name='bio']",
        "input[name='about']",
        ".input-wrapper .input-field .input-field-input[contenteditable='true'][data-no-linebreaks='1']",
        ".input-field .input-field-input[contenteditable='true'][data-no-linebreaks='1']",
        ".input-field-input[contenteditable='true'][data-no-linebreaks='1']",
        ".input-field textarea.input-field-input",
        "textarea.input-field-input",
        "[contenteditable='true'].input-field-input",
    ]
    while time.time() < deadline:
        candidates: list[tuple[int, float, int, Any, dict[str, Any]]] = []
        seen_keys: set[str] = set()
        for selector_index, selector in enumerate(selectors):
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=300):
                        continue
                    info = _visible_field_info(item)
                    width = float(info.get("width") or 0)
                    height = float(info.get("height") or 0)
                    if width < 20 or height < 10:
                        continue

                    key = f"{round(float(info.get('top') or 0))}:{round(float(info.get('left') or 0))}:{str(info.get('outer_html') or '')[:120]}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    text_blob = " ".join(str(info.get(key_name) or "") for key_name in [
                        "name", "id", "aria", "placeholder", "label_text", "wrapper_text", "field_text", "row_text", "parent_text", "outer_html"
                    ]).lower()
                    tag = str(info.get("tag") or "").lower()
                    name_attr = str(info.get("name") or "").lower()
                    contenteditable = str(info.get("contenteditable") or "").lower() == "true"
                    class_name = str(info.get("className") or "")
                    field_text = str(info.get("field_text") or "")
                    top = float(info.get("top") or 0)

                    score = _score_profile_field(info, "bio")

                    if name_attr in {"bio", "about"}:
                        score += 800
                    if contenteditable and "input-field-input" in class_name and str(info.get("data_no_linebreaks") or "") == "1":
                        score += 300
                    if tag == "textarea":
                        score += 260
                    if "bio" in text_blob or "about" in text_blob or "签名" in text_blob or "简介" in text_blob:
                        score += 500
                    if "t.me/" in field_text or "telegram.me/" in field_text or "@" in field_text or "http" in field_text:
                        score += 180

                    # 明确排除用户名输入框和昵称输入框。签名框经常没有 label，昵称框通常更靠上。
                    if name_attr == "username" or "username" in text_blob or "user name" in text_blob or "用户名" in text_blob:
                        score -= 1000
                    for bad in ("first name", "last name", "名字", "昵称", "姓名", "姓"):
                        if bad in text_blob:
                            score -= 650

                    # 当没有明显 label 时，签名框通常位于昵称框下方，因此给更靠下的候选一点权重。
                    if contenteditable and "input-field-input" in class_name:
                        score += int(min(max(top, 0), 1200) // 8)

                    if score <= 0:
                        continue
                    candidates.append((score, top, selector_index, item, info))
                except Exception:
                    continue
        if candidates:
            candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
            best_score, best_top, _selector_index, best, best_info = candidates[0]
            log(f"已定位签名输入框：score={best_score} top={best_top} info={str(best_info)[:260]}")
            return best
        wait_after_click(page, 500)
    return None

def open_profile_editor_for_field(page, finder, debug_label: str, timeout: int = 8000):
    deadline = time.time() + timeout / 1000
    field = finder(page, timeout=1000)
    if field is not None:
        return field

    if not open_settings(page):
        raise RuntimeError("未能打开 Telegram 设置页")

    field = finder(page, timeout=1200)
    if field is not None:
        return field

    if click_profile_edit_icon(page, timeout=8000):
        field = finder(page, timeout=6000)
        if field is not None:
            return field

    if open_edit_profile(page):
        field = finder(page, timeout=4000)
        if field is not None:
            return field
        if click_profile_edit_icon(page, timeout=4000):
            field = finder(page, timeout=4000)
            if field is not None:
                return field

    while time.time() < deadline:
        field = finder(page, timeout=1000)
        if field is not None:
            return field
        wait_after_click(page, 500)

    dump_debug_html(page, f"profile_{debug_label}_field_not_found")
    return None


def _profile_page_text_contains(page, expected: str) -> bool:
    expected_text = str(expected or "").strip()
    if not expected_text:
        return True
    visible_text = collect_profile_visible_text(page)
    return expected_text in visible_text


def wait_for_username_applied(page, username: str, timeout: int = PROFILE_FORM_VERIFY_TIMEOUT_MS) -> bool:
    expected = str(username or "").strip().lstrip("@")
    if not expected:
        return True
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        field = find_profile_username_field(page, timeout=800)
        if field is not None:
            current = _field_text_value(field).strip().lstrip("@")
            if current == expected:
                return True
        visible_text = collect_profile_visible_text(page)
        if expected in visible_text or f"@{expected}" in visible_text:
            return True
        wait_after_click(page, 1000)
    return False


def wait_for_bio_applied(page, bio_text: str, timeout: int = PROFILE_FORM_VERIFY_TIMEOUT_MS) -> bool:
    expected = str(bio_text or "").strip()
    if not expected:
        return True
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        field = find_profile_bio_field(page, timeout=800)
        if field is not None:
            current = _field_text_value(field).strip()
            if current == expected:
                return True
        if _profile_page_text_contains(page, expected):
            return True
        wait_after_click(page, 1000)
    return False


def _profile_username_error_status(page) -> str | None:
    text = safe_page_text(page, limit=5000).lower()
    if "already taken" in text or "username is taken" in text or "被占用" in text or "已被使用" in text:
        return "username_taken"
    if ("invalid" in text and "username" in text) or "用户名无效" in text or "无效的用户名" in text:
        return "invalid_username"
    return None


def update_username_once(page, username: str, attempt: int) -> str:
    field = open_profile_editor_for_field(
        page,
        find_profile_username_field,
        debug_label="username",
        timeout=14000,
    )
    if field is None:
        raise RuntimeError("未找到输入框：Username")

    log(f"用户名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS}：准备写入 {username!r}")
    _fill_profile_text_field(page, field, username, "Username")
    wait_after_click(page, 1200)

    error_status = _profile_username_error_status(page)
    if error_status:
        return error_status

    if not click_profile_form_save(page, "用户名", timeout=12000):
        dump_debug_html(page, f"profile_username_save_button_not_found_attempt_{attempt}")
        raise RuntimeError("修改用户名后未找到保存按钮")

    wait_after_click(page, 2000)
    error_status = _profile_username_error_status(page)
    if error_status:
        return error_status

    log(f"用户名第 {attempt} 次保存后等待 {PROFILE_FORM_SYNC_WAIT_MS} 毫秒，让 Telegram Web 完成同步。")
    wait_after_click(page, PROFILE_FORM_SYNC_WAIT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return "saved"


def update_username(page, username: str) -> str:
    if not username:
        return "skipped_empty"
    if not validate_username(username):
        return "invalid_username"

    last_error = ""
    for attempt in range(1, PROFILE_FORM_MAX_ATTEMPTS + 1):
        try:
            status = update_username_once(page, username, attempt)
            if status in {"username_taken", "invalid_username"}:
                return status
        except Exception as exc:
            last_error = str(exc)
            log(f"用户名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS} 失败：{last_error}")
            if attempt >= PROFILE_FORM_MAX_ATTEMPTS:
                raise
            wait_after_click(page, 3000)
            continue

        if wait_for_username_applied(page, username, timeout=PROFILE_FORM_VERIFY_TIMEOUT_MS):
            log(f"已检测到用户名修改生效。尝试次数：{attempt}")
            return "success"

        last_error = "用户名保存后未检测到页面用户名变化"
        log(
            f"用户名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS} 后仍未检测到变化，"
            "将继续使用同一个用户名再执行一次。"
        )
        dump_debug_html(page, f"profile_username_not_changed_after_save_attempt_{attempt}")
        wait_after_click(page, 3000)

    dump_debug_html(page, "profile_username_not_changed_after_two_attempts")
    raise RuntimeError(
        "用户名已使用同一个值连续执行 2 次写入和保存，但仍未检测到页面用户名变化，"
        f"最后状态：{last_error or '未检测到变化'}"
    )


def update_bio_once(page, bio_text: str, attempt: int) -> None:
    field = open_profile_editor_for_field(
        page,
        find_profile_bio_field,
        debug_label="bio",
        timeout=14000,
    )
    if field is None:
        raise RuntimeError("未找到输入框：Bio / About")

    log(f"签名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS}：准备写入统一签名。")
    _fill_profile_text_field(page, field, bio_text, "Bio / About")

    if not click_profile_form_save(page, "签名", timeout=12000):
        dump_debug_html(page, f"profile_bio_save_button_not_found_attempt_{attempt}")
        raise RuntimeError("修改签名后未找到保存按钮")

    log(f"签名第 {attempt} 次保存后等待 {PROFILE_FORM_SYNC_WAIT_MS} 毫秒，让 Telegram Web 完成同步。")
    wait_after_click(page, PROFILE_FORM_SYNC_WAIT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass


def update_bio(page, bio_text: str) -> str:
    if not str(bio_text or "").strip():
        return "skipped_empty"

    last_error = ""
    for attempt in range(1, PROFILE_FORM_MAX_ATTEMPTS + 1):
        try:
            update_bio_once(page, str(bio_text or ""), attempt)
        except Exception as exc:
            last_error = str(exc)
            log(f"签名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS} 失败：{last_error}")
            if attempt >= PROFILE_FORM_MAX_ATTEMPTS:
                raise
            wait_after_click(page, 3000)
            continue

        if wait_for_bio_applied(page, str(bio_text or ""), timeout=PROFILE_FORM_VERIFY_TIMEOUT_MS):
            log(f"已检测到签名修改生效。尝试次数：{attempt}")
            return "success"

        last_error = "签名保存后未检测到页面签名变化"
        log(
            f"签名修改尝试 {attempt}/{PROFILE_FORM_MAX_ATTEMPTS} 后仍未检测到变化，"
            "将继续使用同一个签名再执行一次。"
        )
        dump_debug_html(page, f"profile_bio_not_changed_after_save_attempt_{attempt}")
        wait_after_click(page, 3000)

    dump_debug_html(page, "profile_bio_not_changed_after_two_attempts")
    raise RuntimeError(
        "签名已使用同一个值连续执行 2 次写入和保存，但仍未检测到页面签名变化，"
        f"最后状态：{last_error or '未检测到变化'}"
    )


def avatar_upload_button_locators(page) -> list[Any]:
    return [
        page.locator("button.profile-change-avatar"),
        page.locator(".profile-change-avatar"),
        page.locator("button.btn-circle.profile-change-avatar"),
        page.locator("button[aria-label*='photo' i]"),
        page.locator("button[title*='photo' i]"),
        page.locator(".avatar-edit"),
        page.locator(".profile-photo"),
        page.get_by_text(PHOTO_TEXT_REGEX),
    ]


def find_file_input(page, timeout: int = 5000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        input_locator = page.locator("input[type='file']")
        try:
            count = input_locator.count()
        except Exception:
            count = 0
        if count > 0:
            try:
                return input_locator.last
            except Exception:
                return input_locator.first
        wait_after_click(page, 300)
    return None


def choose_profile_photo_file(page, photo_path: Path) -> None:
    clicked = False
    try:
        with page.expect_file_chooser(timeout=7000) as chooser_info:
            clicked = click_first_visible(
                avatar_upload_button_locators(page),
                timeout=5000,
                force=True,
            )
        chooser_info.value.set_files(str(photo_path))
        log(f"已通过头像按钮打开文件选择器并选择图片：{photo_path}")
        return
    except PlaywrightTimeoutError:
        log("点击头像按钮后未捕获原生文件选择器，改用 file input 方式上传。")
    except Exception as exc:
        log(f"头像文件选择器方式失败，改用 file input 方式上传：{exc}")

    if not clicked:
        clicked = click_first_visible(
            avatar_upload_button_locators(page),
            timeout=5000,
            force=True,
        )
        if clicked:
            wait_after_click(page, 1000)

    upload_input = find_file_input(page, timeout=7000)
    if upload_input is None:
        if clicked:
            raise RuntimeError("已点击头像修改按钮，但未找到头像 file input")
        raise RuntimeError("未找到头像上传入口")

    upload_input.set_input_files(str(photo_path))
    log(f"已通过头像 file input 选择图片：{photo_path}")


def click_media_editor_finish(page, timeout: int = 10000) -> bool:
    deadline = time.time() + timeout / 1000
    finish_locators = [
        page.locator(".media-editor__finish-button"),
        page.locator("div.media-editor__finish-button"),
        page.locator(".media-editor .media-editor__finish-button"),
        page.locator(".media-editor button[aria-label*='done' i]"),
        page.locator(".media-editor button[aria-label*='save' i]"),
        page.locator(".media-editor .btn-primary"),
        page.locator("button[aria-label*='done' i]"),
        page.locator("button[aria-label*='save' i]"),
    ]
    while time.time() < deadline:
        if click_first_visible(finish_locators, timeout=1200, force=True):
            wait_after_click(page, 2500)
            log("已点击头像裁剪/媒体编辑器完成按钮。")
            return True
        if click_by_text(page, MEDIA_EDITOR_FINISH_REGEX, timeout=1200):
            wait_after_click(page, 2500)
            log("已通过文字按钮完成头像裁剪/媒体编辑器确认。")
            return True
        wait_after_click(page, 500)
    return False


def get_avatar_fingerprint(page) -> str:
    try:
        fingerprint = page.evaluate(
            """
            () => {
                const items = [];
                const seen = new Set();
                const directSelectors = [
                    'button.profile-change-avatar',
                    '.profile-change-avatar',
                    '.profile-photo',
                    '.profile-avatar',
                    '.avatar',
                    '.Avatar',
                    '.profile-card',
                    '.settings-content img',
                    '.settings-content canvas',
                    '.sidebar-content img',
                    '.sidebar-content canvas'
                ];
                const addElement = (el) => {
                    if (!el || seen.has(el)) return;
                    seen.add(el);
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible = rect.width > 8
                        && rect.height > 8
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || 1) > 0;
                    if (!visible) return;

                    const className = String(el.className || '');
                    const text = [className, el.id || '', el.getAttribute('aria-label') || '', el.getAttribute('title') || ''].join(' ');
                    const image = el.tagName && el.tagName.toLowerCase() === 'img' ? el : el.querySelector('img');
                    const canvas = el.tagName && el.tagName.toLowerCase() === 'canvas' ? el : el.querySelector('canvas');
                    const src = image ? (image.currentSrc || image.src || image.getAttribute('src') || '') : '';
                    const backgroundImage = style.backgroundImage || '';
                    const canvasInfo = canvas ? `${canvas.width || 0}x${canvas.height || 0}` : '';
                    const looksLikeAvatar = /avatar|photo|profile|userpic/i.test(text) || Boolean(src) || Boolean(canvasInfo) || backgroundImage.includes('url(');
                    if (!looksLikeAvatar) return;

                    items.push({
                        tag: String(el.tagName || '').toLowerCase(),
                        className: className.slice(0, 120),
                        id: String(el.id || '').slice(0, 80),
                        aria: String(el.getAttribute('aria-label') || '').slice(0, 80),
                        title: String(el.getAttribute('title') || '').slice(0, 80),
                        src: src.slice(0, 300),
                        backgroundImage: backgroundImage.slice(0, 300),
                        canvasInfo,
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    });
                };

                for (const selector of directSelectors) {
                    for (const el of Array.from(document.querySelectorAll(selector))) {
                        addElement(el);
                    }
                }

                for (const el of Array.from(document.querySelectorAll('[class], img, canvas'))) {
                    const className = String(el.className || '');
                    if (/avatar|photo|profile-change-avatar|userpic/i.test(className)) {
                        addElement(el);
                    }
                }

                items.sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
                return JSON.stringify(items);
            }
            """
        )
        return str(fingerprint or "")
    except Exception as exc:
        log(f"读取头像页面指纹失败：{exc}")
        return ""


def is_media_editor_visible(page) -> bool:
    try:
        editor = page.locator(".media-editor")
        count = editor.count()
    except Exception:
        return False

    for index in range(count):
        try:
            if editor.nth(index).is_visible(timeout=300):
                return True
        except Exception:
            continue
    return False


def wait_media_editor_closed(page, timeout: int = 15000) -> bool:
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if not is_media_editor_visible(page):
            return True
        wait_after_click(page, 500)
    return False


def wait_for_avatar_changed(page, before_fingerprint: str, timeout: int = PHOTO_VERIFY_TIMEOUT_MS) -> tuple[bool, str]:
    deadline = time.time() + timeout / 1000
    last_fingerprint = ""
    while time.time() < deadline:
        current_fingerprint = get_avatar_fingerprint(page)
        if current_fingerprint:
            last_fingerprint = current_fingerprint
        if current_fingerprint and current_fingerprint != before_fingerprint:
            return True, current_fingerprint
        wait_after_click(page, 1000)
    return False, last_fingerprint


def update_photo_once(page, photo_path: Path, attempt: int) -> None:
    log(f"头像修改尝试 {attempt}/{PHOTO_UPLOAD_MAX_ATTEMPTS}：准备上传同一张图片：{photo_path}")
    open_profile_editor(page)
    choose_profile_photo_file(page, photo_path)
    wait_after_click(page, 3000)

    if not click_media_editor_finish(page, timeout=15000):
        dump_debug_html(page, f"profile_photo_finish_button_not_found_attempt_{attempt}")
        raise RuntimeError("未找到头像裁剪/媒体编辑器完成按钮")

    if not wait_media_editor_closed(page, timeout=30000):
        dump_debug_html(page, f"profile_photo_media_editor_not_closed_attempt_{attempt}")
        raise RuntimeError("点击头像完成按钮后，媒体编辑器没有关闭")

    log(f"头像第 {attempt} 次保存后等待 {PHOTO_SYNC_WAIT_MS} 毫秒，让 Telegram Web 完成上传和同步。")
    wait_after_click(page, PHOTO_SYNC_WAIT_MS)

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass


def visible_element_info(page, selector: str, timeout: int = 500) -> list[dict[str, Any]]:
    locator = page.locator(selector)
    result: list[dict[str, Any]] = []
    try:
        count = locator.count()
    except Exception:
        return result

    for index in range(count):
        item = locator.nth(index)
        try:
            if not item.is_visible(timeout=timeout):
                continue
            info = item.evaluate(
                """
                (el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        index,
                        text: el.innerText || el.textContent || '',
                        className: el.getAttribute('class') || '',
                        aria: el.getAttribute('aria-label') || '',
                        title: el.getAttribute('title') || '',
                        html: el.outerHTML || '',
                        top: rect.top,
                        right: rect.right,
                        width: rect.width,
                        height: rect.height,
                    };
                }
                """
            ) or {}
            info["index"] = index
            result.append(info)
        except Exception:
            continue
    return result


def click_profile_edit_icon_button(page) -> bool:
    """
    点击 Telegram 设置页右上角编辑按钮。

    用户提供的真实按钮：
    <button class="btn-icon rp">
      <span class="tgico button-icon"></span>
    </button>
    """
    candidates = [
        "button.btn-icon.rp",
        "button.btn-icon",
        ".btn-icon.rp",
        "button",
    ]

    for selector in candidates:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue

        # 优先点击包含  图标、并且位置靠右上的按钮。
        scored: list[tuple[int, int, Any]] = []
        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible(timeout=500):
                    continue
                info = item.evaluate(
                    """
                    (el) => {
                        const rect = el.getBoundingClientRect();
                        const text = el.innerText || el.textContent || '';
                        const html = el.outerHTML || '';
                        return {
                            text,
                            html,
                            top: rect.top,
                            right: rect.right,
                            width: rect.width,
                            height: rect.height,
                            aria: el.getAttribute('aria-label') || '',
                            title: el.getAttribute('title') || '',
                            className: el.getAttribute('class') || '',
                        };
                    }
                    """
                ) or {}
                text = str(info.get("text") or "")
                html = str(info.get("html") or "")
                aria = str(info.get("aria") or "").lower()
                title = str(info.get("title") or "").lower()
                class_name = str(info.get("className") or "")
                top = float(info.get("top") or 9999)
                right = float(info.get("right") or 0)
                score = 0

                if "" in text or "" in html:
                    score += 1000
                if "edit" in aria or "edit" in title or "编辑" in aria or "编辑" in title:
                    score += 500
                if "btn-icon" in class_name:
                    score += 100
                if top < 160:
                    score += 80
                if right > 800:
                    score += 60

                if score > 0:
                    scored.append((score, index, item))
            except Exception:
                continue

        for _score, _index, item in sorted(scored, key=lambda row: row[0], reverse=True):
            try:
                item.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            try:
                item.click(timeout=5000, force=True)
                wait_after_click(page, 1500)
                log(f"已点击资料页右上角编辑按钮：selector={selector}, index={_index}, score={_score}")
                return True
            except Exception:
                continue

    dump_debug_html(page, "profile_edit_icon_button_not_found")
    return False


def avatar_photo_fingerprint(page) -> str:
    try:
        data = page.evaluate(
            """
            () => {
                function visible(el) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return style
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                }

                const selectors = [
                    '.avatar.avatar-120 img.avatar-photo',
                    '.avatar-120 img.avatar-photo',
                    '.avatar.avatar-120',
                    '.avatar-120',
                    '.profile-content .avatar img',
                    '.settings-content .avatar img',
                    'img.avatar-photo'
                ];

                const pieces = [];
                for (const selector of selectors) {
                    for (const el of Array.from(document.querySelectorAll(selector))) {
                        if (!visible(el)) continue;
                        const img = el.matches('img') ? el : el.querySelector('img');
                        const rect = el.getBoundingClientRect();
                        pieces.push([
                            selector,
                            img ? (img.getAttribute('src') || '') : '',
                            el.getAttribute('data-peer-id') || '',
                            el.getAttribute('data-color') || '',
                            Math.round(rect.width),
                            Math.round(rect.height),
                            Math.round(rect.top),
                            Math.round(rect.left),
                            el.outerHTML.slice(0, 300)
                        ].join('|'));
                    }
                }
                return pieces.join('\\n');
            }
            """
        )
        return str(data or "")
    except Exception:
        return ""


def click_profile_avatar_for_upload(page, photo_path: Path) -> None:
    """
    在编辑资料页点击大头像位置触发上传。

    用户提供的真实头像区域：
    <div class="avatar avatar-like avatar-120 avatar-gradient avatar-placeholder" ...>
      <img class="avatar-photo" ...>
    </div>
    """
    avatar_selectors = [
        ".avatar.avatar-120",
        ".avatar-120",
        ".avatar.avatar-like.avatar-120",
        ".profile-content .avatar",
        ".settings-content .avatar",
        "img.avatar-photo",
    ]

    last_error = ""

    for selector in avatar_selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            avatar = locator.nth(index)
            try:
                if not avatar.is_visible(timeout=800):
                    continue

                avatar.scroll_into_view_if_needed(timeout=5000)
                wait_after_click(page, 300)

                try:
                    with page.expect_file_chooser(timeout=6000) as chooser_info:
                        avatar.click(timeout=5000, force=True)
                    file_chooser = chooser_info.value
                    file_chooser.set_files(str(photo_path))
                    log(f"已通过点击大头像触发文件选择器并上传：selector={selector}, index={index}")
                    wait_after_click(page, 2500)
                    return
                except PlaywrightTimeoutError:
                    log(f"点击大头像后未捕获原生文件选择器，检查 file input：selector={selector}, index={index}")
                except Exception as e:
                    last_error = str(e)
                    log(f"点击大头像触发上传出现临时错误，继续兜底：{e}")

                # 兜底：点击后如果 DOM 出现 file input，直接 set_input_files。
                try:
                    file_inputs = page.locator("input[type='file']")
                    file_input_count = file_inputs.count()
                except Exception:
                    file_input_count = 0

                for file_index in range(file_input_count - 1, -1, -1):
                    try:
                        file_input = file_inputs.nth(file_index)
                        file_input.set_input_files(str(photo_path))
                        log(f"已通过 input[type=file] 上传头像：file_input_index={file_index}")
                        wait_after_click(page, 2500)
                        return
                    except Exception as e:
                        last_error = str(e)
                        continue

                # 有些版本点击头像后先弹菜单，再选 Upload Photo。
                upload_text_regex = re.compile(
                    r"(upload photo|set photo|change photo|choose photo|select photo|上传头像|更换头像|选择照片|设置头像)",
                    re.IGNORECASE,
                )
                if click_by_text(page, upload_text_regex, timeout=2500):
                    wait_after_click(page, 800)
                    try:
                        with page.expect_file_chooser(timeout=6000) as chooser_info:
                            pass
                    except Exception:
                        pass

                    try:
                        file_inputs = page.locator("input[type='file']")
                        for file_index in range(file_inputs.count() - 1, -1, -1):
                            try:
                                file_inputs.nth(file_index).set_input_files(str(photo_path))
                                log(f"已通过头像菜单后的 file input 上传头像：file_input_index={file_index}")
                                wait_after_click(page, 2500)
                                return
                            except Exception as e:
                                last_error = str(e)
                                continue
                    except Exception as e:
                        last_error = str(e)

            except Exception as e:
                last_error = str(e)
                continue

    dump_debug_html(page, "profile_avatar_upload_entry_not_found")
    raise RuntimeError(f"未找到头像上传入口：已点击编辑按钮，但点击大头像无法上传。最后错误：{last_error}")


def click_photo_editor_finish_button(page) -> bool:
    """
    头像保存分两段：

    第一段：头像裁剪/媒体编辑器右下角保存按钮
        <div class="media-editor__finish-button rp">...</div>

    第二段：媒体编辑器保存后等待 3 秒，再点资料编辑页保存按钮
        <button class="btn-circle btn-corner z-depth-1 rp is-visible">
            <span class="tgico button-icon"></span>
        </button>

    等待上限：
    - 第一段按钮最多等 15 秒；
    - 第二段按钮最多等 15 秒；
    - 第二段保存按钮最多点 3 次。
    """
    first_save_selectors = [
        "div.media-editor__finish-button.rp",
        ".media-editor__finish-button.rp",
        "div.media-editor__finish-button",
        ".media-editor__finish-button",
        "div[class*='media-editor__finish-button']",
        "[class*='media-editor__finish-button']",
    ]

    second_save_selectors = [
        "button.btn-circle.btn-corner.z-depth-1.rp.is-visible",
        ".btn-circle.btn-corner.z-depth-1.rp.is-visible",
        "button.btn-circle.btn-corner.rp.is-visible",
        "button[class*='btn-circle'][class*='btn-corner'][class*='is-visible']",
    ]

    last_error = ""

    def is_editor_finish_visible() -> bool:
        try:
            locator = page.locator(".media-editor__finish-button")
            count = locator.count()
        except Exception:
            return False
        for index in range(count):
            try:
                if locator.nth(index).is_visible(timeout=200):
                    return True
            except Exception:
                continue
        return False

    def click_locator_by_selectors(selectors: list[str], label: str, max_wait_seconds: int, max_clicks: int) -> int:
        nonlocal last_error
        deadline = time.time() + max_wait_seconds
        clicked_count = 0

        while time.time() < deadline and clicked_count < max_clicks:
            clicked_this_round = False

            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    count = locator.count()
                except Exception as e:
                    last_error = str(e)
                    continue

                for index in range(count):
                    item = locator.nth(index)
                    try:
                        box = item.bounding_box(timeout=700)
                        if not box:
                            continue

                        html = ""
                        text = ""
                        try:
                            html = item.evaluate("(el) => el.outerHTML || ''") or ""
                            text = item.evaluate("(el) => el.innerText || el.textContent || ''") or ""
                        except Exception:
                            pass

                        # 第二段保存按钮必须包含  或者 btn-circle 保存样式；避免误点其它圆形按钮。
                        if label == "第二段资料保存按钮":
                            if (
                                "" not in html
                                and "btn-circle" not in html
                                and "is-visible" not in html
                                and "Save" not in text
                                and "Done" not in text
                                and "保存" not in text
                                and "完成" not in text
                            ):
                                continue

                        try:
                            item.scroll_into_view_if_needed(timeout=2000)
                        except Exception:
                            pass

                        item.click(timeout=4000, force=True)
                        clicked_count += 1
                        clicked_this_round = True
                        log(f"已点击{label}：selector={selector}, index={index}, click={clicked_count}/{max_clicks}")
                        wait_after_click(page, 900)
                        break
                    except Exception as e:
                        last_error = str(e)
                        continue

                if clicked_this_round:
                    break

            if clicked_this_round:
                continue

            wait_after_click(page, 1000)

        return clicked_count

    def js_click_first_save() -> bool:
        nonlocal last_error
        try:
            result = page.evaluate(
                """
                () => {
                    function visibleEnough(el) {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    }

                    const selectors = [
                        'div.media-editor__finish-button.rp',
                        '.media-editor__finish-button.rp',
                        'div.media-editor__finish-button',
                        '.media-editor__finish-button',
                        "div[class*='media-editor__finish-button']",
                        "[class*='media-editor__finish-button']"
                    ];

                    for (const selector of selectors) {
                        for (const el of Array.from(document.querySelectorAll(selector))) {
                            if (!visibleEnough(el)) continue;
                            el.scrollIntoView({block: 'center', inline: 'center'});
                            const rect = el.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;

                            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                                el.dispatchEvent(new MouseEvent(type, {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window,
                                    clientX: x,
                                    clientY: y,
                                    buttons: type.includes('down') ? 1 : 0
                                }));
                            }
                            if (typeof el.click === 'function') el.click();

                            return {ok: true, selector, x, y};
                        }
                    }
                    return {ok: false};
                }
                """
            ) or {}
            if result.get("ok"):
                log(f"已通过 JS 点击第一段媒体编辑器保存按钮：selector={result.get('selector')}")
                wait_after_click(page, 1200)
                return True
        except Exception as e:
            last_error = str(e)
        return False

    def click_bottom_right_fallback() -> bool:
        nonlocal last_error
        try:
            viewport = page.viewport_size or {"width": 1200, "height": 900}
            width = int(viewport.get("width") or 1200)
            height = int(viewport.get("height") or 900)
            for x, y in [(width - 58, height - 58), (width - 72, height - 72), (width - 90, height - 60)]:
                page.mouse.click(x, y)
                log(f"已按右下角坐标点击第一段媒体编辑器保存按钮兜底：x={x}, y={y}")
                wait_after_click(page, 900)
                if not is_editor_finish_visible():
                    return True
            return True
        except Exception as e:
            last_error = str(e)
            return False

    # 第一段：点击媒体编辑器完成按钮，最多等 15 秒。
    first_clicked = click_locator_by_selectors(
        first_save_selectors,
        "第一段媒体编辑器保存按钮",
        max_wait_seconds=15,
        max_clicks=2,
    )

    if first_clicked <= 0:
        if not js_click_first_save():
            click_bottom_right_fallback()

    if first_clicked <= 0 and is_editor_finish_visible():
        dump_debug_html(page, "profile_photo_first_finish_button_not_clicked")
        log(f"15 秒内未能点击第一段媒体编辑器保存按钮，最后错误：{last_error}")
        return False

    # 等媒体编辑器关闭/提交一下。
    wait_after_click(page, 3000)

    # 第二段：点击资料页保存按钮。用户明确要求点完第一段后延迟 3 秒再点这个按钮。
    second_clicked = click_locator_by_selectors(
        second_save_selectors,
        "第二段资料保存按钮",
        max_wait_seconds=15,
        max_clicks=3,
    )

    if second_clicked <= 0:
        # 有些版本第二段保存按钮可能瞬间消失，说明已经自动保存；这里不直接失败，先记录。
        log("未找到第二段资料保存按钮，可能已自动提交；继续后续保存完成判断。")
    else:
        log(f"第二段资料保存按钮已点击 {second_clicked} 次。")
        click_profile_save_button_multi(page, "资料保存按钮", max_clicks=3, max_wait_seconds=15)

    return True

def wait_photo_save_ui_settled(page, timeout_ms: int = 15000) -> bool:
    """
    不再用头像 src/blob 指纹判断是否换成功。
    最多等 15 秒，只确认媒体编辑器关闭并回到资料/设置界面。
    """
    deadline = time.time() + timeout_ms / 1000

    while time.time() < deadline:
        wait_after_click(page, 1000)

        try:
            editor_count = page.locator(".media-editor__finish-button").count()
        except Exception:
            editor_count = 0

        editor_visible = False
        for index in range(editor_count):
            try:
                if page.locator(".media-editor__finish-button").nth(index).is_visible(timeout=200):
                    editor_visible = True
                    break
            except Exception:
                continue

        if editor_visible:
            log("头像保存后媒体编辑器仍在，继续等待，最多 15 秒。")
            continue

        ui_selectors = [
            ".avatar.avatar-120",
            ".avatar-120",
            ".profile-content",
            ".settings-content",
            ".sidebar-content",
            "button.btn-icon.rp",
        ]
        for selector in ui_selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    if locator.nth(index).is_visible(timeout=300):
                        log(f"头像保存后页面已回到资料/设置界面：selector={selector}, index={index}")
                        return True
                except Exception:
                    continue

        log("头像媒体编辑器已关闭，但资料页面还未稳定，继续等待，最多 15 秒。")

    dump_debug_html(page, "profile_photo_save_ui_not_settled")
    return False

def update_photo_once_by_edit_avatar(page, photo_path: Path, attempt: int) -> None:
    log(f"头像修改尝试 {attempt}/2：先进入设置页，再点右上角编辑按钮，再点大头像上传。")
    if not open_settings(page):
        raise RuntimeError("未能打开 Telegram 设置页")

    if not click_profile_edit_icon_button(page):
        raise RuntimeError("未找到右上角资料编辑按钮：button.btn-icon.rp / 图标 ")

    wait_after_click(page, 1200)
    click_profile_avatar_for_upload(page, photo_path)

    if not click_photo_editor_finish_button(page):
        dump_debug_html(page, f"profile_photo_finish_button_not_found_attempt_{attempt}")
        raise RuntimeError("头像上传后 15 秒内未找到/未能点击右下角媒体编辑器保存按钮")

    log("头像两段保存按钮已处理，等待 Telegram Web 上传和同步 15 秒。")
    wait_after_click(page, 15000)

    if not wait_photo_save_ui_settled(page, timeout_ms=15000):
        raise RuntimeError("头像保存后 15 秒内页面没有回到资料/设置界面，无法确认保存动作完成")

    log("头像保存动作已完成：媒体编辑器关闭，页面已回到资料/设置界面。")

def update_photo(page, photo_path: Path) -> str:
    if photo_path is None or not photo_path.exists():
        return "skipped_no_photo"

    last_error = ""
    for attempt in range(1, 3):
        try:
            log(f"头像修改尝试 {attempt}/2：准备上传同一张图片：{photo_path}")
            update_photo_once_by_edit_avatar(page, photo_path, attempt)
            return "success"
        except Exception as e:
            last_error = str(e)
            log(f"头像修改尝试 {attempt}/2 失败：{last_error}")
            try:
                page.keyboard.press("Escape")
                wait_after_click(page, 1000)
            except Exception:
                pass

    dump_debug_html(page, "profile_photo_failed")
    raise RuntimeError(last_error or "未找到头像上传入口")

def open_saved_messages(page) -> bool:
    # 先尝试页面上已经可见的入口。
    if click_saved_messages_menu_item(page, timeout=2000):
        return True

    if click_by_text(page, SAVED_MESSAGES_REGEX, timeout=1800):
        wait_after_click(page, 1500)
        return True

    # 收藏夹菜单项默认是隐藏的，先打开 Telegram 左侧主菜单再找。
    for attempt in range(1, 4):
        log(f"打开 Saved Messages / 收藏夹尝试 {attempt}/3")
        open_main_menu(page)
        wait_after_click(page, 700)
        if click_saved_messages_menu_item(page, timeout=3500):
            return True
        page.keyboard.press("Escape")
        wait_after_click(page, 500)

    # 兜底：使用搜索进入 Saved Messages。
    search_selectors = [
        page.locator("input[type='search']"),
        page.locator("input[placeholder*='Search' i]"),
        page.locator(".input-search input"),
        page.locator("[contenteditable='true'][data-placeholder*='Search' i]"),
        page.locator("[contenteditable='true'][aria-label*='Search' i]"),
    ]
    for locator in search_selectors:
        try:
            count = locator.count()
        except Exception:
            continue
        if count <= 0:
            continue
        try:
            item = locator.first
            item.click(timeout=3000)
            wait_after_click(page, 300)
            try:
                item.fill("Saved Messages", timeout=3000)
            except Exception:
                page.keyboard.press("Control+A")
                page.keyboard.insert_text("Saved Messages")
            wait_after_click(page, 1800)
            if click_saved_messages_menu_item(page, timeout=2500):
                return True
            if click_by_text(page, SAVED_MESSAGES_REGEX, timeout=4000):
                wait_after_click(page, 1500)
                return True
        except Exception:
            continue
    dump_debug_html(page, "open_saved_messages_failed")
    return False

def find_message_box(page):
    selectors = [
        "[contenteditable='true'][data-placeholder*='Message' i]",
        "[contenteditable='true'][aria-label*='Message' i]",
        ".input-message-input[contenteditable='true']",
        ".input-message-container [contenteditable='true']",
        "div[contenteditable='true']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=800):
                    return item
            except Exception:
                continue
    return None


def send_message_to_current_chat(page, text: str) -> None:
    box = find_message_box(page)
    if box is None:
        raise RuntimeError("未找到收藏夹消息输入框")
    box.click(timeout=5000)
    wait_after_click(page, 300)
    page.keyboard.insert_text(text)
    wait_after_click(page, 300)
    page.keyboard.press("Enter")
    wait_after_click(page, 2500)


def click_latest_folder_link(page, link: str) -> bool:
    escaped_link = re.escape(link)
    candidates = [
        page.get_by_text(re.compile(escaped_link)),
        page.locator("a").filter(has_text=re.compile(escaped_link)),
        page.locator(f"a[href='{link}']"),
        page.locator(".message").filter(has_text=re.compile(escaped_link)),
        page.locator(".bubble").filter(has_text=re.compile(escaped_link)),
    ]
    if click_first_visible(candidates, timeout=5000, force=True):
        wait_after_click(page, 3000)
        return True
    return False


def add_chat_folder(page, link: str) -> str:
    if not link:
        return "skipped_empty"
    if "t.me/addlist" not in link and "telegram.me/addlist" not in link:
        return "failed_invalid_link"

    if not open_saved_messages(page):
        raise RuntimeError("未能打开 Saved Messages / 收藏夹")
    send_message_to_current_chat(page, link)
    if not click_latest_folder_link(page, link):
        # 兜底：直接打开链接，仍然使用当前已登录浏览器上下文和代理。
        page.goto(link, wait_until="commit", timeout=15000)
        wait_after_click(page, 5000)

    text = safe_page_text(page, limit=4000).lower()
    if "already" in text and ("added" in text or "joined" in text):
        return "already_added"
    if "已添加" in text or "已经添加" in text:
        return "already_added"

    if click_by_text(page, ADD_FOLDER_BUTTON_REGEX, timeout=8000):
        wait_after_click(page, 3000)
        text = safe_page_text(page, limit=4000).lower()
        if "already" in text and ("added" in text or "joined" in text):
            return "already_added"
        return "success"

    dump_debug_html(page, "add_chat_folder_button_not_found")
    raise RuntimeError("未找到添加分组文件夹按钮")


def ensure_logged_in_without_mytelegram(page, account: dict[str, str]) -> bool:
    page = open_telegram_web_until_ready(page, max_page_reopens=3)
    if is_telegram_logged_in_page(page, timeout=1500):
        log("当前 Telegram Web 已登录，跳过登录流程。")
        return True

    handled_phone = False
    handled_code = False
    restart_count = 0
    deadline = time.time() + 300

    while time.time() < deadline:
        state = get_telegram_page_state(page)
        log(f"当前 Telegram 页面状态：{state}")

        if state == "logged_in":
            return True

        if state == "phone_entry":
            click_login_by_phone(page)
            wait_after_click(page, 1200)
            continue

        if state == "phone":
            if not handled_phone:
                fill_phone_number(page, account["telegram_phone"], account.get("country", ""))
                if get_telegram_page_state(page) == "phone":
                    click_next_after_phone(page)
                    click_phone_confirm_modal_if_present(page)
                    handled_phone = True
            next_state = wait_after_phone_submit_transition(
                page,
                checks_per_round=12,
                max_refresh_rounds=3,
                interval_ms=3000,
            )
            if next_state == "restart":
                restart_count += 1
                if restart_count > 3:
                    raise RuntimeError("手机号提交后多次重新打开仍未进入验证码/已登录状态")
                page = restart_telegram_page_from_scratch(page, label="资料维护登录手机号提交后重新打开")
                handled_phone = False
                handled_code = False
            continue

        if state == "code":
            if handled_code:
                wait_after_click(page, 2000)
                handled_code = False
                continue
            next_state = fill_current_code_page(page, account.get("yanzheng", ""))
            handled_code = True
            if next_state == "restart":
                restart_count += 1
                if restart_count > 3:
                    raise RuntimeError("验证码提交后多次重新打开仍未登录")
                page = restart_telegram_page_from_scratch(page, label="资料维护验证码提交后重新打开")
                handled_phone = False
                handled_code = False
            continue

        if state == "password":
            next_state = fill_current_password_page(page, account.get("yanzheng", ""))
            if next_state == "logged_in":
                return True
            if next_state == "restart":
                restart_count += 1
                if restart_count > 3:
                    raise RuntimeError("2FA 提交后多次重新打开仍未登录")
                page = restart_telegram_page_from_scratch(page, label="资料维护 2FA 提交后重新打开")
                handled_phone = False
                handled_code = False
            continue

        if state == "blank_or_error":
            restart_count += 1
            if restart_count > 3:
                return False
            page = restart_telegram_page_from_scratch(page, label="资料维护空白页重新打开")
            continue

        if click_login_by_phone(page):
            wait_after_click(page, 2000)
            continue
        wait_after_click(page, 1500)

    return False


def launch_context_for_account(playwright, account: dict[str, str]):
    parsed_proxy = parse_raw_proxy(account["raw_proxy"])
    profile_dir = BASE_DIR / account["profile_dir"]
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        proxy=parsed_proxy.playwright_proxy,
        viewport={"width": 1200, "height": 900},
    )
    return context, parsed_proxy


def verify_proxy_before_browser(account: dict[str, str], parsed_proxy) -> tuple[bool, str, str]:
    log("正在实时检测代理出口 IP...")
    ok, realtime_ip, error = detect_exit_ip_by_requests(parsed_proxy)
    if not ok:
        return False, "", f"proxy_check_failed: {error}"
    log(f"实时出口 IP：{realtime_ip}")
    return True, realtime_ip, ""


def verify_browser_proxy(context, account: dict[str, str], realtime_ip: str) -> tuple[bool, str, str]:
    check_page = context.new_page()
    try:
        browser_ok, browser_ip, browser_error = detect_exit_ip_by_browser(check_page)
    finally:
        try:
            check_page.close()
        except Exception:
            pass

    if not browser_ok:
        return False, "", f"browser_proxy_check_failed: {browser_error}"

    log(f"浏览器出口 IP：{browser_ip}")
    if browser_ip != realtime_ip:
        log("动态轮换代理模式：requests 出口 IP 与浏览器出口 IP 不一致，允许继续。")
        log(f"requests={realtime_ip}, browser={browser_ip}")

    if account.get("exit_ip") != browser_ip:
        update_account_proxy_map_exit_ip(account["phone"], browser_ip)

    return True, browser_ip, ""


def execute_step(page, step: str, config: dict[str, Any], account: dict[str, str], account_index: int, used_photos: set[Path]) -> str:
    if step == "photo":
        photo_path = select_photo(config, account_index, used_photos)
        if photo_path is not None:
            used_photos.add(photo_path)
        return update_photo(page, photo_path)

    if step == "name":
        selected_name = select_name(config)
        if selected_name is None:
            return "skipped_empty"
        first_name, last_name = selected_name
        return update_name(page, first_name, last_name)

    if step == "username":
        username = username_for_account(config, account_index)
        return update_username(page, username)

    if step == "bio":
        return update_bio(page, str(config.get("bio_text") or ""))

    if step == "folder":
        return add_chat_folder(page, str(config.get("chat_folder_link") or ""))

    return "skipped_unknown_step"


def process_account(action: str, config: dict[str, Any], account: dict[str, str], account_index: int, total: int, used_photos: set[Path]) -> dict[str, Any]:
    result_row = safe_status_row(account, action)
    steps = action_steps(action, config)
    note_parts: list[str] = []

    log("-" * 80)
    log(f"资料维护脚本版本：{SCRIPT_VERSION}")
    log(f"开始处理账号 {account_index}/{total}：{account.get('phone', '')}")
    log(f"Profile：{account.get('profile_dir', '')}")
    log(f"代理：{account.get('masked_proxy', '')}")
    log(f"动作：{action}，步骤：{steps or ['status']}")
    log("-" * 80)

    parsed_proxy = parse_raw_proxy(account["raw_proxy"])
    result_row["masked_proxy"] = parsed_proxy.masked_raw_proxy

    ok, realtime_ip, error = verify_proxy_before_browser(account, parsed_proxy)
    if not ok:
        result_row["final_status"] = "failed"
        result_row["note"] = error
        return result_row

    with sync_playwright() as playwright:
        context = None
        try:
            context, _ = launch_context_for_account(playwright, account)
            ok, browser_ip, error = verify_browser_proxy(context, account, realtime_ip)
            if not ok:
                result_row["final_status"] = "failed"
                result_row["note"] = error
                return result_row

            telegram_page = context.new_page()
            try:
                logged_in = ensure_logged_in_without_mytelegram(telegram_page, account)
            except Exception as exc:
                dump_debug_html(telegram_page, "profile_maintenance_login_failed")
                raise RuntimeError(f"login_failed: {exc}") from exc

            if not logged_in:
                result_row["final_status"] = "not_logged_in"
                result_row["note"] = "Telegram Web 未登录，自动登录失败"
                for step in steps:
                    result_row[STEP_STATUS_FIELDS[step]] = "not_logged_in"
                return result_row

            if action == "status":
                result_row["final_status"] = "success"
                result_row["note"] = f"logged_in，browser_ip={browser_ip}"
                return result_row

            for step in steps:
                field = STEP_STATUS_FIELDS[step]
                try:
                    status = execute_step(telegram_page, step, config, account, account_index, used_photos)
                    result_row[field] = status
                    log(f"账号 {account.get('phone', '')} 步骤 {step} 完成：{status}")
                except Exception as exc:
                    error_text = str(exc)
                    result_row[field] = f"failed: {error_text}"
                    note_parts.append(f"{step}: {error_text}")
                    try:
                        dump_debug_html(telegram_page, f"profile_{step}_failed")
                    except Exception:
                        pass
                    log(f"账号 {account.get('phone', '')} 步骤 {step} 失败：{error_text}")

            failed = failed_steps_from_result(result_row)
            if failed:
                result_row["final_status"] = "partial_failed" if len(failed) < len(steps) else "failed"
            else:
                result_row["final_status"] = "success"
            result_row["note"] = " | ".join(note_parts) if note_parts else "完成"
            return result_row
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram 账号资料维护")
    parser.add_argument("--action", choices=sorted(ACTIONS), default="status")
    args = parser.parse_args()

    action = str(args.action or "status").strip().lower()
    config = load_config()
    rows = read_account_proxy_map()
    total = len(rows)
    used_photos: set[Path] = set()

    log("=" * 80)
    log(f"账号资料维护开始：动作={action}，账号数={total}")
    log(f"配置文件：{CONFIG_FILE}")
    log(f"结果文件：{RESULTS_FILE}")
    log(f"失败文件：{FAILED_FILE}")
    log("=" * 80)

    success_count = 0
    failed_count = 0

    for index, account in enumerate(rows, start=1):
        try:
            # 补齐 phone 拆分字段，兼容 account_proxy_map.csv 的原始行。
            telegram_phone, country_code, national_number = split_phone_for_telegram(
                account.get("phone", ""),
                account.get("country", ""),
            )
            account["telegram_phone"] = telegram_phone
            account["country_code"] = country_code
            account["national_number"] = national_number

            result_row = process_account(action, config, account, index, total, used_photos)
        except Exception as exc:
            result_row = safe_status_row(account, action)
            result_row["final_status"] = "failed"
            result_row["note"] = f"batch_unhandled_error: {exc}"
            log(f"账号 {account.get('phone', '')} 出现未捕获错误：{exc}")

        result_row["updated_at"] = now_text()
        write_result(result_row)

        steps = action_steps(action, config)
        failed = failed_steps_from_result(result_row)
        unfinished = unfinished_steps_from_result(result_row, steps)
        final_status = str(result_row.get("final_status") or "")

        if final_status == "success":
            success_count += 1
            log(f"账号 {account.get('phone', '')} 资料维护成功。")
        else:
            failed_count += 1
            write_failed({
                "phone": result_row.get("phone", ""),
                "profile_dir": result_row.get("profile_dir", ""),
                "masked_proxy": result_row.get("masked_proxy", ""),
                "action": action,
                "failed_steps": ";".join(failed),
                "unfinished_steps": ";".join(unfinished),
                "error_message": result_row.get("note", ""),
                "updated_at": now_text(),
            })
            log(f"账号 {account.get('phone', '')} 资料维护未完全成功：{final_status}，{result_row.get('note', '')}")
            if config.get("stop_on_error"):
                log("配置为遇到账号错误后停止全部流程，当前流程结束。")
                break

        if index < total:
            delay_ms = int(config.get("account_delay_ms") or 3000)
            log(f"等待 {delay_ms} 毫秒后处理下一个账号。")
            time.sleep(delay_ms / 1000)

    log("=" * 80)
    log(f"账号资料维护结束：成功 {success_count} 个，未完全成功 {failed_count} 个，总计 {total} 个。")
    log("=" * 80)
    return 0









# ===== profile maintenance final override v15 begin =====
def _v15_sleep(page, ms: int = 1500) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def _v15_click_exact_icon_button(
    page,
    button_selector: str,
    icon_text: str,
    label: str,
    max_clicks: int = 1,
    max_wait_seconds: int = 15,
) -> bool:
    """
    固定按钮点击：
    - 不用 JS
    - 不用坐标
    - 不用文本模糊识别
    - 只用 Playwright locator.click(force=True)
    - 每次点击后延迟，给 Telegram Web 反应时间
    """
    deadline = time.time() + max_wait_seconds
    clicked_count = 0
    last_error = ""

    while time.time() < deadline and clicked_count < max_clicks:
        clicked_this_round = False

        try:
            locator = page.locator(button_selector)
            count = locator.count()
        except Exception as e:
            last_error = str(e)
            _v15_sleep(page, 800)
            continue

        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible(timeout=800):
                    continue

                if icon_text:
                    try:
                        icon_count = item.locator("span.tgico.button-icon").filter(has_text=icon_text).count()
                    except Exception:
                        icon_count = 0
                    if icon_count <= 0:
                        continue

                try:
                    item.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass

                _v15_sleep(page, 500)
                item.click(timeout=6000, force=True)
                clicked_count += 1
                clicked_this_round = True
                log(f"已点击{label}：selector={button_selector}, index={index}, click={clicked_count}/{max_clicks}")
                _v15_sleep(page, 1800)
                break
            except Exception as e:
                last_error = str(e)
                continue

        if clicked_this_round:
            continue

        if clicked_count > 0:
            log(f"{label} 已点击过，当前按钮已消失，停止继续点击。")
            break

        _v15_sleep(page, 1000)

    if clicked_count > 0:
        log(f"{label} 点击完成，共点击 {clicked_count} 次。")
        return True

    log(f"未点到{label}：{button_selector} / {icon_text}，最后错误：{last_error}")
    return False


def _v15_click_edit_button(page, label: str = "资料编辑按钮") -> bool:
    return _v15_click_exact_icon_button(
        page,
        "button.btn-icon.rp",
        "",
        label,
        max_clicks=1,
        max_wait_seconds=15,
    )


def _v15_click_save_button(page, label: str = "资料保存按钮") -> bool:
    return _v15_click_exact_icon_button(
        page,
        "button.btn-circle.btn-corner.z-depth-1.rp.is-visible",
        "",
        label,
        max_clicks=3,
        max_wait_seconds=15,
    )


def click_profile_save_button_multi(page, label: str = "资料保存按钮", max_clicks: int = 3, max_wait_seconds: int = 15) -> bool:
    return _v15_click_exact_icon_button(
        page,
        "button.btn-circle.btn-corner.z-depth-1.rp.is-visible",
        "",
        label,
        max_clicks=max_clicks,
        max_wait_seconds=max_wait_seconds,
    )


def click_save(page) -> bool:
    return _v15_click_save_button(page, "资料保存按钮")


def click_name_save_button(page, *args, **kwargs) -> bool:
    return _v15_click_save_button(page, "昵称保存按钮")


def click_username_save_button(page, *args, **kwargs) -> bool:
    return _v15_click_save_button(page, "用户名保存按钮")


def click_bio_save_button(page, *args, **kwargs) -> bool:
    return _v15_click_save_button(page, "签名保存按钮")


def _v15_open_profile_edit_page(page, label: str = "资料编辑页") -> None:
    if not open_settings(page):
        raise RuntimeError("未能打开 Telegram 设置页")

    _v15_sleep(page, 1500)

    if not _v15_click_edit_button(page, label):
        raise RuntimeError(f"未能点击{label}入口：button.btn-icon.rp / 图标 ")

    _v15_sleep(page, 2000)


def _v15_fill_contenteditable(page, field, value: str, label: str) -> None:
    field.wait_for(state="visible", timeout=10000)
    field.scroll_into_view_if_needed(timeout=5000)
    _v15_sleep(page, 500)
    field.click(timeout=6000, force=True)
    _v15_sleep(page, 600)

    page.keyboard.press("Control+A")
    _v15_sleep(page, 300)
    page.keyboard.press("Backspace")
    _v15_sleep(page, 300)

    if value:
        page.keyboard.insert_text(value)

    _v15_sleep(page, 1200)

    try:
        current = field.evaluate("el => el.innerText || el.textContent || ''")
    except Exception:
        current = ""

    if str(value or "") and str(value or "") not in str(current or ""):
        raise RuntimeError(f"{label} 写入后校验失败，目标={value!r}，当前={current!r}")

    log(f"{label} 已写入：{value!r}")


def _v15_find_name_fields(page):
    """
    昵称编辑页里的 First Name / Last Name 都是：
    div.input-field-input[contenteditable=true][data-no-linebreaks=1]
    """
    deadline = time.time() + 15
    last_count = 0

    while time.time() < deadline:
        locator = page.locator("div.input-field-input[contenteditable='true'][data-no-linebreaks='1']")
        try:
            count = locator.count()
            last_count = count
        except Exception:
            count = 0

        visible_items = []
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    visible_items.append(item)
            except Exception:
                continue

        if len(visible_items) >= 1:
            first_field = visible_items[0]
            last_field = visible_items[1] if len(visible_items) >= 2 else None
            log(f"已定位昵称输入框 {len(visible_items)} 个。")
            return first_field, last_field

        _v15_sleep(page, 800)

    raise RuntimeError(f"15 秒内未找到昵称输入框，最后数量={last_count}")


def _v15_find_username_field(page):
    deadline = time.time() + 15
    while time.time() < deadline:
        locator = page.locator("input[name='username']")
        try:
            count = locator.count()
        except Exception:
            count = 0

        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    log(f"已定位用户名输入框：input[name='username'] index={index}")
                    return item
            except Exception:
                continue

        _v15_sleep(page, 800)

    raise RuntimeError("15 秒内未找到用户名输入框：input[name='username']")


def _v15_find_bio_field(page):
    """
    签名输入框也是 contenteditable。
    昵称页有两个 contenteditable，签名页一般有一个或多个；取最后一个可见输入框更接近 Bio/About。
    """
    deadline = time.time() + 15
    while time.time() < deadline:
        locator = page.locator("div.input-field-input[contenteditable='true'][data-no-linebreaks='1']")
        try:
            count = locator.count()
        except Exception:
            count = 0

        visible_items = []
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    visible_items.append(item)
            except Exception:
                continue

        if visible_items:
            log(f"已定位签名输入框候选 {len(visible_items)} 个，使用最后一个。")
            return visible_items[-1]

        _v15_sleep(page, 800)

    raise RuntimeError("15 秒内未找到签名输入框")


def update_name(page, first_name: str, last_name: str) -> str:
    """
    最终覆盖版昵称修改。
    不再调用 open_name_editor，避免 bool object is not subscriptable。
    """
    _v15_open_profile_edit_page(page, "昵称编辑按钮")

    first_field, last_field = _v15_find_name_fields(page)
    _v15_fill_contenteditable(page, first_field, str(first_name or ""), "First Name")

    if last_field is not None:
        _v15_fill_contenteditable(page, last_field, str(last_name or ""), "Last Name")

    if not _v15_click_save_button(page, "昵称保存按钮"):
        raise RuntimeError("昵称保存按钮点击失败：button.btn-circle.btn-corner.z-depth-1.rp.is-visible / 图标 ")

    log("昵称保存后等待 15000 毫秒，让 Telegram Web 完成同步。")
    _v15_sleep(page, 15000)
    return "success"


def update_username(page, username: str) -> str:
    if not username:
        return "skipped_empty"
    if not validate_username(username):
        return "invalid_username"

    _v15_open_profile_edit_page(page, "用户名编辑按钮")

    field = _v15_find_username_field(page)
    field.wait_for(state="visible", timeout=10000)
    field.scroll_into_view_if_needed(timeout=5000)
    _v15_sleep(page, 500)
    field.click(timeout=6000, force=True)
    _v15_sleep(page, 600)
    field.fill("", timeout=5000)
    _v15_sleep(page, 400)
    field.fill(username, timeout=8000)
    _v15_sleep(page, 1500)

    try:
        current = field.input_value(timeout=3000)
    except Exception:
        current = ""

    if username not in str(current or ""):
        raise RuntimeError(f"用户名写入后校验失败，目标={username}，当前={current}")

    text = safe_page_text(page, limit=3000).lower()
    if "already taken" in text or "username is taken" in text or "被占用" in text or "已被使用" in text:
        return "username_taken"
    if "invalid" in text and "username" in text:
        return "invalid_username"

    if not _v15_click_save_button(page, "用户名保存按钮"):
        raise RuntimeError("用户名保存按钮点击失败：button.btn-circle.btn-corner.z-depth-1.rp.is-visible / 图标 ")

    log("用户名保存后等待 15000 毫秒，让 Telegram Web 完成同步。")
    _v15_sleep(page, 15000)
    return "success"


def update_bio(page, bio_text: str) -> str:
    if not str(bio_text or "").strip():
        return "skipped_empty"

    _v15_open_profile_edit_page(page, "签名编辑按钮")

    field = _v15_find_bio_field(page)
    _v15_fill_contenteditable(page, field, str(bio_text or ""), "Bio / About")

    if not _v15_click_save_button(page, "签名保存按钮"):
        raise RuntimeError("签名保存按钮点击失败：button.btn-circle.btn-corner.z-depth-1.rp.is-visible / 图标 ")

    log("签名保存后等待 15000 毫秒，让 Telegram Web 完成同步。")
    _v15_sleep(page, 15000)
    return "success"
# ===== profile maintenance final override v15 end =====



# ===== profile maintenance folder override v16 begin =====
def _v16_sleep(page, ms: int = 1500) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def _v16_click_telegram_777000_chat(page) -> bool:
    """
    打开左侧 Telegram 官方服务号 #777000。
    不再使用 Saved Messages / 收藏夹。
    优先点击左侧聊天列表里的 data-peer-id=777000。
    """
    selectors = [
        "a.chatlist-chat[data-peer-id='777000']",
        "a[href='#777000'][data-peer-id='777000']",
        ".chatlist-chat[data-peer-id='777000']",
        "[data-peer-id='777000'].chatlist-chat",
        "a[href='#777000']",
    ]

    deadline = time.time() + 30
    last_error = ""

    while time.time() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception as e:
                last_error = str(e)
                continue

            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=600):
                        continue
                    item.scroll_into_view_if_needed(timeout=3000)
                    _v16_sleep(page, 500)
                    item.click(timeout=6000, force=True)
                    log(f"已点击左侧 #777000 官方消息聊天：selector={selector}, index={index}")
                    _v16_sleep(page, 2500)
                    return True
                except Exception as e:
                    last_error = str(e)
                    continue

        # 如果当前左侧没渲染出 #777000，兜底用 hash 打开一次，再继续找/确认。
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        if "#777000" not in current_url:
            try:
                page.goto("https://web.telegram.org/k/#777000", wait_until="commit", timeout=12000)
                log("左侧未找到 #777000，已兜底打开 https://web.telegram.org/k/#777000")
                _v16_sleep(page, 4000)
            except Exception as e:
                last_error = str(e)

        # 如果已经进入 #777000，直接返回。
        try:
            if "#777000" in (page.url or ""):
                log("当前地址已进入 #777000。")
                _v16_sleep(page, 2000)
                return True
        except Exception:
            pass

        _v16_sleep(page, 1200)

    dump_debug_html(page, "folder_open_777000_failed")
    log(f"30 秒内未能打开 #777000 官方消息聊天，最后错误：{last_error}")
    return False


def _v16_find_current_chat_message_box(page):
    selectors = [
        ".input-message-input[contenteditable='true']",
        ".input-message-container [contenteditable='true']",
        "[contenteditable='true'][data-placeholder*='Message' i]",
        "[contenteditable='true'][aria-label*='Message' i]",
        "div[contenteditable='true']",
    ]

    deadline = time.time() + 20
    while time.time() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue

            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=600):
                        continue

                    # 避免误选搜索框：消息输入框通常在页面下半部分。
                    box = item.bounding_box(timeout=800)
                    if box and float(box.get("y") or 0) < 250:
                        continue

                    log(f"已定位当前聊天消息输入框：selector={selector}, index={index}")
                    return item
                except Exception:
                    continue

        _v16_sleep(page, 800)

    return None


def _v16_send_link_to_current_chat(page, link: str) -> None:
    box = _v16_find_current_chat_message_box(page)
    if box is None:
        dump_debug_html(page, "folder_777000_message_box_not_found")
        raise RuntimeError("未找到 #777000 对话消息输入框")

    box.click(timeout=6000, force=True)
    _v16_sleep(page, 600)
    page.keyboard.press("Control+A")
    _v16_sleep(page, 200)
    page.keyboard.press("Backspace")
    _v16_sleep(page, 300)
    page.keyboard.insert_text(link)
    _v16_sleep(page, 1000)
    page.keyboard.press("Enter")
    log(f"已把分组文件夹链接发送到 #777000：{link}")
    _v16_sleep(page, 3500)


def _v16_click_sent_folder_link(page, link: str) -> bool:
    """
    点击刚发送出去的 addlist 链接。
    优先点 href 精确匹配，其次点包含链接文字的 a / message / bubble。
    """
    escaped_link = re.escape(link)
    candidates = [
        page.locator(f"a[href='{link}']"),
        page.locator(f"a[href*='{link}']"),
        page.locator("a").filter(has_text=re.compile(escaped_link)),
        page.get_by_text(re.compile(escaped_link)),
        page.locator(".message").filter(has_text=re.compile(escaped_link)),
        page.locator(".bubble").filter(has_text=re.compile(escaped_link)),
    ]

    deadline = time.time() + 25
    while time.time() < deadline:
        for locator in candidates:
            try:
                count = locator.count()
            except Exception:
                count = 1

            for index in range(max(1, count)):
                try:
                    item = locator.nth(index) if count > 1 else locator
                    if not item.is_visible(timeout=600):
                        continue
                    item.scroll_into_view_if_needed(timeout=3000)
                    _v16_sleep(page, 500)
                    item.click(timeout=6000, force=True)
                    log(f"已点击 #777000 里刚发送的分组文件夹链接。")
                    _v16_sleep(page, 5000)
                    return True
                except Exception:
                    continue

        _v16_sleep(page, 1000)

    dump_debug_html(page, "folder_777000_link_click_failed")
    return False


def _v16_click_add_folder_button(page) -> str:
    text = safe_page_text(page, limit=5000).lower()
    if "already" in text and ("added" in text or "joined" in text):
        return "already_added"
    if "已添加" in text or "已经添加" in text or "已加入" in text or "已经加入" in text:
        return "already_added"

    selectors = [
        "button.btn-primary",
        ".popup button",
        ".modal button",
        "button",
        ".btn-primary",
        ".Button",
    ]

    button_regex = re.compile(
        r"^(add|add folder|join|apply|save|done|ok|open|添加|添加文件夹|加入|保存|完成|确定|打开)$",
        re.IGNORECASE,
    )

    deadline = time.time() + 30
    last_text = ""

    while time.time() < deadline:
        # 先用原脚本已有的 click_by_text，兼容英文/中文按钮。
        try:
            if click_by_text(page, button_regex, timeout=2500):
                log("已点击添加分组文件夹按钮。")
                _v16_sleep(page, 5000)
                text = safe_page_text(page, limit=5000).lower()
                if "already" in text and ("added" in text or "joined" in text):
                    return "already_added"
                return "success"
        except Exception:
            pass

        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue

            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=600):
                        continue

                    item_text = str(item.inner_text(timeout=800) or "").strip()
                    last_text = item_text
                    if not button_regex.search(item_text):
                        continue

                    item.scroll_into_view_if_needed(timeout=3000)
                    _v16_sleep(page, 500)
                    item.click(timeout=6000, force=True)
                    log(f"已点击添加分组文件夹按钮：selector={selector}, index={index}, text={item_text!r}")
                    _v16_sleep(page, 5000)
                    text = safe_page_text(page, limit=5000).lower()
                    if "already" in text and ("added" in text or "joined" in text):
                        return "already_added"
                    return "success"
                except Exception:
                    continue

        text = safe_page_text(page, limit=5000).lower()
        if "already" in text and ("added" in text or "joined" in text):
            return "already_added"

        _v16_sleep(page, 1000)

    dump_debug_html(page, "folder_add_button_not_found_777000")
    raise RuntimeError(f"未找到添加分组文件夹按钮，最后按钮文本：{last_text}")


def add_chat_folder(page, link: str) -> str:
    """
    v16：分组文件夹链接不再发送到收藏夹。
    改为发送到 Telegram 官方消息 #777000 对话，再点击链接加入。
    """
    link = str(link or "").strip()

    if not link:
        return "skipped_empty"

    if "t.me/addlist" not in link and "telegram.me/addlist" not in link:
        return "failed_invalid_link"

    if not _v16_click_telegram_777000_chat(page):
        raise RuntimeError("未能打开 #777000 官方消息对话")

    _v16_send_link_to_current_chat(page, link)

    if not _v16_click_sent_folder_link(page, link):
        log("未能从 #777000 消息里点击链接，改用当前登录浏览器直接打开链接兜底。")
        try:
            page.goto(link, wait_until="commit", timeout=15000)
            _v16_sleep(page, 5000)
        except Exception as e:
            raise RuntimeError(f"点击/打开分组文件夹链接失败：{e}")

    return _v16_click_add_folder_button(page)
# ===== profile maintenance folder override v16 end =====



# ===== profile maintenance all strict override v17 begin =====
def _v17_sleep(page, ms: int) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def _v17_step_delay_ms() -> int:
    try:
        return random.randint(3000, 5000)
    except Exception:
        return 4000


def _v17_success_status(status: str) -> bool:
    clean_status = str(status or "").strip().lower()
    return clean_status in {"success", "already_added"}


def _v17_return_to_initial_telegram_page(page, account: dict[str, str], reason: str) -> None:
    """
    每个动作完成后回到 Telegram Web 初始聊天页面，避免下一个动作接不上。
    """
    log(f"{reason}：准备返回 Telegram Web 初始页面。")

    for _ in range(2):
        try:
            page.keyboard.press("Escape")
            _v17_sleep(page, 500)
        except Exception:
            pass

    try:
        page.goto(TELEGRAM_WEB_URL, wait_until="commit", timeout=20000)
    except Exception as exc:
        log(f"{reason}：返回 Telegram Web 初始页 commit 超时/失败，继续等待页面状态：{exc}")

    _v17_sleep(page, 4000)

    try:
        if not is_telegram_logged_in_page(page, timeout=2000):
            log(f"{reason}：返回初始页后未识别为已登录，重新确认登录状态。")
            ensure_logged_in_without_mytelegram(page, account)
    except Exception as exc:
        log(f"{reason}：返回初始页后登录态确认异常，继续后续流程：{exc}")

    _v17_sleep(page, 1000)


def _v17_hard_refresh_for_retry(page, account: dict[str, str], step: str, attempt: int, error_text: str) -> None:
    """
    单个动作失败后，硬刷新 Telegram Web，再从当前步骤重新尝试。
    """
    log(f"步骤 {step} 第 {attempt} 次失败，准备硬刷新后重试。错误：{error_text}")

    try:
        dump_debug_html(page, f"profile_all_{step}_attempt_{attempt}_failed")
    except Exception:
        pass

    for _ in range(2):
        try:
            page.keyboard.press("Escape")
            _v17_sleep(page, 500)
        except Exception:
            pass

    try:
        page.keyboard.press("Control+F5")
        log(f"步骤 {step}：已发送 Ctrl+F5。")
        _v17_sleep(page, 3000)
    except Exception as exc:
        log(f"步骤 {step}：Ctrl+F5 失败，继续 reload：{exc}")

    try:
        page.reload(wait_until="commit", timeout=20000)
        log(f"步骤 {step}：reload(commit) 已执行。")
    except Exception as exc:
        log(f"步骤 {step}：reload(commit) 失败，继续 goto 初始页：{exc}")

    try:
        page.goto(TELEGRAM_WEB_URL, wait_until="commit", timeout=20000)
        log(f"步骤 {step}：已重新打开 Telegram Web 初始页。")
    except Exception as exc:
        log(f"步骤 {step}：重新打开 Telegram Web 初始页失败，继续等待页面恢复：{exc}")

    _v17_sleep(page, 5000)

    try:
        if not is_telegram_logged_in_page(page, timeout=2500):
            log(f"步骤 {step}：硬刷新后未识别为已登录，重新确认登录状态。")
            ensure_logged_in_without_mytelegram(page, account)
    except Exception as exc:
        log(f"步骤 {step}：硬刷新后登录态确认异常：{exc}")

    delay_ms = _v17_step_delay_ms()
    log(f"步骤 {step}：硬刷新恢复完成，等待 {delay_ms} 毫秒后重试当前步骤。")
    _v17_sleep(page, delay_ms)


def _v17_execute_step_strict(
    telegram_page,
    step: str,
    config: dict[str, Any],
    account: dict[str, str],
    account_index: int,
    used_photos: set[Path],
    max_attempts: int,
) -> str:
    """
    严格执行单个步骤：
    - 调用已经修好的单独按钮逻辑 execute_step；
    - 失败不跳过；
    - 硬刷新后重试当前步骤；
    - 只有 success / already_added 才算完成。
    """
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            log(f"开始执行步骤 {step}，尝试 {attempt}/{max_attempts}。")
            status = execute_step(telegram_page, step, config, account, account_index, used_photos)
            clean_status = str(status or "").strip()
            log(f"步骤 {step} 返回状态：{clean_status}")

            if _v17_success_status(clean_status):
                _v17_return_to_initial_telegram_page(
                    telegram_page,
                    account,
                    reason=f"步骤 {step} 完成",
                )
                delay_ms = _v17_step_delay_ms()
                log(f"步骤 {step} 完成后等待 {delay_ms} 毫秒，再进入下一个动作。")
                _v17_sleep(telegram_page, delay_ms)
                return clean_status

            last_error = f"step_status_not_success: {clean_status}"
            if attempt < max_attempts:
                _v17_hard_refresh_for_retry(telegram_page, account, step, attempt, last_error)
                continue

            raise RuntimeError(last_error)

        except Exception as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                _v17_hard_refresh_for_retry(telegram_page, account, step, attempt, last_error)
                continue
            break

    raise RuntimeError(f"步骤 {step} 在 {max_attempts} 次尝试后仍未完成：{last_error}")


def process_account(action: str, config: dict[str, Any], account: dict[str, str], account_index: int, total: int, used_photos: set[Path]) -> dict[str, Any]:
    """
    v17 覆盖版账号处理逻辑。

    修改全部选项 action=all：
    - 使用单个按钮已经修好的 execute_step 逻辑；
    - 账号 A 必须完成所有动作，才允许进入账号 B；
    - 某一步失败，硬刷新 Telegram Web 后重试当前步骤；
    - 不跳过失败步骤；
    - 每个动作之间 3~5 秒延迟；
    - 每个动作完成后返回 Telegram Web 初始页面。
    """
    result_row = safe_status_row(account, action)
    steps = action_steps(action, config)
    note_parts: list[str] = []

    log("-" * 80)
    log(f"资料维护脚本版本：{SCRIPT_VERSION}")
    log(f"开始处理账号 {account_index}/{total}：{account.get('phone', '')}")
    log(f"Profile：{account.get('profile_dir', '')}")
    log(f"代理：{account.get('masked_proxy', '')}")
    log(f"动作：{action}，步骤：{steps or ['status']}")
    log("-" * 80)

    parsed_proxy = parse_raw_proxy(account["raw_proxy"])
    result_row["masked_proxy"] = parsed_proxy.masked_raw_proxy

    ok, realtime_ip, error = verify_proxy_before_browser(account, parsed_proxy)
    if not ok:
        result_row["final_status"] = "failed"
        result_row["note"] = error
        return result_row

    strict_all_mode = action == "all"
    step_max_attempts = int(config.get("step_max_attempts") or 3)
    if step_max_attempts < 1:
        step_max_attempts = 1
    if step_max_attempts > 5:
        step_max_attempts = 5

    with sync_playwright() as playwright:
        context = None
        try:
            context, _ = launch_context_for_account(playwright, account)
            ok, browser_ip, error = verify_browser_proxy(context, account, realtime_ip)
            if not ok:
                result_row["final_status"] = "failed"
                result_row["note"] = error
                return result_row

            telegram_page = context.new_page()
            try:
                logged_in = ensure_logged_in_without_mytelegram(telegram_page, account)
            except Exception as exc:
                try:
                    dump_debug_html(telegram_page, "profile_maintenance_login_failed")
                except Exception:
                    pass
                raise RuntimeError(f"login_failed: {exc}") from exc

            if not logged_in:
                result_row["final_status"] = "not_logged_in"
                result_row["note"] = "Telegram Web 未登录，自动登录失败"
                for step in steps:
                    result_row[STEP_STATUS_FIELDS[step]] = "not_logged_in"
                return result_row

            if action == "status":
                result_row["final_status"] = "success"
                result_row["note"] = f"logged_in，browser_ip={browser_ip}"
                return result_row

            if strict_all_mode:
                log("修改全部选项进入严格模式：必须当前账号全部动作完成后才进入下一个账号。")
                for step in steps:
                    field = STEP_STATUS_FIELDS[step]
                    try:
                        status = _v17_execute_step_strict(
                            telegram_page,
                            step,
                            config,
                            account,
                            account_index,
                            used_photos,
                            max_attempts=step_max_attempts,
                        )
                        result_row[field] = status
                        log(f"账号 {account.get('phone', '')} 步骤 {step} 完成：{status}")
                    except Exception as exc:
                        error_text = str(exc)
                        result_row[field] = f"failed: {error_text}"
                        note_parts.append(f"{step}: {error_text}")
                        try:
                            dump_debug_html(telegram_page, f"profile_all_{step}_final_failed")
                        except Exception:
                            pass
                        log(f"账号 {account.get('phone', '')} 步骤 {step} 最终失败，严格模式停止当前账号后续动作：{error_text}")
                        result_row["final_status"] = "failed"
                        result_row["note"] = " | ".join(note_parts)
                        return result_row

                result_row["final_status"] = "success"
                result_row["note"] = "修改全部选项全部动作完成"
                return result_row

            # 单独按钮仍然使用原来的宽松模式：单步失败记录失败，不影响后续账号。
            for step in steps:
                field = STEP_STATUS_FIELDS[step]
                try:
                    status = execute_step(telegram_page, step, config, account, account_index, used_photos)
                    result_row[field] = status
                    log(f"账号 {account.get('phone', '')} 步骤 {step} 完成：{status}")
                except Exception as exc:
                    error_text = str(exc)
                    result_row[field] = f"failed: {error_text}"
                    note_parts.append(f"{step}: {error_text}")
                    try:
                        dump_debug_html(telegram_page, f"profile_{step}_failed")
                    except Exception:
                        pass
                    log(f"账号 {account.get('phone', '')} 步骤 {step} 失败：{error_text}")

            failed = failed_steps_from_result(result_row)
            if failed:
                result_row["final_status"] = "partial_failed" if len(failed) < len(steps) else "failed"
            else:
                result_row["final_status"] = "success"
            result_row["note"] = " | ".join(note_parts) if note_parts else "完成"
            return result_row
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram 账号资料维护")
    parser.add_argument("--action", choices=sorted(ACTIONS), default="status")
    args = parser.parse_args()

    action = str(args.action or "status").strip().lower()
    config = load_config()
    rows = read_account_proxy_map()
    total = len(rows)
    used_photos: set[Path] = set()

    log("=" * 80)
    log(f"账号资料维护开始：动作={action}，账号数={total}")
    log(f"配置文件：{CONFIG_FILE}")
    log(f"结果文件：{RESULTS_FILE}")
    log(f"失败文件：{FAILED_FILE}")
    log("=" * 80)

    success_count = 0
    failed_count = 0

    for index, account in enumerate(rows, start=1):
        try:
            telegram_phone, country_code, national_number = split_phone_for_telegram(
                account.get("phone", ""),
                account.get("country", ""),
            )
            account["telegram_phone"] = telegram_phone
            account["country_code"] = country_code
            account["national_number"] = national_number

            result_row = process_account(action, config, account, index, total, used_photos)
        except Exception as exc:
            result_row = safe_status_row(account, action)
            result_row["final_status"] = "failed"
            result_row["note"] = f"batch_unhandled_error: {exc}"
            log(f"账号 {account.get('phone', '')} 出现未捕获错误：{exc}")

        result_row["updated_at"] = now_text()
        write_result(result_row)

        steps = action_steps(action, config)
        failed = failed_steps_from_result(result_row)
        unfinished = unfinished_steps_from_result(result_row, steps)
        final_status = str(result_row.get("final_status") or "")

        if final_status == "success":
            success_count += 1
            log(f"账号 {account.get('phone', '')} 资料维护成功。")
        else:
            failed_count += 1
            write_failed({
                "phone": result_row.get("phone", ""),
                "profile_dir": result_row.get("profile_dir", ""),
                "masked_proxy": result_row.get("masked_proxy", ""),
                "action": action,
                "failed_steps": ";".join(failed),
                "unfinished_steps": ";".join(unfinished),
                "error_message": result_row.get("note", ""),
                "updated_at": now_text(),
            })
            log(f"账号 {account.get('phone', '')} 资料维护未完全成功：{final_status}，{result_row.get('note', '')}")

            if action == "all":
                log("修改全部选项严格模式：当前账号没有全部完成，停止整个批次，不进入下一个账号。")
                break

            if config.get("stop_on_error"):
                log("配置为遇到账号错误后停止全部流程，当前流程结束。")
                break

        if index < total:
            delay_ms = int(config.get("account_delay_ms") or 3000)
            log(f"等待 {delay_ms} 毫秒后处理下一个账号。")
            time.sleep(delay_ms / 1000)

    log("=" * 80)
    log(f"账号资料维护结束：成功 {success_count} 个，未完全成功 {failed_count} 个，总计 {total} 个。")
    log("=" * 80)
    return 0
# ===== profile maintenance all strict override v17 end =====


if __name__ == "__main__":
    raise SystemExit(main())

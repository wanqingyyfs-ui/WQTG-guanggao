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


SCRIPT_VERSION = "profile-maintenance-001"

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


def click_save(page) -> bool:
    for _ in range(3):
        if click_by_text(page, SAVE_BUTTON_REGEX, timeout=2500):
            wait_after_click(page, 1500)
            return True
        if click_first_visible([
            page.locator("button[aria-label*='save' i]"),
            page.locator("button[aria-label*='done' i]"),
            page.locator(".btn-primary"),
            page.locator("button.confirm"),
        ], timeout=2000, force=True):
            wait_after_click(page, 1500)
            return True
    return False


def update_name(page, first_name: str, last_name: str) -> str:
    open_profile_editor(page)
    first_field = find_text_field(page, ["first name", "first", "名", "名字", "昵称"])
    fill_text_field(page, first_field, first_name, "First Name")

    last_field = find_text_field(page, ["last name", "last", "姓"] , timeout=2500)
    if last_field is not None:
        fill_text_field(page, last_field, last_name, "Last Name")

    if not click_save(page):
        raise RuntimeError("修改昵称后未找到保存按钮")
    return "success"


def update_bio(page, bio_text: str) -> str:
    if not str(bio_text or "").strip():
        return "skipped_empty"
    open_profile_editor(page)
    bio_field = find_text_field(page, ["bio", "about", "简介", "签名", "个人简介"])
    fill_text_field(page, bio_field, bio_text, "Bio / About")
    if not click_save(page):
        raise RuntimeError("修改签名后未找到保存按钮")
    return "success"


def update_username(page, username: str) -> str:
    if not username:
        return "skipped_empty"
    if not validate_username(username):
        return "invalid_username"
    open_profile_editor(page)
    username_field = find_text_field(page, ["username", "user name", "用户名"])
    if username_field is None:
        # 部分 Telegram Web 需要先点击 Username 行
        if click_by_text(page, re.compile(r"(username|user name|用户名)", re.IGNORECASE), timeout=2500):
            wait_after_click(page, 1000)
            username_field = find_text_field(page, ["username", "user name", "用户名"], timeout=5000)
    fill_text_field(page, username_field, username, "Username")
    wait_after_click(page, 800)
    text = safe_page_text(page, limit=3000).lower()
    if "already taken" in text or "username is taken" in text or "被占用" in text or "已被使用" in text:
        return "username_taken"
    if "invalid" in text and "username" in text:
        return "invalid_username"
    if not click_save(page):
        raise RuntimeError("修改用户名后未找到保存按钮")
    return "success"


def update_photo(page, photo_path: Path) -> str:
    if photo_path is None or not photo_path.exists():
        return "skipped_no_photo"
    open_profile_editor(page)

    upload_input = None
    input_locator = page.locator("input[type='file']")
    try:
        if input_locator.count() > 0:
            upload_input = input_locator.first
    except Exception:
        upload_input = None

    if upload_input is None:
        clicked = click_first_visible([
            page.locator("button[aria-label*='photo' i]"),
            page.locator("button[title*='photo' i]"),
            page.locator(".avatar-edit"),
            page.locator(".profile-photo"),
            page.get_by_text(re.compile(r"(change photo|set photo|upload photo|更换头像|上传头像|头像)", re.IGNORECASE)),
        ], timeout=3000, force=True)
        wait_after_click(page, 1000)
        try:
            if page.locator("input[type='file']").count() > 0:
                upload_input = page.locator("input[type='file']").last
        except Exception:
            upload_input = None
        if upload_input is None and not clicked:
            raise RuntimeError("未找到头像上传入口")

    if upload_input is None:
        raise RuntimeError("未找到头像 file input")

    upload_input.set_input_files(str(photo_path))
    wait_after_click(page, 2500)
    click_save(page)
    click_by_text(page, re.compile(r"^(crop|apply|save|done|确定|保存|完成|应用)$", re.IGNORECASE), timeout=5000)
    wait_after_click(page, 2500)
    return "success"


def open_saved_messages(page) -> bool:
    if click_by_text(page, SAVED_MESSAGES_REGEX, timeout=2500):
        wait_after_click(page, 1500)
        return True

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
        return False, browser_ip, f"ip_mismatch: requests={realtime_ip}, browser={browser_ip}"

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


if __name__ == "__main__":
    raise SystemExit(main())

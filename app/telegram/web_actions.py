from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.telegram.selectors import (
    CODE_INPUTS,
    MESSAGE_INPUTS,
    PASSWORD_INPUTS,
    PHONE_INPUTS,
    first_visible,
)
from app.telegram.verification import provider_for


TELEGRAM_WEB_URL = "https://web.telegram.org/k/"


def login_start(page: Any, phone: str) -> dict[str, object]:
    page.goto(TELEGRAM_WEB_URL, wait_until="domcontentloaded", timeout=60000)
    if is_logged_in(page):
        return {"status": "logged_in"}
    phone_input = first_visible(page, PHONE_INPUTS, timeout_ms=30000)
    phone_input.fill(phone)
    phone_input.press("Enter")
    return {"status": "waiting_code"}


def read_verification(context: Any, url: str) -> dict[str, str | None]:
    verification_page = context.new_page()
    try:
        verification_page.goto(url, wait_until="domcontentloaded", timeout=45000)
        text = verification_page.locator("body").inner_text(timeout=10000)
        html = verification_page.content()
        result = provider_for(url).parse(html, text)
        return {"code": result.code, "two_factor_password": result.two_factor_password}
    finally:
        verification_page.close()


def submit_code(page: Any, code: str) -> dict[str, object]:
    code_input = first_visible(page, CODE_INPUTS, timeout_ms=30000)
    code_input.fill(code)
    code_input.press("Enter")
    page.wait_for_timeout(2500)
    if is_logged_in(page):
        return {"status": "logged_in"}
    for selector in PASSWORD_INPUTS:
        if page.locator(selector).count():
            return {"status": "waiting_2fa"}
    return {"status": "waiting_code"}


def submit_2fa(page: Any, password: str) -> dict[str, object]:
    password_input = first_visible(page, PASSWORD_INPUTS, timeout_ms=30000)
    password_input.fill(password)
    password_input.press("Enter")
    page.wait_for_timeout(2500)
    return {"status": "logged_in" if is_logged_in(page) else "waiting_2fa"}


def is_logged_in(page: Any) -> bool:
    if page.locator("input[type='tel']").count() or page.locator("input[name='phone_number']").count():
        return False
    return bool(
        page.locator("#column-left").count()
        or page.locator(".chatlist").count()
        or page.locator("[data-peer-id]").count()
    )


PLATFORM_WARNING_PATTERNS = (
    "too many attempts",
    "flood wait",
    "spam",
    "account limited",
    "verification required",
    "验证码",
    "操作过于频繁",
    "账号受限",
    "垃圾信息",
)


def _platform_warning(page: Any) -> str | None:
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return None
    for pattern in PLATFORM_WARNING_PATTERNS:
        if pattern.lower() in text:
            return pattern
    return None


def _any_visible_text(page: Any, labels: tuple[str, ...]) -> bool:
    for label in labels:
        try:
            matches = page.get_by_text(label, exact=True)
            for index in range(min(matches.count(), 5)):
                if matches.nth(index).is_visible():
                    return True
        except Exception:
            continue
    return False


def resolve_group(page: Any, link: str) -> dict[str, object]:
    page.goto(link, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    body_text = page.locator("body").inner_text(timeout=10000)
    title = page.title().replace("Telegram: Contact", "").strip()
    title_candidates = (
        "header .peer-title",
        ".chat-info .peer-title",
        ".profile-name",
        "h1",
    )
    for selector in title_candidates:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                candidate = locator.inner_text().strip()
                if candidate:
                    title = candidate
                    break
        except Exception:
            continue
    join_visible = _any_visible_text(
        page, ("Join", "加入", "JOIN", "Join Group", "加入群组")
    )
    can_send = False
    try:
        can_send = first_visible(page, MESSAGE_INPUTS, timeout_ms=3000).is_editable()
    except Exception:
        can_send = False
    description = None
    for selector in (".profile-description", ".group-description", "[class*='description']"):
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                description = loc.inner_text().strip() or None
                if description:
                    break
        except Exception:
            continue
    members = None
    match = re.search(r"([0-9.,KMB万]+)\s+(?:members|subscribers|成员|订阅者)", body_text, re.I)
    if match:
        members = match.group(1)
    observed_chat_id = page.evaluate(
        """
        () => {
          const nodes = [...document.querySelectorAll('[data-peer-id],[data-chat-id],[data-dialog-id]')];
          for (const node of nodes) {
            for (const key of ['data-peer-id','data-chat-id','data-dialog-id']) {
              const value = node.getAttribute(key);
              if (value && /^-?\\d+$/.test(value)) return value;
            }
          }
          return null;
        }
        """
    )
    return {
        "title": title or None,
        "current_url": page.url,
        "description": description,
        "visible_member_count": members,
        "observed_chat_id": observed_chat_id,
        "chat_type": "private_invite" if "/+" in link or "/joinchat/" in link else "public",
        "joined": not join_visible,
        "can_send": can_send,
        "read_only": not can_send,
    }


def send_message(
    page: Any,
    *,
    link: str,
    text: str,
    asset_paths: list[str] | None = None,
) -> dict[str, object]:
    metadata = resolve_group(page, link)
    warning = _platform_warning(page)
    if warning:
        return {"status": "manual_required", "reason": f"platform_warning:{warning}"}
    if not metadata["joined"]:
        return {"status": "manual_required", "reason": "account_not_joined", "metadata": metadata}
    if not metadata["can_send"]:
        return {"status": "failed", "reason": "group_not_writable", "metadata": metadata}
    message_input = first_visible(page, MESSAGE_INPUTS, timeout_ms=15000)
    before = page.locator(".message").count()
    files = [str(Path(item).resolve()) for item in (asset_paths or [])]
    for file_path in files:
        if not Path(file_path).is_file():
            return {"status": "failed", "reason": f"asset_missing:{file_path}"}
    if text and not files:
        message_input.fill(text)
    if files:
        chooser = page.locator("input[type='file']").first
        if not chooser.count():
            return {"status": "failed", "reason": "upload_input_missing"}
        chooser.set_input_files(files)
        page.wait_for_timeout(2200)
        caption = None
        for selector in (
            "div.popup div[contenteditable='true']",
            "div.modal div[contenteditable='true']",
            "div[contenteditable='true'][data-placeholder]",
        ):
            try:
                loc = page.locator(selector).last
                if loc.count() and loc.is_visible():
                    caption = loc
                    break
            except Exception:
                continue
        if text and caption is not None:
            caption.fill(text)
        sent = False
        for label in ("Send", "发送", "SEND"):
            try:
                buttons = page.get_by_role("button", name=label, exact=True)
                for index in range(min(buttons.count(), 5)):
                    button = buttons.nth(index)
                    if button.is_visible() and button.is_enabled():
                        button.click()
                        sent = True
                        break
            except Exception:
                continue
            if sent:
                break
        if not sent:
            page.keyboard.press("Enter")
    else:
        message_input.press("Enter")
    page.wait_for_timeout(2200)
    warning = _platform_warning(page)
    if warning:
        return {"status": "manual_required", "reason": f"platform_warning:{warning}"}
    after = page.locator(".message").count()
    outgoing_visible = False
    for selector in (".message.is-out", ".message.out", ".own", "[class*='message'][class*='out']"):
        try:
            loc = page.locator(selector).last
            if loc.count() and loc.is_visible():
                outgoing_visible = True
                break
        except Exception:
            continue
    return {
        "status": "success" if outgoing_visible or after > before else "failed",
        "before_count": before,
        "after_count": after,
        "outgoing_visible": outgoing_visible,
        "metadata": metadata,
    }


def forward_message(
    page: Any,
    *,
    source_link: str,
    target_link: str,
) -> dict[str, object]:
    target_metadata = resolve_group(page, target_link)
    if not target_metadata["joined"]:
        return {"status": "manual_required", "reason": "target_not_joined"}
    if not target_metadata["can_send"]:
        return {"status": "failed", "reason": "target_not_writable"}
    page.goto(source_link, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2200)
    if _platform_warning(page):
        return {"status": "manual_required", "reason": "platform_warning"}
    message = None
    for selector in (".message", "[data-mid]", "[data-message-id]"):
        loc = page.locator(selector).last
        if loc.count() and loc.is_visible():
            message = loc
            break
    if message is None:
        return {"status": "failed", "reason": "source_message_not_visible"}
    message.click(button="right")
    forward_clicked = False
    for label in ("Forward", "转发", "FORWARD"):
        try:
            item = page.get_by_text(label, exact=True).last
            if item.count() and item.is_visible():
                item.click()
                forward_clicked = True
                break
        except Exception:
            continue
    if not forward_clicked:
        return {"status": "failed", "reason": "forward_action_missing"}
    page.wait_for_timeout(800)
    search = None
    for selector in ("input[type='search']", "input[placeholder*='Search']", "input[placeholder*='搜索']"):
        loc = page.locator(selector).last
        if loc.count() and loc.is_visible():
            search = loc
            break
    username = target_link.rstrip("/").rsplit("/", 1)[-1].lstrip("+")
    if search is not None and username:
        search.fill(username)
        page.wait_for_timeout(1200)
    candidate = None
    for selector in (".chatlist-chat", "[data-peer-id]", ".selector-user"):
        loc = page.locator(selector).first
        if loc.count() and loc.is_visible():
            candidate = loc
            break
    if candidate is None:
        return {"status": "manual_required", "reason": "target_picker_unresolved"}
    candidate.click()
    page.wait_for_timeout(500)
    for label in ("Send", "发送", "Forward", "转发"):
        try:
            button = page.get_by_role("button", name=label, exact=True).last
            if button.count() and button.is_visible() and button.is_enabled():
                button.click()
                page.wait_for_timeout(1800)
                return {"status": "success"}
        except Exception:
            continue
    return {"status": "manual_required", "reason": "forward_confirmation_missing"}

from __future__ import annotations

import re

import update_telegram_profile as implementation


ENTRY_VERSION = "wqtg-profile-entry-2026-07-settings-header-v2"
_ORIGINAL_OPEN_EDIT_PROFILE = implementation.open_edit_profile
_SETTINGS_TITLE_REGEX = re.compile(r"^(settings|设置)$", re.IGNORECASE)


def _visible_settings_header(page):
    headers = page.locator(".sidebar-header")
    try:
        count = headers.count()
    except Exception:
        return None

    for index in range(count):
        header = headers.nth(index)
        try:
            if not header.is_visible(timeout=500):
                continue
            title = header.locator(".sidebar-header__title").first
            title_text = (title.inner_text(timeout=1000) or "").strip()
            if _SETTINGS_TITLE_REGEX.fullmatch(title_text):
                return header
        except Exception:
            continue
    return None


def open_edit_profile_latest(page) -> bool:
    """Open Edit Profile from Telegram Web K's current Settings header.

    Current DOM contains three ``button.btn-icon.rp`` buttons in the Settings
    header. The first opens QR-related UI; the second is the profile edit action.
    The locator is scoped to the visible Settings sidebar before using nth(1), so
    unrelated icon buttons elsewhere on the page cannot be selected.
    """

    header = _visible_settings_header(page)
    if header is not None:
        buttons = header.locator("button.btn-icon.rp")
        try:
            count = buttons.count()
        except Exception:
            count = 0

        if count >= 2:
            target = buttons.nth(1)
            try:
                target.wait_for(state="visible", timeout=5000)
                target.scroll_into_view_if_needed(timeout=2000)
                target.click(timeout=8000, force=True)
                implementation.log(
                    "已按 Telegram 最新设置栏结构点击编辑资料按钮："
                    ".sidebar-header[标题=设置] button.btn-icon.rp -> nth(1)"
                )
                implementation.wait_after_click(page, 1200)
                return True
            except Exception as exc:
                implementation.log(f"设置栏第二个资料按钮点击失败，转入安全兜底：{exc}")
        else:
            implementation.log(
                f"设置栏 button.btn-icon.rp 数量不足 2 个（当前 {count} 个），转入安全兜底。"
            )

    # The existing fallback only uses text/profile-card routes; it does not
    # intentionally click the first generic Settings header icon.
    return _ORIGINAL_OPEN_EDIT_PROFILE(page)


def main() -> int:
    implementation.open_edit_profile = open_edit_profile_latest
    implementation.SCRIPT_VERSION = f"{implementation.SCRIPT_VERSION}+{ENTRY_VERSION}"
    implementation.log(f"资料维护兼容入口：{ENTRY_VERSION}")
    return int(implementation.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())

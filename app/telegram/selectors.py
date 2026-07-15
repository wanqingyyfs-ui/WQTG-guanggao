from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def first_visible(page: Any, selectors: Iterable[str], timeout_ms: int = 12000) -> Any:
    last_error: Exception | None = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"No supported Telegram Web selector became visible: {last_error}")


PHONE_INPUTS = (
    "input[name='phone_number']",
    "input[type='tel']",
    "input[autocomplete='tel']",
)
CODE_INPUTS = (
    "input[name='phone_code']",
    "input[autocomplete='one-time-code']",
    "input[type='tel']",
)
PASSWORD_INPUTS = (
    "input[name='password']",
    "input[type='password']",
)
MESSAGE_INPUTS = (
    "div[contenteditable='true'][data-placeholder]",
    "div[contenteditable='true'].input-message-input",
    "div[contenteditable='true']",
)

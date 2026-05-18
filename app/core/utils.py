from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_dir(path: str | Path) -> Path:
    target_path = Path(path).expanduser()
    target_path.mkdir(parents=True, exist_ok=True)
    return target_path


def safe_text_preview(text: Any, max_len: int = 300) -> str:
    if text is None:
        return ""

    try:
        limit = int(max_len)
    except (TypeError, ValueError):
        limit = 300

    if limit <= 0:
        return ""

    value = str(text).replace("\r", "").replace("\n", "\\n")

    if len(value) <= limit:
        return value

    return value[:limit] + "..."


def normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_positive_int(value: Any, field_name: str) -> int:
    raw_text = str(value or "").strip()

    if not raw_text:
        raise ValueError(f"{field_name} 不能为空")

    try:
        number = int(raw_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc

    if number <= 0:
        raise ValueError(f"{field_name} 必须大于 0")

    return number


def parse_chat_id(value: Any, field_name: str = "Chat ID") -> int:
    raw_text = str(value or "").strip()

    if not raw_text:
        raise ValueError(f"{field_name} 不能为空")

    try:
        chat_id = int(raw_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc

    if chat_id == 0:
        raise ValueError(f"{field_name} 不能为 0")

    return chat_id


def normalize_message_ids(value: Any) -> list[int]:
    if value is None:
        return []

    if isinstance(value, int):
        raw_items = [value]
    elif isinstance(value, str):
        raw_items = value.replace("，", ",").split(",")
    elif isinstance(value, list | tuple | set):
        raw_items = list(value)
    else:
        return []

    result: list[int] = []

    for item in raw_items:
        try:
            message_id = int(str(item).strip())
        except (TypeError, ValueError):
            continue

        if message_id > 0 and message_id not in result:
            result.append(message_id)

    return result


def normalize_username_or_link(value: Any) -> str:
    raw_text = str(value or "").strip()

    if not raw_text:
        return ""

    if raw_text.startswith("https://t.me/"):
        return raw_text

    if raw_text.startswith("http://t.me/"):
        return raw_text.replace("http://t.me/", "https://t.me/", 1)

    if raw_text.startswith("t.me/"):
        return "https://" + raw_text

    if raw_text.startswith("@"):
        return raw_text

    if "/" not in raw_text and " " not in raw_text:
        return "@" + raw_text

    return raw_text


def split_keywords_text(text: str) -> list[str]:
    if not text:
        return []

    raw_text = str(text).replace("，", ",")
    parts = [item.strip() for item in raw_text.split(",")]

    result: list[str] = []
    for item in parts:
        if item and item not in result:
            result.append(item)

    return result


def keywords_to_text(keywords: list[str]) -> str:
    if not keywords:
        return ""

    result: list[str] = []
    for keyword in keywords:
        value = str(keyword or "").strip()

        if value and value not in result:
            result.append(value)

    return ",".join(result)
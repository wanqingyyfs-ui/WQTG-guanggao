from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.json_utils import atomic_write_json, read_json_file

from app.core.models import (
    AccountConfig,
    GroupConfig,
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    PAIRING_MODE_ROTATE,
    SendTaskConfig,
    Settings,
    TEMPLATE_MESSAGE_TYPE_ALBUM,
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
    TemplateConfig,
)


def _read_json_file(file_path: str | Path) -> Any:
    return read_json_file(file_path)


def _write_json_file(file_path: str | Path, data: Any) -> None:
    atomic_write_json(file_path, data)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "是", "启用", "开启"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "否", "禁用", "关闭"}:
            return False
    return bool(value)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    return max(0, _to_int(value, default))


def _seconds_to_ms(value: Any, default_seconds: float = 0.0) -> int:
    return int(round(max(0.0, _to_float(value, default_seconds)) * 1000))


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return []
    result: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _to_noise_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        return []
    result: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            if not _to_bool(item.get("enabled"), True):
                continue
            text = _to_str(item.get("text"), "").strip()
        else:
            text = _to_str(item, "").strip()
        if text:
            result.append(text)
    return result


def _to_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        raw_items = [value]
    elif isinstance(value, str):
        raw_items = [item.strip() for item in value.replace("，", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return []
    result: list[int] = []
    for item in raw_items:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in result:
            result.append(number)
    return result


def _normalize_ms_range(item: dict[str, Any], min_key: str, max_key: str, legacy_seconds_key: str) -> tuple[int, int]:
    if min_key in item or max_key in item:
        min_ms = _to_non_negative_int(item.get(min_key), 0)
        max_ms = _to_non_negative_int(item.get(max_key), min_ms)
    else:
        min_ms = _seconds_to_ms(item.get(legacy_seconds_key), 0)
        max_ms = min_ms
    if max_ms < min_ms:
        max_ms = min_ms
    return min_ms, max_ms


def _normalize_interval_ms(item: dict[str, Any]) -> int:
    if "interval_ms" in item:
        return _to_non_negative_int(item.get("interval_ms"), 3600000)
    return _seconds_to_ms(item.get("interval_seconds"), 3600)


def load_accounts(file_path: str) -> list[AccountConfig]:
    data = _read_json_file(file_path)
    if not isinstance(data, list):
        raise ValueError("accounts.json 必须是数组")
    accounts: list[AccountConfig] = []
    for raw_item in data:
        item = _as_dict(raw_item)
        accounts.append(
            AccountConfig(
                account_name=_to_str(item.get("account_name", "")).strip(),
                api_id=_to_int(item.get("api_id"), 0),
                api_hash=_to_str(item.get("api_hash", "")).strip(),
                phone=_to_str(item.get("phone", "")).strip(),
                session_name=_to_str(item.get("session_name", "")).strip(),
                enabled=_to_bool(item.get("enabled"), True),
                account_group=_to_str(item.get("account_group", "")).strip(),
            )
        )
    return accounts


def save_accounts(file_path: str, accounts: list[AccountConfig]) -> None:
    _write_json_file(file_path, [account.to_dict() for account in accounts])


def load_groups(file_path: str) -> list[GroupConfig]:
    data = _read_json_file(file_path)
    if not isinstance(data, list):
        raise ValueError("groups.json 必须是数组")
    groups: list[GroupConfig] = []
    for raw_item in data:
        item = _as_dict(raw_item)
        groups.append(
            GroupConfig(
                group_id=_to_str(item.get("group_id", "")).strip(),
                group_name=_to_str(item.get("group_name", "")).strip(),
                chat_id=_to_int(item.get("chat_id"), 0),
                username=_to_str(item.get("username", "")).strip(),
                remark=_to_str(item.get("remark", "")),
                enabled=_to_bool(item.get("enabled"), True),
                group_group=_to_str(item.get("group_group", "")).strip(),
                group_group_names=_to_str_list(item.get("group_group_names")),
            )
        )
    return groups


def save_groups(file_path: str, groups: list[GroupConfig]) -> None:
    _write_json_file(file_path, [group.to_dict() for group in groups])


def load_tasks(file_path: str) -> list[SendTaskConfig]:
    data = _read_json_file(file_path)
    if not isinstance(data, list):
        raise ValueError("tasks.json 必须是数组")
    tasks: list[SendTaskConfig] = []
    # 旧账号池/群组池任务在新版中不再运行。读取时只忽略，不在读取阶段自动覆盖 tasks.json。
    for raw_item in data:
        item = _as_dict(raw_item)
        account_group_names = _to_str_list(item.get("account_group_names"))
        group_group_names = _to_str_list(item.get("group_group_names"))
        if not account_group_names or not group_group_names:
            continue
        account_delay_min_ms, account_delay_max_ms = _normalize_ms_range(
            item, "account_delay_min_ms", "account_delay_max_ms", "account_delay_seconds"
        )
        group_delay_min_ms, group_delay_max_ms = _normalize_ms_range(
            item, "group_delay_min_ms", "group_delay_max_ms", "group_delay_seconds"
        )
        interval_ms = _normalize_interval_ms(item)
        tasks.append(
            SendTaskConfig(
                task_id=_to_str(item.get("task_id", "")).strip(),
                task_name=_to_str(item.get("task_name", "")).strip(),
                enabled=_to_bool(item.get("enabled"), True),
                account_group_names=account_group_names,
                group_group_names=group_group_names,
                pairing_mode=_to_str(item.get("pairing_mode", PAIRING_MODE_ROTATE)).strip() or PAIRING_MODE_ROTATE,
                account_delay_min_ms=account_delay_min_ms,
                account_delay_max_ms=account_delay_max_ms,
                account_delay_seconds=_to_non_negative_int(item.get("account_delay_seconds"), int(account_delay_min_ms // 1000)),
                group_delay_min_ms=group_delay_min_ms,
                group_delay_max_ms=group_delay_max_ms,
                group_delay_seconds=_to_non_negative_int(item.get("group_delay_seconds"), int(group_delay_min_ms // 1000)),
                interval_ms=interval_ms,
                interval_seconds=_to_non_negative_int(item.get("interval_seconds"), int(interval_ms // 1000)),
                daily_window_enabled=_to_bool(item.get("daily_window_enabled"), False),
                daily_start_time=_to_str(item.get("daily_start_time", item.get("daily_time", "09:00"))).strip() or "09:00",
                daily_end_time=_to_str(item.get("daily_end_time", "21:00")).strip() or "21:00",
                message_mode=_to_str(item.get("message_mode", MESSAGE_MODE_TEMPLATE)).strip() or MESSAGE_MODE_TEMPLATE,
                text=_to_str(item.get("text", "")),
                template_ids=_to_str_list(item.get("template_ids")),
                template_id=_to_str(item.get("template_id", "")).strip(),
                last_run_at=_to_str(item.get("last_run_at", "")).strip(),
                remark=_to_str(item.get("remark", "")),
            )
        )
    return tasks


def save_tasks(file_path: str, tasks: list[SendTaskConfig]) -> None:
    _write_json_file(file_path, [task.to_dict() for task in tasks])


def _normalize_message_type(value: Any) -> str:
    text = _to_str(value, TEMPLATE_MESSAGE_TYPE_TEXT).strip()
    if text in {TEMPLATE_MESSAGE_TYPE_TEXT, TEMPLATE_MESSAGE_TYPE_PHOTO, TEMPLATE_MESSAGE_TYPE_ALBUM}:
        return text
    return TEMPLATE_MESSAGE_TYPE_TEXT


def _normalize_send_mode(value: Any) -> str:
    text = _to_str(value, TEMPLATE_SEND_MODE_FORWARD).strip()
    return text or TEMPLATE_SEND_MODE_FORWARD


def load_templates(file_path: str) -> list[TemplateConfig]:
    data = _read_json_file(file_path)
    if not isinstance(data, list):
        raise ValueError("templates.json 必须是数组")
    templates: list[TemplateConfig] = []
    for raw_item in data:
        item = _as_dict(raw_item)
        templates.append(
            TemplateConfig(
                template_id=_to_str(item.get("template_id", "")).strip(),
                template_name=_to_str(item.get("template_name", "")).strip(),
                source_account_name=_to_str(item.get("source_account_name", "")).strip(),
                source_chat_id=_to_int(item.get("source_chat_id"), 0),
                source_chat_title=_to_str(item.get("source_chat_title", "")),
                source_message_ids=_to_int_list(item.get("source_message_ids")),
                message_type=_normalize_message_type(item.get("message_type")),
                send_mode=_normalize_send_mode(item.get("send_mode")),
                preview_text=_to_str(item.get("preview_text", "")),
                raw_text=_to_str(item.get("raw_text", "")),
                has_custom_emoji=_to_bool(item.get("has_custom_emoji"), False),
                has_media=_to_bool(item.get("has_media"), False),
                media_count=_to_non_negative_int(item.get("media_count"), 0),
                preview_images=_to_str_list(item.get("preview_images")),
                enabled=_to_bool(item.get("enabled"), True),
                created_at=_to_str(item.get("created_at", "")).strip(),
                remark=_to_str(item.get("remark", "")),
            )
        )
    return templates


def save_templates(file_path: str, templates: list[TemplateConfig]) -> None:
    _write_json_file(file_path, [template.to_dict() for template in templates])


def load_settings(file_path: str) -> Settings:
    data = _read_json_file(file_path)
    if not isinstance(data, dict):
        raise ValueError("settings.json 必须是对象")
    return Settings.from_dict(data)


def save_settings(file_path: str, settings: Settings) -> None:
    _write_json_file(file_path, settings.to_dict())


def load_noise_pool(file_path: str) -> list[str]:
    data = _read_json_file(file_path)
    return _to_noise_text_list(data)


def save_noise_pool(file_path: str, noise_pool: list[str]) -> None:
    _write_json_file(file_path, _to_noise_text_list(noise_pool))

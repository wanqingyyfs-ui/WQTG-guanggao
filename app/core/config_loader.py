from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_SINGLE,
    AccountConfig,
    GroupConfig,
    MESSAGE_MODE_TEXT,
    SCHEDULE_MODE_MANUAL,
    SendTaskConfig,
    Settings,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
    TemplateConfig,
)


def _read_json_file(file_path: str | Path) -> Any:
    path = Path(file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {file_path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_file(file_path: str | Path, data: Any) -> None:
    path = Path(file_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    number = _to_int(value, default)

    if number < 0:
        return 0

    return number


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
        if normalized in {"1", "true", "yes", "y", "on", "是", "启用"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "否", "禁用"}:
            return False

    return bool(value)


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
        if item is None or item == "":
            continue

        try:
            number = int(item)
        except (TypeError, ValueError):
            continue

        if number not in result:
            result.append(number)

    return result


def _normalize_account_names(item: dict[str, Any]) -> list[str]:
    account_names = _to_str_list(item.get("account_names"))
    account_name = _to_str(item.get("account_name", "")).strip()

    if not account_names and account_name:
        account_names = [account_name]

    if account_name and account_name not in account_names:
        account_names.insert(0, account_name)

    return account_names


def _normalize_group_ids(item: dict[str, Any]) -> list[str]:
    group_ids = _to_str_list(item.get("group_ids"))
    group_id = _to_str(item.get("group_id", "")).strip()

    if not group_ids and group_id:
        group_ids = [group_id]

    if group_id and group_id not in group_ids:
        group_ids.insert(0, group_id)

    return group_ids


def _normalize_account_rotate_mode(value: Any) -> str:
    rotate_mode = _to_str(value, ACCOUNT_ROTATE_MODE_SINGLE).strip()

    if rotate_mode not in {
        ACCOUNT_ROTATE_MODE_SINGLE,
        ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    }:
        return ACCOUNT_ROTATE_MODE_SINGLE

    return rotate_mode


def _normalize_group_rotate_mode(value: Any) -> str:
    rotate_mode = _to_str(value, GROUP_ROTATE_MODE_SINGLE).strip()

    if rotate_mode not in {
        GROUP_ROTATE_MODE_SINGLE,
        GROUP_ROTATE_MODE_ROUND_ROBIN,
    }:
        return GROUP_ROTATE_MODE_SINGLE

    return rotate_mode


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

    for raw_item in data:
        item = _as_dict(raw_item)

        account_names = _normalize_account_names(item)
        account_name = _to_str(item.get("account_name", "")).strip()
        if not account_name and account_names:
            account_name = account_names[0]

        group_ids = _normalize_group_ids(item)
        group_id = _to_str(item.get("group_id", "")).strip()
        if not group_id and group_ids:
            group_id = group_ids[0]

        tasks.append(
            SendTaskConfig(
                task_id=_to_str(item.get("task_id", "")).strip(),
                task_name=_to_str(item.get("task_name", "")).strip(),
                enabled=_to_bool(item.get("enabled"), True),
                account_name=account_name,
                account_names=account_names,
                account_rotate_mode=_normalize_account_rotate_mode(
                    item.get("account_rotate_mode")
                ),
                current_account_index=_to_non_negative_int(
                    item.get("current_account_index"),
                    0,
                ),
                account_delay_seconds=_to_non_negative_int(
                    item.get("account_delay_seconds"),
                    0,
                ),
                group_id=group_id,
                group_ids=group_ids,
                group_rotate_mode=_normalize_group_rotate_mode(
                    item.get("group_rotate_mode")
                ),
                current_group_index=_to_non_negative_int(
                    item.get("current_group_index"),
                    0,
                ),
                group_delay_seconds=_to_non_negative_int(
                    item.get("group_delay_seconds"),
                    0,
                ),
                message_mode=_to_str(item.get("message_mode", MESSAGE_MODE_TEXT)),
                text=_to_str(item.get("text", "")),
                template_id=_to_str(item.get("template_id", "")).strip(),
                schedule_mode=_to_str(
                    item.get("schedule_mode", SCHEDULE_MODE_MANUAL)
                ),
                interval_seconds=max(
                    1,
                    _to_int(item.get("interval_seconds"), 3600),
                ),
                daily_time=_to_str(item.get("daily_time", "09:00")).strip()
                or "09:00",
                random_delay_min=_to_non_negative_int(
                    item.get("random_delay_min"),
                    0,
                ),
                random_delay_max=_to_non_negative_int(
                    item.get("random_delay_max"),
                    0,
                ),
                last_run_at=_to_str(item.get("last_run_at", "")).strip(),
                next_run_at=_to_str(item.get("next_run_at", "")).strip(),
                remark=_to_str(item.get("remark", "")),
            )
        )

    return tasks


def save_tasks(file_path: str, tasks: list[SendTaskConfig]) -> None:
    _write_json_file(file_path, [task.to_dict() for task in tasks])


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
                source_account_name=_to_str(
                    item.get("source_account_name", "")
                ).strip(),
                source_chat_id=_to_int(item.get("source_chat_id"), 0),
                source_chat_title=_to_str(item.get("source_chat_title", "")),
                source_message_ids=_to_int_list(item.get("source_message_ids")),
                message_type=_to_str(
                    item.get("message_type", TEMPLATE_MESSAGE_TYPE_TEXT)
                ),
                send_mode=_to_str(item.get("send_mode", TEMPLATE_SEND_MODE_FORWARD)),
                preview_text=_to_str(item.get("preview_text", "")),
                raw_text=_to_str(item.get("raw_text", "")),
                has_custom_emoji=_to_bool(item.get("has_custom_emoji"), False),
                has_media=_to_bool(item.get("has_media"), False),
                media_count=_to_int(item.get("media_count"), 0),
                preview_images=_to_str_list(item.get("preview_images")),
                enabled=_to_bool(item.get("enabled"), True),
                created_at=_to_str(item.get("created_at", "")).strip(),
            )
        )

    return templates


def save_templates(file_path: str, templates: list[TemplateConfig]) -> None:
    _write_json_file(file_path, [template.to_dict() for template in templates])


def load_settings(file_path: str) -> Settings:
    data = _read_json_file(file_path)

    if not isinstance(data, dict):
        raise ValueError("settings.json 必须是对象")

    return Settings.from_dict(
        {
            "app_name": _to_str(data.get("app_name", "telegram_user_group_sender_gui")),
            "log_level": _to_str(data.get("log_level", "INFO")),
            "log_file": _to_str(data.get("log_file", "logs/app.log")),
            "sessions_dir": _to_str(data.get("sessions_dir", "")),
            "scheduler_tick_seconds": _to_float(
                data.get("scheduler_tick_seconds"),
                1.0,
            ),
            "max_concurrent_tasks": _to_int(data.get("max_concurrent_tasks"), 1),
            "default_send_interval_seconds": _to_float(
                data.get("default_send_interval_seconds"),
                1.0,
            ),
            "template_source_account_name": _to_str(
                data.get("template_source_account_name", "")
            ).strip(),
            "template_source_chat_id": _to_int(
                data.get("template_source_chat_id"),
                0,
            ),
        }
    )


def save_settings(file_path: str, settings: Settings) -> None:
    _write_json_file(file_path, settings.to_dict())
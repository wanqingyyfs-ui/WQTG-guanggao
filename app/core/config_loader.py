from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import (
    AccountConfig,
    GroupConfig,
    SendTaskConfig,
    Settings,
    TemplateConfig,
    MESSAGE_MODE_TEXT,
    SCHEDULE_MODE_MANUAL,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
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


def load_accounts(file_path: str) -> list[AccountConfig]:
    data = _read_json_file(file_path)

    if not isinstance(data, list):
        raise ValueError("accounts.json 必须是数组")

    accounts: list[AccountConfig] = []

    for item in data:
        accounts.append(
            AccountConfig(
                account_name=str(item["account_name"]),
                api_id=int(item["api_id"]),
                api_hash=str(item["api_hash"]),
                phone=str(item["phone"]),
                session_name=str(item["session_name"]),
                enabled=bool(item.get("enabled", True)),
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

    for item in data:
        groups.append(
            GroupConfig(
                group_id=str(item.get("group_id", "")),
                group_name=str(item.get("group_name", "")),
                chat_id=int(item.get("chat_id", 0)),
                username=str(item.get("username", "")),
                remark=str(item.get("remark", "")),
                enabled=bool(item.get("enabled", True)),
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

    for item in data:
        tasks.append(
            SendTaskConfig(
                task_id=str(item.get("task_id", "")),
                task_name=str(item.get("task_name", "")),
                enabled=bool(item.get("enabled", True)),
                account_name=str(item.get("account_name", "")),
                group_id=str(item.get("group_id", "")),
                message_mode=str(item.get("message_mode", MESSAGE_MODE_TEXT)),
                text=str(item.get("text", "")),
                template_id=str(item.get("template_id", "")),
                schedule_mode=str(item.get("schedule_mode", SCHEDULE_MODE_MANUAL)),
                interval_seconds=int(item.get("interval_seconds", 3600)),
                daily_time=str(item.get("daily_time", "09:00")),
                random_delay_min=int(item.get("random_delay_min", 0)),
                random_delay_max=int(item.get("random_delay_max", 0)),
                last_run_at=str(item.get("last_run_at", "")),
                next_run_at=str(item.get("next_run_at", "")),
                remark=str(item.get("remark", "")),
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

    for item in data:
        templates.append(
            TemplateConfig(
                template_id=str(item.get("template_id", "")),
                template_name=str(item.get("template_name", "")),
                source_account_name=str(item.get("source_account_name", "")),
                source_chat_id=int(item.get("source_chat_id", 0)),
                source_chat_title=str(item.get("source_chat_title", "")),
                source_message_ids=[int(x) for x in item.get("source_message_ids", [])],
                message_type=str(item.get("message_type", TEMPLATE_MESSAGE_TYPE_TEXT)),
                send_mode=str(item.get("send_mode", TEMPLATE_SEND_MODE_FORWARD)),
                preview_text=str(item.get("preview_text", "")),
                raw_text=str(item.get("raw_text", "")),
                has_custom_emoji=bool(item.get("has_custom_emoji", False)),
                has_media=bool(item.get("has_media", False)),
                media_count=int(item.get("media_count", 0)),
                preview_images=[str(x) for x in item.get("preview_images", [])],
                enabled=bool(item.get("enabled", True)),
                created_at=str(item.get("created_at", "")),
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
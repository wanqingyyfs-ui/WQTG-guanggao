from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import (
    AccountConfig,
    RuleConfig,
    Settings,
    TemplateConfig,
    RULE_TYPE_KEYWORD,
    REPLY_MODE_TEXT,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
)
from app.core.utils import split_keywords_text


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


def load_rules(file_path: str) -> list[RuleConfig]:
    data = _read_json_file(file_path)
    if not isinstance(data, list):
        raise ValueError("rules.json 必须是数组")

    rules: list[RuleConfig] = []
    for item in data:
        raw_keywords = item.get("keywords", [])
        if isinstance(raw_keywords, str):
            keywords = split_keywords_text(raw_keywords)
        elif isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        rules.append(
            RuleConfig(
                rule_name=str(item["rule_name"]),
                rule_type=str(item.get("rule_type", RULE_TYPE_KEYWORD)),
                trigger_name=str(item.get("trigger_name", "")),
                keywords=keywords,
                reply_text=str(item.get("reply_text", "")),
                match_type=str(item.get("match_type", "contains")),
                enabled=bool(item.get("enabled", True)),
                reply_mode=str(item.get("reply_mode", REPLY_MODE_TEXT)),
                template_id=str(item.get("template_id", "")),
            )
        )
    return rules


def save_rules(file_path: str, rules: list[RuleConfig]) -> None:
    _write_json_file(file_path, [rule.to_dict() for rule in rules])


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
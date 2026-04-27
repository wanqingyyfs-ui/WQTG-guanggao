from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RULE_TYPE_KEYWORD = "keyword"
RULE_TYPE_FIRST_CONTACT = "first_contact"

FIRST_CONTACT_WELCOME = "welcome"
FIRST_CONTACT_BUSINESS_HOURS = "business_hours"

REPLY_MODE_TEXT = "text"
REPLY_MODE_TEMPLATE = "template"

TEMPLATE_MESSAGE_TYPE_TEXT = "text"
TEMPLATE_MESSAGE_TYPE_PHOTO = "photo"
TEMPLATE_MESSAGE_TYPE_ALBUM = "album"

TEMPLATE_SEND_MODE_FORWARD = "forward"
TEMPLATE_SEND_MODE_CLONE = "clone"


@dataclass
class AccountConfig:
    account_name: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_name": self.account_name,
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "phone": self.phone,
            "session_name": self.session_name,
            "enabled": self.enabled,
        }


@dataclass
class RuleConfig:
    rule_name: str
    rule_type: str = RULE_TYPE_KEYWORD
    trigger_name: str = ""
    keywords: list[str] = field(default_factory=list)
    reply_text: str = ""
    match_type: str = "contains"
    enabled: bool = True

    # 新增：回复模式
    reply_mode: str = REPLY_MODE_TEXT
    template_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "trigger_name": self.trigger_name,
            "keywords": self.keywords,
            "reply_text": self.reply_text,
            "match_type": self.match_type,
            "enabled": self.enabled,
            "reply_mode": self.reply_mode,
            "template_id": self.template_id,
        }


@dataclass
class TemplateConfig:
    template_id: str
    template_name: str
    source_account_name: str
    source_chat_id: int
    source_chat_title: str
    source_message_ids: list[int] = field(default_factory=list)
    message_type: str = TEMPLATE_MESSAGE_TYPE_TEXT
    send_mode: str = TEMPLATE_SEND_MODE_FORWARD
    preview_text: str = ""
    raw_text: str = ""
    has_custom_emoji: bool = False
    has_media: bool = False
    media_count: int = 0
    preview_images: list[str] = field(default_factory=list)
    enabled: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "source_account_name": self.source_account_name,
            "source_chat_id": self.source_chat_id,
            "source_chat_title": self.source_chat_title,
            "source_message_ids": self.source_message_ids,
            "message_type": self.message_type,
            "send_mode": self.send_mode,
            "preview_text": self.preview_text,
            "raw_text": self.raw_text,
            "has_custom_emoji": self.has_custom_emoji,
            "has_media": self.has_media,
            "media_count": self.media_count,
            "preview_images": self.preview_images,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }


@dataclass
class MatchOptions:
    ignore_case: bool = True
    strip_text: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ignore_case": self.ignore_case,
            "strip_text": self.strip_text,
        }


@dataclass
class Settings:
    app_name: str = "telegram_user_auto_reply_gui"
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    sessions_dir: str = ""
    only_private_chat: bool = True
    ignore_bots: bool = True
    ignore_outgoing: bool = True
    ignore_self: bool = True
    text_only: bool = True
    reply_interval_seconds: float = 0.8
    match_options: MatchOptions = field(default_factory=MatchOptions)

    # 新增：素材群设置
    template_source_account_name: str = ""
    template_source_chat_id: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        match_options_data = data.get("match_options", {}) or {}
        return cls(
            app_name=str(data.get("app_name", "telegram_user_auto_reply_gui")),
            log_level=str(data.get("log_level", "INFO")),
            log_file=str(data.get("log_file", "logs/app.log")),
            sessions_dir=str(data.get("sessions_dir", "sessions")),
            only_private_chat=bool(data.get("only_private_chat", True)),
            ignore_bots=bool(data.get("ignore_bots", True)),
            ignore_outgoing=bool(data.get("ignore_outgoing", True)),
            ignore_self=bool(data.get("ignore_self", True)),
            text_only=bool(data.get("text_only", True)),
            reply_interval_seconds=float(data.get("reply_interval_seconds", 0.8)),
            match_options=MatchOptions(
                ignore_case=bool(match_options_data.get("ignore_case", True)),
                strip_text=bool(match_options_data.get("strip_text", True)),
            ),
            template_source_account_name=str(data.get("template_source_account_name", "")),
            template_source_chat_id=int(data.get("template_source_chat_id", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "sessions_dir": self.sessions_dir,
            "only_private_chat": self.only_private_chat,
            "ignore_bots": self.ignore_bots,
            "ignore_outgoing": self.ignore_outgoing,
            "ignore_self": self.ignore_self,
            "text_only": self.text_only,
            "reply_interval_seconds": self.reply_interval_seconds,
            "match_options": self.match_options.to_dict(),
            "template_source_account_name": self.template_source_account_name,
            "template_source_chat_id": self.template_source_chat_id,
        }
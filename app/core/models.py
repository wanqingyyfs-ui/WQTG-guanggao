from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TEMPLATE_MESSAGE_TYPE_TEXT = "text"
TEMPLATE_MESSAGE_TYPE_PHOTO = "photo"
TEMPLATE_MESSAGE_TYPE_ALBUM = "album"

TEMPLATE_SEND_MODE_FORWARD = "forward"
TEMPLATE_SEND_MODE_CLONE = "clone"

MESSAGE_MODE_TEXT = "text"
MESSAGE_MODE_TEMPLATE = "template"

SCHEDULE_MODE_MANUAL = "manual"
SCHEDULE_MODE_INTERVAL = "interval"
SCHEDULE_MODE_DAILY = "daily"

TASK_STATUS_IDLE = "idle"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_ERROR = "error"


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
class GroupConfig:
    group_id: str
    group_name: str
    chat_id: int
    username: str = ""
    remark: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "chat_id": self.chat_id,
            "username": self.username,
            "remark": self.remark,
            "enabled": self.enabled,
        }


@dataclass
class SendTaskConfig:
    task_id: str
    task_name: str
    enabled: bool = True
    account_name: str = ""
    group_id: str = ""
    message_mode: str = MESSAGE_MODE_TEXT
    text: str = ""
    template_id: str = ""
    schedule_mode: str = SCHEDULE_MODE_MANUAL
    interval_seconds: int = 3600
    daily_time: str = "09:00"
    random_delay_min: int = 0
    random_delay_max: int = 0
    last_run_at: str = ""
    next_run_at: str = ""
    remark: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "enabled": self.enabled,
            "account_name": self.account_name,
            "group_id": self.group_id,
            "message_mode": self.message_mode,
            "text": self.text,
            "template_id": self.template_id,
            "schedule_mode": self.schedule_mode,
            "interval_seconds": self.interval_seconds,
            "daily_time": self.daily_time,
            "random_delay_min": self.random_delay_min,
            "random_delay_max": self.random_delay_max,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "remark": self.remark,
        }


@dataclass
class Settings:
    app_name: str = "telegram_user_group_sender_gui"
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    sessions_dir: str = ""
    scheduler_tick_seconds: float = 1.0
    max_concurrent_tasks: int = 1
    default_send_interval_seconds: float = 1.0
    template_source_account_name: str = ""
    template_source_chat_id: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        return cls(
            app_name=str(data.get("app_name", "telegram_user_group_sender_gui")),
            log_level=str(data.get("log_level", "INFO")),
            log_file=str(data.get("log_file", "logs/app.log")),
            sessions_dir=str(data.get("sessions_dir", "")),
            scheduler_tick_seconds=float(data.get("scheduler_tick_seconds", 1.0)),
            max_concurrent_tasks=int(data.get("max_concurrent_tasks", 1)),
            default_send_interval_seconds=float(
                data.get("default_send_interval_seconds", 1.0)
            ),
            template_source_account_name=str(
                data.get("template_source_account_name", "")
            ),
            template_source_chat_id=int(data.get("template_source_chat_id", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "sessions_dir": self.sessions_dir,
            "scheduler_tick_seconds": self.scheduler_tick_seconds,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "default_send_interval_seconds": self.default_send_interval_seconds,
            "template_source_account_name": self.template_source_account_name,
            "template_source_chat_id": self.template_source_chat_id,
        }
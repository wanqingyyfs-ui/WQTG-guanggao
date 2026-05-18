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

ACCOUNT_ROTATE_MODE_SINGLE = "single"
ACCOUNT_ROTATE_MODE_ROUND_ROBIN = "round_robin"

GROUP_ROTATE_MODE_SINGLE = "single"
GROUP_ROTATE_MODE_ROUND_ROBIN = "round_robin"


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


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    number = _to_int(value, default)

    if number < 0:
        return 0

    return number


def _normalize_unique_text_list(value: Any) -> list[str]:
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


def _normalize_rotate_mode(
    value: Any,
    allowed_modes: set[str],
    default: str,
) -> str:
    rotate_mode = str(value or "").strip()

    if rotate_mode in allowed_modes:
        return rotate_mode

    return default


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
    account_names: list[str] = field(default_factory=list)
    account_rotate_mode: str = ACCOUNT_ROTATE_MODE_SINGLE
    current_account_index: int = 0
    account_delay_seconds: int = 0

    group_id: str = ""
    group_ids: list[str] = field(default_factory=list)
    group_rotate_mode: str = GROUP_ROTATE_MODE_SINGLE
    current_group_index: int = 0
    group_delay_seconds: int = 0

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

    def __post_init__(self) -> None:
        self.account_name = str(self.account_name or "").strip()
        self.account_names = self._normalize_account_names()
        self.account_rotate_mode = _normalize_rotate_mode(
            self.account_rotate_mode,
            {
                ACCOUNT_ROTATE_MODE_SINGLE,
                ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
            },
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        self.current_account_index = _to_non_negative_int(
            self.current_account_index,
            0,
        )
        self.account_delay_seconds = _to_non_negative_int(
            self.account_delay_seconds,
            0,
        )

        self.group_id = str(self.group_id or "").strip()
        self.group_ids = self._normalize_group_ids()
        self.group_rotate_mode = _normalize_rotate_mode(
            self.group_rotate_mode,
            {
                GROUP_ROTATE_MODE_SINGLE,
                GROUP_ROTATE_MODE_ROUND_ROBIN,
            },
            GROUP_ROTATE_MODE_SINGLE,
        )
        self.current_group_index = _to_non_negative_int(
            self.current_group_index,
            0,
        )
        self.group_delay_seconds = _to_non_negative_int(
            self.group_delay_seconds,
            0,
        )

        self.interval_seconds = max(1, _to_int(self.interval_seconds, 3600))
        self.random_delay_min = _to_non_negative_int(self.random_delay_min, 0)
        self.random_delay_max = _to_non_negative_int(self.random_delay_max, 0)

    def _normalize_account_names(self) -> list[str]:
        normalized_account_names = _normalize_unique_text_list(self.account_names)

        if not normalized_account_names and self.account_name:
            normalized_account_names.append(self.account_name)

        if self.account_name and self.account_name not in normalized_account_names:
            normalized_account_names.insert(0, self.account_name)

        if not self.account_name and normalized_account_names:
            self.account_name = normalized_account_names[0]

        return normalized_account_names

    def _normalize_group_ids(self) -> list[str]:
        normalized_group_ids = _normalize_unique_text_list(self.group_ids)

        if not normalized_group_ids and self.group_id:
            normalized_group_ids.append(self.group_id)

        if self.group_id and self.group_id not in normalized_group_ids:
            normalized_group_ids.insert(0, self.group_id)

        if not self.group_id and normalized_group_ids:
            self.group_id = normalized_group_ids[0]

        return normalized_group_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "enabled": self.enabled,
            "account_name": self.account_name,
            "account_names": self.account_names,
            "account_rotate_mode": self.account_rotate_mode,
            "current_account_index": self.current_account_index,
            "account_delay_seconds": self.account_delay_seconds,
            "group_id": self.group_id,
            "group_ids": self.group_ids,
            "group_rotate_mode": self.group_rotate_mode,
            "current_group_index": self.current_group_index,
            "group_delay_seconds": self.group_delay_seconds,
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
        safe_data = data if isinstance(data, dict) else {}

        return cls(
            app_name=_to_str(
                safe_data.get("app_name"),
                "telegram_user_group_sender_gui",
            ),
            log_level=_to_str(safe_data.get("log_level"), "INFO"),
            log_file=_to_str(safe_data.get("log_file"), "logs/app.log"),
            sessions_dir=_to_str(safe_data.get("sessions_dir"), ""),
            scheduler_tick_seconds=_to_float(
                safe_data.get("scheduler_tick_seconds"),
                1.0,
            ),
            max_concurrent_tasks=_to_int(
                safe_data.get("max_concurrent_tasks"),
                1,
            ),
            default_send_interval_seconds=_to_float(
                safe_data.get("default_send_interval_seconds"),
                1.0,
            ),
            template_source_account_name=_to_str(
                safe_data.get("template_source_account_name"),
                "",
            ),
            template_source_chat_id=_to_int(
                safe_data.get("template_source_chat_id"),
                0,
            ),
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
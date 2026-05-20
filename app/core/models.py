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

SCHEDULE_MODE_INTERVAL = "interval"
SCHEDULE_MODE_DAILY = "daily"
LEGACY_SCHEDULE_MODE_MANUAL = "manual"

TASK_STATUS_IDLE = "idle"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_ERROR = "error"

ACCOUNT_ROTATE_MODE_SINGLE = "single"
ACCOUNT_ROTATE_MODE_ROUND_ROBIN = "round_robin"

GROUP_ROTATE_MODE_SINGLE = "single"
GROUP_ROTATE_MODE_ROUND_ROBIN = "round_robin"

SEND_DECISION_AD = "ad"
SEND_DECISION_NOISE = "noise"
SEND_DECISION_SKIP = "skip"

SEND_STATUS_SUCCESS = "success"
SEND_STATUS_FAILED = "failed"
SEND_STATUS_SKIPPED = "skipped"

LOG_MESSAGE_MODE_TEMPLATE = "template"
LOG_MESSAGE_MODE_TEXT = "text"
LOG_MESSAGE_MODE_NOISE = "noise"
LOG_MESSAGE_MODE_SKIP = "skip"


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
        if normalized in {"1", "true", "yes", "y", "on", "是", "启用"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "否", "禁用"}:
            return False

    return bool(value)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    number = _to_int(value, default)
    if number < 0:
        return 0
    return number


def _to_positive_int(value: Any, default: int = 1) -> int:
    number = _to_int(value, default)
    if number <= 0:
        return default
    return number


def _seconds_to_ms(value: Any, default_seconds: float = 0.0) -> int:
    seconds = _to_float(value, default_seconds)
    if seconds < 0:
        return 0
    return int(round(seconds * 1000))


def _ms_to_legacy_seconds(value: Any) -> int:
    ms = _to_non_negative_int(value, 0)
    return int(ms // 1000)


def _normalize_probability(value: Any, default: int) -> int:
    number = _to_int(value, default)
    if number < 0:
        return 0
    if number > 100:
        return 100
    return number


def _normalize_delay_range(min_ms: Any, max_ms: Any) -> tuple[int, int]:
    normalized_min_ms = _to_non_negative_int(min_ms, 0)
    normalized_max_ms = _to_non_negative_int(max_ms, normalized_min_ms)
    if normalized_max_ms < normalized_min_ms:
        normalized_max_ms = normalized_min_ms
    return normalized_min_ms, normalized_max_ms


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


def _normalize_rotate_mode(value: Any, allowed_modes: set[str], default: str) -> str:
    rotate_mode = str(value or "").strip()
    if rotate_mode in allowed_modes:
        return rotate_mode
    return default


def _normalize_message_mode(value: Any, default: str = MESSAGE_MODE_TEMPLATE) -> str:
    message_mode = str(value or "").strip()
    if message_mode in {MESSAGE_MODE_TEXT, MESSAGE_MODE_TEMPLATE}:
        return message_mode
    return default


def _normalize_schedule_mode(value: Any, default: str = SCHEDULE_MODE_INTERVAL) -> str:
    schedule_mode = str(value or "").strip()
    if schedule_mode == LEGACY_SCHEDULE_MODE_MANUAL:
        return SCHEDULE_MODE_INTERVAL
    if schedule_mode in {SCHEDULE_MODE_INTERVAL, SCHEDULE_MODE_DAILY}:
        return schedule_mode
    return default


def _normalize_daily_time(value: Any, default: str = "09:00") -> str:
    raw_text = str(value or "").strip()
    if not raw_text:
        raw_text = default

    try:
        hour_text, minute_text = raw_text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return default

    if hour < 0 or hour > 23:
        return default
    if minute < 0 or minute > 59:
        return default

    return f"{hour:02d}:{minute:02d}"


@dataclass
class AccountConfig:
    account_name: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    enabled: bool = True

    def __post_init__(self) -> None:
        self.account_name = str(self.account_name or "").strip()
        self.api_id = _to_int(self.api_id, 0)
        self.api_hash = str(self.api_hash or "").strip()
        self.phone = str(self.phone or "").strip()
        self.session_name = str(self.session_name or "").strip()
        self.enabled = _to_bool(self.enabled, True)

        if not self.session_name and self.account_name:
            self.session_name = self.account_name

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
    remark: str = ""

    def __post_init__(self) -> None:
        self.template_id = str(self.template_id or "").strip()
        self.template_name = str(self.template_name or "").strip()
        self.source_account_name = str(self.source_account_name or "").strip()
        self.source_chat_id = _to_int(self.source_chat_id, 0)
        self.source_chat_title = str(self.source_chat_title or "")
        self.source_message_ids = self._normalize_message_ids(self.source_message_ids)
        self.message_type = self._normalize_message_type(self.message_type)
        self.send_mode = self._normalize_send_mode(self.send_mode)
        self.preview_text = str(self.preview_text or "")
        self.raw_text = str(self.raw_text or "")
        self.has_custom_emoji = _to_bool(self.has_custom_emoji, False)
        self.has_media = _to_bool(
            self.has_media,
            self.message_type in {TEMPLATE_MESSAGE_TYPE_PHOTO, TEMPLATE_MESSAGE_TYPE_ALBUM},
        )
        self.media_count = _to_non_negative_int(self.media_count, 0)
        self.preview_images = _normalize_unique_text_list(self.preview_images)
        self.enabled = _to_bool(self.enabled, True)
        self.created_at = str(self.created_at or "").strip()
        self.remark = str(self.remark or "")

    @staticmethod
    def _normalize_message_type(value: Any) -> str:
        message_type = str(value or TEMPLATE_MESSAGE_TYPE_TEXT).strip()
        if message_type in {
            TEMPLATE_MESSAGE_TYPE_TEXT,
            TEMPLATE_MESSAGE_TYPE_PHOTO,
            TEMPLATE_MESSAGE_TYPE_ALBUM,
        }:
            return message_type
        return TEMPLATE_MESSAGE_TYPE_TEXT

    @staticmethod
    def _normalize_send_mode(value: Any) -> str:
        send_mode = str(value or TEMPLATE_SEND_MODE_FORWARD).strip()
        if send_mode in {TEMPLATE_SEND_MODE_FORWARD, TEMPLATE_SEND_MODE_CLONE}:
            return send_mode
        return TEMPLATE_SEND_MODE_FORWARD

    @staticmethod
    def _normalize_message_ids(value: Any) -> list[int]:
        if value is None:
            return []

        if isinstance(value, int):
            raw_items = [value]
        elif isinstance(value, str):
            raw_items = value.replace("，", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            return []

        result: list[int] = []
        for item in raw_items:
            message_id = _to_int(str(item).strip(), 0)
            if message_id > 0 and message_id not in result:
                result.append(message_id)
        return result

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
            "remark": self.remark,
        }


@dataclass
class GroupConfig:
    group_id: str
    group_name: str
    chat_id: int
    username: str = ""
    remark: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        self.group_id = str(self.group_id or "").strip()
        self.group_name = str(self.group_name or "").strip()
        self.chat_id = _to_int(self.chat_id, 0)
        self.username = str(self.username or "").strip()
        self.remark = str(self.remark or "")
        self.enabled = _to_bool(self.enabled, True)

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
    account_delay_min_ms: int = -1
    account_delay_max_ms: int = -1
    account_delay_seconds: int = 0

    group_id: str = ""
    group_ids: list[str] = field(default_factory=list)
    group_rotate_mode: str = GROUP_ROTATE_MODE_SINGLE
    current_group_index: int = 0
    group_delay_min_ms: int = -1
    group_delay_max_ms: int = -1
    group_delay_seconds: int = 0

    message_mode: str = MESSAGE_MODE_TEMPLATE
    text: str = ""
    template_ids: list[str] = field(default_factory=list)
    template_id: str = ""

    schedule_mode: str = SCHEDULE_MODE_INTERVAL
    interval_ms: int = -1
    interval_seconds: int = 3600
    daily_time: str = "09:00"
    random_delay_min: int = 0
    random_delay_max: int = 0

    last_run_at: str = ""
    next_run_at: str = ""
    remark: str = ""

    def __post_init__(self) -> None:
        self.task_id = str(self.task_id or "").strip()
        self.task_name = str(self.task_name or "").strip()
        self.enabled = _to_bool(self.enabled, True)

        self.account_name = str(self.account_name or "").strip()
        self.account_names = self._normalize_account_names()
        self.account_rotate_mode = _normalize_rotate_mode(
            self.account_rotate_mode,
            {ACCOUNT_ROTATE_MODE_SINGLE, ACCOUNT_ROTATE_MODE_ROUND_ROBIN},
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        self.current_account_index = _to_non_negative_int(self.current_account_index, 0)

        if _to_int(self.account_delay_min_ms, -1) < 0:
            legacy_account_delay_ms = _seconds_to_ms(self.account_delay_seconds, 0)
            self.account_delay_min_ms = legacy_account_delay_ms
            self.account_delay_max_ms = legacy_account_delay_ms
        else:
            self.account_delay_min_ms, self.account_delay_max_ms = _normalize_delay_range(
                self.account_delay_min_ms,
                self.account_delay_max_ms,
            )
        self.account_delay_seconds = _ms_to_legacy_seconds(self.account_delay_min_ms)

        self.group_id = str(self.group_id or "").strip()
        self.group_ids = self._normalize_group_ids()
        self.group_rotate_mode = _normalize_rotate_mode(
            self.group_rotate_mode,
            {GROUP_ROTATE_MODE_SINGLE, GROUP_ROTATE_MODE_ROUND_ROBIN},
            GROUP_ROTATE_MODE_SINGLE,
        )
        self.current_group_index = _to_non_negative_int(self.current_group_index, 0)

        if _to_int(self.group_delay_min_ms, -1) < 0:
            legacy_group_delay_ms = _seconds_to_ms(self.group_delay_seconds, 0)
            self.group_delay_min_ms = legacy_group_delay_ms
            self.group_delay_max_ms = legacy_group_delay_ms
        else:
            self.group_delay_min_ms, self.group_delay_max_ms = _normalize_delay_range(
                self.group_delay_min_ms,
                self.group_delay_max_ms,
            )
        self.group_delay_seconds = _ms_to_legacy_seconds(self.group_delay_min_ms)

        self.message_mode = _normalize_message_mode(self.message_mode)
        self.text = str(self.text or "")
        self.template_id = str(self.template_id or "").strip()
        self.template_ids = self._normalize_template_ids()

        self.schedule_mode = _normalize_schedule_mode(self.schedule_mode)
        if _to_int(self.interval_ms, -1) < 0:
            self.interval_ms = _seconds_to_ms(self.interval_seconds, 3600)
        else:
            self.interval_ms = _to_non_negative_int(self.interval_ms, 3600000)
        self.interval_seconds = _ms_to_legacy_seconds(self.interval_ms)

        self.daily_time = _normalize_daily_time(self.daily_time)
        self.random_delay_min = _to_non_negative_int(self.random_delay_min, 0)
        self.random_delay_max = _to_non_negative_int(self.random_delay_max, 0)
        if self.random_delay_max < self.random_delay_min:
            self.random_delay_max = self.random_delay_min

        self.last_run_at = str(self.last_run_at or "").strip()
        self.next_run_at = str(self.next_run_at or "").strip()
        self.remark = str(self.remark or "")

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

    def _normalize_template_ids(self) -> list[str]:
        normalized_template_ids = _normalize_unique_text_list(self.template_ids)
        if not normalized_template_ids and self.template_id:
            normalized_template_ids.append(self.template_id)
        if self.template_id and self.template_id not in normalized_template_ids:
            normalized_template_ids.insert(0, self.template_id)
        if not self.template_id and normalized_template_ids:
            self.template_id = normalized_template_ids[0]
        return normalized_template_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "enabled": self.enabled,
            "account_name": self.account_name,
            "account_names": self.account_names,
            "account_rotate_mode": self.account_rotate_mode,
            "current_account_index": self.current_account_index,
            "account_delay_min_ms": self.account_delay_min_ms,
            "account_delay_max_ms": self.account_delay_max_ms,
            "account_delay_seconds": self.account_delay_seconds,
            "group_id": self.group_id,
            "group_ids": self.group_ids,
            "group_rotate_mode": self.group_rotate_mode,
            "current_group_index": self.current_group_index,
            "group_delay_min_ms": self.group_delay_min_ms,
            "group_delay_max_ms": self.group_delay_max_ms,
            "group_delay_seconds": self.group_delay_seconds,
            "message_mode": self.message_mode,
            "text": self.text,
            "template_ids": self.template_ids,
            "template_id": self.template_id,
            "schedule_mode": self.schedule_mode,
            "interval_ms": self.interval_ms,
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
    max_concurrent_tasks: int = 0
    default_send_interval_seconds: float = 1.0
    template_source_account_name: str = ""
    template_source_chat_id: int = 0

    ad_probability: int = 75
    noise_probability: int = 22
    skip_probability: int = 3

    default_account_enabled: bool = True
    default_group_enabled: bool = True
    default_template_enabled: bool = True
    default_session_name_follow_account: bool = True
    default_group_username_normalize: bool = True

    default_task_account_rotate_mode: str = ACCOUNT_ROTATE_MODE_SINGLE
    default_task_account_delay_min_ms: int = 0
    default_task_account_delay_max_ms: int = 0
    default_task_group_rotate_mode: str = GROUP_ROTATE_MODE_SINGLE
    default_task_group_delay_min_ms: int = 0
    default_task_group_delay_max_ms: int = 0
    default_task_message_mode: str = MESSAGE_MODE_TEMPLATE
    default_task_schedule_mode: str = SCHEDULE_MODE_INTERVAL
    default_task_interval_ms: int = 3600000
    default_task_daily_time: str = "09:00"

    global_font_size: int = 13
    table_font_size: int = 13
    button_font_size: int = 13
    input_font_size: int = 13
    floating_panel_font_size: int = 13

    account_panel_font_size: int = 13
    account_panel_width: int = 520
    account_panel_height: int = 620

    group_panel_font_size: int = 13
    group_panel_width: int = 520
    group_panel_height: int = 620

    task_panel_font_size: int = 13
    task_panel_width: int = 680
    task_panel_height: int = 760

    template_panel_font_size: int = 13
    template_panel_width: int = 520
    template_panel_height: int = 520

    config_auto_save_debounce_ms: int = 400

    def __post_init__(self) -> None:
        self.app_name = str(self.app_name or "telegram_user_group_sender_gui")
        self.log_level = str(self.log_level or "INFO").strip() or "INFO"
        self.log_file = str(self.log_file or "logs/app.log")
        self.sessions_dir = str(self.sessions_dir or "")
        self.scheduler_tick_seconds = max(0.0, _to_float(self.scheduler_tick_seconds, 1.0))
        self.max_concurrent_tasks = _to_non_negative_int(self.max_concurrent_tasks, 0)
        self.default_send_interval_seconds = max(
            0.0,
            _to_float(self.default_send_interval_seconds, 1.0),
        )
        self.template_source_account_name = str(self.template_source_account_name or "").strip()
        self.template_source_chat_id = _to_int(self.template_source_chat_id, 0)

        self.ad_probability = _normalize_probability(self.ad_probability, 75)
        self.noise_probability = _normalize_probability(self.noise_probability, 22)
        self.skip_probability = _normalize_probability(self.skip_probability, 3)

        self.default_account_enabled = _to_bool(self.default_account_enabled, True)
        self.default_group_enabled = _to_bool(self.default_group_enabled, True)
        self.default_template_enabled = _to_bool(self.default_template_enabled, True)
        self.default_session_name_follow_account = _to_bool(
            self.default_session_name_follow_account,
            True,
        )
        self.default_group_username_normalize = _to_bool(
            self.default_group_username_normalize,
            True,
        )

        self.default_task_account_rotate_mode = _normalize_rotate_mode(
            self.default_task_account_rotate_mode,
            {ACCOUNT_ROTATE_MODE_SINGLE, ACCOUNT_ROTATE_MODE_ROUND_ROBIN},
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        (
            self.default_task_account_delay_min_ms,
            self.default_task_account_delay_max_ms,
        ) = _normalize_delay_range(
            self.default_task_account_delay_min_ms,
            self.default_task_account_delay_max_ms,
        )
        self.default_task_group_rotate_mode = _normalize_rotate_mode(
            self.default_task_group_rotate_mode,
            {GROUP_ROTATE_MODE_SINGLE, GROUP_ROTATE_MODE_ROUND_ROBIN},
            GROUP_ROTATE_MODE_SINGLE,
        )
        (
            self.default_task_group_delay_min_ms,
            self.default_task_group_delay_max_ms,
        ) = _normalize_delay_range(
            self.default_task_group_delay_min_ms,
            self.default_task_group_delay_max_ms,
        )
        self.default_task_message_mode = _normalize_message_mode(
            self.default_task_message_mode,
            MESSAGE_MODE_TEMPLATE,
        )
        self.default_task_schedule_mode = _normalize_schedule_mode(
            self.default_task_schedule_mode,
            SCHEDULE_MODE_INTERVAL,
        )
        self.default_task_interval_ms = _to_non_negative_int(
            self.default_task_interval_ms,
            3600000,
        )
        self.default_task_daily_time = _normalize_daily_time(
            self.default_task_daily_time,
            "09:00",
        )

        self.global_font_size = _to_positive_int(self.global_font_size, 13)
        self.table_font_size = _to_positive_int(self.table_font_size, 13)
        self.button_font_size = _to_positive_int(self.button_font_size, 13)
        self.input_font_size = _to_positive_int(self.input_font_size, 13)
        self.floating_panel_font_size = _to_positive_int(self.floating_panel_font_size, 13)

        self.account_panel_font_size = _to_positive_int(
            self.account_panel_font_size,
            self.floating_panel_font_size,
        )
        self.account_panel_width = _to_positive_int(self.account_panel_width, 520)
        self.account_panel_height = _to_positive_int(self.account_panel_height, 620)

        self.group_panel_font_size = _to_positive_int(
            self.group_panel_font_size,
            self.floating_panel_font_size,
        )
        self.group_panel_width = _to_positive_int(self.group_panel_width, 520)
        self.group_panel_height = _to_positive_int(self.group_panel_height, 620)

        self.task_panel_font_size = _to_positive_int(
            self.task_panel_font_size,
            self.floating_panel_font_size,
        )
        self.task_panel_width = _to_positive_int(self.task_panel_width, 680)
        self.task_panel_height = _to_positive_int(self.task_panel_height, 760)

        self.template_panel_font_size = _to_positive_int(
            self.template_panel_font_size,
            self.floating_panel_font_size,
        )
        self.template_panel_width = _to_positive_int(self.template_panel_width, 520)
        self.template_panel_height = _to_positive_int(self.template_panel_height, 520)

        self.config_auto_save_debounce_ms = max(
            100,
            _to_positive_int(self.config_auto_save_debounce_ms, 400),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        safe_data = data if isinstance(data, dict) else {}

        default_send_interval_seconds = _to_float(
            safe_data.get("default_send_interval_seconds"),
            1.0,
        )

        if "default_task_interval_ms" in safe_data:
            default_task_interval_ms = _to_non_negative_int(
                safe_data.get("default_task_interval_ms"),
                3600000,
            )
        elif "default_send_interval_seconds" in safe_data:
            default_task_interval_ms = _seconds_to_ms(
                safe_data.get("default_send_interval_seconds"),
                3600.0,
            )
        else:
            default_task_interval_ms = 3600000

        return cls(
            app_name=_to_str(safe_data.get("app_name"), "telegram_user_group_sender_gui"),
            log_level=_to_str(safe_data.get("log_level"), "INFO"),
            log_file=_to_str(safe_data.get("log_file"), "logs/app.log"),
            sessions_dir=_to_str(safe_data.get("sessions_dir"), ""),
            scheduler_tick_seconds=_to_float(safe_data.get("scheduler_tick_seconds"), 1.0),
            max_concurrent_tasks=_to_non_negative_int(safe_data.get("max_concurrent_tasks"), 0),
            default_send_interval_seconds=default_send_interval_seconds,
            template_source_account_name=_to_str(
                safe_data.get("template_source_account_name"),
                "",
            ),
            template_source_chat_id=_to_int(safe_data.get("template_source_chat_id"), 0),
            ad_probability=_normalize_probability(safe_data.get("ad_probability"), 75),
            noise_probability=_normalize_probability(safe_data.get("noise_probability"), 22),
            skip_probability=_normalize_probability(safe_data.get("skip_probability"), 3),
            default_account_enabled=_to_bool(safe_data.get("default_account_enabled"), True),
            default_group_enabled=_to_bool(safe_data.get("default_group_enabled"), True),
            default_template_enabled=_to_bool(safe_data.get("default_template_enabled"), True),
            default_session_name_follow_account=_to_bool(
                safe_data.get("default_session_name_follow_account"),
                True,
            ),
            default_group_username_normalize=_to_bool(
                safe_data.get("default_group_username_normalize"),
                True,
            ),
            default_task_account_rotate_mode=_normalize_rotate_mode(
                safe_data.get("default_task_account_rotate_mode"),
                {ACCOUNT_ROTATE_MODE_SINGLE, ACCOUNT_ROTATE_MODE_ROUND_ROBIN},
                ACCOUNT_ROTATE_MODE_SINGLE,
            ),
            default_task_account_delay_min_ms=_to_non_negative_int(
                safe_data.get("default_task_account_delay_min_ms"),
                0,
            ),
            default_task_account_delay_max_ms=_to_non_negative_int(
                safe_data.get("default_task_account_delay_max_ms"),
                0,
            ),
            default_task_group_rotate_mode=_normalize_rotate_mode(
                safe_data.get("default_task_group_rotate_mode"),
                {GROUP_ROTATE_MODE_SINGLE, GROUP_ROTATE_MODE_ROUND_ROBIN},
                GROUP_ROTATE_MODE_SINGLE,
            ),
            default_task_group_delay_min_ms=_to_non_negative_int(
                safe_data.get("default_task_group_delay_min_ms"),
                0,
            ),
            default_task_group_delay_max_ms=_to_non_negative_int(
                safe_data.get("default_task_group_delay_max_ms"),
                0,
            ),
            default_task_message_mode=_normalize_message_mode(
                safe_data.get("default_task_message_mode"),
                MESSAGE_MODE_TEMPLATE,
            ),
            default_task_schedule_mode=_normalize_schedule_mode(
                safe_data.get("default_task_schedule_mode"),
                SCHEDULE_MODE_INTERVAL,
            ),
            default_task_interval_ms=default_task_interval_ms,
            default_task_daily_time=_to_str(safe_data.get("default_task_daily_time"), "09:00"),
            global_font_size=_to_positive_int(safe_data.get("global_font_size"), 13),
            table_font_size=_to_positive_int(safe_data.get("table_font_size"), 13),
            button_font_size=_to_positive_int(safe_data.get("button_font_size"), 13),
            input_font_size=_to_positive_int(safe_data.get("input_font_size"), 13),
            floating_panel_font_size=_to_positive_int(
                safe_data.get("floating_panel_font_size"),
                13,
            ),
            account_panel_font_size=_to_positive_int(
                safe_data.get("account_panel_font_size"),
                13,
            ),
            account_panel_width=_to_positive_int(safe_data.get("account_panel_width"), 520),
            account_panel_height=_to_positive_int(safe_data.get("account_panel_height"), 620),
            group_panel_font_size=_to_positive_int(safe_data.get("group_panel_font_size"), 13),
            group_panel_width=_to_positive_int(safe_data.get("group_panel_width"), 520),
            group_panel_height=_to_positive_int(safe_data.get("group_panel_height"), 620),
            task_panel_font_size=_to_positive_int(safe_data.get("task_panel_font_size"), 13),
            task_panel_width=_to_positive_int(safe_data.get("task_panel_width"), 680),
            task_panel_height=_to_positive_int(safe_data.get("task_panel_height"), 760),
            template_panel_font_size=_to_positive_int(
                safe_data.get("template_panel_font_size"),
                13,
            ),
            template_panel_width=_to_positive_int(safe_data.get("template_panel_width"), 520),
            template_panel_height=_to_positive_int(safe_data.get("template_panel_height"), 520),
            config_auto_save_debounce_ms=_to_positive_int(
                safe_data.get("config_auto_save_debounce_ms"),
                400,
            ),
        )

    @property
    def probability_total(self) -> int:
        return self.ad_probability + self.noise_probability + self.skip_probability

    @property
    def probability_is_valid(self) -> bool:
        return self.probability_total == 100

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
            "ad_probability": self.ad_probability,
            "noise_probability": self.noise_probability,
            "skip_probability": self.skip_probability,
            "default_account_enabled": self.default_account_enabled,
            "default_group_enabled": self.default_group_enabled,
            "default_template_enabled": self.default_template_enabled,
            "default_session_name_follow_account": self.default_session_name_follow_account,
            "default_group_username_normalize": self.default_group_username_normalize,
            "default_task_account_rotate_mode": self.default_task_account_rotate_mode,
            "default_task_account_delay_min_ms": self.default_task_account_delay_min_ms,
            "default_task_account_delay_max_ms": self.default_task_account_delay_max_ms,
            "default_task_group_rotate_mode": self.default_task_group_rotate_mode,
            "default_task_group_delay_min_ms": self.default_task_group_delay_min_ms,
            "default_task_group_delay_max_ms": self.default_task_group_delay_max_ms,
            "default_task_message_mode": self.default_task_message_mode,
            "default_task_schedule_mode": self.default_task_schedule_mode,
            "default_task_interval_ms": self.default_task_interval_ms,
            "default_task_daily_time": self.default_task_daily_time,
            "global_font_size": self.global_font_size,
            "table_font_size": self.table_font_size,
            "button_font_size": self.button_font_size,
            "input_font_size": self.input_font_size,
            "floating_panel_font_size": self.floating_panel_font_size,
            "account_panel_font_size": self.account_panel_font_size,
            "account_panel_width": self.account_panel_width,
            "account_panel_height": self.account_panel_height,
            "group_panel_font_size": self.group_panel_font_size,
            "group_panel_width": self.group_panel_width,
            "group_panel_height": self.group_panel_height,
            "task_panel_font_size": self.task_panel_font_size,
            "task_panel_width": self.task_panel_width,
            "task_panel_height": self.task_panel_height,
            "template_panel_font_size": self.template_panel_font_size,
            "template_panel_width": self.template_panel_width,
            "template_panel_height": self.template_panel_height,
            "config_auto_save_debounce_ms": self.config_auto_save_debounce_ms,
        }

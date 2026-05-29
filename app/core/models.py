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

PAIRING_MODE_ROTATE = "rotate"

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
        if normalized in {"1", "true", "yes", "y", "on", "是", "启用", "开启"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "否", "禁用", "关闭"}:
            return False
    return bool(value)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    number = _to_int(value, default)
    return max(0, number)


def _to_positive_int(value: Any, default: int = 1) -> int:
    number = _to_int(value, default)
    return number if number > 0 else default


def _seconds_to_ms(value: Any, default_seconds: float = 0.0) -> int:
    seconds = _to_float(value, default_seconds)
    return int(round(max(0.0, seconds) * 1000))


def _ms_to_legacy_seconds(value: Any) -> int:
    return int(_to_non_negative_int(value, 0) // 1000)


def _normalize_probability(value: Any, default: int) -> int:
    number = _to_int(value, default)
    return min(100, max(0, number))


def _normalize_delay_range(min_ms: Any, max_ms: Any) -> tuple[int, int]:
    left = _to_non_negative_int(min_ms, 0)
    right = _to_non_negative_int(max_ms, left)
    if right < left:
        right = left
    return left, right


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


def _normalize_time(value: Any, default: str = "09:00") -> str:
    raw_text = str(value or "").strip() or default
    try:
        hour_text, minute_text = raw_text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return default
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def _normalize_message_mode(value: Any, default: str = MESSAGE_MODE_TEMPLATE) -> str:
    text = str(value or "").strip()
    if text in {MESSAGE_MODE_TEXT, MESSAGE_MODE_TEMPLATE}:
        return text
    return default


def _normalize_pairing_mode(value: Any) -> str:
    text = str(value or "").strip()
    if text == PAIRING_MODE_ROTATE:
        return text
    return PAIRING_MODE_ROTATE


@dataclass
class AccountConfig:
    account_name: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    enabled: bool = True
    account_group: str = ""

    def __post_init__(self) -> None:
        self.account_name = str(self.account_name or "").strip()
        self.api_id = _to_int(self.api_id, 0)
        self.api_hash = str(self.api_hash or "").strip()
        self.phone = str(self.phone or "").strip()
        self.session_name = str(self.session_name or "").strip()
        self.enabled = _to_bool(self.enabled, True)
        self.account_group = str(self.account_group or "").strip()
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
            "account_group": self.account_group,
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
        self.has_media = _to_bool(self.has_media, self.message_type in {TEMPLATE_MESSAGE_TYPE_PHOTO, TEMPLATE_MESSAGE_TYPE_ALBUM})
        self.media_count = _to_non_negative_int(self.media_count, 0)
        self.preview_images = _normalize_unique_text_list(self.preview_images)
        self.enabled = _to_bool(self.enabled, True)
        self.created_at = str(self.created_at or "").strip()
        self.remark = str(self.remark or "")

    @staticmethod
    def _normalize_message_type(value: Any) -> str:
        text = str(value or TEMPLATE_MESSAGE_TYPE_TEXT).strip()
        if text in {TEMPLATE_MESSAGE_TYPE_TEXT, TEMPLATE_MESSAGE_TYPE_PHOTO, TEMPLATE_MESSAGE_TYPE_ALBUM}:
            return text
        return TEMPLATE_MESSAGE_TYPE_TEXT

    @staticmethod
    def _normalize_send_mode(value: Any) -> str:
        text = str(value or TEMPLATE_SEND_MODE_FORWARD).strip()
        if text in {TEMPLATE_SEND_MODE_FORWARD, TEMPLATE_SEND_MODE_CLONE}:
            return text
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
            number = _to_int(str(item).strip(), 0)
            if number > 0 and number not in result:
                result.append(number)
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
    group_group: str = ""
    group_group_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.group_id = str(self.group_id or "").strip()
        self.group_name = str(self.group_name or "").strip()
        self.chat_id = _to_int(self.chat_id, 0)
        self.username = str(self.username or "").strip()
        self.remark = str(self.remark or "")
        self.enabled = _to_bool(self.enabled, True)

        legacy_group_group = str(self.group_group or "").strip()
        self.group_group_names = _normalize_unique_text_list(self.group_group_names)
        if legacy_group_group and legacy_group_group not in self.group_group_names:
            self.group_group_names.insert(0, legacy_group_group)
        self.group_group = self.group_group_names[0] if self.group_group_names else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "chat_id": self.chat_id,
            "username": self.username,
            "remark": self.remark,
            "enabled": self.enabled,
            "group_group": self.group_group,
            "group_group_names": self.group_group_names,
        }


@dataclass
class SendTaskConfig:
    task_id: str
    task_name: str
    enabled: bool = True

    account_group_names: list[str] = field(default_factory=list)
    group_group_names: list[str] = field(default_factory=list)
    pairing_mode: str = PAIRING_MODE_ROTATE

    account_delay_min_ms: int = -1
    account_delay_max_ms: int = -1
    account_delay_seconds: int = 0
    group_delay_min_ms: int = -1
    group_delay_max_ms: int = -1
    group_delay_seconds: int = 0
    interval_ms: int = -1
    interval_seconds: int = 3600

    daily_window_enabled: bool = False
    daily_start_time: str = "09:00"
    daily_end_time: str = "21:00"

    message_mode: str = MESSAGE_MODE_TEMPLATE
    text: str = ""
    template_ids: list[str] = field(default_factory=list)
    template_id: str = ""

    last_run_at: str = ""
    remark: str = ""

    # Runtime-only compatibility fields for existing send/log service.
    account_name: str = ""
    account_names: list[str] = field(default_factory=list)
    account_rotate_mode: str = ACCOUNT_ROTATE_MODE_ROUND_ROBIN
    current_account_index: int = 0
    group_id: str = ""
    group_ids: list[str] = field(default_factory=list)
    group_rotate_mode: str = GROUP_ROTATE_MODE_ROUND_ROBIN
    current_group_index: int = 0
    schedule_mode: str = SCHEDULE_MODE_INTERVAL
    daily_time: str = "09:00"
    next_run_at: str = ""
    random_delay_min: int = 0
    random_delay_max: int = 0

    def __post_init__(self) -> None:
        self.task_id = str(self.task_id or "").strip()
        self.task_name = str(self.task_name or "").strip()
        self.enabled = _to_bool(self.enabled, True)
        self.account_group_names = _normalize_unique_text_list(self.account_group_names)
        self.group_group_names = _normalize_unique_text_list(self.group_group_names)
        self.pairing_mode = _normalize_pairing_mode(self.pairing_mode)

        if _to_int(self.account_delay_min_ms, -1) < 0:
            delay = _seconds_to_ms(self.account_delay_seconds, 0)
            self.account_delay_min_ms = delay
            self.account_delay_max_ms = delay
        else:
            self.account_delay_min_ms, self.account_delay_max_ms = _normalize_delay_range(
                self.account_delay_min_ms,
                self.account_delay_max_ms,
            )
        self.account_delay_seconds = _ms_to_legacy_seconds(self.account_delay_min_ms)

        if _to_int(self.group_delay_min_ms, -1) < 0:
            delay = _seconds_to_ms(self.group_delay_seconds, 0)
            self.group_delay_min_ms = delay
            self.group_delay_max_ms = delay
        else:
            self.group_delay_min_ms, self.group_delay_max_ms = _normalize_delay_range(
                self.group_delay_min_ms,
                self.group_delay_max_ms,
            )
        self.group_delay_seconds = _ms_to_legacy_seconds(self.group_delay_min_ms)

        if _to_int(self.interval_ms, -1) < 0:
            self.interval_ms = _seconds_to_ms(self.interval_seconds, 3600)
        else:
            self.interval_ms = _to_non_negative_int(self.interval_ms, 3600000)
        self.interval_seconds = _ms_to_legacy_seconds(self.interval_ms)

        self.daily_window_enabled = _to_bool(self.daily_window_enabled, False)
        self.daily_start_time = _normalize_time(self.daily_start_time, "09:00")
        self.daily_end_time = _normalize_time(self.daily_end_time, "21:00")
        self.daily_time = self.daily_start_time

        self.message_mode = _normalize_message_mode(self.message_mode)
        self.text = str(self.text or "")
        self.template_id = str(self.template_id or "").strip()
        self.template_ids = _normalize_unique_text_list(self.template_ids)
        if not self.template_ids and self.template_id:
            self.template_ids.append(self.template_id)
        if self.template_ids and not self.template_id:
            self.template_id = self.template_ids[0]
        if self.template_id and self.template_id not in self.template_ids:
            self.template_ids.insert(0, self.template_id)

        self.last_run_at = str(self.last_run_at or "").strip()
        self.remark = str(self.remark or "")
        self.next_run_at = str(self.next_run_at or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "enabled": self.enabled,
            "account_group_names": self.account_group_names,
            "group_group_names": self.group_group_names,
            "pairing_mode": self.pairing_mode,
            "account_delay_min_ms": self.account_delay_min_ms,
            "account_delay_max_ms": self.account_delay_max_ms,
            "account_delay_seconds": self.account_delay_seconds,
            "group_delay_min_ms": self.group_delay_min_ms,
            "group_delay_max_ms": self.group_delay_max_ms,
            "group_delay_seconds": self.group_delay_seconds,
            "interval_ms": self.interval_ms,
            "interval_seconds": self.interval_seconds,
            "daily_window_enabled": self.daily_window_enabled,
            "daily_start_time": self.daily_start_time,
            "daily_end_time": self.daily_end_time,
            "message_mode": self.message_mode,
            "text": self.text,
            "template_ids": self.template_ids,
            "template_id": self.template_id,
            "last_run_at": self.last_run_at,
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

    default_task_account_rotate_mode: str = ACCOUNT_ROTATE_MODE_ROUND_ROBIN
    default_task_account_delay_min_ms: int = 0
    default_task_account_delay_max_ms: int = 0
    default_task_group_rotate_mode: str = GROUP_ROTATE_MODE_ROUND_ROBIN
    default_task_group_delay_min_ms: int = 0
    default_task_group_delay_max_ms: int = 0
    default_task_message_mode: str = MESSAGE_MODE_TEMPLATE
    default_task_schedule_mode: str = SCHEDULE_MODE_INTERVAL
    default_task_interval_ms: int = 3600000
    default_task_daily_time: str = "09:00"
    default_task_daily_window_enabled: bool = False
    default_task_daily_start_time: str = "09:00"
    default_task_daily_end_time: str = "21:00"

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
        self.default_send_interval_seconds = max(0.0, _to_float(self.default_send_interval_seconds, 1.0))
        self.template_source_account_name = str(self.template_source_account_name or "").strip()
        self.template_source_chat_id = _to_int(self.template_source_chat_id, 0)
        self.ad_probability = _normalize_probability(self.ad_probability, 75)
        self.noise_probability = _normalize_probability(self.noise_probability, 22)
        self.skip_probability = _normalize_probability(self.skip_probability, 3)
        self.default_account_enabled = _to_bool(self.default_account_enabled, True)
        self.default_group_enabled = _to_bool(self.default_group_enabled, True)
        self.default_template_enabled = _to_bool(self.default_template_enabled, True)
        self.default_session_name_follow_account = _to_bool(self.default_session_name_follow_account, True)
        self.default_group_username_normalize = _to_bool(self.default_group_username_normalize, True)
        self.default_task_account_delay_min_ms, self.default_task_account_delay_max_ms = _normalize_delay_range(
            self.default_task_account_delay_min_ms,
            self.default_task_account_delay_max_ms,
        )
        self.default_task_group_delay_min_ms, self.default_task_group_delay_max_ms = _normalize_delay_range(
            self.default_task_group_delay_min_ms,
            self.default_task_group_delay_max_ms,
        )
        self.default_task_message_mode = _normalize_message_mode(self.default_task_message_mode)
        self.default_task_interval_ms = _to_non_negative_int(self.default_task_interval_ms, 3600000)
        self.default_task_daily_window_enabled = _to_bool(self.default_task_daily_window_enabled, False)
        self.default_task_daily_start_time = _normalize_time(self.default_task_daily_start_time or self.default_task_daily_time, "09:00")
        self.default_task_daily_end_time = _normalize_time(self.default_task_daily_end_time, "21:00")
        self.default_task_daily_time = self.default_task_daily_start_time

        self.global_font_size = _to_positive_int(self.global_font_size, 13)
        self.table_font_size = _to_positive_int(self.table_font_size, 13)
        self.button_font_size = _to_positive_int(self.button_font_size, 13)
        self.input_font_size = _to_positive_int(self.input_font_size, 13)
        self.floating_panel_font_size = _to_positive_int(self.floating_panel_font_size, 13)
        self.account_panel_font_size = _to_positive_int(self.account_panel_font_size, self.floating_panel_font_size)
        self.account_panel_width = _to_positive_int(self.account_panel_width, 520)
        self.account_panel_height = _to_positive_int(self.account_panel_height, 620)
        self.group_panel_font_size = _to_positive_int(self.group_panel_font_size, self.floating_panel_font_size)
        self.group_panel_width = _to_positive_int(self.group_panel_width, 520)
        self.group_panel_height = _to_positive_int(self.group_panel_height, 620)
        self.task_panel_font_size = _to_positive_int(self.task_panel_font_size, self.floating_panel_font_size)
        self.task_panel_width = _to_positive_int(self.task_panel_width, 680)
        self.task_panel_height = _to_positive_int(self.task_panel_height, 760)
        self.template_panel_font_size = _to_positive_int(self.template_panel_font_size, self.floating_panel_font_size)
        self.template_panel_width = _to_positive_int(self.template_panel_width, 520)
        self.template_panel_height = _to_positive_int(self.template_panel_height, 520)
        self.config_auto_save_debounce_ms = max(100, _to_positive_int(self.config_auto_save_debounce_ms, 400))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        safe_data = data if isinstance(data, dict) else {}
        kwargs = {field_name: safe_data.get(field_name, getattr(cls(), field_name)) for field_name in cls().__dataclass_fields__.keys()}
        return cls(**kwargs)

    @property
    def probability_total(self) -> int:
        return self.ad_probability + self.noise_probability + self.skip_probability

    @property
    def probability_is_valid(self) -> bool:
        return self.probability_total == 100

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

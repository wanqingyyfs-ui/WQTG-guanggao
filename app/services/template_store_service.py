from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config_loader import load_templates, save_templates
from app.core.models import (
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
    TemplateConfig,
)


class TemplateStoreService:
    def __init__(self, file_path: str | Path, log_func=None):
        self.file_path = Path(file_path).expanduser()
        self.log = log_func
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, level: str, msg: str) -> None:
        if callable(self.log):
            self.log(str(level or "INFO").upper(), str(msg or ""))

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return str(value)

    @classmethod
    def _normalize_message_ids(cls, message_ids: Any) -> list[int]:
        if message_ids is None:
            return []

        if isinstance(message_ids, int):
            raw_items = [message_ids]
        elif isinstance(message_ids, str):
            raw_items = [item.strip() for item in message_ids.split(",")]
        elif isinstance(message_ids, list | tuple | set):
            raw_items = list(message_ids)
        else:
            return []

        result: list[int] = []

        for item in raw_items:
            message_id = cls._safe_int(item, 0)

            if message_id > 0 and message_id not in result:
                result.append(message_id)

        return result

    @classmethod
    def _template_key(cls, template: TemplateConfig) -> tuple[str, int, tuple[int, ...]]:
        account_name = cls._safe_text(template.source_account_name).strip()
        chat_id = cls._safe_int(template.source_chat_id, 0)
        message_ids = tuple(cls._normalize_message_ids(template.source_message_ids))

        return account_name, chat_id, message_ids

    @classmethod
    def _normalize_template(cls, template: TemplateConfig) -> TemplateConfig:
        template.template_id = cls._safe_text(template.template_id).strip() or uuid.uuid4().hex
        template.template_name = cls._safe_text(template.template_name).strip() or (
            f"模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        template.source_account_name = cls._safe_text(
            template.source_account_name
        ).strip()
        template.source_chat_id = cls._safe_int(template.source_chat_id, 0)
        template.source_chat_title = cls._safe_text(template.source_chat_title).strip()
        template.source_message_ids = cls._normalize_message_ids(
            template.source_message_ids
        )

        template.message_type = cls._safe_text(
            template.message_type,
            TEMPLATE_MESSAGE_TYPE_TEXT,
        ).strip() or TEMPLATE_MESSAGE_TYPE_TEXT

        template.send_mode = cls._safe_text(
            template.send_mode,
            TEMPLATE_SEND_MODE_FORWARD,
        ).strip() or TEMPLATE_SEND_MODE_FORWARD

        template.preview_text = cls._safe_text(template.preview_text)
        template.raw_text = cls._safe_text(template.raw_text)
        template.has_custom_emoji = bool(template.has_custom_emoji)
        template.has_media = bool(template.has_media)
        template.media_count = max(
            cls._safe_int(template.media_count, len(template.source_message_ids)),
            0,
        )
        template.preview_images = [
            cls._safe_text(item).strip()
            for item in template.preview_images
            if cls._safe_text(item).strip()
        ]
        template.enabled = bool(template.enabled)
        template.created_at = cls._safe_text(template.created_at).strip() or (
            datetime.now().isoformat(timespec="seconds")
        )

        return template

    def load_all(self) -> list[TemplateConfig]:
        try:
            templates = load_templates(self.file_path)
        except FileNotFoundError:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            save_templates(str(self.file_path), [])
            return []
        except Exception as exc:
            self._log("error", f"读取模板库失败: {exc}")
            return []

        return [self._normalize_template(template) for template in templates]

    def save_all(self, templates: list[TemplateConfig]) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            normalized_templates = [
                self._normalize_template(template)
                for template in templates
            ]
            save_templates(str(self.file_path), normalized_templates)
        except Exception as exc:
            self._log("error", f"保存模板库失败: {exc}")
            raise

    def add_template(self, template: TemplateConfig) -> bool:
        normalized_template = self._normalize_template(template)

        if not normalized_template.source_account_name:
            self._log("warning", "模板来源账号为空，已跳过入库")
            return False

        if not normalized_template.source_chat_id:
            self._log(
                "warning",
                f"模板来源 Chat ID 为空，已跳过入库 | template={normalized_template.template_name}",
            )
            return False

        if not normalized_template.source_message_ids:
            self._log(
                "warning",
                f"模板来源消息 ID 为空，已跳过入库 | template={normalized_template.template_name}",
            )
            return False

        templates = self.load_all()
        new_key = self._template_key(normalized_template)

        for existing_template in templates:
            if self._template_key(existing_template) == new_key:
                self._log(
                    "info",
                    "模板重复，已跳过 | "
                    f"account={normalized_template.source_account_name} | "
                    f"chat_id={normalized_template.source_chat_id} | "
                    f"message_ids={normalized_template.source_message_ids}",
                )
                return False

        templates.append(normalized_template)
        self.save_all(templates)

        self._log(
            "info",
            f"模板已入库：{normalized_template.template_name} | "
            f"account={normalized_template.source_account_name} | "
            f"chat_id={normalized_template.source_chat_id} | "
            f"message_ids={normalized_template.source_message_ids}",
        )
        return True

    def create_template(
        self,
        account_name: str,
        chat_id: int,
        chat_title: str,
        message_ids: list[int],
        text: str,
        has_media: bool,
    ) -> TemplateConfig:
        safe_account_name = self._safe_text(account_name).strip()
        safe_chat_id = self._safe_int(chat_id, 0)
        safe_chat_title = self._safe_text(chat_title).strip()
        safe_message_ids = self._normalize_message_ids(message_ids)
        safe_text = self._safe_text(text).strip()
        created_at = datetime.now().isoformat(timespec="seconds")

        message_type = (
            TEMPLATE_MESSAGE_TYPE_PHOTO
            if has_media
            else TEMPLATE_MESSAGE_TYPE_TEXT
        )

        return TemplateConfig(
            template_id=uuid.uuid4().hex,
            template_name=f"模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            source_account_name=safe_account_name,
            source_chat_id=safe_chat_id,
            source_chat_title=safe_chat_title,
            source_message_ids=safe_message_ids,
            message_type=message_type,
            send_mode=TEMPLATE_SEND_MODE_FORWARD,
            preview_text=safe_text[:80],
            raw_text=safe_text,
            has_custom_emoji=False,
            has_media=bool(has_media),
            media_count=len(safe_message_ids) if has_media else 0,
            preview_images=[],
            enabled=True,
            created_at=created_at,
        )
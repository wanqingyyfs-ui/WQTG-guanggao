from __future__ import annotations
from pathlib import Path

import uuid
from datetime import datetime

from app.core.models import TemplateConfig
from app.core.config_loader import load_templates, save_templates


class TemplateStoreService:
    def __init__(self, file_path: str | Path, log_func=None):
        self.file_path = Path(file_path).expanduser()
        self.log = log_func

    def _log(self, level: str, msg: str):
        if callable(self.log):
            self.log(level, msg)

    def load_all(self) -> list[TemplateConfig]:
        try:
            return load_templates(self.file_path)
        except Exception:
            return []

    def save_all(self, templates: list[TemplateConfig]):
        save_templates(self.file_path, templates)

    def add_template(self, template: TemplateConfig):
        templates = self.load_all()

        # 防重复（根据消息ID判断）
        for t in templates:
            if set(t.source_message_ids) == set(template.source_message_ids):
                self._log("info", "模板重复，已跳过")
                return

        templates.append(template)
        self.save_all(templates)

        self._log(
            "info",
            f"模板已入库：{template.template_name} | message_ids={template.source_message_ids}",
        )

    def create_template(
        self,
        account_name: str,
        chat_id: int,
        chat_title: str,
        message_ids: list[int],
        text: str,
        has_media: bool,
    ) -> TemplateConfig:

        return TemplateConfig(
            template_id=uuid.uuid4().hex,
            template_name=f"模板_{datetime.now().strftime('%H%M%S')}",
            source_account_name=account_name,
            source_chat_id=chat_id,
            source_chat_title=chat_title,
            source_message_ids=message_ids,
            message_type="photo" if has_media else "text",
            send_mode="forward",
            preview_text=text[:50],
            raw_text=text,
            has_custom_emoji="emoji" in text,
            has_media=has_media,
            media_count=len(message_ids),
            preview_images=[],
            enabled=True,
            created_at=str(datetime.now()),
        )
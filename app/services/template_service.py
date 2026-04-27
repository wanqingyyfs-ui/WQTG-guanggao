from __future__ import annotations

from typing import Iterable

from app.core.models import (
    TemplateConfig,
    TEMPLATE_SEND_MODE_FORWARD,
)


class TemplateSender:
    def __init__(self, templates: Iterable[TemplateConfig] | None = None, log_func=None):
        self.log_func = log_func
        self.templates: dict[str, TemplateConfig] = {}
        self.update_templates(list(templates or []))

    def update_templates(self, templates: list[TemplateConfig]) -> None:
        self.templates = {item.template_id: item for item in templates if item.template_id}

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    def get_template(self, template_id: str) -> TemplateConfig | None:
        if not template_id:
            return None
        return self.templates.get(template_id)

    async def send_template_by_rule(self, account_name: str, client, event, rule) -> bool:
        """
        当前第一阶段只支持：
        - rule.reply_mode == template
        - template.send_mode == forward

        后续再扩展 clone。
        """
        template = self.get_template(rule.template_id)
        if template is None:
            self._log(
                "warning",
                f"[{account_name}] 模板不存在 | rule={rule.rule_name} | template_id={rule.template_id}",
            )
            return False

        if not template.enabled:
            self._log(
                "warning",
                f"[{account_name}] 模板未启用 | rule={rule.rule_name} | template_id={rule.template_id}",
            )
            return False

        if not template.source_message_ids:
            self._log(
                "warning",
                f"[{account_name}] 模板没有来源消息ID | rule={rule.rule_name} | template_id={rule.template_id}",
            )
            return False

        if template.send_mode != TEMPLATE_SEND_MODE_FORWARD:
            self._log(
                "warning",
                f"[{account_name}] 当前仅支持 forward 模式 | "
                f"rule={rule.rule_name} | template_id={rule.template_id} | send_mode={template.send_mode}",
            )
            return False

        try:
            target_peer = await event.get_input_chat()

            source_peer = await client.get_input_entity(template.source_chat_id)

            await client.forward_messages(
                entity=target_peer,
                messages=template.source_message_ids,
                from_peer=source_peer,
            )

            self._log(
                "info",
                f"[{account_name}] 模板转发成功 | "
                f"rule={rule.rule_name} | template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | source_message_ids={template.source_message_ids}",
            )
            return True

        except Exception as exc:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败 | "
                f"rule={rule.rule_name} | template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={template.source_message_ids} | error={exc}",
            )
            return False
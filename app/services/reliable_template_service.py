from __future__ import annotations

from telethon.errors import FloodWaitError

from app.core.models import TemplateConfig
from app.services.template_service import TemplateSender

try:
    from telethon.errors import WorkerBusyTooLongRetryError
except ImportError:  # pragma: no cover - compatibility with older Telethon
    class WorkerBusyTooLongRetryError(Exception):
        pass


class ReliableTemplateSender(TemplateSender):
    """Forward templates while preserving the original Telegram exception."""

    async def send_template_to_chat(
        self,
        account_name: str,
        client,
        template_id: str,
        target_chat_id: int,
    ) -> bool:
        safe_template_id = str(template_id or "").strip()
        template = self.get_template(safe_template_id)
        if template is None:
            self._log("warning", f"[{account_name}] 模板不存在 | template_id={safe_template_id}")
            return False

        source_message_ids = self._validate_template(
            account_name=account_name,
            template=template,
            target_chat_id=target_chat_id,
        )
        if source_message_ids is None:
            raise RuntimeError(
                f"模板配置无效或未启用：template_id={safe_template_id}"
            )

        # Resolve peers without swallowing Telegram exceptions, so the task result
        # can distinguish private/inaccessible/invalid peers from generic failures.
        target_peer = await client.get_input_entity(target_chat_id)
        source_peer = await client.get_input_entity(template.source_chat_id)

        # The grouped runtime intentionally uses Telegram ForwardMessagesRequest.
        # It does not silently switch to clone/text mode after an error.
        return await self._send_template_by_forward(
            account_name=account_name,
            client=client,
            template=template,
            source_peer=source_peer,
            target_peer=target_peer,
            target_chat_id=target_chat_id,
            source_message_ids=source_message_ids,
        )

    async def _send_template_by_forward(
        self,
        account_name: str,
        client,
        template: TemplateConfig,
        source_peer,
        target_peer,
        target_chat_id: int,
        source_message_ids: list[int],
    ) -> bool:
        try:
            await client.forward_messages(
                entity=target_peer,
                messages=source_message_ids,
                from_peer=source_peer,
            )
            self._log(
                "info",
                f"[{account_name}] 模板转发成功 | template={template.template_name} | "
                f"target_chat_id={target_chat_id} | source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids}",
            )
            return True
        except FloodWaitError as exc:
            self._log(
                "warning",
                f"[{account_name}] 模板转发触发 FloodWait | seconds={getattr(exc, 'seconds', 0)} | "
                f"template={template.template_name} | target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | source_message_ids={source_message_ids}",
            )
            raise
        except WorkerBusyTooLongRetryError as exc:
            self._log(
                "warning",
                f"[{account_name}] Telegram 工作节点繁忙，转发结果不确定，已停止本次请求重试 | "
                f"template={template.template_name} | target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | error={exc}",
            )
            raise RuntimeError(f"Telegram工作节点繁忙（WorkerBusyTooLongRetryError）：{exc}") from exc
        except Exception as exc:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败 | error_type={type(exc).__name__} | "
                f"template={template.template_name} | target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | source_message_ids={source_message_ids} | "
                f"error={exc}",
            )
            raise

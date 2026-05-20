from __future__ import annotations

from typing import Any, Iterable

from telethon.errors import (
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerIdInvalidError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from app.core.models import (
    TEMPLATE_SEND_MODE_CLONE,
    TEMPLATE_SEND_MODE_FORWARD,
    TemplateConfig,
)


class TemplateSender:
    def __init__(self, templates: Iterable[TemplateConfig] | None = None, log_func=None):
        self.log_func = log_func
        self.templates: dict[str, TemplateConfig] = {}
        self.update_templates(list(templates or []))

    def update_templates(self, templates: list[TemplateConfig]) -> None:
        self.templates = {
            str(item.template_id or "").strip(): item
            for item in templates
            if str(item.template_id or "").strip()
        }

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_message_ids(cls, value: Any) -> list[int]:
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
            message_id = cls._safe_int(item, 0)

            if message_id > 0 and message_id not in result:
                result.append(message_id)

        return result

    def get_template(self, template_id: str) -> TemplateConfig | None:
        safe_template_id = str(template_id or "").strip()

        if not safe_template_id:
            return None

        return self.templates.get(safe_template_id)

    def has_template(self, template_id: str) -> bool:
        return self.get_template(template_id) is not None

    def get_enabled_template_ids(self) -> list[str]:
        return [
            template_id
            for template_id, template in self.templates.items()
            if bool(getattr(template, "enabled", True))
        ]

    def _validate_template(
        self,
        account_name: str,
        template: TemplateConfig,
        target_chat_id: int,
    ) -> list[int] | None:
        if not template.enabled:
            self._log(
                "warning",
                f"[{account_name}] 模板未启用 | template_id={template.template_id}",
            )
            return None

        source_chat_id = self._safe_int(
            getattr(template, "source_chat_id", 0),
            0,
        )
        if not source_chat_id:
            self._log(
                "warning",
                f"[{account_name}] 模板来源 Chat ID 为空 | "
                f"template_id={template.template_id}",
            )
            return None

        safe_target_chat_id = self._safe_int(target_chat_id, 0)
        if not safe_target_chat_id:
            self._log(
                "warning",
                f"[{account_name}] 模板目标 Chat ID 为空 | "
                f"template_id={template.template_id}",
            )
            return None

        source_message_ids = self._normalize_message_ids(
            getattr(template, "source_message_ids", []),
        )
        if not source_message_ids:
            self._log(
                "warning",
                f"[{account_name}] 模板没有有效来源消息 ID | "
                f"template_id={template.template_id}",
            )
            return None

        send_mode = self._get_template_send_mode(template)
        if send_mode not in {TEMPLATE_SEND_MODE_FORWARD, TEMPLATE_SEND_MODE_CLONE}:
            self._log(
                "warning",
                f"[{account_name}] 不支持的模板发送模式 | "
                f"template_id={template.template_id} | send_mode={send_mode}",
            )
            return None

        return source_message_ids

    @staticmethod
    def _get_template_send_mode(template: TemplateConfig) -> str:
        send_mode = str(
            getattr(template, "send_mode", TEMPLATE_SEND_MODE_FORWARD) or ""
        ).strip()

        if send_mode in {TEMPLATE_SEND_MODE_FORWARD, TEMPLATE_SEND_MODE_CLONE}:
            return send_mode

        return TEMPLATE_SEND_MODE_FORWARD

    async def _resolve_target_peer(
        self,
        account_name: str,
        client,
        template: TemplateConfig,
        target_chat_id: int,
    ):
        try:
            return await client.get_input_entity(target_chat_id)
        except PeerIdInvalidError:
            self._log(
                "error",
                f"[{account_name}] 模板目标 Chat ID 无效或账号无法解析目标会话 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return None
        except ChannelPrivateError:
            self._log(
                "error",
                f"[{account_name}] 模板目标群组/频道不可访问 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return None

    async def _resolve_source_peer(
        self,
        account_name: str,
        client,
        template: TemplateConfig,
    ):
        try:
            return await client.get_input_entity(template.source_chat_id)
        except PeerIdInvalidError:
            self._log(
                "error",
                f"[{account_name}] 模板来源 Chat ID 无效或账号无法解析来源会话 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id}",
            )
            return None
        except ChannelPrivateError:
            self._log(
                "error",
                f"[{account_name}] 模板来源群组/频道不可访问 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id}",
            )
            return None

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
            self._log(
                "warning",
                f"[{account_name}] 模板不存在 | template_id={safe_template_id}",
            )
            return False

        source_message_ids = self._validate_template(
            account_name=account_name,
            template=template,
            target_chat_id=target_chat_id,
        )
        if source_message_ids is None:
            return False

        target_peer = await self._resolve_target_peer(
            account_name=account_name,
            client=client,
            template=template,
            target_chat_id=target_chat_id,
        )
        if target_peer is None:
            return False

        source_peer = await self._resolve_source_peer(
            account_name=account_name,
            client=client,
            template=template,
        )
        if source_peer is None:
            return False

        send_mode = self._get_template_send_mode(template)

        if send_mode == TEMPLATE_SEND_MODE_CLONE:
            return await self._send_template_by_clone(
                account_name=account_name,
                client=client,
                template=template,
                source_peer=source_peer,
                target_peer=target_peer,
                target_chat_id=target_chat_id,
                source_message_ids=source_message_ids,
            )

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
                f"[{account_name}] 模板转发成功 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids}",
            )
            return True

        except FloodWaitError as exc:
            self._log(
                "warning",
                f"[{account_name}] 模板转发触发 FloodWait | "
                f"seconds={getattr(exc, 'seconds', 0)} | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id}",
            )
            raise

        except ChatWriteForbiddenError:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败，账号没有目标群发言权限 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except UserBannedInChannelError:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败，账号在目标群/频道中被限制或封禁 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except UserNotParticipantError:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败，账号不是来源群或目标群成员 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except ChannelPrivateError:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败，来源群或目标群不可访问 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except PeerIdInvalidError:
            self._log(
                "error",
                f"[{account_name}] 模板转发失败，来源或目标 Peer 无效 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except ValueError as exc:
            self._log(
                "error",
                f"[{account_name}] 模板转发参数无效 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids} | error={exc}",
            )
            return False

        except Exception as exc:
            self._log(
                "error",
                f"[{account_name}] 模板转发未知异常 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids} | "
                f"error={exc}",
            )
            return False

    async def _send_template_by_clone(
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
            messages = await client.get_messages(
                source_peer,
                ids=source_message_ids,
            )
            message_list = self._normalize_loaded_messages(messages)

            if not message_list:
                self._log(
                    "warning",
                    f"[{account_name}] clone 模式未读取到来源消息 | "
                    f"template={template.template_name} | "
                    f"source_message_ids={source_message_ids}",
                )
                return False

            for message in message_list:
                await self._clone_one_message(
                    client=client,
                    target_peer=target_peer,
                    message=message,
                )

            self._log(
                "info",
                f"[{account_name}] 模板克隆发送成功 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids}",
            )
            return True

        except FloodWaitError as exc:
            self._log(
                "warning",
                f"[{account_name}] 模板克隆触发 FloodWait | "
                f"seconds={getattr(exc, 'seconds', 0)} | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id}",
            )
            raise

        except ChatWriteForbiddenError:
            self._log(
                "error",
                f"[{account_name}] 模板克隆失败，账号没有目标群发言权限 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except UserBannedInChannelError:
            self._log(
                "error",
                f"[{account_name}] 模板克隆失败，账号在目标群/频道中被限制或封禁 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except UserNotParticipantError:
            self._log(
                "error",
                f"[{account_name}] 模板克隆失败，账号不是来源群或目标群成员 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except ChannelPrivateError:
            self._log(
                "error",
                f"[{account_name}] 模板克隆失败，来源群或目标群不可访问 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except PeerIdInvalidError:
            self._log(
                "error",
                f"[{account_name}] 模板克隆失败，来源或目标 Peer 无效 | "
                f"template={template.template_name} | "
                f"source_chat_id={template.source_chat_id} | "
                f"target_chat_id={target_chat_id}",
            )
            return False

        except ValueError as exc:
            self._log(
                "error",
                f"[{account_name}] 模板克隆参数无效 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids} | error={exc}",
            )
            return False

        except Exception as exc:
            self._log(
                "error",
                f"[{account_name}] 模板克隆未知异常 | "
                f"template={template.template_name} | "
                f"target_chat_id={target_chat_id} | "
                f"source_chat_id={template.source_chat_id} | "
                f"source_message_ids={source_message_ids} | "
                f"error={exc}",
            )
            return False

    @staticmethod
    def _normalize_loaded_messages(messages: Any) -> list[Any]:
        if messages is None:
            return []

        if isinstance(messages, list):
            raw_items = messages
        elif isinstance(messages, tuple):
            raw_items = list(messages)
        else:
            raw_items = [messages]

        return [message for message in raw_items if message is not None]

    @staticmethod
    def _message_text(message: Any) -> str:
        raw_text = getattr(message, "raw_text", None)

        if raw_text:
            return str(raw_text)

        text = getattr(message, "message", None)

        if text:
            return str(text)

        return ""

    @staticmethod
    def _message_entities(message: Any):
        entities = getattr(message, "entities", None)

        if entities:
            return entities

        return None

    async def _clone_one_message(self, client, target_peer, message: Any) -> None:
        text = self._message_text(message)
        entities = self._message_entities(message)
        media = getattr(message, "media", None)

        if media is not None:
            kwargs: dict[str, Any] = {
                "entity": target_peer,
                "file": media,
            }

            if text:
                kwargs["caption"] = text

            if entities is not None:
                kwargs["formatting_entities"] = entities

            await client.send_file(**kwargs)
            return

        kwargs = {
            "entity": target_peer,
            "message": text,
        }

        if entities is not None:
            kwargs["formatting_entities"] = entities

        await client.send_message(**kwargs)
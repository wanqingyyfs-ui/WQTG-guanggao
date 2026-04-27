from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Callable

from telethon import errors
from telethon.tl.types import User

from app.core.matcher import KeywordMatcher
from app.core.models import (
    RuleConfig,
    Settings,
    RULE_TYPE_FIRST_CONTACT,
    REPLY_MODE_TEMPLATE,
)
from app.core.utils import safe_text_preview


class MessageHandler:
    def __init__(
        self,
        log_func: Callable[[str, str], None],
        rules: list[RuleConfig],
        settings: Settings,
        user_state_store,
        template_sender=None,
    ):
        self.log = log_func
        self.rules = rules
        self.settings = settings
        self.user_state_store = user_state_store
        self.template_sender = template_sender
        self.matcher = KeywordMatcher(rules, settings.match_options)

        self._processed_messages: OrderedDict[tuple[str, int, int], float] = OrderedDict()
        self._processed_cache_limit = 5000
        self._processed_ttl_seconds = 600

    def update_rules_and_settings(self, rules: list[RuleConfig], settings: Settings) -> None:
        self.rules = rules
        self.settings = settings
        self.matcher.update(rules, settings.match_options)

    def _cleanup_processed_cache(self) -> None:
        now = time.time()
        expired_keys = []

        for key, ts in self._processed_messages.items():
            if now - ts > self._processed_ttl_seconds:
                expired_keys.append(key)
            else:
                break

        for key in expired_keys:
            self._processed_messages.pop(key, None)

        while len(self._processed_messages) > self._processed_cache_limit:
            self._processed_messages.popitem(last=False)

    def _is_duplicate_message(self, account_name: str, chat_id: int, message_id: int) -> bool:
        self._cleanup_processed_cache()
        key = (account_name, chat_id, message_id)

        if key in self._processed_messages:
            return True

        self._processed_messages[key] = time.time()
        return False

    async def _should_process(self, event, client_me_id: int) -> bool:
        if self.settings.only_private_chat and not event.is_private:
            return False

        if self.settings.ignore_outgoing and event.out:
            return False

        if event.message is None:
            return False

        if getattr(event.message, "action", None) is not None:
            return False

        raw_text = event.raw_text or ""

        sender = await event.get_sender()
        if sender is None:
            return False

        if self.settings.ignore_self and getattr(sender, "id", None) == client_me_id:
            return False

        if self.settings.ignore_bots and isinstance(sender, User) and getattr(sender, "bot", False):
            return False

        return True

    async def _extract_sender_display(self, event) -> str:
        sender = await event.get_sender()
        if sender is None:
            return "unknown"

        username = getattr(sender, "username", None)
        sender_id = getattr(sender, "id", None)
        first_name = getattr(sender, "first_name", None)

        if username:
            return f"@{username}({sender_id})"
        if first_name:
            return f"{first_name}({sender_id})"
        return str(sender_id)

    def _get_first_contact_rules(self) -> list[RuleConfig]:
        return [
            rule
            for rule in self.rules
            if rule.enabled and rule.rule_type == RULE_TYPE_FIRST_CONTACT
        ]

    async def _send_one_rule(
        self,
        account_name: str,
        client,
        event,
        sender_display: str,
        rule: RuleConfig,
        reason: str,
    ) -> bool:
        try:
            if rule.reply_mode == REPLY_MODE_TEMPLATE:
                if self.template_sender is None:
                    self.log(
                        "warning",
                        f"[{account_name}] 模板发送器未配置，已跳过 | reason={reason} | rule={rule.rule_name}",
                    )
                    return False

                sent = await self.template_sender.send_template_by_rule(
                    account_name=account_name,
                    client=client,
                    event=event,
                    rule=rule,
                )

                if sent:
                    self.log(
                        "info",
                        f"[{account_name}] 模板回复成功 | reason={reason} | rule={rule.rule_name} | sender={sender_display}",
                    )
                else:
                    self.log(
                        "warning",
                        f"[{account_name}] 模板回复未执行 | reason={reason} | rule={rule.rule_name} | sender={sender_display}",
                    )
                return sent

            await event.reply(rule.reply_text)
            self.log(
                "info",
                f"[{account_name}] 回复成功 | reason={reason} | rule={rule.rule_name} | sender={sender_display}",
            )
            return True

        except errors.FloodWaitError as exc:
            self.log(
                "warning",
                f"[{account_name}] FloodWait | 等待秒数={exc.seconds} | "
                f"reason={reason} | rule={rule.rule_name} | sender={sender_display}",
            )
            return False
        except Exception as exc:
            self.log(
                "error",
                f"[{account_name}] 回复失败 | reason={reason} | rule={rule.rule_name} | "
                f"sender={sender_display} | error={exc}",
            )
            return False

    async def _send_rule_replies(
        self,
        account_name: str,
        client,
        event,
        sender_display: str,
        matched_rules: list[RuleConfig],
        reason: str,
    ) -> None:
        if not matched_rules:
            return

        self.log(
            "info",
            f"[{account_name}] 即将发送 {len(matched_rules)} 条回复 | reason={reason} | "
            f"rules={[rule.rule_name for rule in matched_rules]} | sender={sender_display}",
        )

        for index, rule in enumerate(matched_rules):
            await self._send_one_rule(
                account_name=account_name,
                client=client,
                event=event,
                sender_display=sender_display,
                rule=rule,
                reason=reason,
            )

            if index < len(matched_rules) - 1 and self.settings.reply_interval_seconds > 0:
                await asyncio.sleep(self.settings.reply_interval_seconds)

    async def handle_new_message(self, account_name: str, client, event) -> None:
        try:
            me = await client.get_me()
            me_id = me.id

            if not await self._should_process(event, me_id):
                return

            sender = await event.get_sender()
            sender_id = int(getattr(sender, "id", 0))
            sender_display = await self._extract_sender_display(event)
            message_text = event.raw_text or ""

            chat = await event.get_chat()
            chat_id = int(getattr(chat, "id", 0))
            message_id = int(getattr(event.message, "id", 0))

            if chat_id and message_id:
                if self._is_duplicate_message(account_name, chat_id, message_id):
                    self.log(
                        "warning",
                        f"[{account_name}] 检测到重复消息事件，已跳过 | "
                        f"sender={sender_display} | chat_id={chat_id} | message_id={message_id}",
                    )
                    return

            self.log(
                "info",
                f"[{account_name}] 收到消息 | sender={sender_display} | "
                f"content={safe_text_preview(message_text)}",
            )

            is_first_contact = self.user_state_store.is_first_contact(account_name, sender_id)

            if is_first_contact:
                self.user_state_store.mark_contacted(
                    account_name=account_name,
                    user_id=sender_id,
                    sender_display=sender_display,
                    last_message=message_text,
                )

                first_contact_rules = self._get_first_contact_rules()
                if first_contact_rules:
                    await self._send_rule_replies(
                        account_name=account_name,
                        client=client,
                        event=event,
                        sender_display=sender_display,
                        matched_rules=first_contact_rules,
                        reason="first_contact",
                    )

            matched_keyword_rules = self.matcher.match_all_in_order(message_text)

            if matched_keyword_rules:
                await self._send_rule_replies(
                    account_name=account_name,
                    client=client,
                    event=event,
                    sender_display=sender_display,
                    matched_rules=matched_keyword_rules,
                    reason="keyword",
                )
            else:
                if message_text.strip():
                    self.log(
                        "info",
                        f"[{account_name}] 未命中关键词规则 | sender={sender_display}",
                    )
                else:
                    self.log(
                        "info",
                        f"[{account_name}] 非文本消息，不进行关键词匹配 | sender={sender_display}",
                    )

        except Exception as exc:
            self.log("error", f"[{account_name}] 处理消息异常: {exc}")
from __future__ import annotations

import random
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.models import SEND_DECISION_AD, SEND_DECISION_NOISE, SEND_DECISION_SKIP
from app.services.group_send_service import GroupSendService, SendResult
from app.services.telegram_entity_resolver import TelegramEntityResolver


class ReliableGroupSendService(GroupSendService):
    """Adds exact probability audit data, entity recovery and result classification."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decision_details: ContextVar[dict[str, Any] | None] = ContextVar(
            "wqtg_send_decision_details",
            default=None,
        )
        self._active_group: ContextVar[Any | None] = ContextVar(
            "wqtg_active_send_group",
            default=None,
        )

    def _choose_decision(self, settings, rng: random.Random | None = None) -> str:
        random_source = rng if rng is not None else random
        ad_probability = self._safe_probability(getattr(settings, "ad_probability", 75), 75)
        noise_probability = self._safe_probability(getattr(settings, "noise_probability", 22), 22)
        skip_probability = self._safe_probability(getattr(settings, "skip_probability", 3), 3)
        total = ad_probability + noise_probability + skip_probability

        if total <= 0:
            decision = SEND_DECISION_AD
            roll = 0.0
            total = 1
        else:
            # random() is in [0, 1), so a configured zero-probability bucket can never be hit.
            roll = float(random_source.random()) * total
            if roll < ad_probability:
                decision = SEND_DECISION_AD
            elif roll < ad_probability + noise_probability:
                decision = SEND_DECISION_NOISE
            else:
                decision = SEND_DECISION_SKIP

        self._decision_details.set({
            "probability_roll": round(roll, 6),
            "probability_total": total,
            "configured_ad_probability": ad_probability,
            "configured_noise_probability": noise_probability,
            "configured_skip_probability": skip_probability,
            "actual_ad_probability": round(ad_probability * 100 / total, 6),
            "actual_noise_probability": round(noise_probability * 100 / total, 6),
            "actual_skip_probability": round(skip_probability * 100 / total, 6),
            "decision": decision,
        })
        return decision

    async def execute_task(self, *args, **kwargs) -> SendResult:
        group = kwargs.get("group")
        if group is None and len(args) >= 3:
            group = args[2]
        group_token = self._active_group.set(group)
        decision_token = self._decision_details.set(None)
        try:
            result = await super().execute_task(*args, **kwargs)
            self._enrich_result(result, self._decision_details.get())
            return result
        finally:
            self._decision_details.reset(decision_token)
            self._active_group.reset(group_token)

    def _current_group_metadata(self, chat_id: int) -> tuple[str, str]:
        group = self._active_group.get()
        if group is None:
            return "", ""
        group_chat_id = self._safe_int(getattr(group, "chat_id", 0), 0)
        if group_chat_id and group_chat_id != self._safe_int(chat_id, 0):
            return "", ""
        return (
            str(getattr(group, "username", "") or "").strip(),
            str(getattr(group, "group_name", "") or "").strip(),
        )

    async def send_text_to_chat(
        self,
        account_name: str,
        client,
        chat_id: int,
        text: str,
    ) -> bool:
        safe_text = str(text or "").strip()
        if not safe_text:
            self._log("warning", f"[{account_name}] 文本消息为空，已跳过 | chat_id={chat_id}")
            return False
        if not chat_id:
            self._log("warning", f"[{account_name}] 目标 Chat ID 为空，已跳过文本发送")
            return False

        username, title = self._current_group_metadata(chat_id)
        resolved = await TelegramEntityResolver(log_func=self._log).resolve(
            account_name,
            client,
            chat_id=chat_id,
            username=username,
            title=title,
            role="目标群",
        )
        self._log(
            "info",
            f"[{account_name}] 文本目标群实体解析完成 | strategy={resolved.strategy} | "
            f"chat_id={chat_id} | username={username or '-'}",
        )
        await client.send_message(resolved.peer, safe_text)
        return True

    async def send_template_to_chat(
        self,
        account_name: str,
        client,
        chat_id: int,
        template_id: str,
    ) -> bool:
        safe_template_id = str(template_id or "").strip()
        if not safe_template_id:
            self._log(
                "warning",
                f"[{account_name}] 模板 ID 为空，已跳过 | chat_id={chat_id}",
            )
            return False
        if not self._template_exists_and_enabled(safe_template_id):
            self._log(
                "warning",
                f"[{account_name}] 模板不存在或未启用，已跳过 | "
                f"template_id={safe_template_id} | chat_id={chat_id}",
            )
            return False
        if not chat_id:
            self._log(
                "warning",
                f"[{account_name}] 目标 Chat ID 为空，已跳过模板发送 | "
                f"template_id={safe_template_id}",
            )
            return False

        username, title = self._current_group_metadata(chat_id)
        return await self.template_sender.send_template_to_chat(
            account_name=account_name,
            client=client,
            template_id=safe_template_id,
            target_chat_id=chat_id,
            target_chat_username=username,
            target_chat_title=title,
        )

    def _enrich_result(self, result: SendResult, decision_details: dict[str, Any] | None) -> None:
        setattr(result, "attempt_id", uuid4().hex)
        for key, value in dict(decision_details or {}).items():
            setattr(result, key, value)

        group = self._active_group.get()
        setattr(result, "target_chat_username", str(getattr(group, "username", "") or ""))
        setattr(result, "target_chat_title", str(getattr(group, "group_name", "") or ""))

        template_id = str(getattr(result, "selected_template_id", "") or "").strip()
        template = self.template_sender.get_template(template_id) if template_id else None
        if template is not None:
            setattr(result, "template_name", str(getattr(template, "template_name", "") or ""))
            setattr(result, "template_send_mode", str(getattr(template, "send_mode", "") or ""))
            setattr(result, "source_chat_id", int(getattr(template, "source_chat_id", 0) or 0))
            setattr(
                result,
                "source_message_ids",
                self.template_sender._normalize_message_ids(
                    getattr(template, "source_message_ids", [])
                ),
            )
        else:
            setattr(result, "template_name", "")
            setattr(result, "template_send_mode", "")
            setattr(result, "source_chat_id", 0)
            setattr(result, "source_message_ids", [])

        error = str(getattr(result, "error", "") or "")
        flood_wait_seconds = max(0, int(getattr(result, "flood_wait_seconds", 0) or 0))
        status = str(getattr(result, "status", "") or "failed")
        category = status
        error_type = ""

        if flood_wait_seconds > 0:
            status = category = "flood_wait"
            error_type = "FloodWaitError"
            cooldown_until = datetime.now() + timedelta(seconds=flood_wait_seconds + 3)
            setattr(result, "retry_after_seconds", flood_wait_seconds)
            setattr(result, "cooldown_until", cooldown_until.isoformat(timespec="seconds"))
        elif status == "success":
            category = "success"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif status == "skipped":
            category = "skipped"
            error_type = "Skipped"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "ENTITY_UNRESOLVED" in error:
            status = category = "entity_unresolved"
            error_type = "InputEntityNotFound"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "WorkerBusyTooLongRetryError" in error or "Telegram工作节点繁忙" in error or "workers are too busy" in error.lower():
            status = category = "telegram_busy"
            error_type = "WorkerBusyTooLongRetryError"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "没有该群组发言权限" in error or "限制或封禁" in error:
            status = category = "blocked"
            error_type = "ChatWriteForbiddenOrBanned"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "不是目标群组成员" in error or "不是来源群或目标群成员" in error:
            status = category = "not_participant"
            error_type = "UserNotParticipantError"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "不可访问" in error or "私有群" in error:
            status = category = "unavailable"
            error_type = "ChannelPrivateError"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        elif "Chat ID 无效" in error or "Peer 无效" in error:
            status = category = "invalid_target"
            error_type = "PeerIdInvalidError"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")
        else:
            status = category = "failed"
            error_type = "SendError"
            setattr(result, "retry_after_seconds", 0)
            setattr(result, "cooldown_until", "")

        result.status = status
        setattr(result, "result_category", category)
        setattr(result, "error_type", error_type)
        setattr(
            result,
            "reason_detail",
            error or str(getattr(result, "skip_reason", "") or "") or "发送成功",
        )

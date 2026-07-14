from __future__ import annotations

import random
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.models import SEND_DECISION_AD, SEND_DECISION_NOISE, SEND_DECISION_SKIP
from app.services.group_send_service import GroupSendService, SendResult


class ReliableGroupSendService(GroupSendService):
    """Adds exact probability audit data and detailed result classification."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decision_details: ContextVar[dict[str, Any] | None] = ContextVar(
            "wqtg_send_decision_details",
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
        token = self._decision_details.set(None)
        try:
            result = await super().execute_task(*args, **kwargs)
            self._enrich_result(result, self._decision_details.get())
            return result
        finally:
            self._decision_details.reset(token)

    def _enrich_result(self, result: SendResult, decision_details: dict[str, Any] | None) -> None:
        setattr(result, "attempt_id", uuid4().hex)
        for key, value in dict(decision_details or {}).items():
            setattr(result, key, value)

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

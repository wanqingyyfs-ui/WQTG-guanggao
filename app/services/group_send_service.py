from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from telethon.errors import (
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerIdInvalidError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_SINGLE,
    LOG_MESSAGE_MODE_NOISE,
    LOG_MESSAGE_MODE_SKIP,
    LOG_MESSAGE_MODE_TEMPLATE,
    LOG_MESSAGE_MODE_TEXT,
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    SEND_DECISION_AD,
    SEND_DECISION_NOISE,
    SEND_DECISION_SKIP,
    SEND_STATUS_FAILED,
    SEND_STATUS_SKIPPED,
    SEND_STATUS_SUCCESS,
    GroupConfig,
    SendTaskConfig,
    Settings,
)
from app.services.noise_pool_service import NoisePoolService
from app.services.template_service import TemplateSender


@dataclass
class SendResult:
    task_id: str
    task_name: str
    account_name: str
    group_id: str
    chat_id: int
    status: str
    error: str = ""
    started_at: str = ""
    finished_at: str = ""

    decision: str = SEND_DECISION_AD
    message_mode: str = LOG_MESSAGE_MODE_TEMPLATE
    selected_template_id: str = ""
    template_id: str = ""
    template_ids: list[str] = field(default_factory=list)
    configured_template_ids: list[str] = field(default_factory=list)
    enabled_template_ids: list[str] = field(default_factory=list)
    noise_text_preview: str = ""
    skip_reason: str = ""

    ad_probability: int = 75
    noise_probability: int = 22
    skip_probability: int = 3

    rotate_mode: str = ACCOUNT_ROTATE_MODE_SINGLE
    account_index: int = 0
    selected_account_name: str = ""
    account_pool: list[str] = field(default_factory=list)
    account_pool_size: int = 0

    group_rotate_mode: str = GROUP_ROTATE_MODE_SINGLE
    group_index: int = 0
    selected_group_id: str = ""
    selected_group_name: str = ""
    group_pool: list[str] = field(default_factory=list)
    group_pool_size: int = 0

    account_delay_min_ms: int = 0
    account_delay_max_ms: int = 0
    group_delay_min_ms: int = 0
    group_delay_max_ms: int = 0
    actual_account_delay_ms: int = 0
    actual_group_delay_ms: int = 0

    account_delay_seconds: int = 0
    group_delay_seconds: int = 0
    flood_wait_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "account_name": self.account_name,
            "group_id": self.group_id,
            "chat_id": self.chat_id,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "decision": self.decision,
            "message_mode": self.message_mode,
            "selected_template_id": self.selected_template_id,
            "template_id": self.template_id,
            "template_ids": self.template_ids,
            "configured_template_ids": self.configured_template_ids,
            "enabled_template_ids": self.enabled_template_ids,
            "noise_text_preview": self.noise_text_preview,
            "skip_reason": self.skip_reason,
            "ad_probability": self.ad_probability,
            "noise_probability": self.noise_probability,
            "skip_probability": self.skip_probability,
            "rotate_mode": self.rotate_mode,
            "account_index": self.account_index,
            "selected_account_name": self.selected_account_name,
            "account_pool": self.account_pool,
            "account_pool_size": self.account_pool_size,
            "group_rotate_mode": self.group_rotate_mode,
            "group_index": self.group_index,
            "selected_group_id": self.selected_group_id,
            "selected_group_name": self.selected_group_name,
            "group_pool": self.group_pool,
            "group_pool_size": self.group_pool_size,
            "account_delay_min_ms": self.account_delay_min_ms,
            "account_delay_max_ms": self.account_delay_max_ms,
            "group_delay_min_ms": self.group_delay_min_ms,
            "group_delay_max_ms": self.group_delay_max_ms,
            "actual_account_delay_ms": self.actual_account_delay_ms,
            "actual_group_delay_ms": self.actual_group_delay_ms,
            "account_delay_seconds": self.account_delay_seconds,
            "group_delay_seconds": self.group_delay_seconds,
            "flood_wait_seconds": self.flood_wait_seconds,
        }


class GroupSendService:
    def __init__(
        self,
        template_sender: TemplateSender,
        noise_pool_service: NoisePoolService,
        log_func=None,
    ):
        self.template_sender = template_sender
        self.noise_pool_service = noise_pool_service
        self.log_func = log_func

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _now_text() -> str:
        return datetime.now().isoformat(timespec="milliseconds")

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _safe_non_negative_int(cls, value, default: int = 0) -> int:
        number = cls._safe_int(value, default)

        if number < 0:
            return 0

        return number

    @staticmethod
    def _safe_text_list(value: Any) -> list[str]:
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

    @classmethod
    def _safe_probability(cls, value: Any, default: int) -> int:
        number = cls._safe_int(value, default)

        if number < 0:
            return 0

        if number > 100:
            return 100

        return number

    @staticmethod
    def _task_account_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            ACCOUNT_ROTATE_MODE_SINGLE,
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        }:
            return ACCOUNT_ROTATE_MODE_SINGLE

        return rotate_mode

    @staticmethod
    def _task_group_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "group_rotate_mode", GROUP_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            GROUP_ROTATE_MODE_SINGLE,
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        }:
            return GROUP_ROTATE_MODE_SINGLE

        return rotate_mode

    @staticmethod
    def _task_account_pool(
        task: SendTaskConfig,
        account_name: str,
    ) -> list[str]:
        account_pool: list[str] = []

        for raw_account_name in getattr(task, "account_names", []) or []:
            value = str(raw_account_name or "").strip()

            if value and value not in account_pool:
                account_pool.append(value)

        selected_account_name = str(account_name or "").strip()

        if selected_account_name and selected_account_name not in account_pool:
            account_pool.insert(0, selected_account_name)

        return account_pool

    @staticmethod
    def _task_group_pool(
        task: SendTaskConfig,
        group: GroupConfig,
    ) -> list[str]:
        group_pool: list[str] = []

        for raw_group_id in getattr(task, "group_ids", []) or []:
            value = str(raw_group_id or "").strip()

            if value and value not in group_pool:
                group_pool.append(value)

        selected_group_id = str(getattr(group, "group_id", "") or "").strip()
        legacy_group_id = str(getattr(task, "group_id", "") or "").strip()

        if legacy_group_id and legacy_group_id not in group_pool:
            group_pool.insert(0, legacy_group_id)

        if selected_group_id and selected_group_id not in group_pool:
            group_pool.append(selected_group_id)

        return group_pool

    @staticmethod
    def _configured_template_pool(task: SendTaskConfig) -> list[str]:
        template_pool: list[str] = []

        for raw_template_id in getattr(task, "template_ids", []) or []:
            value = str(raw_template_id or "").strip()

            if value and value not in template_pool:
                template_pool.append(value)

        legacy_template_id = str(getattr(task, "template_id", "") or "").strip()

        if legacy_template_id and legacy_template_id not in template_pool:
            template_pool.insert(0, legacy_template_id)

        return template_pool

    def _template_exists_and_enabled(self, template_id: str) -> bool:
        safe_template_id = str(template_id or "").strip()

        if not safe_template_id:
            return False

        template = None

        if hasattr(self.template_sender, "get_template"):
            template = self.template_sender.get_template(safe_template_id)
        elif hasattr(self.template_sender, "templates"):
            templates = getattr(self.template_sender, "templates", {}) or {}
            if isinstance(templates, dict):
                template = templates.get(safe_template_id)

        if template is None:
            return False

        return bool(getattr(template, "enabled", True))

    def _enabled_template_pool(self, task: SendTaskConfig) -> list[str]:
        return [
            template_id
            for template_id in self._configured_template_pool(task)
            if self._template_exists_and_enabled(template_id)
        ]

    def _account_index(
        self,
        task: SendTaskConfig,
        account_name: str,
        account_pool: list[str],
    ) -> int:
        selected_account_name = str(account_name or "").strip()

        if selected_account_name in account_pool:
            return account_pool.index(selected_account_name)

        current_index = self._safe_int(
            getattr(task, "current_account_index", 0),
            0,
        )

        if not account_pool:
            return 0

        return max(0, current_index) % len(account_pool)

    def _group_index(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        group_pool: list[str],
    ) -> int:
        selected_group_id = str(getattr(group, "group_id", "") or "").strip()

        if selected_group_id in group_pool:
            return group_pool.index(selected_group_id)

        current_index = self._safe_int(
            getattr(task, "current_group_index", 0),
            0,
        )

        if not group_pool:
            return 0

        return max(0, current_index) % len(group_pool)

    def _build_result(
        self,
        account_name: str,
        group: GroupConfig,
        task: SendTaskConfig,
        settings: Settings,
        started_at: str,
    ) -> SendResult:
        account_pool = self._task_account_pool(task, account_name)
        group_pool = self._task_group_pool(task, group)
        configured_template_pool = self._configured_template_pool(task)
        enabled_template_pool = self._enabled_template_pool(task)

        account_index = self._account_index(
            task=task,
            account_name=account_name,
            account_pool=account_pool,
        )
        group_index = self._group_index(
            task=task,
            group=group,
            group_pool=group_pool,
        )

        account_delay_min_ms = self._safe_non_negative_int(
            getattr(task, "account_delay_min_ms", 0),
            0,
        )
        account_delay_max_ms = self._safe_non_negative_int(
            getattr(task, "account_delay_max_ms", account_delay_min_ms),
            account_delay_min_ms,
        )
        if account_delay_max_ms < account_delay_min_ms:
            account_delay_max_ms = account_delay_min_ms

        group_delay_min_ms = self._safe_non_negative_int(
            getattr(task, "group_delay_min_ms", 0),
            0,
        )
        group_delay_max_ms = self._safe_non_negative_int(
            getattr(task, "group_delay_max_ms", group_delay_min_ms),
            group_delay_min_ms,
        )
        if group_delay_max_ms < group_delay_min_ms:
            group_delay_max_ms = group_delay_min_ms

        return SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status=SEND_STATUS_FAILED,
            started_at=started_at,
            template_id=str(getattr(task, "template_id", "") or "").strip(),
            template_ids=enabled_template_pool,
            configured_template_ids=configured_template_pool,
            enabled_template_ids=enabled_template_pool,
            ad_probability=self._safe_probability(
                getattr(settings, "ad_probability", 75),
                75,
            ),
            noise_probability=self._safe_probability(
                getattr(settings, "noise_probability", 22),
                22,
            ),
            skip_probability=self._safe_probability(
                getattr(settings, "skip_probability", 3),
                3,
            ),
            rotate_mode=self._task_account_rotate_mode(task),
            account_index=account_index,
            selected_account_name=account_name,
            account_pool=account_pool,
            account_pool_size=len(account_pool),
            group_rotate_mode=self._task_group_rotate_mode(task),
            group_index=group_index,
            selected_group_id=str(group.group_id or ""),
            selected_group_name=str(group.group_name or ""),
            group_pool=group_pool,
            group_pool_size=len(group_pool),
            account_delay_min_ms=account_delay_min_ms,
            account_delay_max_ms=account_delay_max_ms,
            group_delay_min_ms=group_delay_min_ms,
            group_delay_max_ms=group_delay_max_ms,
            account_delay_seconds=int(account_delay_min_ms // 1000),
            group_delay_seconds=int(group_delay_min_ms // 1000),
        )

    def _choose_decision(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> str:
        random_source = rng if rng is not None else random

        ad_probability = self._safe_probability(
            getattr(settings, "ad_probability", 75),
            75,
        )
        noise_probability = self._safe_probability(
            getattr(settings, "noise_probability", 22),
            22,
        )
        skip_probability = self._safe_probability(
            getattr(settings, "skip_probability", 3),
            3,
        )

        total = ad_probability + noise_probability + skip_probability

        if total <= 0:
            return SEND_DECISION_AD

        hit = random_source.uniform(0, total)

        if hit < ad_probability:
            return SEND_DECISION_AD

        if hit < ad_probability + noise_probability:
            return SEND_DECISION_NOISE

        return SEND_DECISION_SKIP

    def _choose_template_id(
        self,
        task: SendTaskConfig,
        rng: random.Random | None = None,
    ) -> str:
        random_source = rng if rng is not None else random
        template_pool = self._enabled_template_pool(task)

        if not template_pool:
            return ""

        return random_source.choice(template_pool)

    @staticmethod
    def _mark_skipped(
        result: SendResult,
        reason: str,
        message_mode: str | None = None,
    ) -> None:
        result.status = SEND_STATUS_SKIPPED
        result.error = reason
        result.skip_reason = reason

        if message_mode:
            result.message_mode = message_mode

    async def send_text_to_chat(
        self,
        account_name: str,
        client,
        chat_id: int,
        text: str,
    ) -> bool:
        safe_text = str(text or "").strip()

        if not safe_text:
            self._log(
                "warning",
                f"[{account_name}] 文本消息为空，已跳过 | chat_id={chat_id}",
            )
            return False

        if not chat_id:
            self._log(
                "warning",
                f"[{account_name}] 目标 Chat ID 为空，已跳过文本发送",
            )
            return False

        target_peer = await client.get_input_entity(chat_id)
        await client.send_message(target_peer, safe_text)
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

        return await self.template_sender.send_template_to_chat(
            account_name=account_name,
            client=client,
            template_id=safe_template_id,
            target_chat_id=chat_id,
        )

    async def execute_task(
        self,
        account_name: str,
        client,
        group: GroupConfig,
        task: SendTaskConfig,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> SendResult:
        started_at = self._now_text()
        result = self._build_result(
            account_name=account_name,
            group=group,
            task=task,
            settings=settings,
            started_at=started_at,
        )

        try:
            if not getattr(task, "enabled", True):
                reason = "任务未启用"
                self._mark_skipped(result, reason)
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务跳过，任务未启用 | task={task.task_name}",
                )
                return result

            if not group.enabled:
                reason = "目标群组未启用"
                self._mark_skipped(result, reason)
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务跳过，目标群组未启用 | "
                    f"task={task.task_name} | group={group.group_name}",
                )
                return result

            if not group.chat_id:
                reason = "目标 Chat ID 为空"
                self._mark_skipped(result, reason)
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务跳过，目标 Chat ID 为空 | "
                    f"task={task.task_name} | group={group.group_name}",
                )
                return result

            decision = self._choose_decision(settings=settings, rng=rng)
            result.decision = decision

            if decision == SEND_DECISION_SKIP:
                reason = "命中跳过概率，本轮不发送"
                self._mark_skipped(result, reason, LOG_MESSAGE_MODE_SKIP)
                self._log(
                    "info",
                    f"[{account_name}] 命中跳过概率，本轮不发送 | "
                    f"task={task.task_name} | group={group.group_name} | "
                    f"chat_id={group.chat_id}",
                )
                return result

            if decision == SEND_DECISION_NOISE:
                noise_text = self.noise_pool_service.choose_random(rng=rng)

                if not noise_text:
                    reason = "命中噪音概率，但噪音池为空，本轮跳过"
                    self._mark_skipped(result, reason, LOG_MESSAGE_MODE_NOISE)
                    self._log(
                        "warning",
                        f"[{account_name}] 命中噪音概率，但噪音池为空，本轮跳过 | "
                        f"task={task.task_name} | group={group.group_name} | "
                        f"chat_id={group.chat_id}",
                    )
                    return result

                result.message_mode = LOG_MESSAGE_MODE_NOISE
                result.noise_text_preview = noise_text[:120]
                ok = await self.send_text_to_chat(
                    account_name=account_name,
                    client=client,
                    chat_id=group.chat_id,
                    text=noise_text,
                )

            else:
                if task.message_mode == MESSAGE_MODE_TEXT:
                    text = str(getattr(task, "text", "") or "").strip()
                    if not text:
                        reason = "文本内容为空，本轮跳过"
                        self._mark_skipped(result, reason, LOG_MESSAGE_MODE_TEXT)
                        self._log(
                            "warning",
                            f"[{account_name}] 文本内容为空，本轮跳过 | "
                            f"task={task.task_name} | group={group.group_name}",
                        )
                        return result

                    result.message_mode = LOG_MESSAGE_MODE_TEXT
                    ok = await self.send_text_to_chat(
                        account_name=account_name,
                        client=client,
                        chat_id=group.chat_id,
                        text=text,
                    )

                elif task.message_mode == MESSAGE_MODE_TEMPLATE:
                    selected_template_id = self._choose_template_id(
                        task=task,
                        rng=rng,
                    )
                    result.message_mode = LOG_MESSAGE_MODE_TEMPLATE
                    result.selected_template_id = selected_template_id
                    result.template_id = selected_template_id

                    if not selected_template_id:
                        reason = "没有可用的已启用模板，本轮跳过"
                        self._mark_skipped(result, reason, LOG_MESSAGE_MODE_TEMPLATE)
                        self._log(
                            "warning",
                            f"[{account_name}] 没有可用的已启用模板，本轮跳过 | "
                            f"task={task.task_name} | group={group.group_name} | "
                            f"configured_template_ids={result.configured_template_ids}",
                        )
                        return result

                    ok = await self.send_template_to_chat(
                        account_name=account_name,
                        client=client,
                        chat_id=group.chat_id,
                        template_id=selected_template_id,
                    )

                else:
                    reason = f"不支持的消息类型: {task.message_mode}"
                    self._mark_skipped(result, reason)
                    self._log(
                        "warning",
                        f"[{account_name}] 不支持的消息类型 | "
                        f"task={task.task_name} | message_mode={task.message_mode}",
                    )
                    return result

            if ok:
                result.status = SEND_STATUS_SUCCESS
                self._log(
                    "info",
                    f"[{account_name}] 群发任务执行成功 | "
                    f"task={task.task_name} | "
                    f"group={group.group_name} | "
                    f"chat_id={group.chat_id} | "
                    f"decision={result.decision} | "
                    f"message_mode={result.message_mode} | "
                    f"template_id={result.selected_template_id} | "
                    f"account_rotate_mode={result.rotate_mode} | "
                    f"account_index={result.account_index} | "
                    f"group_rotate_mode={result.group_rotate_mode} | "
                    f"group_index={result.group_index}",
                )
            else:
                result.status = SEND_STATUS_FAILED
                if not result.error:
                    result.error = "发送服务返回失败"
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务执行失败 | "
                    f"task={task.task_name} | "
                    f"group={group.group_name} | "
                    f"chat_id={group.chat_id} | "
                    f"decision={result.decision} | "
                    f"message_mode={result.message_mode} | "
                    f"template_id={result.selected_template_id} | "
                    f"account_rotate_mode={result.rotate_mode} | "
                    f"account_index={result.account_index} | "
                    f"group_rotate_mode={result.group_rotate_mode} | "
                    f"group_index={result.group_index}",
                )

            return result

        except FloodWaitError as exc:
            result.status = SEND_STATUS_FAILED
            result.flood_wait_seconds = self._safe_non_negative_int(
                getattr(exc, "seconds", 0),
                0,
            )
            result.error = f"FloodWait，需要等待 {result.flood_wait_seconds} 秒"

            self._log(
                "warning",
                f"[{account_name}] 触发 FloodWait，已记录失败并释放调度槽 | "
                f"seconds={result.flood_wait_seconds} | "
                f"task={task.task_name} | "
                f"group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except ChatWriteForbiddenError:
            result.status = SEND_STATUS_FAILED
            result.error = "账号没有该群组发言权限"
            self._log(
                "error",
                f"[{account_name}] 账号没有群组发言权限 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except UserBannedInChannelError:
            result.status = SEND_STATUS_FAILED
            result.error = "账号在该群组/频道中被限制或封禁"
            self._log(
                "error",
                f"[{account_name}] 账号在目标群被限制或封禁 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except ChannelPrivateError:
            result.status = SEND_STATUS_FAILED
            result.error = "目标群组/频道不可访问，可能是私有群或账号未加入"
            self._log(
                "error",
                f"[{account_name}] 目标群组/频道不可访问 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except UserNotParticipantError:
            result.status = SEND_STATUS_FAILED
            result.error = "账号不是目标群组成员"
            self._log(
                "error",
                f"[{account_name}] 账号不是目标群组成员 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except PeerIdInvalidError:
            result.status = SEND_STATUS_FAILED
            result.error = "目标 Chat ID 无效或账号无法解析该会话"
            self._log(
                "error",
                f"[{account_name}] 目标 Chat ID 无效 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except Exception as exc:
            result.status = SEND_STATUS_FAILED
            result.error = str(exc)
            self._log(
                "error",
                f"[{account_name}] 群发任务异常 | "
                f"task={task.task_name} | "
                f"group={group.group_name} | "
                f"chat_id={group.chat_id} | "
                f"decision={result.decision} | "
                f"message_mode={result.message_mode} | "
                f"template_id={result.selected_template_id} | "
                f"account_rotate_mode={result.rotate_mode} | "
                f"account_index={result.account_index} | "
                f"group_rotate_mode={result.group_rotate_mode} | "
                f"group_index={result.group_index} | "
                f"error={exc}",
            )
            return result

        finally:
            result.finished_at = self._now_text()

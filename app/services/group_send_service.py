from __future__ import annotations

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
    GroupConfig,
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    SendTaskConfig,
)
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

    account_delay_seconds: int = 0
    group_delay_seconds: int = 0
    flood_wait_seconds: int = 0

    message_mode: str = MESSAGE_MODE_TEXT
    template_id: str = ""

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
            "account_delay_seconds": self.account_delay_seconds,
            "group_delay_seconds": self.group_delay_seconds,
            "flood_wait_seconds": self.flood_wait_seconds,
            "message_mode": self.message_mode,
            "template_id": self.template_id,
        }


class GroupSendService:
    def __init__(
        self,
        template_sender: TemplateSender,
        log_func=None,
    ):
        self.template_sender = template_sender
        self.log_func = log_func

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _now_text() -> str:
        return datetime.now().isoformat(timespec="seconds")

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
        started_at: str,
    ) -> SendResult:
        account_pool = self._task_account_pool(task, account_name)
        group_pool = self._task_group_pool(task, group)

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

        return SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status="failed",
            started_at=started_at,
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
            account_delay_seconds=self._safe_non_negative_int(
                getattr(task, "account_delay_seconds", 0),
                0,
            ),
            group_delay_seconds=self._safe_non_negative_int(
                getattr(task, "group_delay_seconds", 0),
                0,
            ),
            message_mode=str(task.message_mode or MESSAGE_MODE_TEXT),
            template_id=str(task.template_id or ""),
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
    ) -> SendResult:
        started_at = self._now_text()
        result = self._build_result(
            account_name=account_name,
            group=group,
            task=task,
            started_at=started_at,
        )

        try:
            if not group.enabled:
                result.error = "目标群组未启用"
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务跳过，目标群组未启用 | "
                    f"task={task.task_name} | group={group.group_name}",
                )
                return result

            if not group.chat_id:
                result.error = "目标 Chat ID 为空"
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务跳过，目标 Chat ID 为空 | "
                    f"task={task.task_name} | group={group.group_name}",
                )
                return result

            if task.message_mode == MESSAGE_MODE_TEXT:
                ok = await self.send_text_to_chat(
                    account_name=account_name,
                    client=client,
                    chat_id=group.chat_id,
                    text=task.text,
                )
            elif task.message_mode == MESSAGE_MODE_TEMPLATE:
                ok = await self.send_template_to_chat(
                    account_name=account_name,
                    client=client,
                    chat_id=group.chat_id,
                    template_id=task.template_id,
                )
            else:
                result.error = f"不支持的消息类型: {task.message_mode}"
                self._log(
                    "warning",
                    f"[{account_name}] 不支持的消息类型 | "
                    f"task={task.task_name} | message_mode={task.message_mode}",
                )
                return result

            if ok:
                result.status = "success"
                self._log(
                    "info",
                    f"[{account_name}] 群发任务执行成功 | "
                    f"task={task.task_name} | "
                    f"group={group.group_name} | "
                    f"chat_id={group.chat_id} | "
                    f"account_rotate_mode={result.rotate_mode} | "
                    f"account_index={result.account_index} | "
                    f"group_rotate_mode={result.group_rotate_mode} | "
                    f"group_index={result.group_index}",
                )
            else:
                result.error = "发送服务返回失败"
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务执行失败 | "
                    f"task={task.task_name} | "
                    f"group={group.group_name} | "
                    f"chat_id={group.chat_id} | "
                    f"account_rotate_mode={result.rotate_mode} | "
                    f"account_index={result.account_index} | "
                    f"group_rotate_mode={result.group_rotate_mode} | "
                    f"group_index={result.group_index}",
                )

            return result

        except FloodWaitError as exc:
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
            result.error = "账号没有该群组发言权限"
            self._log(
                "error",
                f"[{account_name}] 账号没有群组发言权限 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except UserBannedInChannelError:
            result.error = "账号在该群组/频道中被限制或封禁"
            self._log(
                "error",
                f"[{account_name}] 账号在目标群被限制或封禁 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except ChannelPrivateError:
            result.error = "目标群组/频道不可访问，可能是私有群或账号未加入"
            self._log(
                "error",
                f"[{account_name}] 目标群组/频道不可访问 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except UserNotParticipantError:
            result.error = "账号不是目标群组成员"
            self._log(
                "error",
                f"[{account_name}] 账号不是目标群组成员 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except PeerIdInvalidError:
            result.error = "目标 Chat ID 无效或账号无法解析该会话"
            self._log(
                "error",
                f"[{account_name}] 目标 Chat ID 无效 | "
                f"task={task.task_name} | group={group.group_name} | "
                f"chat_id={group.chat_id}",
            )
            return result

        except Exception as exc:
            result.error = str(exc)
            self._log(
                "error",
                f"[{account_name}] 群发任务异常 | "
                f"task={task.task_name} | "
                f"group={group.group_name} | "
                f"chat_id={group.chat_id} | "
                f"account_rotate_mode={result.rotate_mode} | "
                f"account_index={result.account_index} | "
                f"group_rotate_mode={result.group_rotate_mode} | "
                f"group_index={result.group_index} | "
                f"error={exc}",
            )
            return result

        finally:
            result.finished_at = self._now_text()
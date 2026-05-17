from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    UserBannedInChannelError,
)

from app.core.models import (
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

    async def send_text_to_chat(
        self,
        account_name: str,
        client,
        chat_id: int,
        text: str,
    ) -> bool:
        if not text.strip():
            self._log(
                "warning",
                f"[{account_name}] 文本消息为空，已跳过 | chat_id={chat_id}",
            )
            return False

        target_peer = await client.get_input_entity(chat_id)
        await client.send_message(target_peer, text)
        return True

    async def send_template_to_chat(
        self,
        account_name: str,
        client,
        chat_id: int,
        template_id: str,
    ) -> bool:
        return await self.template_sender.send_template_to_chat(
            account_name=account_name,
            client=client,
            template_id=template_id,
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

        result = SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status="failed",
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
                return result

            if ok:
                result.status = "success"
                self._log(
                    "info",
                    f"[{account_name}] 群发任务执行成功 | "
                    f"task={task.task_name} | group={group.group_name} | chat_id={group.chat_id}",
                )
            else:
                result.error = "发送服务返回失败"
                self._log(
                    "warning",
                    f"[{account_name}] 群发任务执行失败 | "
                    f"task={task.task_name} | group={group.group_name} | chat_id={group.chat_id}",
                )

            return result

        except FloodWaitError as exc:
            result.error = f"FloodWait，需要等待 {exc.seconds} 秒"
            self._log(
                "warning",
                f"[{account_name}] 触发 FloodWait | seconds={exc.seconds} | "
                f"task={task.task_name} | chat_id={group.chat_id}",
            )
            await asyncio.sleep(exc.seconds)
            return result

        except ChatWriteForbiddenError:
            result.error = "账号没有该群组发言权限"
            self._log(
                "error",
                f"[{account_name}] 账号没有群组发言权限 | "
                f"task={task.task_name} | chat_id={group.chat_id}",
            )
            return result

        except UserBannedInChannelError:
            result.error = "账号在该群组/频道中被限制或封禁"
            self._log(
                "error",
                f"[{account_name}] 账号在目标群被限制或封禁 | "
                f"task={task.task_name} | chat_id={group.chat_id}",
            )
            return result

        except Exception as exc:
            result.error = str(exc)
            self._log(
                "error",
                f"[{account_name}] 群发任务异常 | "
                f"task={task.task_name} | chat_id={group.chat_id} | error={exc}",
            )
            return result

        finally:
            result.finished_at = self._now_text()
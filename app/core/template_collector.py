from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from telethon import utils as telethon_utils

from app.services.template_store_service import TemplateStoreService


class TemplateCollector:
    def __init__(self, settings, store: TemplateStoreService, log_func):
        self.settings = settings
        self.store = store
        self.log = log_func

        # grouped_id -> list[Message]
        self.album_cache: dict[int, list[Any]] = defaultdict(list)
        # grouped_id -> asyncio.Task
        self.album_tasks: dict[int, asyncio.Task] = {}

    def _log(self, level: str, msg: str) -> None:
        if callable(self.log):
            self.log(level, msg)

    async def handle(self, account_name: str, client, event) -> None:
        """
        只采集：
        1) 指定监听账号
        2) 指定素材群
        3) 新消息（包含自己发的消息）
        """
        try:
            # 先按“监听账号名”过滤
            expected_account = (self.settings.template_source_account_name or "").strip()
            if expected_account and account_name != expected_account:
                return

            chat = await event.get_chat()
            if chat is None:
                return

            # Telethon 中超级群/频道应使用 get_peer_id 获取带 -100 的 marked id
            marked_chat_id = telethon_utils.get_peer_id(chat)
            expected_chat_id = int(self.settings.template_source_chat_id or 0)

            if not expected_chat_id:
                return

            if marked_chat_id != expected_chat_id:
                return

            message = event.message
            if message is None:
                return

            self._log(
                "info",
                f"[模板采集] 命中素材群消息 | account={account_name} | "
                f"chat_id={marked_chat_id} | message_id={message.id}"
            )

            grouped_id = getattr(message, "grouped_id", None)

            # 相册消息：延迟聚合
            if grouped_id:
                self.album_cache[grouped_id].append(message)

                old_task = self.album_tasks.get(grouped_id)
                if old_task and not old_task.done():
                    old_task.cancel()

                self.album_tasks[grouped_id] = asyncio.create_task(
                    self._delayed_flush_album(
                        account_name=account_name,
                        chat=chat,
                        grouped_id=grouped_id,
                        delay=1.2,
                    )
                )
                return

            # 单条消息
            await self._save_single(account_name, chat, message)

        except Exception as exc:
            self._log("error", f"[模板采集] 处理素材群消息失败: {exc}")

    async def _delayed_flush_album(self, account_name: str, chat, grouped_id: int, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._flush_album(account_name, chat, grouped_id)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._log("error", f"[模板采集] 相册聚合失败 | grouped_id={grouped_id} | error={exc}")

    async def _flush_album(self, account_name: str, chat, grouped_id: int) -> None:
        messages = self.album_cache.pop(grouped_id, [])
        self.album_tasks.pop(grouped_id, None)

        if not messages:
            return

        # 按消息 id 排序，保证顺序稳定
        messages.sort(key=lambda m: m.id)

        message_ids = [m.id for m in messages]
        text = ""

        # 优先取最后一条里可见的文本/caption
        for m in reversed(messages):
            candidate = (m.message or m.text or "").strip()
            if candidate:
                text = candidate
                break

        has_media = any(bool(getattr(m, "media", None)) for m in messages)

        template = self.store.create_template(
            account_name=account_name,
            chat_id=telethon_utils.get_peer_id(chat),
            chat_title=getattr(chat, "title", "") or "",
            message_ids=message_ids,
            text=text,
            has_media=has_media,
        )

        # 相册模板标记
        template.message_type = "album"
        template.media_count = len(message_ids)

        self.store.add_template(template)

        self._log(
            "info",
            f"[模板采集] 相册模板已入库 | grouped_id={grouped_id} | message_ids={message_ids}"
        )

    async def _save_single(self, account_name: str, chat, message) -> None:
        text = (message.message or message.text or "").strip()
        has_media = bool(getattr(message, "media", None))

        template = self.store.create_template(
            account_name=account_name,
            chat_id=telethon_utils.get_peer_id(chat),
            chat_title=getattr(chat, "title", "") or "",
            message_ids=[message.id],
            text=text,
            has_media=has_media,
        )

        # 单条消息类型
        template.message_type = "photo" if has_media else "text"
        template.media_count = 1 if has_media else 0

        self.store.add_template(template)

        self._log(
            "info",
            f"[模板采集] 单条模板已入库 | message_id={message.id} | has_media={has_media}"
        )
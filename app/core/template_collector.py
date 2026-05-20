from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from telethon import utils as telethon_utils

try:
    from telethon.tl.types import MessageEntityCustomEmoji
except Exception:
    MessageEntityCustomEmoji = None

from app.core.models import (
    TEMPLATE_MESSAGE_TYPE_ALBUM,
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_FORWARD,
)
from app.services.template_store_service import TemplateStoreService


AlbumKey = tuple[str, int, int]


class TemplateCollector:
    def __init__(self, settings, store: TemplateStoreService, log_func):
        self.settings = settings
        self.store = store
        self.log = log_func

        self.album_cache: dict[AlbumKey, list[Any]] = defaultdict(list)
        self.album_tasks: dict[AlbumKey, asyncio.Task] = {}

    def _log(self, level: str, msg: str) -> None:
        if callable(self.log):
            self.log(str(level or "INFO").upper(), str(msg or ""))

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _message_id(message) -> int:
        return TemplateCollector._safe_int(getattr(message, "id", 0), 0)

    @staticmethod
    def _extract_message_text(message) -> str:
        raw_text = getattr(message, "message", None)

        if raw_text is None:
            raw_text = getattr(message, "text", "")

        return str(raw_text or "").strip()

    @staticmethod
    def _has_media(message) -> bool:
        return bool(getattr(message, "media", None))

    @staticmethod
    def _message_entities(message) -> list[Any]:
        entities = getattr(message, "entities", None)

        if entities is None:
            entities = getattr(message, "formatting_entities", None)

        if not entities:
            return []

        return list(entities)

    @staticmethod
    def _has_custom_emoji(message) -> bool:
        if MessageEntityCustomEmoji is None:
            return False

        for entity in TemplateCollector._message_entities(message):
            if isinstance(entity, MessageEntityCustomEmoji):
                return True

        return False

    @staticmethod
    def _chat_title(chat) -> str:
        title = str(getattr(chat, "title", "") or "").strip()
        if title:
            return title

        username = str(getattr(chat, "username", "") or "").strip()
        if username:
            return username

        return str(getattr(chat, "id", "") or "").strip()

    @staticmethod
    def _marked_chat_id(chat) -> int:
        return int(telethon_utils.get_peer_id(chat))

    def _expected_account_name(self) -> str:
        return str(
            getattr(self.settings, "template_source_account_name", "") or ""
        ).strip()

    def _expected_chat_id(self) -> int:
        return self._safe_int(
            getattr(self.settings, "template_source_chat_id", 0),
            0,
        )

    def _is_expected_account(self, account_name: str) -> bool:
        expected_account = self._expected_account_name()

        if not expected_account:
            return True

        return str(account_name or "").strip() == expected_account

    async def _get_expected_chat_context(self, event) -> tuple[Any, int] | None:
        expected_chat_id = self._expected_chat_id()

        if not expected_chat_id:
            return None

        chat = await event.get_chat()
        if chat is None:
            return None

        marked_chat_id = self._marked_chat_id(chat)

        if marked_chat_id != expected_chat_id:
            return None

        return chat, marked_chat_id

    def _should_skip_message(self, message) -> bool:
        if message is None:
            return True

        message_id = self._message_id(message)
        if message_id <= 0:
            return True

        text = self._extract_message_text(message)
        has_media = self._has_media(message)

        return not text and not has_media

    async def handle(self, account_name: str, client, event) -> None:
        """
        模板采集规则：
        1. 如果配置了素材账号，只采集该账号收到的新消息；
        2. 必须配置素材群 Chat ID；
        3. 只采集素材群内有文本或媒体的消息；
        4. 相册消息按 grouped_id 聚合后保存为 album 模板；
        5. 单条媒体保存为 photo 模板，纯文本保存为 text 模板。
        """
        safe_account_name = str(account_name or "").strip()

        try:
            if not self._is_expected_account(safe_account_name):
                return

            chat_context = await self._get_expected_chat_context(event)
            if chat_context is None:
                return

            chat, marked_chat_id = chat_context
            message = getattr(event, "message", None)

            if self._should_skip_message(message):
                return

            message_id = self._message_id(message)

            self._log(
                "info",
                f"[模板采集] 命中素材群消息 | "
                f"account={safe_account_name} | "
                f"chat_id={marked_chat_id} | "
                f"message_id={message_id}",
            )

            grouped_id = self._safe_int(getattr(message, "grouped_id", 0), 0)

            if grouped_id:
                self._queue_album_message(
                    account_name=safe_account_name,
                    chat=chat,
                    marked_chat_id=marked_chat_id,
                    grouped_id=grouped_id,
                    message=message,
                )
                return

            await self._save_single(
                account_name=safe_account_name,
                chat=chat,
                marked_chat_id=marked_chat_id,
                message=message,
            )

        except Exception as exc:
            self._log("error", f"[模板采集] 处理素材群消息失败: {exc}")

    def _queue_album_message(
        self,
        account_name: str,
        chat,
        marked_chat_id: int,
        grouped_id: int,
        message,
    ) -> None:
        album_key: AlbumKey = (account_name, marked_chat_id, grouped_id)
        message_id = self._message_id(message)

        cached_messages = self.album_cache[album_key]

        if not any(self._message_id(item) == message_id for item in cached_messages):
            cached_messages.append(message)

        old_task = self.album_tasks.get(album_key)
        if old_task is not None and not old_task.done():
            old_task.cancel()

        task = asyncio.create_task(
            self._delayed_flush_album(
                album_key=album_key,
                account_name=account_name,
                chat=chat,
                marked_chat_id=marked_chat_id,
                grouped_id=grouped_id,
                delay=1.2,
            ),
            name=f"template-album-flush-{marked_chat_id}-{grouped_id}",
        )
        task.add_done_callback(
            lambda done_task, key=album_key: self._handle_album_task_done(
                key,
                done_task,
            )
        )

        self.album_tasks[album_key] = task

    def _handle_album_task_done(
        self,
        album_key: AlbumKey,
        task: asyncio.Task,
    ) -> None:
        if task.cancelled():
            return

        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return

        if exception is not None:
            self.album_cache.pop(album_key, None)
            self.album_tasks.pop(album_key, None)
            self._log(
                "error",
                f"[模板采集] 相册聚合任务异常 | key={album_key} | error={exception}",
            )

    async def _delayed_flush_album(
        self,
        album_key: AlbumKey,
        account_name: str,
        chat,
        marked_chat_id: int,
        grouped_id: int,
        delay: float,
    ) -> None:
        try:
            await asyncio.sleep(delay)
            await self._flush_album(
                album_key=album_key,
                account_name=account_name,
                chat=chat,
                marked_chat_id=marked_chat_id,
                grouped_id=grouped_id,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self.album_cache.pop(album_key, None)
            self.album_tasks.pop(album_key, None)
            self._log(
                "error",
                f"[模板采集] 相册聚合失败 | "
                f"chat_id={marked_chat_id} | grouped_id={grouped_id} | error={exc}",
            )

    async def _flush_album(
        self,
        album_key: AlbumKey,
        account_name: str,
        chat,
        marked_chat_id: int,
        grouped_id: int,
    ) -> None:
        messages = self.album_cache.pop(album_key, [])
        self.album_tasks.pop(album_key, None)

        ordered_messages = self._deduplicate_and_sort_messages(messages)

        if not ordered_messages:
            return

        message_ids = [self._message_id(message) for message in ordered_messages]
        text = self._album_text(ordered_messages)
        has_media = any(self._has_media(message) for message in ordered_messages)
        has_custom_emoji = any(
            self._has_custom_emoji(message)
            for message in ordered_messages
        )

        if not text and not has_media:
            self._log(
                "warning",
                f"[模板采集] 相册内容为空，已跳过 | "
                f"chat_id={marked_chat_id} | grouped_id={grouped_id}",
            )
            return

        template = self.store.create_template(
            account_name=account_name,
            chat_id=marked_chat_id,
            chat_title=self._chat_title(chat),
            message_ids=message_ids,
            text=text,
            has_media=has_media,
        )

        template.message_type = TEMPLATE_MESSAGE_TYPE_ALBUM
        template.send_mode = TEMPLATE_SEND_MODE_FORWARD
        template.media_count = len(message_ids)
        template.has_media = has_media
        template.has_custom_emoji = has_custom_emoji
        template.enabled = True

        added = self.store.add_template(template)

        if not added:
            self._log(
                "info",
                f"[模板采集] 相册模板未入库，可能是重复模板或数据不完整 | "
                f"chat_id={marked_chat_id} | "
                f"grouped_id={grouped_id} | "
                f"message_ids={message_ids}",
            )
            return

        self._log(
            "info",
            f"[模板采集] 相册模板已入库 | "
            f"chat_id={marked_chat_id} | "
            f"grouped_id={grouped_id} | "
            f"message_ids={message_ids} | "
            f"has_custom_emoji={has_custom_emoji}",
        )

    @staticmethod
    def _deduplicate_and_sort_messages(messages: list[Any]) -> list[Any]:
        unique_messages: dict[int, Any] = {}

        for message in messages:
            message_id = TemplateCollector._message_id(message)

            if message_id > 0:
                unique_messages[message_id] = message

        return [
            unique_messages[message_id]
            for message_id in sorted(unique_messages)
        ]

    def _album_text(self, messages: list[Any]) -> str:
        for message in reversed(messages):
            text = self._extract_message_text(message)

            if text:
                return text

        return ""

    async def _save_single(
        self,
        account_name: str,
        chat,
        marked_chat_id: int,
        message,
    ) -> None:
        message_id = self._message_id(message)
        text = self._extract_message_text(message)
        has_media = self._has_media(message)
        has_custom_emoji = self._has_custom_emoji(message)

        if not text and not has_media:
            self._log(
                "warning",
                f"[模板采集] 单条消息内容为空，已跳过 | "
                f"chat_id={marked_chat_id} | message_id={message_id}",
            )
            return

        template = self.store.create_template(
            account_name=account_name,
            chat_id=marked_chat_id,
            chat_title=self._chat_title(chat),
            message_ids=[message_id],
            text=text,
            has_media=has_media,
        )

        template.message_type = (
            TEMPLATE_MESSAGE_TYPE_PHOTO
            if has_media
            else TEMPLATE_MESSAGE_TYPE_TEXT
        )
        template.send_mode = TEMPLATE_SEND_MODE_FORWARD
        template.media_count = 1 if has_media else 0
        template.has_media = has_media
        template.has_custom_emoji = has_custom_emoji
        template.enabled = True

        added = self.store.add_template(template)

        if not added:
            self._log(
                "info",
                f"[模板采集] 单条模板未入库，可能是重复模板或数据不完整 | "
                f"chat_id={marked_chat_id} | "
                f"message_id={message_id} | "
                f"has_media={has_media}",
            )
            return

        self._log(
            "info",
            f"[模板采集] 单条模板已入库 | "
            f"chat_id={marked_chat_id} | "
            f"message_id={message_id} | "
            f"has_media={has_media} | "
            f"has_custom_emoji={has_custom_emoji}",
        )
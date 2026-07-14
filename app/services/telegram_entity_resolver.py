from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from telethon import utils
from telethon.errors import ChannelPrivateError, UserNotParticipantError


class EntityResolutionError(ValueError):
    """Raised when the current Telegram account cannot resolve a chat entity."""


@dataclass(frozen=True)
class ResolvedTelegramEntity:
    peer: Any
    strategy: str
    requested_chat_id: int
    requested_username: str = ""


class TelegramEntityResolver:
    """Resolve a peer for the current account and refresh its entity cache once."""

    def __init__(self, log_func=None) -> None:
        self.log_func = log_func

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_username(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text.startswith("@"):
            return text[1:].strip()

        candidate = text
        if "://" not in candidate and candidate.lower().startswith(("t.me/", "telegram.me/")):
            candidate = "https://" + candidate
        if "://" in candidate:
            parsed = urlparse(candidate)
            host = str(parsed.netloc or "").lower()
            if host in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
                path = str(parsed.path or "").strip("/")
                if path and not path.startswith(("+", "joinchat/")):
                    return path.split("/", 1)[0].strip()
        return text

    @classmethod
    def _candidate_values(cls, chat_id: int, username: str) -> list[Any]:
        candidates: list[Any] = []
        normalized_username = cls._normalize_username(username)
        if normalized_username:
            for value in (normalized_username, f"@{normalized_username}"):
                if value not in candidates:
                    candidates.append(value)
        safe_chat_id = cls._safe_int(chat_id)
        if safe_chat_id and safe_chat_id not in candidates:
            candidates.append(safe_chat_id)
        return candidates

    @staticmethod
    def _dialog_entity(dialog: Any) -> Any:
        return getattr(dialog, "entity", dialog)

    @classmethod
    def _peer_id(cls, entity: Any) -> int:
        try:
            return int(utils.get_peer_id(entity))
        except Exception:
            entity_id = cls._safe_int(getattr(entity, "id", 0))
            if not entity_id:
                return 0
            class_name = type(entity).__name__.lower()
            if "channel" in class_name:
                return int(f"-100{entity_id}")
            if "chat" in class_name:
                return -entity_id
            return entity_id

    @classmethod
    def _entity_username(cls, entity: Any) -> str:
        return cls._normalize_username(getattr(entity, "username", ""))

    async def _try_candidate(
        self,
        client,
        candidate: Any,
        *,
        strategy: str,
        chat_id: int,
        username: str,
    ) -> ResolvedTelegramEntity | None:
        try:
            peer = await client.get_input_entity(candidate)
            return ResolvedTelegramEntity(
                peer=peer,
                strategy=strategy,
                requested_chat_id=self._safe_int(chat_id),
                requested_username=str(username or "").strip(),
            )
        except (ChannelPrivateError, UserNotParticipantError):
            raise
        except Exception:
            return None

    async def _load_dialogs(self, client) -> list[Any]:
        dialogs: list[Any] = []
        seen: set[int] = set()

        def append_items(items: Any) -> None:
            for dialog in list(items or []):
                entity = self._dialog_entity(dialog)
                peer_id = self._peer_id(entity)
                marker = peer_id or id(entity)
                if marker in seen:
                    continue
                seen.add(marker)
                dialogs.append(dialog)

        try:
            append_items(await client.get_dialogs(limit=None))
        except TypeError:
            append_items(await client.get_dialogs())
        except Exception:
            pass

        try:
            append_items(await client.get_dialogs(limit=None, archived=True))
        except (TypeError, AttributeError):
            pass
        except Exception:
            pass

        return dialogs

    async def resolve(
        self,
        account_name: str,
        client,
        *,
        chat_id: int,
        username: str = "",
        title: str = "",
        role: str = "目标群",
    ) -> ResolvedTelegramEntity:
        safe_chat_id = self._safe_int(chat_id)
        safe_username = str(username or "").strip()
        safe_title = str(title or "").strip()
        candidates = self._candidate_values(safe_chat_id, safe_username)

        for candidate in candidates:
            resolved = await self._try_candidate(
                client,
                candidate,
                strategy="session_cache",
                chat_id=safe_chat_id,
                username=safe_username,
            )
            if resolved is not None:
                return resolved

        self._log(
            "warning",
            f"[{account_name}] {role}实体未命中当前 Session 缓存，正在刷新 dialogs | "
            f"chat_id={safe_chat_id} | username={safe_username or '-'} | title={safe_title or '-'}",
        )
        dialogs = await self._load_dialogs(client)
        normalized_username = self._normalize_username(safe_username)

        for dialog in dialogs:
            entity = self._dialog_entity(dialog)
            if safe_chat_id and self._peer_id(entity) == safe_chat_id:
                resolved = await self._try_candidate(
                    client,
                    entity,
                    strategy="dialogs_chat_id",
                    chat_id=safe_chat_id,
                    username=safe_username,
                )
                if resolved is not None:
                    return resolved

        if normalized_username:
            for dialog in dialogs:
                entity = self._dialog_entity(dialog)
                if self._entity_username(entity).casefold() == normalized_username.casefold():
                    resolved = await self._try_candidate(
                        client,
                        entity,
                        strategy="dialogs_username",
                        chat_id=safe_chat_id,
                        username=safe_username,
                    )
                    if resolved is not None:
                        return resolved

        for candidate in candidates:
            resolved = await self._try_candidate(
                client,
                candidate,
                strategy="after_dialog_refresh",
                chat_id=safe_chat_id,
                username=safe_username,
            )
            if resolved is not None:
                return resolved

        if normalized_username:
            try:
                entity = await client.get_entity(normalized_username)
                peer = await client.get_input_entity(entity)
                return ResolvedTelegramEntity(
                    peer=peer,
                    strategy="public_username_lookup",
                    requested_chat_id=safe_chat_id,
                    requested_username=safe_username,
                )
            except (ChannelPrivateError, UserNotParticipantError):
                raise
            except Exception:
                pass

        raise EntityResolutionError(
            "ENTITY_UNRESOLVED | "
            f"账号【{account_name}】无法解析{role}实体 | "
            f"chat_id={safe_chat_id} | username={safe_username or '-'} | "
            f"title={safe_title or '-'} | "
            "已刷新当前账号 dialogs 并重试。该账号可能未加入私有群、"
            "Session 尚未缓存该会话，或群组配置缺少可解析的公开 username。"
        )

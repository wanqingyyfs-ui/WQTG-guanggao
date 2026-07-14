from __future__ import annotations

import asyncio

import pytest

from app.core.models import TemplateConfig
from app.services.reliable_template_service import ReliableTemplateSender
from app.services.telegram_entity_resolver import (
    EntityResolutionError,
    TelegramEntityResolver,
)


class FakeChannel:
    def __init__(self, entity_id: int, username: str = "") -> None:
        self.id = entity_id
        self.username = username


class FakeDialog:
    def __init__(self, entity) -> None:
        self.entity = entity


class FakeClient:
    def __init__(self, dialogs=None, public_username: str = "") -> None:
        self.dialogs = list(dialogs or [])
        self.public_username = public_username
        self.dialogs_loaded = False
        self.input_candidates = []
        self.forward_call = None

    async def get_input_entity(self, candidate):
        self.input_candidates.append(candidate)
        if isinstance(candidate, FakeChannel):
            return f"peer:{candidate.id}"
        if isinstance(candidate, str) and candidate.lstrip("@").casefold() == self.public_username.casefold():
            return f"peer:username:{self.public_username}"
        if isinstance(candidate, int) and self.dialogs_loaded:
            for dialog in self.dialogs:
                entity = dialog.entity
                peer_id = int(f"-100{entity.id}")
                if peer_id == candidate:
                    return f"peer:{entity.id}"
        raise ValueError(f"Could not find the input entity for {candidate!r}")

    async def get_dialogs(self, *args, **kwargs):
        self.dialogs_loaded = True
        return self.dialogs

    async def get_entity(self, username):
        if str(username).lstrip("@").casefold() == self.public_username.casefold():
            return FakeChannel(999, self.public_username)
        raise ValueError("username not found")

    async def forward_messages(self, *, entity, messages, from_peer):
        self.forward_call = {
            "entity": entity,
            "messages": list(messages),
            "from_peer": from_peer,
        }


def test_resolver_refreshes_dialogs_and_matches_channel_id() -> None:
    client = FakeClient(
        dialogs=[FakeDialog(FakeChannel(1601148299, "target_group"))]
    )
    result = asyncio.run(
        TelegramEntityResolver().resolve(
            "account-a",
            client,
            chat_id=-1001601148299,
            role="目标群",
        )
    )

    assert result.peer == "peer:1601148299"
    assert result.strategy == "dialogs_chat_id"
    assert client.dialogs_loaded is True


def test_resolver_prefers_configured_public_username() -> None:
    client = FakeClient(public_username="public_group")
    result = asyncio.run(
        TelegramEntityResolver().resolve(
            "account-a",
            client,
            chat_id=-1001601148299,
            username="https://t.me/public_group",
            role="目标群",
        )
    )

    assert result.peer == "peer:username:public_group"
    assert result.strategy == "session_cache"
    assert client.input_candidates[0] == "public_group"
    assert client.dialogs_loaded is False


def test_resolver_reports_clear_entity_unresolved_error() -> None:
    client = FakeClient()
    with pytest.raises(EntityResolutionError, match="ENTITY_UNRESOLVED") as exc_info:
        asyncio.run(
            TelegramEntityResolver().resolve(
                "account-a",
                client,
                chat_id=-1001601148299,
                title="private group",
                role="目标群",
            )
        )

    message = str(exc_info.value)
    assert "已刷新当前账号 dialogs" in message
    assert "可能未加入私有群" in message


def test_template_forward_recovers_target_and_source_from_current_account_dialogs() -> None:
    target = FakeChannel(1601148299, "target_group")
    source = FakeChannel(4405598036, "source_group")
    client = FakeClient(dialogs=[FakeDialog(target), FakeDialog(source)])
    template = TemplateConfig(
        template_id="template-a",
        template_name="template",
        source_account_name="account-a",
        source_chat_id=-1004405598036,
        source_chat_title="source group",
        source_message_ids=[80, 81],
        enabled=True,
    )
    sender = ReliableTemplateSender([template])

    ok = asyncio.run(
        sender.send_template_to_chat(
            account_name="account-a",
            client=client,
            template_id="template-a",
            target_chat_id=-1001601148299,
            target_chat_title="target group",
        )
    )

    assert ok is True
    assert client.forward_call == {
        "entity": "peer:1601148299",
        "messages": [80, 81],
        "from_peer": "peer:4405598036",
    }

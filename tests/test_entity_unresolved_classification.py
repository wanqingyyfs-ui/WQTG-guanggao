from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.group_send_service import SendResult
from app.services.reliable_group_send_service import ReliableGroupSendService


class FakeTemplateSender:
    def __init__(self) -> None:
        self.calls = []

    def get_template(self, template_id: str):
        if template_id == "template-a":
            return SimpleNamespace(enabled=True)
        return None

    async def send_template_to_chat(self, **kwargs):
        self.calls.append(kwargs)
        return True


class FakeNoisePool:
    pass


def test_entity_resolution_failure_has_dedicated_category() -> None:
    service = ReliableGroupSendService(
        template_sender=FakeTemplateSender(),
        noise_pool_service=FakeNoisePool(),
    )
    result = SendResult(
        task_id="task-a",
        task_name="task",
        account_name="account-a",
        group_id="group-a",
        chat_id=-1001601148299,
        status="failed",
        error=(
            "ENTITY_UNRESOLVED | 账号【account-a】无法解析目标群实体 | "
            "chat_id=-1001601148299"
        ),
    )

    service._enrich_result(result, None)

    assert result.status == "entity_unresolved"
    assert result.result_category == "entity_unresolved"
    assert result.error_type == "InputEntityNotFound"


def test_group_username_is_forwarded_to_template_entity_resolver() -> None:
    template_sender = FakeTemplateSender()
    service = ReliableGroupSendService(
        template_sender=template_sender,
        noise_pool_service=FakeNoisePool(),
    )
    group = SimpleNamespace(
        chat_id=-1001601148299,
        username="target_group",
        group_name="target title",
    )
    token = service._active_group.set(group)
    try:
        ok = asyncio.run(
            service.send_template_to_chat(
                account_name="account-a",
                client=object(),
                chat_id=-1001601148299,
                template_id="template-a",
            )
        )
    finally:
        service._active_group.reset(token)

    assert ok is True
    assert template_sender.calls[0]["target_chat_username"] == "target_group"
    assert template_sender.calls[0]["target_chat_title"] == "target title"

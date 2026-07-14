from __future__ import annotations

from app.services.group_send_service import SendResult
from app.services.reliable_group_send_service import ReliableGroupSendService


class FakeTemplateSender:
    def get_template(self, template_id: str):
        return None


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

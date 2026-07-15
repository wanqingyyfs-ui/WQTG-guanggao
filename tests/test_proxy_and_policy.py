from __future__ import annotations

import pytest

from app.services.account_service import AccountImportError
from app.services.task_service import TaskPolicyError


def test_account_cannot_enable_without_group_and_healthy_proxy(services) -> None:
    account_id = services["accounts"].create("+16595590986", "https://example.test/code")
    with pytest.raises(AccountImportError):
        services["accounts"].set_enabled(account_id, True)
    proxy_id = services["proxies"].create(protocol="http", host="127.0.0.1", port=8888, expected_ip="203.0.113.10")
    group_id = services["db"].execute(
        "INSERT INTO account_groups(name,static_proxy_id) VALUES('US-1',?)", (proxy_id,)
    ).lastrowid
    services["accounts"].assign_group(account_id, int(group_id))
    with pytest.raises(AccountImportError):
        services["accounts"].set_enabled(account_id, True)
    services["db"].execute(
        "UPDATE static_proxies SET last_status='healthy' WHERE id=?", (proxy_id,)
    )
    services["accounts"].set_enabled(account_id, True)
    assert services["db"].scalar("SELECT enabled FROM accounts WHERE id=?", (account_id,)) == 1


def test_task_target_must_be_verified_and_approved(services) -> None:
    group_id = services["groups"].import_links("https://t.me/example_group")["created_ids"][0]
    with pytest.raises(TaskPolicyError):
        services["tasks"].validate_target(group_id)
    services["db"].execute(
        "UPDATE telegram_groups SET status='verified',joined=1,can_send=1,approved=1 WHERE id=?",
        (group_id,),
    )
    target = services["tasks"].validate_target(group_id)
    assert target["canonical_link"] == "https://t.me/example_group"

from __future__ import annotations

import pytest

from app.services.account_service import AccountImportError, normalize_phone


def test_phone_normalization() -> None:
    assert normalize_phone("(165) 955-90986") == "+16595590986"
    assert normalize_phone("+86 138 0013 8000") == "+8613800138000"
    with pytest.raises(AccountImportError):
        normalize_phone("123")


def test_import_creates_unique_profile_and_fixed_environment(services) -> None:
    result = services["accounts"].import_lines(
        "16595590986|https://example.test/code\n+8613800138000|https://example.test/code2"
    )
    assert not result["errors"]
    assert len(result["created_ids"]) == 2
    rows = services["db"].query_all("SELECT phone,profile_dir,enabled FROM accounts ORDER BY id")
    assert rows[0]["phone"] == "+16595590986"
    assert rows[0]["profile_dir"] != rows[1]["profile_dir"]
    assert rows[0]["enabled"] == 0
    env = services["environments"].get_for_account(result["created_ids"][0])
    assert env["finalized"] == 0
    assert env["webrtc_policy"] == "disable_non_proxied_udp"


def test_duplicate_account_is_rejected(services) -> None:
    services["accounts"].create("+16595590986", "https://example.test/code")
    with pytest.raises(AccountImportError):
        services["accounts"].create("16595590986", "https://example.test/code2")

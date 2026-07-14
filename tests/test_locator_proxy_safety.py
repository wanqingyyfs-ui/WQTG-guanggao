from __future__ import annotations

from types import SimpleNamespace

from app.services.strict_tgapipldc_locator_service import (
    StrictTgapipldcLocatorService,
)


def test_locator_only_validates_selected_profile_account() -> None:
    selected = SimpleNamespace(
        account_name="selected",
        phone="+10000000001",
        account_group="group-a",
    )
    unrelated = SimpleNamespace(
        account_name="监听",
        phone="+10000000002",
        account_group="",
    )

    class FakeService:
        @staticmethod
        def _metadata_rows():
            return [
                {
                    "phone": "+10000000001",
                    "telegram_phone": "+10000000001",
                    "phone_for_web": "+10000000001",
                    "national_number": "10000000001",
                    "profile_dir": "profiles/selected",
                }
            ]

        @staticmethod
        def _phone_keys(value):
            text = str(value or "").strip()
            digits = "".join(character for character in text if character.isdigit())
            return {
                item
                for item in (
                    text,
                    digits,
                    f"+{digits}" if digits else "",
                )
                if item
            }

        @staticmethod
        def proxy_for_account(account, proxies):
            assert account is selected
            assert proxies == {"group-a": {"enabled": True}}
            return {
                "enabled": True,
                "proxy_type": "socks5",
                "host": "proxy.example",
                "port": 1080,
                "username": "user",
                "password": "pass",
            }

        @staticmethod
        def _proxy_url(_config):
            return "socks5://user:pass@proxy.example:1080"

    runtime = SimpleNamespace(
        static_account_proxy_service=FakeService(),
        _accounts_from_disk=lambda: [selected, unrelated],
        _load_account_group_proxies_for_runtime=lambda: {
            "group-a": {"enabled": True}
        },
    )

    result = StrictTgapipldcLocatorService._resolve_selected_profile_proxy(
        runtime,
        "profiles/selected",
    )
    assert result == "socks5://user:pass@proxy.example:1080"


def test_profile_path_matching_accepts_absolute_and_relative_paths() -> None:
    assert StrictTgapipldcLocatorService._same_profile_dir(
        r"D:\WQTG\app\vendor\tgapipldc\profiles\selected",
        "profiles/selected",
    )

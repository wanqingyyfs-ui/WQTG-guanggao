from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.models import AccountConfig
from app.services.config_service import ConfigService
from app.services.static_account_proxy_service import StaticAccountProxyService
from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


def _proxy(host: str, port: int) -> dict:
    return {
        "enabled": True,
        "proxy_type": "socks5",
        "host": host,
        "port": port,
        "username": "user",
        "password": "pass",
    }


def _account(name: str, phone: str, group: str, session: str | None = None) -> AccountConfig:
    return AccountConfig(
        account_name=name,
        api_id=12345,
        api_hash="a" * 32,
        phone=phone,
        session_name=session or name,
        enabled=True,
        account_group=group,
    )


def _write_dynamic_metadata(workspace: TgapipldcWorkspaceService) -> str:
    dynamic_proxy = "dynamic:secret@dynamic.example:9000"
    rows = [
        {
            "phone": "+10000000001",
            "country": "US",
            "country_code": "+1",
            "national_number": "0000000001",
            "telegram_phone": "+10000000001",
            "phone_for_web": "+10000000001",
            "profile_dir": "profiles/account_a",
            "yanzheng": "https://example.invalid/a",
            "raw_proxy": dynamic_proxy,
            "masked_proxy": "dynamic:******@dynamic.example:9000",
            "exit_ip": "",
            "status": "dynamic_proxy_assigned",
            "note": "api only",
        },
        {
            "phone": "+10000000002",
            "country": "US",
            "country_code": "+1",
            "national_number": "0000000002",
            "telegram_phone": "+10000000002",
            "phone_for_web": "+10000000002",
            "profile_dir": "profiles/account_b",
            "yanzheng": "https://example.invalid/b",
            "raw_proxy": dynamic_proxy,
            "masked_proxy": "dynamic:******@dynamic.example:9000",
            "exit_ip": "",
            "status": "dynamic_proxy_assigned",
            "note": "api only",
        },
    ]
    workspace.account_proxy_map_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with workspace.account_proxy_map_csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return dynamic_proxy


class _Response:
    def __init__(self, ip: str):
        self._ip = ip

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ip": self._ip}


def test_static_profile_map_never_reuses_dynamic_api_proxy(tmp_path: Path) -> None:
    config = ConfigService(tmp_path / "config-root")
    workspace = TgapipldcWorkspaceService(tmp_path / "workspace")
    workspace.ensure_structure()
    dynamic_proxy = _write_dynamic_metadata(workspace)
    config.save_account_group_proxies({
        "group-a": _proxy("static-a.example", 1080),
        "group-b": _proxy("static-b.example", 1081),
    })
    service = StaticAccountProxyService(config, workspace)
    accounts = [
        _account("account-a", "+10000000001", "group-a"),
        _account("account-b", "+10000000002", "group-b"),
    ]

    def fake_get(_url, *, proxies, timeout):
        assert timeout == 20
        proxy_url = proxies["https"]
        return _Response("203.0.113.10" if "static-a.example" in proxy_url else "203.0.113.11")

    with patch("app.services.static_account_proxy_service.requests.get", side_effect=fake_get):
        static_path = service.build_static_profile_map(accounts)

    source_text = workspace.account_proxy_map_csv_path.read_text(encoding="utf-8-sig")
    assert dynamic_proxy in source_text
    with static_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert all("dynamic.example" not in row["raw_proxy"] for row in rows)
    assert {row["exit_ip"] for row in rows} == {"203.0.113.10", "203.0.113.11"}
    assert all(row["status"] == "static_group_proxy_verified" for row in rows)


def test_enabled_accounts_cannot_share_proxy_configuration(tmp_path: Path) -> None:
    config = ConfigService(tmp_path / "config-root")
    workspace = TgapipldcWorkspaceService(tmp_path / "workspace")
    workspace.ensure_structure()
    service = StaticAccountProxyService(config, workspace)
    shared = _proxy("same-static.example", 1080)
    proxies = {"group-a": shared, "group-b": dict(shared)}
    accounts = [
        _account("account-a", "+10000000001", "group-a"),
        _account("account-b", "+10000000002", "group-b"),
    ]

    with pytest.raises(RuntimeError, match="同一个静态代理"):
        service.validate_enabled_accounts(accounts, proxies)


def test_enabled_account_without_group_is_fail_closed(tmp_path: Path) -> None:
    config = ConfigService(tmp_path / "config-root")
    workspace = TgapipldcWorkspaceService(tmp_path / "workspace")
    workspace.ensure_structure()
    service = StaticAccountProxyService(config, workspace)
    account = _account("account-a", "+10000000001", "")

    with pytest.raises(RuntimeError, match="未分配账号组"):
        service.validate_enabled_accounts([account], {})


def test_actual_static_exit_ip_must_be_unique(tmp_path: Path) -> None:
    config = ConfigService(tmp_path / "config-root")
    workspace = TgapipldcWorkspaceService(tmp_path / "workspace")
    workspace.ensure_structure()
    service = StaticAccountProxyService(config, workspace)
    proxies = {
        "group-a": _proxy("static-a.example", 1080),
        "group-b": _proxy("static-b.example", 1081),
    }
    accounts = [
        _account("account-a", "+10000000001", "group-a"),
        _account("account-b", "+10000000002", "group-b"),
    ]

    response = _Response("203.0.113.99")
    with patch(
        "app.services.static_account_proxy_service.requests.get",
        return_value=response,
    ):
        with pytest.raises(RuntimeError, match="实际出口重复"):
            service.verify_unique_exit_ips(accounts, proxies)


def test_strict_calibration_script_has_no_direct_fallback() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "vendor"
        / "tgapipldc"
        / "src"
        / "strict_automation_entry.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "定位校准缺少静态代理，禁止直连" in source
    assert "已禁止回退直连" in source
    assert "attempts.append((\"direct\", None))" not in source
    assert "proxies=parsed_proxy.requests_proxies" in source

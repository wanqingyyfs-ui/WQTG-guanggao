from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "vendor"
    / "tgapipldc"
    / "src"
)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import authenticated_proxy_bridge as bridge_module
from proxy_utils import parse_raw_proxy


def test_authenticated_socks5_is_converted_to_local_no_auth_proxy(monkeypatch) -> None:
    started = []

    def fake_start(self, timeout=10.0):
        self._port = 19080
        started.append(self)
        return self

    monkeypatch.setattr(
        bridge_module.AuthenticatedProxyBridge,
        "start",
        fake_start,
    )
    prepared = bridge_module.prepare_playwright_proxy(
        parse_raw_proxy("socks5://user:pass@proxy.example:1080")
    )

    assert prepared.proxy == {"server": "socks5://127.0.0.1:19080"}
    assert "username" not in prepared.proxy
    assert "password" not in prepared.proxy
    assert prepared.bridge is started[0]


def test_http_proxy_keeps_playwright_native_authentication() -> None:
    prepared = bridge_module.prepare_playwright_proxy(
        parse_raw_proxy("http://user:pass@proxy.example:8080")
    )
    assert prepared.bridge is None
    assert prepared.proxy == {
        "server": "http://proxy.example:8080",
        "username": "user",
        "password": "pass",
    }

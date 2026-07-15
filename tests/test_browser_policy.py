from __future__ import annotations

from app.browser_runtime.worker import browser_worker_main


class FakeConnection:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def send(self, event: dict) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


def test_browser_worker_fails_closed_without_static_proxy(tmp_path) -> None:
    connection = FakeConnection()
    browser_worker_main(
        connection,
        {
            "account_id": 7,
            "profile_dir": str(tmp_path / "profile"),
            "proxy": None,
            "environment": {},
        },
    )
    names = [event["name"] for event in connection.events]
    assert names == ["fatal_error", "stopped"]
    assert "direct network fallback is forbidden" in connection.events[0]["payload"]["error"]

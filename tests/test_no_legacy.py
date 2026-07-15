from __future__ import annotations

from pathlib import Path


def test_no_telethon_or_api_credentials_in_production_code() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("telethon", "api_hash", "session_name", "TelegramClient")
    violations: list[str] = []
    for path in (root / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            if token.lower() in text:
                violations.append(f"{path.relative_to(root)}:{token}")
    assert not violations

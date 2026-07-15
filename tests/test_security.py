from __future__ import annotations

from app.core.audit import redact


def test_secrets_are_encrypted_and_round_trip(services) -> None:
    token = services["secrets"].encrypt("https://example.test/private-token")
    assert "private-token" not in token
    assert services["secrets"].decrypt(token) == "https://example.test/private-token"


def test_audit_redaction() -> None:
    value = redact(
        {
            "verification_url": "https://secret",
            "nested": {"password": "abc", "safe": "ok"},
            "token": "123",
        }
    )
    assert value["verification_url"] == "***"
    assert value["nested"]["password"] == "***"
    assert value["nested"]["safe"] == "ok"
    assert value["token"] == "***"

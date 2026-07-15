from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.core.database import Database


SENSITIVE_KEYS = {
    "password",
    "password_encrypted",
    "verification_url",
    "verification_url_encrypted",
    "code",
    "two_factor_password",
    "cookie",
    "local_storage",
    "token",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, db: Database):
        self.db = db

    def write(
        self,
        action: str,
        *,
        actor: str = "system",
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO audit_logs(created_at,actor,action,entity_type,entity_id,detail_json) "
            "VALUES(?,?,?,?,?,?)",
            (
                utc_now(),
                actor,
                action,
                entity_type,
                None if entity_id is None else str(entity_id),
                json.dumps(redact(detail or {}), ensure_ascii=False, sort_keys=True),
            ),
        )

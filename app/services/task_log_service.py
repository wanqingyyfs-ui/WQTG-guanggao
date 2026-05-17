from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.group_send_service import SendResult


class TaskLogService:
    def __init__(self, log_file: str | Path, log_func=None):
        self.log_file = Path(log_file).expanduser()
        self.log_func = log_func
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    def append_result(self, result: SendResult) -> None:
        self.append_record(result.to_dict())

    def append_record(self, record: dict[str, Any]) -> None:
        safe_record = self._sanitize_record(record)

        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe_record, ensure_ascii=False) + "\n")

    def _sanitize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        blocked_keys = {
            "api_hash",
            "api_id",
            "phone_code",
            "password",
            "session",
            "session_name",
        }

        return {
            str(key): value
            for key, value in record.items()
            if str(key).lower() not in blocked_keys
        }
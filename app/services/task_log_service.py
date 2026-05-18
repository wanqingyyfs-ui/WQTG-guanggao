from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
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

    def append_result(self, result: SendResult | None) -> None:
        if result is None:
            self._log("warning", "任务发送结果为空，已跳过写入任务日志")
            return

        try:
            if hasattr(result, "to_dict") and callable(result.to_dict):
                record = result.to_dict()
            elif is_dataclass(result):
                record = asdict(result)
            else:
                record = {
                    "status": "unknown",
                    "error": f"不支持的任务结果类型: {type(result).__name__}",
                    "raw_result": str(result),
                }

            self.append_record(record)

        except Exception as exc:
            self._log("error", f"写入任务发送结果失败: {exc}")

    def append_record(self, record: Mapping[str, Any] | dict[str, Any]) -> None:
        try:
            safe_record = self._sanitize_record(record)
            line = json.dumps(
                safe_record,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )

            self.log_file.parent.mkdir(parents=True, exist_ok=True)

            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")

        except Exception as exc:
            self._log("error", f"追加任务日志失败: {exc}")

    def _sanitize_record(self, record: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, Mapping):
            return {
                "status": "unknown",
                "error": f"任务日志记录不是字典: {type(record).__name__}",
                "raw_record": str(record),
            }

        return {
            str(key): self._sanitize_value(value)
            for key, value in record.items()
            if not self._is_blocked_key(str(key))
        }

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): self._sanitize_value(child_value)
                for key, child_value in value.items()
                if not self._is_blocked_key(str(key))
            }

        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]

        if isinstance(value, tuple):
            return [self._sanitize_value(item) for item in value]

        if isinstance(value, set):
            return [self._sanitize_value(item) for item in value]

        if is_dataclass(value):
            return self._sanitize_value(asdict(value))

        return value

    @staticmethod
    def _is_blocked_key(key: str) -> bool:
        blocked_keys = {
            "api_hash",
            "api_id",
            "auth_token",
            "password",
            "phone_code",
            "session",
            "session_name",
            "token",
        }

        return key.strip().lower() in blocked_keys
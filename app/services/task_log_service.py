from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
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

    @staticmethod
    def _now_text() -> str:
        return datetime.now().isoformat(timespec="seconds")

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

            if "logged_at" not in safe_record:
                safe_record["logged_at"] = self._now_text()

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

    def read_recent_records(self, limit: int = 300) -> list[dict[str, Any]]:
        safe_limit = self._normalize_limit(limit)

        if not self.log_file.exists():
            return []

        try:
            records: list[dict[str, Any]] = []
            lines = self._read_tail_lines(safe_limit)

            for line in lines:
                text = line.strip()

                if not text:
                    continue

                try:
                    record = json.loads(text)
                except json.JSONDecodeError:
                    records.append(
                        {
                            "status": "invalid",
                            "error": "日志行不是有效 JSON",
                            "raw_line": text[:500],
                        }
                    )
                    continue

                if isinstance(record, dict):
                    records.append(self._sanitize_record(record))
                else:
                    records.append(
                        {
                            "status": "invalid",
                            "error": f"日志记录不是对象: {type(record).__name__}",
                            "raw_record": str(record)[:500],
                        }
                    )

            return records

        except Exception as exc:
            self._log("error", f"读取任务日志失败: {exc}")
            return []

    def clear(self) -> None:
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.write_text("", encoding="utf-8")
        except Exception as exc:
            self._log("error", f"清空任务日志失败: {exc}")

    def get_log_file(self) -> Path:
        return self.log_file

    def _read_tail_lines(self, limit: int) -> list[str]:
        if limit <= 0:
            return []

        try:
            with self.log_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with self.log_file.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        if not lines:
            return []

        return lines[-limit:]

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        try:
            safe_limit = int(limit)
        except (TypeError, ValueError):
            safe_limit = 300

        if safe_limit <= 0:
            return 300

        if safe_limit > 5000:
            return 5000

        return safe_limit

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
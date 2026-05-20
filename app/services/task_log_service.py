from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.group_send_service import SendResult


class TaskLogService:
    REQUIRED_LOG_DEFAULTS: dict[str, Any] = {
        "task_id": "",
        "task_name": "",
        "account_name": "",
        "group_id": "",
        "chat_id": 0,
        "status": "unknown",
        "error": "",
        "started_at": "",
        "finished_at": "",
        "decision": "",
        "message_mode": "",
        "selected_template_id": "",
        "template_id": "",
        "template_ids": [],
        "configured_template_ids": [],
        "enabled_template_ids": [],
        "noise_text_preview": "",
        "skip_reason": "",
        "ad_probability": 0,
        "noise_probability": 0,
        "skip_probability": 0,
        "rotate_mode": "",
        "account_index": 0,
        "selected_account_name": "",
        "account_pool": [],
        "account_pool_size": 0,
        "group_rotate_mode": "",
        "group_index": 0,
        "selected_group_id": "",
        "selected_group_name": "",
        "group_pool": [],
        "group_pool_size": 0,
        "account_delay_min_ms": 0,
        "account_delay_max_ms": 0,
        "group_delay_min_ms": 0,
        "group_delay_max_ms": 0,
        "actual_account_delay_ms": 0,
        "actual_group_delay_ms": 0,
        "account_delay_seconds": 0,
        "group_delay_seconds": 0,
        "flood_wait_seconds": 0,
    }

    def __init__(self, log_file: str | Path, log_func=None):
        self.log_file = Path(log_file).expanduser()
        self.log_func = log_func
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _now_text() -> str:
        return datetime.now().isoformat(timespec="milliseconds")

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
            safe_record = self._ensure_required_fields(safe_record)

            if "logged_at" not in safe_record:
                safe_record["logged_at"] = self._now_text()

            if "log_schema_version" not in safe_record:
                safe_record["log_schema_version"] = 2

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
                        self._ensure_required_fields(
                            {
                                "status": "invalid",
                                "error": "日志行不是有效 JSON",
                                "raw_line": text[:500],
                            }
                        )
                    )
                    continue

                if isinstance(record, dict):
                    records.append(
                        self._ensure_required_fields(self._sanitize_record(record))
                    )
                else:
                    records.append(
                        self._ensure_required_fields(
                            {
                                "status": "invalid",
                                "error": (
                                    f"日志记录不是对象: {type(record).__name__}"
                                ),
                                "raw_record": str(record)[:500],
                            }
                        )
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

    def _ensure_required_fields(self, record: dict[str, Any]) -> dict[str, Any]:
        safe_record = dict(record)

        for key, default_value in self.REQUIRED_LOG_DEFAULTS.items():
            if key not in safe_record:
                safe_record[key] = self._copy_default(default_value)

        if safe_record.get("selected_template_id") and not safe_record.get("template_id"):
            safe_record["template_id"] = safe_record["selected_template_id"]

        if safe_record.get("template_id") and not safe_record.get("selected_template_id"):
            safe_record["selected_template_id"] = safe_record["template_id"]

        if safe_record.get("error") and not safe_record.get("skip_reason"):
            if str(safe_record.get("status") or "").strip() == "skipped":
                safe_record["skip_reason"] = str(safe_record.get("error") or "")

        return safe_record

    @staticmethod
    def _copy_default(value: Any) -> Any:
        if isinstance(value, list):
            return list(value)

        if isinstance(value, dict):
            return dict(value)

        if isinstance(value, set):
            return set(value)

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

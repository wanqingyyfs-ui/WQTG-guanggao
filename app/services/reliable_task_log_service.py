from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from app.services.task_log_service import TaskLogService


class ReliableTaskLogService(TaskLogService):
    EXTRA_DEFAULTS: dict[str, Any] = {
        "attempt_id": "",
        "result_category": "",
        "error_type": "",
        "reason_detail": "",
        "retry_after_seconds": 0,
        "cooldown_until": "",
        "probability_roll": -1.0,
        "probability_total": 100,
        "configured_ad_probability": 0,
        "configured_noise_probability": 0,
        "configured_skip_probability": 0,
        "actual_ad_probability": 0.0,
        "actual_noise_probability": 0.0,
        "actual_skip_probability": 0.0,
        "template_name": "",
        "template_send_mode": "",
        "source_chat_id": 0,
        "source_message_ids": [],
        "target_chat_username": "",
        "target_chat_title": "",
    }

    def append_result(self, result) -> None:
        if result is None:
            self._log("warning", "任务发送结果为空，已跳过写入任务日志")
            return
        try:
            if hasattr(result, "to_dict") and callable(result.to_dict):
                record = dict(result.to_dict())
            elif is_dataclass(result):
                record = asdict(result)
            else:
                record = {"status": "unknown", "error": str(result)}
            if hasattr(result, "__dict__"):
                record.update(vars(result))
            record["log_schema_version"] = 4
            self.append_record(record)
        except Exception as exc:
            self._log("error", f"写入详细任务发送结果失败: {exc}")

    def _ensure_required_fields(self, record: dict[str, Any]) -> dict[str, Any]:
        safe_record = super()._ensure_required_fields(record)
        for key, default_value in self.EXTRA_DEFAULTS.items():
            if key not in safe_record:
                safe_record[key] = self._copy_default(default_value)
        return safe_record

    def load_active_flood_waits(self, limit: int = 5000) -> dict[str, datetime]:
        now = datetime.now()
        active: dict[str, datetime] = {}
        for record in self.read_recent_records(limit):
            if str(record.get("status") or "") != "flood_wait":
                continue
            account_name = str(record.get("account_name") or "").strip()
            cooldown_text = str(record.get("cooldown_until") or "").strip()
            if not account_name or not cooldown_text:
                continue
            try:
                cooldown_until = datetime.fromisoformat(cooldown_text)
            except ValueError:
                continue
            if cooldown_until <= now:
                continue
            previous = active.get(account_name)
            if previous is None or cooldown_until > previous:
                active[account_name] = cooldown_until
        return active

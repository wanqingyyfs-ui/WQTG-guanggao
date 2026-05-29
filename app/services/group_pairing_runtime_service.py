from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.json_utils import atomic_write_json, read_json_file
from app.services.config_service import ConfigService


class GroupPairingRuntimeService:
    def __init__(self, state_path: str | Path | None = None):
        if state_path is None:
            state_path = ConfigService().group_pairing_runtime_state_path
        self.state_path = Path(state_path).expanduser()
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="milliseconds")

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "updated_at": self._now(), "tasks": {}}
        try:
            data = read_json_file(self.state_path, default={"version": 1, "updated_at": self._now(), "tasks": {}})
        except Exception:
            return {"version": 1, "updated_at": self._now(), "tasks": {}}
        if not isinstance(data, dict):
            data = {}
        tasks = data.get("tasks")
        if not isinstance(tasks, dict):
            tasks = {}
        data["version"] = int(data.get("version") or 1)
        data["tasks"] = tasks
        data["updated_at"] = str(data.get("updated_at") or self._now())
        return data

    def _write_state(self, data: dict[str, Any]) -> None:
        data["updated_at"] = self._now()
        atomic_write_json(self.state_path, data)

    def init_task(
        self,
        task_id: str,
        task_name: str,
        account_group_order: list[str],
        group_group_order: list[str],
        daily_window_enabled: bool,
        daily_start_time: str,
        daily_end_time: str,
    ) -> None:
        with self._lock:
            data = self._read_state()
            progress = {name: 0 for name in account_group_order}
            current_target = {}
            for index, account_group in enumerate(account_group_order):
                if group_group_order:
                    current_target[account_group] = group_group_order[index % len(group_group_order)]
            data["tasks"][task_id] = {
                "task_id": task_id,
                "task_name": task_name,
                "started_at": self._now(),
                "updated_at": self._now(),
                "task_status": "running",
                "pairing_mode": "rotate",
                "daily_window_enabled": bool(daily_window_enabled),
                "daily_start_time": daily_start_time,
                "daily_end_time": daily_end_time,
                "account_group_order": list(account_group_order),
                "group_group_order": list(group_group_order),
                "account_group_progress": progress,
                "account_group_current_target": current_target,
                "account_group_status": {name: "waiting" for name in account_group_order},
            }
            self._write_state(data)

    def set_task_status(self, task_id: str, status: str, reason: str = "") -> None:
        with self._lock:
            data = self._read_state()
            task_state = data.get("tasks", {}).get(task_id)
            if not isinstance(task_state, dict):
                return
            task_state["task_status"] = status
            task_state["status_reason"] = reason
            task_state["updated_at"] = self._now()
            self._write_state(data)

    def set_account_group_status(self, task_id: str, account_group: str, status: str, target: str = "") -> None:
        with self._lock:
            data = self._read_state()
            task_state = data.get("tasks", {}).get(task_id)
            if not isinstance(task_state, dict):
                return
            task_state.setdefault("account_group_status", {})[account_group] = status
            if target:
                task_state.setdefault("account_group_current_target", {})[account_group] = target
            task_state["updated_at"] = self._now()
            self._write_state(data)

    def complete_round(self, task_id: str, account_group: str) -> None:
        with self._lock:
            data = self._read_state()
            task_state = data.get("tasks", {}).get(task_id)
            if not isinstance(task_state, dict):
                return
            progress = task_state.setdefault("account_group_progress", {})
            group_order = list(task_state.get("group_group_order") or [])
            account_order = list(task_state.get("account_group_order") or [])
            current = int(progress.get(account_group, 0) or 0) + 1
            progress[account_group] = current
            if group_order and account_group in account_order:
                account_index = account_order.index(account_group)
                target_index = (account_index + current) % len(group_order)
                task_state.setdefault("account_group_current_target", {})[account_group] = group_order[target_index]
            task_state.setdefault("account_group_status", {})[account_group] = "waiting_interval"
            task_state["updated_at"] = self._now()
            self._write_state(data)

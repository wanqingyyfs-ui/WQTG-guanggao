from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.audit import AuditLogger
from app.core.database import Database
from app.services.task_runner import TaskRunner


class TaskScheduler:
    """Single-flight scheduler. Scheduled tasks never bypass preview or target policy."""

    def __init__(self, db: Database, runner: TaskRunner, audit: AuditLogger):
        self.db = db
        self.runner = runner
        self.audit = audit
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._run_lock = threading.Lock()
        self._last_errors: list[str] = []

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def last_errors(self) -> list[str]:
        return list(self._last_errors[-20:])

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="TaskScheduler", daemon=True)
        self._thread.start()
        self.audit.write("scheduler.started")

    def stop(self) -> None:
        self._stop.set()
        self.runner.cancel()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.audit.write("scheduler.stopped")

    def _loop(self) -> None:
        while not self._stop.wait(15):
            for task in self.db.query_all(
                "SELECT * FROM tasks WHERE enabled=1 AND schedule_mode!='manual' ORDER BY id"
            ):
                if self._stop.is_set():
                    return
                try:
                    if int(task["require_preview"]):
                        continue
                    if self._is_due(dict(task)):
                        self._run_once(int(task["id"]))
                except Exception as exc:
                    self._last_errors.append(f"Task {task['id']}: {exc}")
                    self.audit.write(
                        "scheduler.task_failed",
                        entity_type="task",
                        entity_id=task["id"],
                        detail={"error": str(exc)},
                    )

    def _is_due(self, task: dict[str, Any]) -> bool:
        last = self.db.query_one(
            "SELECT started_at FROM task_runs WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
            (task["id"],),
        )
        last_dt = datetime.fromisoformat(last["started_at"]) if last else None
        mode = task["schedule_mode"]
        value = str(task.get("schedule_value") or "").strip()
        now = datetime.now(UTC)
        if mode == "interval":
            seconds = max(60, int(value or task["min_interval_seconds"]))
            return last_dt is None or now - last_dt >= timedelta(seconds=seconds)
        if mode == "daily":
            try:
                hour, minute = (int(part) for part in value.split(":", 1))
            except Exception:
                return False
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return now >= scheduled and (last_dt is None or last_dt.date() < now.date())
        return False

    def _run_once(self, task_id: int) -> None:
        if not self._run_lock.acquire(blocking=False):
            return
        try:
            self.runner.run_task(task_id, preview_confirmed=False)
        finally:
            self._run_lock.release()

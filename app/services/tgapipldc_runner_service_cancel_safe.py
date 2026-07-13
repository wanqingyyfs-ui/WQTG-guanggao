from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.services.tgapipldc_runner_service import (
    TgapipldcCommandResult,
    TgapipldcRunnerService,
)


class CancelSafeTgapipldcRunnerService(TgapipldcRunnerService):
    """Convert explicit user stops into a structured cancelled terminal state."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cancelled_job_ids: set[str] = set()
        self._cancel_lock = threading.RLock()

    def stop_current_process(self) -> bool:
        job = self.current_job()
        job_id = str(job.get("job_id") or "")
        if job_id:
            with self._cancel_lock:
                self._cancelled_job_ids.add(job_id)
        stopped = super().stop_current_process()
        if not stopped and job_id:
            with self._cancel_lock:
                self._cancelled_job_ids.discard(job_id)
        return stopped

    def run_script(self, *args, **kwargs) -> TgapipldcCommandResult:
        result = super().run_script(*args, **kwargs)
        with self._cancel_lock:
            was_cancelled = result.job_id in self._cancelled_job_ids
            self._cancelled_job_ids.discard(result.job_id)

        if not was_cancelled:
            return result

        details = self.build_cancelled_details(
            result.details,
            job_id=result.job_id,
            job_type=result.job_type,
        )
        if result.result_path is not None:
            self._write_details(result.result_path, details)
        log_callback = kwargs.get("log_callback")
        if log_callback is None and len(args) >= 3:
            log_callback = args[2]
        self._emit(
            log_callback,
            f"[{result.job_type}][{result.job_id}] 用户已取消",
        )
        # Cancellation is a handled terminal state. Returning success=True keeps
        # the GUI background wrapper from misreporting it as an execution fault.
        return replace(result, success=True, details=details)

    @staticmethod
    def build_cancelled_details(
        details: dict[str, Any] | None,
        *,
        job_id: str,
        job_type: str,
    ) -> dict[str, Any]:
        payload = dict(details or {})
        payload.update(
            {
                "job_id": job_id,
                "job_type": job_type,
                "status": "cancelled",
                "error": "用户主动停止",
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        return payload

    @staticmethod
    def _write_details(path: Path, details: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(details, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

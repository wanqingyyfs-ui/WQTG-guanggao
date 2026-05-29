from __future__ import annotations

import app.services.runtime_service as base_runtime_service
from app.core.safe_telegram_client_manager import SafeTelegramClientManager
from app.services.scheduler_service import SchedulerService

base_runtime_service.TelegramClientManager = SafeTelegramClientManager
BaseRuntimeService = base_runtime_service.RuntimeService


class RuntimeService(BaseRuntimeService):
    def start_task_scheduler(self, task_id: str) -> None:
        self.reload_config_cache()
        task = next((item for item in self.tasks if str(getattr(item, "task_id", "") or "") == str(task_id or "")), None)
        if task is None:
            raise RuntimeError("任务不存在")
        if not bool(getattr(task, "enabled", True)):
            raise RuntimeError("未启用任务不能启动，请先启用任务")
        scheduler = self._get_scheduler()
        self._submit_coroutine(self._start_single_task_and_update_status(scheduler, str(task_id or "")))

    async def _start_single_task_and_update_status(self, scheduler: SchedulerService, task_id: str) -> None:
        try:
            await scheduler.start_task(task_id)
            self._emit_scheduler_status("running" if scheduler.is_running() else "stopped")
        except Exception:
            self._emit_scheduler_status("error")
            raise

    def stop_task_scheduler(self, task_id: str) -> None:
        scheduler = self._get_scheduler()
        self._submit_coroutine(self._stop_single_task_and_update_status(scheduler, str(task_id or "")))

    async def _stop_single_task_and_update_status(self, scheduler: SchedulerService, task_id: str) -> None:
        try:
            await scheduler.stop_task(task_id)
            self._emit_scheduler_status("running" if scheduler.is_running() else "stopped")
        except Exception:
            self._emit_scheduler_status("error")
            raise

from __future__ import annotations

import asyncio

from app.core.safe_telegram_client_manager import SafeTelegramClientManager
from app.services.runtime_service import RuntimeService as BaseRuntimeService
from app.services.scheduler_service import SchedulerService


class RuntimeService(BaseRuntimeService):
    """正式的分组运行服务扩展。

    保留原 RuntimeService 的全部行为，只显式使用 SafeTelegramClientManager，
    并补充单任务启动/停止入口。不再通过 monkey patch 修改基础模块。
    """

    def _load_account_group_proxies_for_runtime(self) -> dict:
        try:
            return self.config_service.load_account_group_proxies()
        except Exception as exc:
            self._emit_log("warning", f"读取账号组代理配置失败，已按直连处理: {exc}")
            return {}

    def _update_runtime_components(self) -> None:
        super()._update_runtime_components()
        if self._manager is not None and hasattr(self._manager, "update_configuration"):
            self._manager.update_configuration(
                account_group_proxies=self._load_account_group_proxies_for_runtime(),
            )

    def _thread_main(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._manager = SafeTelegramClientManager(
                accounts=self.accounts,
                settings=self.settings,
                logger=self.logger,
                log_callback=self._emit_log,
                status_callback=self._emit_status,
                template_collector=self.template_collector,
                account_group_proxies=self._load_account_group_proxies_for_runtime(),
            )

            self._scheduler = SchedulerService(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                templates=self.templates,
                settings=self.settings,
                client_manager=self._manager,
                group_send_service=self.group_send_service,
                noise_pool_service=self.noise_pool_service,
                task_log_service=self.task_log_service,
                save_tasks_callback=self.save_tasks_from_runtime,
                log_func=self._emit_log,
            )

            self._runtime_start_error = None
            self._loop_ready.set()
            self.runtime_hint.emit("后台事件循环已启动")
            self._loop.run_forever()

        except BaseException as exc:
            self._runtime_start_error = exc
            self._loop_ready.set()
            self._emit_log("error", f"后台运行时启动失败: {exc}")

        finally:
            loop = self._loop
            if loop is not None and not loop.is_closed():
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as exc:
                    self._emit_log("error", f"清理后台异步任务失败: {exc}")
                finally:
                    loop.close()

            self._manager = None
            self._scheduler = None
            self._loop = None
            self._emit_scheduler_status("stopped")
            self.runtime_hint.emit("后台事件循环已关闭")

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

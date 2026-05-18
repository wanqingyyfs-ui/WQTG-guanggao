from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from app.core.logger import setup_logger
from app.core.telegram_client_manager import TelegramClientManager
from app.core.template_collector import TemplateCollector
from app.services.config_service import ConfigService
from app.services.group_send_service import GroupSendService
from app.services.scheduler_service import SchedulerService
from app.services.task_log_service import TaskLogService
from app.services.template_service import TemplateSender
from app.services.template_store_service import TemplateStoreService


class GuiLoginInputProvider(QObject):
    code_input_required = Signal(str, str, object)
    password_input_required = Signal(str, object)

    async def request_code(self, account) -> str | None:
        future: concurrent.futures.Future[str | None] = concurrent.futures.Future()
        self.code_input_required.emit(account.account_name, account.phone, future)
        return await asyncio.wrap_future(future)

    async def request_password(self, account) -> str | None:
        future: concurrent.futures.Future[str | None] = concurrent.futures.Future()
        self.password_input_required.emit(account.account_name, future)
        return await asyncio.wrap_future(future)


class RuntimeService(QObject):
    log_received = Signal(str, str)
    account_status_changed = Signal(str, str, str)
    runtime_hint = Signal(str)
    templates_changed = Signal()
    scheduler_status_changed = Signal(str)

    def __init__(self, base_dir: str = "."):
        super().__init__()

        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.config_service = ConfigService(str(self.base_dir))
        self.base_dir = self.config_service.base_dir

        (
            self.accounts,
            self.groups,
            self.tasks,
            self.templates,
            self.settings,
        ) = self.config_service.load_all()

        self._apply_runtime_paths()

        self.logger = setup_logger(self.settings)
        self._sync_logger_level()

        self.input_provider = GuiLoginInputProvider()

        self.template_sender = TemplateSender(
            templates=self.templates,
            log_func=self._emit_log,
        )

        self.template_store = TemplateStoreService(
            file_path=str(self.config_service.templates_path),
            log_func=self._emit_log,
        )

        self.template_collector = TemplateCollector(
            settings=self.settings,
            store=self.template_store,
            log_func=self._emit_log,
        )

        self.group_send_service = GroupSendService(
            template_sender=self.template_sender,
            log_func=self._emit_log,
        )

        self.task_log_service = TaskLogService(
            log_file=self.config_service.logs_dir / "task_send.jsonl",
            log_func=self._emit_log,
        )

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._manager: TelegramClientManager | None = None
        self._scheduler: SchedulerService | None = None
        self._loop_ready = threading.Event()
        self._runtime_start_error: BaseException | None = None
        self._status_map: dict[str, tuple[str, str]] = {}
        self._scheduler_status = "stopped"

        self._last_templates_signature = self._build_templates_signature(
            self.templates
        )

    def _build_templates_signature(
        self,
        templates,
    ) -> tuple[tuple[str, str, tuple[int, ...], bool], ...]:
        return tuple(
            (
                str(item.template_id),
                str(item.template_name),
                tuple(int(x) for x in item.source_message_ids),
                bool(item.enabled),
            )
            for item in templates
        )

    def _apply_runtime_paths(self) -> None:
        self.config_service.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config_service.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.config_service.template_cache_dir.mkdir(parents=True, exist_ok=True)

        self.settings.log_file = str(self.config_service.logs_dir / "app.log")
        self.settings.sessions_dir = str(self.config_service.sessions_dir)

    def _sync_logger_level(self) -> None:
        level_name = str(getattr(self.settings, "log_level", "INFO") or "INFO")
        self.logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))

    def _emit_log(self, level: str, message: str) -> None:
        safe_level = str(level or "INFO").upper()
        safe_message = str(message or "")
        self.log_received.emit(safe_level, safe_message)

        if hasattr(self, "logger") and self.logger is not None:
            log_method = getattr(self.logger, safe_level.lower(), self.logger.info)
            log_method(safe_message)

    def _emit_status(self, account_name: str, status: str, detail: str) -> None:
        safe_account_name = str(account_name or "")
        safe_status = str(status or "")
        safe_detail = str(detail or "")

        self._status_map[safe_account_name] = (safe_status, safe_detail)
        self.account_status_changed.emit(safe_account_name, safe_status, safe_detail)

    def _emit_scheduler_status(self, status: str) -> None:
        safe_status = str(status or "stopped")
        self._scheduler_status = safe_status
        self.scheduler_status_changed.emit(safe_status)

    def get_status_map(self) -> dict[str, tuple[str, str]]:
        return dict(self._status_map)

    def get_scheduler_status(self) -> str:
        return self._scheduler_status

    def get_logs_dir(self) -> Path:
        return self.config_service.logs_dir

    def reload_config_cache(self) -> None:
        (
            self.accounts,
            self.groups,
            self.tasks,
            self.templates,
            self.settings,
        ) = self.config_service.load_all()

        self._apply_runtime_paths()
        self._sync_logger_level()

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self._last_templates_signature = self._build_templates_signature(
            self.templates
        )

        self._update_runtime_components()

    def sync_templates_from_disk(self) -> bool:
        _, _, _, latest_templates, latest_settings = self.config_service.load_all()
        latest_signature = self._build_templates_signature(latest_templates)

        if latest_signature == self._last_templates_signature:
            return False

        self.templates = latest_templates
        self.settings = latest_settings
        self._apply_runtime_paths()

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self._last_templates_signature = latest_signature

        self.templates_changed.emit()
        return True

    def save_accounts(self, accounts) -> None:
        self.accounts = list(accounts)
        self.config_service.save_accounts(self.accounts)
        self._update_runtime_components()

    def save_groups(self, groups) -> None:
        self.groups = list(groups)
        self.config_service.save_groups(self.groups)
        self._update_runtime_components()

    def save_tasks(self, tasks) -> None:
        self.tasks = list(tasks)
        self.config_service.save_tasks(self.tasks)
        self._update_runtime_components()

    def save_templates(self, templates) -> None:
        self.templates = list(templates)
        self.config_service.save_templates(self.templates)
        self.template_sender.update_templates(self.templates)
        self._last_templates_signature = self._build_templates_signature(
            self.templates
        )
        self.templates_changed.emit()
        self._update_runtime_components()

    def save_settings(self, settings) -> None:
        self.settings = settings
        self._apply_runtime_paths()
        self.config_service.save_settings(self.settings)
        self._sync_logger_level()

        self.template_collector.settings = self.settings
        self._update_runtime_components()

    def _update_runtime_components(self) -> None:
        if self._manager is not None:
            self._manager.update_configuration(
                accounts=self.accounts,
                settings=self.settings,
            )

        if self._scheduler is not None:
            self._scheduler.update_configuration(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                settings=self.settings,
            )

    def _thread_main(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._manager = TelegramClientManager(
                accounts=self.accounts,
                settings=self.settings,
                logger=self.logger,
                log_callback=self._emit_log,
                status_callback=self._emit_status,
                template_collector=self.template_collector,
            )

            self._scheduler = SchedulerService(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                settings=self.settings,
                client_manager=self._manager,
                group_send_service=self.group_send_service,
                task_log_service=self.task_log_service,
                save_tasks_callback=self.save_tasks,
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
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )

                except Exception as exc:
                    self._emit_log("error", f"清理后台异步任务失败: {exc}")

                finally:
                    loop.close()

            self._manager = None
            self._scheduler = None
            self._loop = None
            self._emit_scheduler_status("stopped")
            self.runtime_hint.emit("后台事件循环已关闭")

    def ensure_runtime(self) -> None:
        if (
            self._thread is not None
            and self._thread.is_alive()
            and self._loop is not None
            and self._manager is not None
            and self._scheduler is not None
            and self._runtime_start_error is None
        ):
            return

        if self._thread is None or not self._thread.is_alive():
            self._runtime_start_error = None
            self._loop_ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="tg-group-sender-runtime",
                daemon=True,
            )
            self._thread.start()

        ok = self._loop_ready.wait(timeout=10)
        if not ok:
            raise RuntimeError("后台运行时初始化超时")

        if self._runtime_start_error is not None:
            raise RuntimeError(
                f"后台运行时初始化失败: {self._runtime_start_error}"
            ) from self._runtime_start_error

        if self._loop is None or self._manager is None or self._scheduler is None:
            raise RuntimeError("后台运行时初始化失败")

    def _submit_coroutine(self, coro):
        self.ensure_runtime()

        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("后台事件循环未启动")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(self._handle_future_result)
        return future

    def _handle_future_result(self, future) -> None:
        try:
            future.result()
        except concurrent.futures.CancelledError:
            self._emit_log("warning", "后台任务已取消")
        except Exception as exc:
            self._emit_log("error", f"后台任务执行失败: {exc}")

    def _get_manager(self) -> TelegramClientManager:
        self.ensure_runtime()

        if self._manager is None:
            raise RuntimeError("后台管理器未初始化")

        return self._manager

    def _get_scheduler(self) -> SchedulerService:
        self.ensure_runtime()

        if self._scheduler is None:
            raise RuntimeError("群发调度器未初始化")

        return self._scheduler

    def start_all(self) -> None:
        self.reload_config_cache()
        manager = self._get_manager()
        self._submit_coroutine(manager.start_all(input_provider=self.input_provider))

    def stop_all(self) -> None:
        manager = self._get_manager()
        self._submit_coroutine(manager.stop_all())

    def login_account(self, account_name: str) -> None:
        self.reload_config_cache()
        manager = self._get_manager()
        self._submit_coroutine(
            manager.login_account(account_name, input_provider=self.input_provider)
        )

    def start_account(self, account_name: str) -> None:
        self.reload_config_cache()
        manager = self._get_manager()
        self._submit_coroutine(
            manager.start_account(account_name, input_provider=self.input_provider)
        )

    def stop_account(self, account_name: str) -> None:
        manager = self._get_manager()
        self._submit_coroutine(manager.stop_account(account_name))

    def start_scheduler(self) -> None:
        self.reload_config_cache()
        scheduler = self._get_scheduler()
        self._submit_coroutine(self._start_scheduler_and_update_status(scheduler))

    async def _start_scheduler_and_update_status(
        self,
        scheduler: SchedulerService,
    ) -> None:
        try:
            await scheduler.start()
            status = "running" if scheduler.is_running() else "stopped"
            self._emit_scheduler_status(status)
        except Exception:
            self._emit_scheduler_status("error")
            raise

    def stop_scheduler(self) -> None:
        scheduler = self._get_scheduler()
        self._submit_coroutine(self._stop_scheduler_and_update_status(scheduler))

    async def _stop_scheduler_and_update_status(
        self,
        scheduler: SchedulerService,
    ) -> None:
        try:
            await scheduler.stop()
            self._emit_scheduler_status("stopped")
        except Exception:
            self._emit_scheduler_status("error")
            raise

    def send_task_once(self, task_id: str) -> None:
        self.reload_config_cache()
        scheduler = self._get_scheduler()
        self._submit_coroutine(scheduler.send_task_once(task_id))

    def get_running_client(self, account_name: str):
        manager = self._get_manager()
        return manager.get_running_client(account_name)

    def shutdown(self) -> None:
        loop = self._loop

        if loop is not None and not loop.is_closed() and self._scheduler is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._scheduler.stop(),
                    loop,
                )
                future.result(timeout=10)
                self._emit_scheduler_status("stopped")
            except Exception as exc:
                self._emit_log("warning", f"停止调度器时出现异常: {exc}")

        if loop is not None and not loop.is_closed() and self._manager is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._manager.stop_all(),
                    loop,
                )
                future.result(timeout=10)
            except Exception as exc:
                self._emit_log("warning", f"停止账号客户端时出现异常: {exc}")

        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception as exc:
                self._emit_log("warning", f"停止后台事件循环失败: {exc}")

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

        self._thread = None
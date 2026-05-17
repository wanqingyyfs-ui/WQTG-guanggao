from __future__ import annotations

import asyncio
import concurrent.futures
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
        (
            self.accounts,
            self.groups,
            self.tasks,
            self.templates,
            self.settings,
        ) = self.config_service.load_all()

        self.rules: list[Any] = []

        self._apply_runtime_paths()

        self.logger = setup_logger(self.settings)
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
        self._status_map: dict[str, tuple[str, str]] = {}
        self._scheduler_status = "stopped"

        self._last_templates_signature = self._build_templates_signature(self.templates)

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
        self.settings.log_file = str(self.config_service.logs_dir / "app.log")
        self.settings.sessions_dir = str(self.config_service.sessions_dir)

    def _emit_log(self, level: str, message: str) -> None:
        self.log_received.emit(level.upper(), message)

    def _emit_status(self, account_name: str, status: str, detail: str) -> None:
        self._status_map[account_name] = (status, detail)
        self.account_status_changed.emit(account_name, status, detail)

    def _emit_scheduler_status(self, status: str) -> None:
        self._scheduler_status = status
        self.scheduler_status_changed.emit(status)

    def get_status_map(self) -> dict[str, tuple[str, str]]:
        return dict(self._status_map)

    def get_scheduler_status(self) -> str:
        return self._scheduler_status

    def reload_config_cache(self) -> None:
        (
            self.accounts,
            self.groups,
            self.tasks,
            self.templates,
            self.settings,
        ) = self.config_service.load_all()

        self._apply_runtime_paths()

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self._last_templates_signature = self._build_templates_signature(self.templates)

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

    def sync_templates_from_disk(self) -> bool:
        _, _, _, latest_templates, _ = self.config_service.load_all()
        latest_signature = self._build_templates_signature(latest_templates)

        if latest_signature == self._last_templates_signature:
            return False

        self.templates = latest_templates
        self.template_sender.update_templates(self.templates)
        self._last_templates_signature = latest_signature
        self.templates_changed.emit()
        return True

    def save_accounts(self, accounts) -> None:
        self.accounts = accounts
        self.config_service.save_accounts(accounts)

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

    def save_groups(self, groups) -> None:
        self.groups = groups
        self.config_service.save_groups(groups)

        if self._scheduler is not None:
            self._scheduler.update_configuration(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                settings=self.settings,
            )

    def save_tasks(self, tasks) -> None:
        self.tasks = tasks
        self.config_service.save_tasks(tasks)

        if self._scheduler is not None:
            self._scheduler.update_configuration(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                settings=self.settings,
            )

    def save_templates(self, templates) -> None:
        self.templates = templates
        self.config_service.save_templates(templates)
        self.template_sender.update_templates(self.templates)
        self._last_templates_signature = self._build_templates_signature(self.templates)
        self.templates_changed.emit()

    def save_settings(self, settings) -> None:
        self.settings = settings
        self._apply_runtime_paths()
        self.config_service.save_settings(settings)
        self.template_collector.settings = self.settings

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

    def save_rules(self, rules) -> None:
        self.rules = list(rules)
        self._emit_log("warning", "自动回复规则已废弃，save_rules 已忽略")

    def _thread_main(self) -> None:
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

        self._loop_ready.set()
        self.runtime_hint.emit("后台事件循环已启动")

        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)

            for task in pending:
                task.cancel()

            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )

            self._loop.close()
            self.runtime_hint.emit("后台事件循环已关闭")

    def ensure_runtime(self) -> None:
        if (
            self._thread is not None
            and self._thread.is_alive()
            and self._loop is not None
            and self._manager is not None
            and self._scheduler is not None
        ):
            return

        if self._thread is None or not self._thread.is_alive():
            self._loop_ready.clear()
            self._thread = threading.Thread(target=self._thread_main, daemon=True)
            self._thread.start()

        ok = self._loop_ready.wait(timeout=10)
        if not ok:
            raise RuntimeError("后台运行时初始化超时")

        if self._loop is None or self._manager is None or self._scheduler is None:
            raise RuntimeError("后台运行时初始化失败")

    def _submit_coroutine(self, coro):
        if self._loop is None:
            raise RuntimeError("后台事件循环未启动")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(self._handle_future_result)
        return future

    def _handle_future_result(self, future) -> None:
        try:
            future.result()
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
        self._emit_scheduler_status("running")
        self._submit_coroutine(scheduler.start())

    def stop_scheduler(self) -> None:
        scheduler = self._get_scheduler()
        self._submit_coroutine(self._stop_scheduler_and_update_status(scheduler))

    async def _stop_scheduler_and_update_status(self, scheduler: SchedulerService) -> None:
        await scheduler.stop()
        self._emit_scheduler_status("stopped")

    def send_task_once(self, task_id: str) -> None:
        self.reload_config_cache()
        scheduler = self._get_scheduler()
        self._submit_coroutine(scheduler.send_task_once(task_id))

    def get_running_client(self, account_name: str):
        manager = self._get_manager()
        return manager.get_running_client(account_name)

    def shutdown(self) -> None:
        if self._scheduler is not None and self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._scheduler.stop(),
                    self._loop,
                )
                future.result(timeout=10)
                self._emit_scheduler_status("stopped")
            except Exception:
                pass

        if self._manager is not None and self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._manager.stop_all(),
                    self._loop,
                )
                future.result(timeout=10)
            except Exception:
                pass

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread is not None:
            self._thread.join(timeout=5)
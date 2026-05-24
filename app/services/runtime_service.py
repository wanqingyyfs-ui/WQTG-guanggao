from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.core.logger import setup_logger
from app.core.telegram_client_manager import TelegramClientManager
from app.core.template_collector import TemplateCollector
from app.services.config_service import ConfigService
from app.services.group_send_service import GroupSendService
from app.services.noise_pool_service import NoisePoolService
from app.services.scheduler_service import SchedulerService
from app.services.task_log_service import TaskLogService
from app.services.template_service import TemplateSender
from app.services.template_store_service import TemplateStoreService
from app.services.tgapipldc_account_bind_service import TgapipldcAccountBindService
from app.services.tgapipldc_import_service import TgapipldcImportService
from app.services.tgapipldc_proxy_service import TgapipldcProxyService
from app.services.tgapipldc_runner_service import TgapipldcRunnerService
from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService
from app.services.yanzheng_login_provider import YanzhengLoginInputProvider


SCHEDULER_STOP_MESSAGE = "请先停止群发功能"

UI_APPEARANCE_SETTING_FIELDS = {
    "global_font_size",
    "table_font_size",
    "button_font_size",
    "input_font_size",
    "floating_panel_font_size",
    "account_panel_font_size",
    "account_panel_width",
    "account_panel_height",
    "group_panel_font_size",
    "group_panel_width",
    "group_panel_height",
    "task_panel_font_size",
    "task_panel_width",
    "task_panel_height",
    "template_panel_font_size",
    "template_panel_width",
    "template_panel_height",
}

TEMPLATE_LISTENING_SETTING_FIELDS = {
    "template_source_account_name",
    "template_source_chat_id",
}

RUNTIME_SAFE_SETTING_FIELDS = (
    UI_APPEARANCE_SETTING_FIELDS
    | TEMPLATE_LISTENING_SETTING_FIELDS
    | {
        "app_name",
        "log_level",
        "log_file",
        "sessions_dir",
        "config_auto_save_debounce_ms",
    }
)

TgapipldcBackgroundCallable = Callable[[], None]


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
    noise_pool_changed = Signal()
    scheduler_status_changed = Signal(str)

    tgapipldc_log_received = Signal(str)
    tgapipldc_process_status_changed = Signal(bool)

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
            self.noise_pool,
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

        self.noise_pool_service = NoisePoolService(
            config_service=self.config_service,
        )
        self.noise_pool_service.replace_all(self.noise_pool, save=False)

        self.group_send_service = GroupSendService(
            template_sender=self.template_sender,
            noise_pool_service=self.noise_pool_service,
            log_func=self._emit_log,
        )

        self.task_log_service = TaskLogService(
            log_file=self.config_service.logs_dir / "task_send.jsonl",
            log_func=self._emit_log,
        )

        self.tgapipldc_workspace_service = TgapipldcWorkspaceService()
        self.tgapipldc_workspace_service.ensure_structure()
        self.tgapipldc_proxy_service = TgapipldcProxyService(
            workspace_service=self.tgapipldc_workspace_service,
        )
        self.tgapipldc_account_bind_service = TgapipldcAccountBindService(
            workspace_service=self.tgapipldc_workspace_service,
        )
        self.tgapipldc_runner_service = TgapipldcRunnerService(
            workspace_service=self.tgapipldc_workspace_service,
        )
        self.tgapipldc_import_service = TgapipldcImportService(
            workspace_service=self.tgapipldc_workspace_service,
        )
        self._tgapipldc_thread: threading.Thread | None = None
        self._tgapipldc_thread_lock = threading.Lock()

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
    ) -> tuple[tuple[str, str, str, tuple[int, ...], str, bool], ...]:
        return tuple(
            (
                str(item.template_id),
                str(item.template_name),
                str(item.source_account_name),
                tuple(int(x) for x in item.source_message_ids),
                str(item.send_mode),
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

    def _emit_tgapipldc_log(self, message: str) -> None:
        safe_message = str(message or "")
        if not safe_message:
            return

        self.tgapipldc_log_received.emit(safe_message)

        if hasattr(self, "logger") and self.logger is not None:
            self.logger.info(f"[tgapipldc] {safe_message}")

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

    def is_scheduler_running(self) -> bool:
        if self._scheduler_status == "running":
            return True

        scheduler = self._scheduler
        if scheduler is None:
            return False

        try:
            return bool(scheduler.is_running())
        except Exception:
            return False

    def ensure_can_modify_sending_data(self) -> None:
        if self.is_scheduler_running():
            raise RuntimeError(SCHEDULER_STOP_MESSAGE)

    def get_logs_dir(self) -> Path:
        return self.config_service.logs_dir

    def get_tgapipldc_workspace_dir(self) -> Path:
        self.tgapipldc_workspace_service.ensure_structure()
        return self.tgapipldc_workspace_service.workspace_dir

    def read_tgapipldc_accounts_csv_text(self) -> str:
        return self.tgapipldc_workspace_service.read_accounts_csv_text()

    def read_tgapipldc_proxies_csv_text(self) -> str:
        return self.tgapipldc_workspace_service.read_proxies_csv_text()

    def overwrite_tgapipldc_accounts_csv(self, raw_text: str) -> None:
        result = self.tgapipldc_workspace_service.overwrite_accounts_csv_data(raw_text)
        self._emit_tgapipldc_log(
            f"accounts.csv 已覆盖：{result.path}，写入 {result.row_count} 行数据"
        )

    def overwrite_tgapipldc_proxies_csv(self, raw_text: str) -> None:
        result = self.tgapipldc_workspace_service.overwrite_proxies_csv_data(raw_text)
        self._emit_tgapipldc_log(
            f"proxies.csv 已覆盖：{result.path}，写入 {result.row_count} 行数据"
        )

    def is_tgapipldc_process_running(self) -> bool:
        with self._tgapipldc_thread_lock:
            thread_running = bool(
                self._tgapipldc_thread is not None
                and self._tgapipldc_thread.is_alive()
            )
        return thread_running or self.tgapipldc_runner_service.is_running()

    def run_tgapipldc_test_proxies(self) -> None:
        def task() -> None:
            summary = self.tgapipldc_proxy_service.test_proxies(
                progress_callback=self._emit_tgapipldc_log,
            )
            self._emit_tgapipldc_log(
                "代理检测完成："
                f"总数 {summary.total}，"
                f"可用 {summary.ok_count}，"
                f"重复 IP {summary.duplicate_ip_count}，"
                f"不可用 {summary.bad_count}，"
                f"解析失败 {summary.parse_failed_count}，"
                f"结果文件 {summary.result_path}"
            )

        self._run_tgapipldc_background("检测代理", task)

    def run_tgapipldc_build_proxy_pool(self) -> None:
        def task() -> None:
            summary = self.tgapipldc_proxy_service.build_proxy_pool()
            self._emit_tgapipldc_log(
                f"可用代理池已生成：{summary.output_path}，可用代理 {summary.usable_count} 条"
            )

        self._run_tgapipldc_background("构建可用代理池", task)

    def run_tgapipldc_assign_proxies(self) -> None:
        def task() -> None:
            result = self.tgapipldc_account_bind_service.assign_accounts_to_proxies()
            self._emit_tgapipldc_log(
                "账号代理绑定完成："
                f"待绑定账号 {result.account_count} 个，"
                f"可用代理 {result.proxy_count} 个，"
                f"实际绑定 {result.assigned_count} 个，"
                f"输出文件 {result.account_proxy_map_path}"
            )

        self._run_tgapipldc_background("绑定账号和代理", task)

    def run_tgapipldc_export_api(self) -> None:
        def task() -> None:
            result = self.tgapipldc_runner_service.run_login_telegram_web(
                log_callback=self._emit_tgapipldc_log,
            )
            if not result.success:
                raise RuntimeError(f"批量获取 API 失败，退出码：{result.return_code}")

        self._run_tgapipldc_background("批量获取 api_id/api_hash", task)

    def run_tgapipldc_import_api_to_wqtg(self) -> None:
        self.ensure_can_modify_sending_data()
        result = self.tgapipldc_import_service.import_accounts(self.accounts)
        self.save_accounts(result.accounts)
        self.reload_config_cache()
        self._emit_tgapipldc_log(
            "API 导入 WQTG 完成："
            f"新增 {result.created_count} 个，"
            f"更新 {result.updated_count} 个，"
            f"跳过 {result.skipped_count} 个，"
            f"来源 {result.api_csv_path}"
        )

    def run_tgapipldc_login_wqtg_accounts(self) -> None:
        self.reload_config_cache()
        provider = YanzhengLoginInputProvider(
            workspace_service=self.tgapipldc_workspace_service,
            log_func=self._emit_tgapipldc_log,
        )
        manager = self._get_manager()
        self._submit_coroutine(
            self._login_wqtg_accounts_with_yanzheng(manager, provider)
        )

    async def _login_wqtg_accounts_with_yanzheng(self, manager, provider) -> None:
        accounts = [account for account in self.accounts if bool(getattr(account, "enabled", True))]
        total = len(accounts)
        self.tgapipldc_process_status_changed.emit(True)
        self._emit_tgapipldc_log(f"WQTG 批量登录开始：共 {total} 个启用账号")
        try:
            for index, account in enumerate(accounts, start=1):
                account_name = str(getattr(account, "account_name", "") or "").strip()
                self._emit_tgapipldc_log(f"[{index}/{total}] 开始登录 WQTG 账号：{account_name}")
                try:
                    await manager.login_account(account_name, input_provider=provider)
                    self._emit_tgapipldc_log(f"[{index}/{total}] WQTG 账号登录完成：{account_name}")
                except Exception as exc:
                    self._emit_tgapipldc_log(f"[{index}/{total}] WQTG 账号登录失败：{account_name}，原因：{exc}")
            self._emit_tgapipldc_log("WQTG 批量登录流程结束")
        finally:
            self.tgapipldc_process_status_changed.emit(False)


    def stop_tgapipldc_process(self) -> None:
        self.tgapipldc_runner_service.stop_current_process()
        self._emit_tgapipldc_log("已请求停止当前 tgapipldc 流程")

    def _run_tgapipldc_background(
        self,
        title: str,
        target: TgapipldcBackgroundCallable,
    ) -> None:
        if self.is_tgapipldc_process_running():
            raise RuntimeError("已有 tgapipldc 流程正在运行，请先停止或等待完成")

        def worker() -> None:
            self.tgapipldc_process_status_changed.emit(True)
            self._emit_tgapipldc_log(f"{title}：开始")
            try:
                target()
                self._emit_tgapipldc_log(f"{title}：完成")
            except Exception as exc:
                self._emit_tgapipldc_log(f"{title}：失败：{exc}")
            finally:
                self.tgapipldc_process_status_changed.emit(False)

        thread = threading.Thread(
            target=worker,
            name=f"tgapipldc-{title}",
            daemon=True,
        )

        with self._tgapipldc_thread_lock:
            self._tgapipldc_thread = thread

        thread.start()

    def reload_config_cache(self) -> None:
        (
            self.accounts,
            self.groups,
            self.tasks,
            self.templates,
            self.settings,
            self.noise_pool,
        ) = self.config_service.load_all()

        self._apply_runtime_paths()
        self._sync_logger_level()

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self.noise_pool_service.replace_all(self.noise_pool, save=False)
        self._last_templates_signature = self._build_templates_signature(
            self.templates
        )

        self._update_runtime_components()

    def sync_templates_from_disk(self) -> bool:
        (
            _latest_accounts,
            _latest_groups,
            _latest_tasks,
            latest_templates,
            latest_settings,
            latest_noise_pool,
        ) = self.config_service.load_all()
        latest_signature = self._build_templates_signature(latest_templates)

        self.settings = latest_settings
        self.noise_pool = latest_noise_pool
        self._apply_runtime_paths()
        self.noise_pool_service.replace_all(self.noise_pool, save=False)

        if latest_signature == self._last_templates_signature:
            return False

        self.templates = latest_templates

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self._last_templates_signature = latest_signature

        self.templates_changed.emit()
        self._update_runtime_components()
        return True

    def sync_noise_pool_from_disk(self) -> bool:
        latest_noise_pool = self.config_service.load_noise_pool()

        if list(latest_noise_pool) == list(self.noise_pool):
            return False

        self.noise_pool = list(latest_noise_pool)
        self.noise_pool_service.replace_all(self.noise_pool, save=False)
        self.noise_pool_changed.emit()
        self._update_runtime_components()
        return True

    def save_accounts(self, accounts) -> None:
        self.ensure_can_modify_sending_data()
        self.accounts = list(accounts)
        self.config_service.save_accounts(self.accounts)
        self._update_runtime_components()

    def save_groups(self, groups) -> None:
        self.ensure_can_modify_sending_data()
        self.groups = list(groups)
        self.config_service.save_groups(self.groups)
        self._update_runtime_components()

    def save_tasks(self, tasks) -> None:
        self.ensure_can_modify_sending_data()
        self.tasks = list(tasks)
        self.config_service.save_tasks(self.tasks)
        self._update_runtime_components()

    def save_tasks_from_runtime(self, tasks) -> None:
        self.tasks = list(tasks)
        self.config_service.save_tasks(self.tasks)
        self._update_runtime_components()

    def save_templates(self, templates) -> None:
        self.ensure_can_modify_sending_data()
        self.templates = list(templates)
        self.config_service.save_templates(self.templates)
        self.template_sender.update_templates(self.templates)
        self._last_templates_signature = self._build_templates_signature(
            self.templates
        )
        self.templates_changed.emit()
        self._update_runtime_components()

    def save_settings(self, settings) -> None:
        changed_fields = self._changed_settings_fields(self.settings, settings)

        if self.is_scheduler_running() and self._settings_change_requires_stop(
            changed_fields
        ):
            raise RuntimeError(SCHEDULER_STOP_MESSAGE)

        template_listening_changed = bool(
            changed_fields & TEMPLATE_LISTENING_SETTING_FIELDS
        )

        self.settings = settings
        self._apply_runtime_paths()
        self.config_service.save_settings(self.settings)
        self._sync_logger_level()

        self.template_collector.settings = self.settings
        self._update_runtime_components()

        if template_listening_changed:
            self.runtime_hint.emit(
                "素材监听配置已更新，正在运行的账号可能需要重启后才会完全生效"
            )

    def save_noise_pool(self, noise_pool: list[str]) -> None:
        self.ensure_can_modify_sending_data()
        self.noise_pool = list(noise_pool)
        self.noise_pool_service.replace_all(self.noise_pool, save=True)
        self.noise_pool = self.noise_pool_service.get_all()
        self.noise_pool_changed.emit()
        self._update_runtime_components()

    def _settings_to_dict(self, settings) -> dict[str, Any]:
        if settings is None:
            return {}

        if hasattr(settings, "to_dict") and callable(settings.to_dict):
            return dict(settings.to_dict())

        if isinstance(settings, dict):
            return dict(settings)

        if hasattr(settings, "__dict__"):
            return dict(settings.__dict__)

        return {}

    def _changed_settings_fields(self, old_settings, new_settings) -> set[str]:
        old_data = self._settings_to_dict(old_settings)
        new_data = self._settings_to_dict(new_settings)
        keys = set(old_data.keys()) | set(new_data.keys())

        return {
            key
            for key in keys
            if old_data.get(key) != new_data.get(key)
        }

    @staticmethod
    def _settings_change_requires_stop(changed_fields: set[str]) -> bool:
        if not changed_fields:
            return False

        return bool(set(changed_fields) - RUNTIME_SAFE_SETTING_FIELDS)

    def _update_runtime_components(self) -> None:
        if self._manager is not None:
            self._manager.update_configuration(
                accounts=self.accounts,
                settings=self.settings,
            )

        self.template_sender.update_templates(self.templates)
        self.template_collector.settings = self.settings
        self.noise_pool_service.replace_all(self.noise_pool, save=False)

        if self._scheduler is not None:
            self._scheduler.update_configuration(
                accounts=self.accounts,
                groups=self.groups,
                tasks=self.tasks,
                templates=self.templates,
                settings=self.settings,
                noise_pool_service=self.noise_pool_service,
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

    def get_running_client(self, account_name: str):
        manager = self._get_manager()
        return manager.get_running_client(account_name)

    def shutdown(self) -> None:
        try:
            self.stop_tgapipldc_process()
        except Exception as exc:
            self._emit_log("warning", f"停止 tgapipldc 流程时出现异常: {exc}")

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

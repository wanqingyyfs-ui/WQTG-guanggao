from __future__ import annotations

import asyncio
import concurrent.futures
import re
import threading

from app.core.strict_static_telegram_client_manager import (
    StrictStaticTelegramClientManager,
)
from app.services.reliable_group_send_service import ReliableGroupSendService
from app.services.reliable_scheduler_service import (
    ReliableSchedulerService as SchedulerService,
)
from app.services.reliable_task_log_service import ReliableTaskLogService
from app.services.reliable_template_service import ReliableTemplateSender
from app.services.runtime_service import RuntimeService as BaseRuntimeService
from app.services.static_account_proxy_service import StaticAccountProxyService
from app.services.strict_tgapipldc_locator_service import (
    StrictTgapipldcLocatorService,
)
from app.services.strict_tgapipldc_runner_service import StrictTgapipldcRunnerService
from app.services.strict_yanzheng_login_provider import (
    StrictStaticYanzhengLoginInputProvider,
)
from app.services.tgapipldc_account_bind_service import TgapipldcAccountBindService
from app.services.tgapipldc_import_service import TgapipldcImportService
from app.services.tgapipldc_proxy_service import TgapipldcProxyService
from app.services.tgapipldc_safe_workspace_service import SafeTgapipldcWorkspaceService


class RuntimeService(BaseRuntimeService):
    """Grouped runtime with a fail-closed static proxy boundary."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.template_sender = ReliableTemplateSender(
            templates=self.templates,
            log_func=self._emit_log,
        )
        self.group_send_service = ReliableGroupSendService(
            template_sender=self.template_sender,
            noise_pool_service=self.noise_pool_service,
            log_func=self._emit_log,
        )
        self.task_log_service = ReliableTaskLogService(
            log_file=self.config_service.logs_dir / "task_send.jsonl",
            log_func=self._emit_log,
        )

        safe_workspace = SafeTgapipldcWorkspaceService(
            self.tgapipldc_workspace_service.workspace_dir
        )
        safe_workspace.ensure_structure()
        self.tgapipldc_workspace_service = safe_workspace
        self.tgapipldc_proxy_service = TgapipldcProxyService(
            workspace_service=safe_workspace
        )
        self.tgapipldc_account_bind_service = TgapipldcAccountBindService(
            workspace_service=safe_workspace
        )
        self.tgapipldc_import_service = TgapipldcImportService(
            workspace_service=safe_workspace
        )
        self.static_account_proxy_service = StaticAccountProxyService(
            config_service=self.config_service,
            workspace_service=safe_workspace,
        )
        self.tgapipldc_runner_service = StrictTgapipldcRunnerService(
            workspace_service=safe_workspace,
            profile_map_builder=self._build_static_profile_map,
        )
        self.tgapipldc_locator_service = StrictTgapipldcLocatorService(
            workspace_service=safe_workspace,
            proxy_provider=self.resolve_static_proxy_for_profile,
        )

        # setup_tgapipldc_pages is imported before RuntimeService is constructed.
        # Replace its service factory before the pages are created so a second
        # locator service cannot silently restore the legacy direct behavior.
        try:
            from app.gui import tgapipldc_panel_bootstrap

            tgapipldc_panel_bootstrap.TgapipldcLocatorService = (
                StrictTgapipldcLocatorService
            )
        except Exception as exc:
            self._emit_log("warning", f"严格定位代理服务注册失败：{exc}")

        self._wqtg_login_future: concurrent.futures.Future | None = None
        self._wqtg_login_lock = threading.RLock()

    def _load_account_group_proxies_for_runtime(self) -> dict:
        return self.static_account_proxy_service.load_group_proxies_strict()

    def _accounts_from_disk(self):
        accounts, _groups, _tasks, _templates, _settings, _noise = (
            self.config_service.load_all()
        )
        return accounts

    def _build_static_profile_map(self):
        accounts = self._accounts_from_disk()
        proxies = self._load_account_group_proxies_for_runtime()
        path = self.static_account_proxy_service.build_static_profile_map(
            accounts,
            proxies,
        )
        self._emit_tgapipldc_log(f"静态代理运行表已生成：{path}")
        return path

    def resolve_static_proxy_for_profile(self, profile_dir: str) -> str:
        accounts = self._accounts_from_disk()
        proxies = self._load_account_group_proxies_for_runtime()
        return self.static_account_proxy_service.proxy_for_profile(
            profile_dir,
            accounts,
            proxies,
        )

    @staticmethod
    def _account_match_key(account) -> str:
        digits = re.sub(r"\D", "", str(getattr(account, "phone", "") or ""))
        if digits:
            return f"phone:{digits}"
        return f"name:{str(getattr(account, 'account_name', '') or '').strip()}"

    def run_tgapipldc_import_api_to_wqtg(self) -> None:
        self.ensure_can_modify_sending_data()
        existing_by_key = {
            self._account_match_key(account): account
            for account in self.accounts
        }
        result = self.tgapipldc_import_service.import_accounts(self.accounts)

        created_disabled = 0
        for account in result.accounts:
            previous = existing_by_key.get(self._account_match_key(account))
            if previous is not None:
                account.account_group = str(
                    getattr(previous, "account_group", "") or ""
                ).strip()
                account.enabled = bool(getattr(previous, "enabled", True))
            else:
                account.account_group = ""
                account.enabled = False
                created_disabled += 1

        self.save_accounts(result.accounts)
        self.reload_config_cache()
        self._emit_tgapipldc_log(
            "API 导入 WQTG 完成："
            f"新增 {result.created_count} 个，"
            f"更新 {result.updated_count} 个，"
            f"跳过 {result.skipped_count} 个，"
            f"其中新账号 {created_disabled} 个已保持禁用，"
            "必须分配账号组静态代理后才能启用；"
            f"来源 {result.api_csv_path}"
        )

    def _update_runtime_components(self) -> None:
        if self._manager is not None:
            self._manager.update_configuration(
                accounts=self.accounts,
                settings=self.settings,
                account_group_proxies=self._load_account_group_proxies_for_runtime(),
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
            self._manager = StrictStaticTelegramClientManager(
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

    def is_tgapipldc_process_running(self) -> bool:
        if super().is_tgapipldc_process_running():
            return True
        with self._wqtg_login_lock:
            future = self._wqtg_login_future
            return bool(future is not None and not future.done())

    def run_tgapipldc_login_wqtg_accounts(self) -> None:
        if self.is_tgapipldc_process_running():
            raise RuntimeError("已有 tgapipldc 流程正在运行，请先停止或等待完成")
        self.reload_config_cache()
        proxies = self._load_account_group_proxies_for_runtime()
        self.static_account_proxy_service.validate_enabled_accounts(
            self.accounts,
            proxies,
        )
        provider = StrictStaticYanzhengLoginInputProvider(
            workspace_service=self.tgapipldc_workspace_service,
            log_func=self._emit_tgapipldc_log,
            static_proxy_service=self.static_account_proxy_service,
            group_proxies=proxies,
        )
        manager = self._get_manager()
        future = self._submit_coroutine(
            self._login_wqtg_accounts_with_yanzheng(manager, provider)
        )
        with self._wqtg_login_lock:
            self._wqtg_login_future = future
        future.add_done_callback(self._clear_wqtg_login_future)

    def _clear_wqtg_login_future(self, future) -> None:
        with self._wqtg_login_lock:
            if self._wqtg_login_future is future:
                self._wqtg_login_future = None

    def stop_tgapipldc_process(self) -> None:
        stopped_process = self.tgapipldc_runner_service.stop_current_process()
        with self._wqtg_login_lock:
            future = self._wqtg_login_future
        cancelled_login = bool(
            future is not None and not future.done() and future.cancel()
        )
        if stopped_process or cancelled_login:
            self._emit_tgapipldc_log("已请求停止当前 tgapipldc 流程及其子任务")
        else:
            self._emit_tgapipldc_log("当前没有可停止的 tgapipldc 流程")

    def start_task_scheduler(self, task_id: str) -> None:
        self.reload_config_cache()
        task = next(
            (
                item
                for item in self.tasks
                if str(getattr(item, "task_id", "") or "") == str(task_id or "")
            ),
            None,
        )
        if task is None:
            raise RuntimeError("任务不存在")
        if not bool(getattr(task, "enabled", True)):
            raise RuntimeError("未启用任务不能启动，请先启用任务")
        scheduler = self._get_scheduler()
        self._submit_coroutine(
            self._start_single_task_and_update_status(scheduler, str(task_id or ""))
        )

    async def _start_single_task_and_update_status(
        self,
        scheduler: SchedulerService,
        task_id: str,
    ) -> None:
        try:
            await scheduler.start_task(task_id)
            self._emit_scheduler_status(
                "running" if scheduler.is_running() else "stopped"
            )
        except Exception:
            self._emit_scheduler_status("error")
            raise

    def stop_task_scheduler(self, task_id: str) -> None:
        scheduler = self._get_scheduler()
        self._submit_coroutine(
            self._stop_single_task_and_update_status(scheduler, str(task_id or ""))
        )

    async def _stop_single_task_and_update_status(
        self,
        scheduler: SchedulerService,
        task_id: str,
    ) -> None:
        try:
            await scheduler.stop_task(task_id)
            self._emit_scheduler_status(
                "running" if scheduler.is_running() else "stopped"
            )
        except Exception:
            self._emit_scheduler_status("error")
            raise

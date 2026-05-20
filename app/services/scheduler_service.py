from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncIterator

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_SINGLE,
    SEND_STATUS_FAILED,
    SEND_STATUS_SKIPPED,
    SEND_STATUS_SUCCESS,
    AccountConfig,
    GroupConfig,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    SendTaskConfig,
    Settings,
    TemplateConfig,
)
from app.services.group_send_service import GroupSendService, SendResult
from app.services.noise_pool_service import NoisePoolService
from app.services.task_log_service import TaskLogService


class SchedulerService:
    def __init__(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        tasks: list[SendTaskConfig],
        templates: list[TemplateConfig],
        settings: Settings,
        client_manager,
        group_send_service: GroupSendService,
        noise_pool_service: NoisePoolService,
        task_log_service: TaskLogService,
        save_tasks_callback,
        log_func=None,
    ):
        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.templates = templates
        self.settings = settings
        self.client_manager = client_manager
        self.group_send_service = group_send_service
        self.noise_pool_service = noise_pool_service
        self.task_log_service = task_log_service
        self.save_tasks_callback = save_tasks_callback
        self.log_func = log_func

        self._stop_event = asyncio.Event()
        self._runner_task: asyncio.Task | None = None
        self._running_task_ids: set[str] = set()
        self._semaphore: asyncio.Semaphore | None = self._build_semaphore(settings)

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _safe_non_negative_int(cls, value, default: int = 0) -> int:
        number = cls._safe_int(value, default)

        if number < 0:
            return 0

        return number

    @classmethod
    def _get_max_concurrent_tasks(cls, settings: Settings) -> int:
        return cls._safe_non_negative_int(
            getattr(settings, "max_concurrent_tasks", 0),
            0,
        )

    @classmethod
    def _build_semaphore(cls, settings: Settings) -> asyncio.Semaphore | None:
        max_concurrent_tasks = cls._get_max_concurrent_tasks(settings)

        if max_concurrent_tasks <= 0:
            return None

        return asyncio.Semaphore(max_concurrent_tasks)

    @asynccontextmanager
    async def _concurrency_slot(self) -> AsyncIterator[None]:
        semaphore = self._semaphore

        if semaphore is None:
            yield
            return

        async with semaphore:
            yield

    def _save_tasks_safely(self) -> None:
        try:
            self.save_tasks_callback(self.tasks)
        except Exception as exc:
            self._log("error", f"保存任务配置失败: {exc}")

    def update_configuration(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        tasks: list[SendTaskConfig],
        templates: list[TemplateConfig],
        settings: Settings,
        noise_pool_service: NoisePoolService,
    ) -> None:
        old_max_concurrent_tasks = self._get_max_concurrent_tasks(self.settings)
        new_max_concurrent_tasks = self._get_max_concurrent_tasks(settings)

        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.templates = templates
        self.settings = settings
        self.noise_pool_service = noise_pool_service
        self.group_send_service.noise_pool_service = noise_pool_service

        if old_max_concurrent_tasks != new_max_concurrent_tasks:
            self._semaphore = self._build_semaphore(settings)

    def is_running(self) -> bool:
        return self._runner_task is not None and not self._runner_task.done()

    async def start(self) -> None:
        if self.is_running():
            self._log("warning", "群发调度器已经在运行")
            return

        self._stop_event = asyncio.Event()
        self._runner_task = asyncio.create_task(
            self.run_loop(),
            name="group-send-scheduler-loop",
        )
        self._runner_task.add_done_callback(
            lambda task: self._handle_background_task_done(
                task,
                "群发调度器主循环",
            )
        )
        self._log("info", "群发调度器已启动")

    async def stop(self) -> None:
        if not self.is_running():
            self._log("info", "群发调度器未运行")
            return

        self._stop_event.set()

        if self._runner_task is not None:
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass

        self._runner_task = None
        self._running_task_ids.clear()
        self._log("info", "群发调度器已停止")

    async def run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_due_tasks()
            except Exception as exc:
                self._log("error", f"群发调度循环异常: {exc}")

            tick_seconds = max(
                0.05,
                self._safe_float(
                    getattr(self.settings, "scheduler_tick_seconds", 1.0),
                    1.0,
                ),
            )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=tick_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def run_due_tasks(self) -> None:
        now = datetime.now()

        for task in list(self.tasks):
            if self._stop_event.is_set():
                return

            if not getattr(task, "enabled", True):
                continue

            if task.task_id in self._running_task_ids:
                continue

            if not self._is_task_due(task, now):
                continue

            background_task = asyncio.create_task(
                self._execute_scheduled_task(task),
                name=f"group-send-task-{task.task_id}",
            )
            background_task.add_done_callback(
                lambda done_task, task_name=task.task_name: (
                    self._handle_background_task_done(
                        done_task,
                        f"群发任务: {task_name}",
                    )
                )
            )

    def _handle_background_task_done(
        self,
        task: asyncio.Task,
        task_name: str,
    ) -> None:
        if task.cancelled():
            self._log("warning", f"{task_name} 已取消")
            return

        try:
            exception = task.exception()
        except asyncio.CancelledError:
            self._log("warning", f"{task_name} 已取消")
            return

        if exception is not None:
            self._log("error", f"{task_name} 异常结束: {exception}")

    async def _execute_scheduled_task(self, task: SendTaskConfig) -> None:
        await self._execute_task(task)

    async def _execute_task(self, task: SendTaskConfig) -> SendResult | None:
        self._running_task_ids.add(task.task_id)
        last_result: SendResult | None = None

        try:
            async with self._concurrency_slot():
                account_names = self._get_effective_task_account_names(task)
                groups = self._get_effective_task_groups(task)

                if not account_names:
                    self._log(
                        "error",
                        f"任务没有可用发送账号 | task={task.task_name}",
                    )
                    return None

                if not groups:
                    self._log(
                        "error",
                        f"任务没有可用目标群组 | task={task.task_name}",
                    )
                    return None

                last_result = await self._execute_matrix_task(
                    task=task,
                    account_names=account_names,
                    groups=groups,
                )
                return last_result

        finally:
            self._mark_task_finished(task)
            self._running_task_ids.discard(task.task_id)

    async def _execute_matrix_task(
        self,
        task: SendTaskConfig,
        account_names: list[str],
        groups: list[GroupConfig],
    ) -> SendResult | None:
        account_delay_min_ms, account_delay_max_ms = self._get_account_delay_range_ms(
            task
        )
        group_delay_min_ms, group_delay_max_ms = self._get_group_delay_range_ms(task)
        account_initial_delays_ms = self._build_account_initial_delays_ms(
            account_count=len(account_names),
            delay_min_ms=account_delay_min_ms,
            delay_max_ms=account_delay_max_ms,
        )

        self._log(
            "info",
            f"开始多账号多群组轮询任务 | task={task.task_name} | "
            f"accounts={len(account_names)} | groups={len(groups)} | "
            f"account_delay={account_delay_min_ms}-{account_delay_max_ms}ms | "
            f"group_delay={group_delay_min_ms}-{group_delay_max_ms}ms | "
            f"max_concurrent_tasks={self._get_max_concurrent_tasks(self.settings)}",
        )

        account_jobs: list[asyncio.Task] = []

        for account_index, account_name in enumerate(account_names):
            account_job = asyncio.create_task(
                self._execute_account_group_pipeline(
                    task=task,
                    account_name=account_name,
                    account_index=account_index,
                    account_count=len(account_names),
                    groups=groups,
                    initial_delay_ms=account_initial_delays_ms[account_index],
                    group_delay_min_ms=group_delay_min_ms,
                    group_delay_max_ms=group_delay_max_ms,
                ),
                name=(
                    f"group-send-matrix-{task.task_id}-"
                    f"account-{account_index}"
                ),
            )
            account_job.add_done_callback(
                lambda done_task, task_name=task.task_name, account=account_name: (
                    self._handle_background_task_done(
                        done_task,
                        f"多账号轮询任务: {task_name} / {account}",
                    )
                )
            )
            account_jobs.append(account_job)

        if not account_jobs:
            return None

        collected_results = await asyncio.gather(
            *account_jobs,
            return_exceptions=True,
        )

        last_result: SendResult | None = None
        success_count = 0
        failed_count = 0
        skipped_count = 0

        for item in collected_results:
            if isinstance(item, Exception):
                failed_count += 1
                self._log(
                    "error",
                    f"多账号轮询任务异常 | task={task.task_name} | error={item}",
                )
                continue

            if not item:
                continue

            for result in item:
                last_result = result

                if getattr(result, "status", "") == SEND_STATUS_SUCCESS:
                    success_count += 1
                elif getattr(result, "status", "") == SEND_STATUS_SKIPPED:
                    skipped_count += 1
                else:
                    failed_count += 1

        self._advance_indexes_after_batch(
            task=task,
            account_count=len(account_names),
            group_count=len(groups),
        )
        self._save_tasks_safely()

        self._log(
            "info",
            f"多账号多群组轮询任务结束 | task={task.task_name} | "
            f"success={success_count} | failed={failed_count} | skipped={skipped_count}",
        )

        return last_result

    async def _execute_account_group_pipeline(
        self,
        task: SendTaskConfig,
        account_name: str,
        account_index: int,
        account_count: int,
        groups: list[GroupConfig],
        initial_delay_ms: int,
        group_delay_min_ms: int,
        group_delay_max_ms: int,
    ) -> list[SendResult]:
        results: list[SendResult] = []

        if initial_delay_ms > 0:
            self._log(
                "info",
                f"账号进入轮询前等待 {initial_delay_ms} 毫秒 | "
                f"task={task.task_name} | account={account_name}",
            )
            await self._sleep_ms(initial_delay_ms)

        if self._stop_event.is_set():
            return results

        account = self._find_account(account_name)
        if account is None:
            for group in groups:
                result = self._build_failed_result(
                    task=task,
                    group=group,
                    account_name=account_name,
                    error=f"账号不存在: {account_name}",
                )
                self.task_log_service.append_result(result)
                results.append(result)

            self._log(
                "error",
                f"轮询账号不存在，已跳过该账号全部群组 | "
                f"task={task.task_name} | account={account_name}",
            )
            return results

        if not account.enabled:
            for group in groups:
                result = self._build_failed_result(
                    task=task,
                    group=group,
                    account_name=account.account_name,
                    error=f"账号未启用: {account.account_name}",
                )
                self.task_log_service.append_result(result)
                results.append(result)

            self._log(
                "warning",
                f"轮询账号未启用，已跳过该账号全部群组 | "
                f"task={task.task_name} | account={account.account_name}",
            )
            return results

        try:
            client = await self.client_manager.ensure_account_started(
                account.account_name
            )
        except Exception as exc:
            for group in groups:
                result = self._build_failed_result(
                    task=task,
                    group=group,
                    account_name=account.account_name,
                    error=f"账号启动失败: {exc}",
                )
                self.task_log_service.append_result(result)
                results.append(result)

            self._log(
                "error",
                f"轮询账号启动失败，已跳过该账号全部群组 | "
                f"task={task.task_name} | account={account.account_name} | "
                f"error={exc}",
            )
            return results

        for group_index, group in enumerate(groups):
            if self._stop_event.is_set():
                return results

            if group_index > 0:
                delay_ms = self._random_delay_ms(
                    group_delay_min_ms,
                    group_delay_max_ms,
                )
                if delay_ms > 0:
                    self._log(
                        "info",
                        f"账号切换下一个群组前等待 {delay_ms} 毫秒 | "
                        f"task={task.task_name} | account={account.account_name} | "
                        f"next_group={group.group_name}",
                    )
                    await self._sleep_ms(delay_ms)

            task.account_name = account.account_name
            task.group_id = group.group_id
            task.current_account_index = account_index
            task.current_group_index = group_index

            self._log(
                "info",
                f"轮询发送 | task={task.task_name} | "
                f"account={account.account_name} | "
                f"account_index={account_index + 1}/{account_count} | "
                f"group={group.group_name} | "
                f"group_index={group_index + 1}/{len(groups)}",
            )

            try:
                result = await self.group_send_service.execute_task(
                    account_name=account.account_name,
                    client=client,
                    group=group,
                    task=task,
                    settings=self.settings,
                )
            except Exception as exc:
                result = self._build_failed_result(
                    task=task,
                    group=group,
                    account_name=account.account_name,
                    error=str(exc),
                )
                self._log(
                    "error",
                    f"轮询发送异常 | task={task.task_name} | "
                    f"account={account.account_name} | group={group.group_name} | "
                    f"error={exc}",
                )

            self.task_log_service.append_result(result)
            results.append(result)

        return results

    def _build_failed_result(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account_name: str,
        error: str,
    ) -> SendResult:
        now_text = datetime.now().isoformat(timespec="seconds")
        account_names = self._get_task_account_names(task)
        group_ids = self._get_task_group_ids(task)
        template_ids = self._get_task_template_ids(task)

        return SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status=SEND_STATUS_FAILED,
            error=error,
            started_at=now_text,
            finished_at=now_text,
            rotate_mode=self._get_task_account_rotate_mode(task),
            account_index=self._safe_int(
                getattr(task, "current_account_index", 0),
                0,
            ),
            selected_account_name=account_name,
            account_pool=account_names,
            account_pool_size=len(account_names),
            group_rotate_mode=self._get_task_group_rotate_mode(task),
            group_index=self._safe_int(
                getattr(task, "current_group_index", 0),
                0,
            ),
            selected_group_id=str(getattr(group, "group_id", "") or ""),
            selected_group_name=str(getattr(group, "group_name", "") or ""),
            group_pool=group_ids,
            group_pool_size=len(group_ids),
            template_id=str(getattr(task, "template_id", "") or ""),
            template_ids=template_ids,
            account_delay_min_ms=self._get_account_delay_range_ms(task)[0],
            account_delay_max_ms=self._get_account_delay_range_ms(task)[1],
            group_delay_min_ms=self._get_group_delay_range_ms(task)[0],
            group_delay_max_ms=self._get_group_delay_range_ms(task)[1],
        )

    def calculate_next_run(self, task: SendTaskConfig, now: datetime | None = None) -> str:
        now = now or datetime.now()

        if task.schedule_mode == SCHEDULE_MODE_DAILY:
            hour, minute = self._parse_daily_time(task.daily_time)
            next_run = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            if next_run <= now:
                next_run = next_run + timedelta(days=1)

            return next_run.isoformat(timespec="seconds")

        interval_ms = self._safe_non_negative_int(
            getattr(task, "interval_ms", 3600000),
            3600000,
        )
        return (now + timedelta(milliseconds=interval_ms)).isoformat(
            timespec="seconds"
        )

    def _is_task_due(self, task: SendTaskConfig, now: datetime) -> bool:
        if task.schedule_mode not in {SCHEDULE_MODE_INTERVAL, SCHEDULE_MODE_DAILY}:
            task.schedule_mode = SCHEDULE_MODE_INTERVAL

        if not task.next_run_at:
            if task.schedule_mode == SCHEDULE_MODE_DAILY:
                task.next_run_at = self.calculate_next_run(task, now)
                self._save_tasks_safely()
                try:
                    return datetime.fromisoformat(task.next_run_at) <= now
                except ValueError:
                    return False

            task.next_run_at = now.isoformat(timespec="seconds")
            self._save_tasks_safely()
            return True

        try:
            next_run_at = datetime.fromisoformat(task.next_run_at)
        except ValueError:
            task.next_run_at = now.isoformat(timespec="seconds")
            self._save_tasks_safely()
            return True

        return next_run_at <= now

    def _mark_task_finished(self, task: SendTaskConfig) -> None:
        now = datetime.now()
        task.last_run_at = now.isoformat(timespec="seconds")
        task.next_run_at = self.calculate_next_run(task, now)
        self._save_tasks_safely()

    def _get_effective_task_account_names(self, task: SendTaskConfig) -> list[str]:
        account_names = self._get_task_account_names(task)

        if not account_names:
            return []

        account_rotate_mode = self._get_task_account_rotate_mode(task)

        if account_rotate_mode == ACCOUNT_ROTATE_MODE_SINGLE:
            selected_account_name = account_names[0]
            task.account_name = selected_account_name
            task.account_names = [selected_account_name]
            return [selected_account_name]

        start_index = self._normalize_current_account_index(
            task=task,
            account_count=len(account_names),
        )
        rotated_account_names = account_names[start_index:] + account_names[:start_index]
        task.account_name = rotated_account_names[0]
        return rotated_account_names

    def _get_effective_task_groups(self, task: SendTaskConfig) -> list[GroupConfig]:
        group_ids = self._get_task_group_ids(task)

        if not group_ids:
            return []

        group_rotate_mode = self._get_task_group_rotate_mode(task)

        if group_rotate_mode == GROUP_ROTATE_MODE_ROUND_ROBIN:
            start_index = self._normalize_current_group_index(
                task=task,
                group_count=len(group_ids),
            )
            group_ids = group_ids[start_index:] + group_ids[:start_index]
        else:
            group_ids = group_ids[:1]

        groups: list[GroupConfig] = []

        for group_id in group_ids:
            group = self._find_group(group_id)

            if group is None:
                self._log(
                    "error",
                    f"任务目标群不存在，已跳过 | "
                    f"task={task.task_name} | group_id={group_id}",
                )
                continue

            groups.append(group)

        if groups:
            task.group_id = groups[0].group_id

        return groups

    def _get_task_account_names(self, task: SendTaskConfig) -> list[str]:
        raw_account_names = getattr(task, "account_names", []) or []
        account_names: list[str] = []

        for raw_account_name in raw_account_names:
            account_name = str(raw_account_name or "").strip()
            if account_name and account_name not in account_names:
                account_names.append(account_name)

        legacy_account_name = str(getattr(task, "account_name", "") or "").strip()

        if legacy_account_name and legacy_account_name not in account_names:
            account_names.insert(0, legacy_account_name)

        if not legacy_account_name and account_names:
            task.account_name = account_names[0]

        task.account_names = account_names

        return account_names

    def _get_task_group_ids(self, task: SendTaskConfig) -> list[str]:
        raw_group_ids = getattr(task, "group_ids", []) or []
        group_ids: list[str] = []

        for raw_group_id in raw_group_ids:
            group_id = str(raw_group_id or "").strip()
            if group_id and group_id not in group_ids:
                group_ids.append(group_id)

        legacy_group_id = str(getattr(task, "group_id", "") or "").strip()

        if legacy_group_id and legacy_group_id not in group_ids:
            group_ids.insert(0, legacy_group_id)

        if not legacy_group_id and group_ids:
            task.group_id = group_ids[0]

        task.group_ids = group_ids

        return group_ids

    def _get_task_template_ids(self, task: SendTaskConfig) -> list[str]:
        raw_template_ids = getattr(task, "template_ids", []) or []
        template_ids: list[str] = []

        for raw_template_id in raw_template_ids:
            template_id = str(raw_template_id or "").strip()
            if template_id and template_id not in template_ids:
                template_ids.append(template_id)

        legacy_template_id = str(getattr(task, "template_id", "") or "").strip()

        if legacy_template_id and legacy_template_id not in template_ids:
            template_ids.insert(0, legacy_template_id)

        if not legacy_template_id and template_ids:
            task.template_id = template_ids[0]

        task.template_ids = template_ids

        return template_ids

    @staticmethod
    def _get_task_account_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            ACCOUNT_ROTATE_MODE_SINGLE,
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        }:
            return ACCOUNT_ROTATE_MODE_SINGLE

        return rotate_mode

    @staticmethod
    def _get_task_group_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "group_rotate_mode", GROUP_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            GROUP_ROTATE_MODE_SINGLE,
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        }:
            return GROUP_ROTATE_MODE_SINGLE

        return rotate_mode

    def _normalize_current_account_index(
        self,
        task: SendTaskConfig,
        account_count: int,
    ) -> int:
        if account_count <= 0:
            task.current_account_index = 0
            return 0

        current_index = self._safe_int(
            getattr(task, "current_account_index", 0),
            0,
        )

        if current_index < 0:
            current_index = 0

        current_index = current_index % account_count
        task.current_account_index = current_index

        return current_index

    def _normalize_current_group_index(
        self,
        task: SendTaskConfig,
        group_count: int,
    ) -> int:
        if group_count <= 0:
            task.current_group_index = 0
            return 0

        current_index = self._safe_int(
            getattr(task, "current_group_index", 0),
            0,
        )

        if current_index < 0:
            current_index = 0

        current_index = current_index % group_count
        task.current_group_index = current_index

        return current_index

    def _advance_indexes_after_batch(
        self,
        task: SendTaskConfig,
        account_count: int,
        group_count: int,
    ) -> None:
        if account_count <= 0:
            task.current_account_index = 0
        elif self._get_task_account_rotate_mode(task) == ACCOUNT_ROTATE_MODE_ROUND_ROBIN:
            task.current_account_index = (
                self._safe_int(getattr(task, "current_account_index", 0), 0) + 1
            ) % account_count
        else:
            task.current_account_index = 0

        if group_count <= 0:
            task.current_group_index = 0
        elif self._get_task_group_rotate_mode(task) == GROUP_ROTATE_MODE_ROUND_ROBIN:
            task.current_group_index = (
                self._safe_int(getattr(task, "current_group_index", 0), 0) + 1
            ) % group_count
        else:
            task.current_group_index = 0

    def _get_account_delay_range_ms(self, task: SendTaskConfig) -> tuple[int, int]:
        min_ms = self._safe_non_negative_int(
            getattr(task, "account_delay_min_ms", 0),
            0,
        )
        max_ms = self._safe_non_negative_int(
            getattr(task, "account_delay_max_ms", min_ms),
            min_ms,
        )

        if max_ms < min_ms:
            max_ms = min_ms

        return min_ms, max_ms

    def _get_group_delay_range_ms(self, task: SendTaskConfig) -> tuple[int, int]:
        min_ms = self._safe_non_negative_int(
            getattr(task, "group_delay_min_ms", 0),
            0,
        )
        max_ms = self._safe_non_negative_int(
            getattr(task, "group_delay_max_ms", min_ms),
            min_ms,
        )

        if max_ms < min_ms:
            max_ms = min_ms

        return min_ms, max_ms

    def _build_account_initial_delays_ms(
        self,
        account_count: int,
        delay_min_ms: int,
        delay_max_ms: int,
    ) -> list[int]:
        if account_count <= 0:
            return []

        delays = [0]
        total_delay_ms = 0

        for _index in range(1, account_count):
            total_delay_ms += self._random_delay_ms(delay_min_ms, delay_max_ms)
            delays.append(total_delay_ms)

        return delays

    @staticmethod
    def _random_delay_ms(delay_min_ms: int, delay_max_ms: int) -> int:
        safe_min = max(0, int(delay_min_ms or 0))
        safe_max = max(0, int(delay_max_ms or 0))

        if safe_max < safe_min:
            safe_max = safe_min

        if safe_max <= 0:
            return 0

        return random.randint(safe_min, safe_max)

    @staticmethod
    async def _sleep_ms(delay_ms: int) -> None:
        if delay_ms <= 0:
            return

        await asyncio.sleep(delay_ms / 1000)

    @staticmethod
    def _parse_daily_time(daily_time: str) -> tuple[int, int]:
        raw_text = (daily_time or "09:00").strip()

        try:
            hour_text, minute_text = raw_text.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except Exception:
            return 9, 0

        if hour < 0 or hour > 23:
            hour = 9

        if minute < 0 or minute > 59:
            minute = 0

        return hour, minute

    def _find_account(self, account_name: str) -> AccountConfig | None:
        return next(
            (
                account
                for account in self.accounts
                if account.account_name == account_name
            ),
            None,
        )

    def _find_group(self, group_id: str) -> GroupConfig | None:
        safe_group_id = str(group_id or "").strip()

        return next(
            (
                group
                for group in self.groups
                if str(group.group_id or "").strip() == safe_group_id
            ),
            None,
        )
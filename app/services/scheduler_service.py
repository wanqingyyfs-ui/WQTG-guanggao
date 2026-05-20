from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from dataclasses import replace
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
    """群发调度器。

    设计目标：
    - 不再依赖用户可见的固定扫描间隔。
    - 根据所有任务最近 next_run_at 精准等待。
    - interval_ms=0 时允许任务结束后立即进入下一轮，但通过事件循环让步避免 CPU 空转。
    - 群组延迟、账号延迟都在动作后执行，并且包括最后一个动作。
    - 调度等待和延迟等待都能响应停止。
    - 并发执行中不通过长期修改共享 task 对象决定本次账号、群组、模板。
    - 写入任务日志前先写入本次真实 group/account 实际延迟。
    """

    MIN_IDLE_SLEEP_SECONDS = 0.05
    ZERO_INTERVAL_YIELD_SECONDS = 0.001
    INTERRUPTIBLE_SLEEP_SLICE_SECONDS = 0.2

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
        self._background_tasks: set[asyncio.Task] = set()
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

    @staticmethod
    def _iso_ms(value: datetime | None = None) -> str:
        return (value or datetime.now()).isoformat(timespec="milliseconds")

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
        self._background_tasks.clear()
        self._running_task_ids.clear()
        self._runner_task = asyncio.create_task(
            self.run_loop(),
            name="group-send-scheduler-loop",
        )
        self._runner_task.add_done_callback(
            lambda task: self._handle_background_task_done(task, "群发调度器主循环")
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

        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._runner_task = None
        self._background_tasks.clear()
        self._running_task_ids.clear()
        self._log("info", "群发调度器已停止")

    async def run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                started_count = await self.run_due_tasks()
            except Exception as exc:
                started_count = 0
                self._log("error", f"群发调度循环异常: {exc}")

            if self._stop_event.is_set():
                break

            if started_count > 0:
                await asyncio.sleep(self.ZERO_INTERVAL_YIELD_SECONDS)
                continue

            timeout_seconds = self._seconds_until_nearest_task(datetime.now())
            await self._wait_for_next_scheduler_event(timeout_seconds)

    async def run_due_tasks(self) -> int:
        now = datetime.now()
        started_count = 0

        for task in list(self.tasks):
            if self._stop_event.is_set():
                return started_count

            if not getattr(task, "enabled", True):
                continue

            if not str(getattr(task, "task_id", "") or "").strip():
                continue

            if task.task_id in self._running_task_ids:
                continue

            if not self._is_task_due(task, now):
                continue

            self._running_task_ids.add(task.task_id)
            background_task = asyncio.create_task(
                self._execute_scheduled_task(task),
                name=f"group-send-task-{task.task_id}",
            )
            self._background_tasks.add(background_task)
            background_task.add_done_callback(
                lambda done_task, task_name=task.task_name: self._on_scheduled_task_done(
                    done_task,
                    task_name,
                )
            )
            started_count += 1

        return started_count

    def _on_scheduled_task_done(self, task: asyncio.Task, task_name: str) -> None:
        self._background_tasks.discard(task)
        self._handle_background_task_done(task, f"群发任务: {task_name}")

    def _handle_background_task_done(self, task: asyncio.Task, task_name: str) -> None:
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

    async def _wait_for_next_scheduler_event(self, timeout_seconds: float | None) -> None:
        if self._stop_event.is_set():
            return

        safe_timeout: float | None
        if timeout_seconds is None:
            safe_timeout = None
        else:
            safe_timeout = max(self.MIN_IDLE_SLEEP_SECONDS, float(timeout_seconds))

        stop_waiter = asyncio.create_task(self._stop_event.wait())
        wait_items: set[asyncio.Task] = {stop_waiter}
        wait_items.update(task for task in self._background_tasks if not task.done())

        try:
            await asyncio.wait(
                wait_items,
                timeout=safe_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            if not stop_waiter.done():
                stop_waiter.cancel()

    async def _execute_scheduled_task(self, task: SendTaskConfig) -> None:
        try:
            await self._execute_task(task)
        finally:
            self._running_task_ids.discard(task.task_id)

    async def _execute_task(self, task: SendTaskConfig) -> SendResult | None:
        last_result: SendResult | None = None

        try:
            async with self._concurrency_slot():
                account_names = self._get_effective_task_account_names(task)
                groups = self._get_effective_task_groups(task)

                if not account_names:
                    self._log("error", f"任务没有可用发送账号 | task={task.task_name}")
                    return None

                if not groups:
                    self._log("error", f"任务没有可用目标群组 | task={task.task_name}")
                    return None

                last_result = await self._execute_matrix_task(
                    task=task,
                    account_names=account_names,
                    groups=groups,
                )
                return last_result

        finally:
            self._mark_task_finished(task)

    async def _execute_matrix_task(
        self,
        task: SendTaskConfig,
        account_names: list[str],
        groups: list[GroupConfig],
    ) -> SendResult | None:
        account_delay_min_ms, account_delay_max_ms = self._get_account_delay_range_ms(task)
        group_delay_min_ms, group_delay_max_ms = self._get_group_delay_range_ms(task)

        traversal_mode = self._choose_traversal_mode(
            account_delay_min_ms=account_delay_min_ms,
            account_delay_max_ms=account_delay_max_ms,
            group_delay_min_ms=group_delay_min_ms,
            group_delay_max_ms=group_delay_max_ms,
        )
        sequence = self._build_send_sequence(
            account_names=account_names,
            groups=groups,
            traversal_mode=traversal_mode,
        )

        self._log(
            "info",
            f"开始多账号多群组交叉轮询任务 | task={task.task_name} | "
            f"accounts={len(account_names)} | groups={len(groups)} | "
            f"traversal_mode={traversal_mode} | "
            f"account_delay={account_delay_min_ms}-{account_delay_max_ms}ms | "
            f"group_delay={group_delay_min_ms}-{group_delay_max_ms}ms | "
            f"max_concurrent_tasks={self._get_max_concurrent_tasks(self.settings)}",
        )

        all_results: list[SendResult] = []
        last_result: SendResult | None = None

        for position, (account_name, group) in enumerate(sequence):
            if self._stop_event.is_set():
                break

            result = await self._execute_sequence_item(
                task=task,
                account_name=account_name,
                group=group,
                account_names=account_names,
                groups=groups,
                sequence_position=position,
                sequence_count=len(sequence),
            )

            account_delay_ms, group_delay_ms = self._delay_for_next_transition(
                sequence=sequence,
                position=position,
                traversal_mode=traversal_mode,
                account_delay_min_ms=account_delay_min_ms,
                account_delay_max_ms=account_delay_max_ms,
                group_delay_min_ms=group_delay_min_ms,
                group_delay_max_ms=group_delay_max_ms,
            )
            self._apply_actual_transition_delay(
                result=result,
                account_delay_ms=account_delay_ms,
                group_delay_ms=group_delay_ms,
            )
            self.task_log_service.append_result(result)

            all_results.append(result)
            last_result = result

            await self._sleep_after_transition(
                task=task,
                account_name=account_name,
                group=group,
                account_delay_ms=account_delay_ms,
                group_delay_ms=group_delay_ms,
                traversal_mode=traversal_mode,
            )

        success_count = 0
        failed_count = 0
        skipped_count = 0

        for result in all_results:
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
            f"多账号多群组交叉轮询任务结束 | task={task.task_name} | "
            f"traversal_mode={traversal_mode} | "
            f"success={success_count} | failed={failed_count} | skipped={skipped_count}",
        )

        return last_result

    async def _execute_sequence_item(
        self,
        task: SendTaskConfig,
        account_name: str,
        group: GroupConfig,
        account_names: list[str],
        groups: list[GroupConfig],
        sequence_position: int,
        sequence_count: int,
    ) -> SendResult:
        account_index = self._source_account_index(task, account_name)
        group_index = self._source_group_index(task, group.group_id)

        account = self._find_account(account_name)
        if account is None:
            self._log(
                "error",
                f"轮询账号不存在，已跳过本次动作 | task={task.task_name} | "
                f"account={account_name} | group={group.group_name}",
            )
            return self._build_failed_result(
                task=task,
                group=group,
                account_name=account_name,
                account_index=account_index,
                group_index=group_index,
                error=f"账号不存在: {account_name}",
            )

        if not account.enabled:
            self._log(
                "warning",
                f"轮询账号未启用，已跳过本次动作 | task={task.task_name} | "
                f"account={account.account_name} | group={group.group_name}",
            )
            return self._build_failed_result(
                task=task,
                group=group,
                account_name=account.account_name,
                account_index=account_index,
                group_index=group_index,
                error=f"账号未启用: {account.account_name}",
            )

        try:
            client = await self.client_manager.ensure_account_started(account.account_name)
        except Exception as exc:
            self._log(
                "error",
                f"轮询账号启动失败，已跳过本次动作 | task={task.task_name} | "
                f"account={account.account_name} | group={group.group_name} | error={exc}",
            )
            return self._build_failed_result(
                task=task,
                group=group,
                account_name=account.account_name,
                account_index=account_index,
                group_index=group_index,
                error=f"账号启动失败: {exc}",
            )

        task_snapshot = self._build_task_snapshot(
            task=task,
            account_name=account.account_name,
            group_id=group.group_id,
            account_index=account_index,
            group_index=group_index,
        )

        self._log(
            "info",
            f"交叉轮询发送 | task={task.task_name} | "
            f"position={sequence_position + 1}/{sequence_count} | "
            f"account={account.account_name} | account_index={account_index + 1}/{len(account_names)} | "
            f"group={group.group_name} | group_index={group_index + 1}/{len(groups)}",
        )

        try:
            return await self.group_send_service.execute_task(
                account_name=account.account_name,
                client=client,
                group=group,
                task=task_snapshot,
                settings=self.settings,
            )
        except Exception as exc:
            self._log(
                "error",
                f"交叉轮询发送异常 | task={task.task_name} | "
                f"account={account.account_name} | group={group.group_name} | error={exc}",
            )
            return self._build_failed_result(
                task=task_snapshot,
                group=group,
                account_name=account.account_name,
                account_index=account_index,
                group_index=group_index,
                error=str(exc),
            )

    def _choose_traversal_mode(
        self,
        account_delay_min_ms: int,
        account_delay_max_ms: int,
        group_delay_min_ms: int,
        group_delay_max_ms: int,
    ) -> str:
        account_score = self._delay_priority_score(account_delay_min_ms, account_delay_max_ms)
        group_score = self._delay_priority_score(group_delay_min_ms, group_delay_max_ms)

        if group_score > account_score:
            return "group_major"

        return "account_major"

    @staticmethod
    def _delay_priority_score(delay_min_ms: int, delay_max_ms: int) -> int:
        return max(0, int(delay_min_ms or 0), int(delay_max_ms or 0))

    @staticmethod
    def _build_send_sequence(
        account_names: list[str],
        groups: list[GroupConfig],
        traversal_mode: str,
    ) -> list[tuple[str, GroupConfig]]:
        sequence: list[tuple[str, GroupConfig]] = []

        if traversal_mode == "group_major":
            for group in groups:
                for account_name in account_names:
                    sequence.append((account_name, group))
            return sequence

        for account_name in account_names:
            for group in groups:
                sequence.append((account_name, group))

        return sequence

    def _delay_for_next_transition(
        self,
        sequence: list[tuple[str, GroupConfig]],
        position: int,
        traversal_mode: str,
        account_delay_min_ms: int,
        account_delay_max_ms: int,
        group_delay_min_ms: int,
        group_delay_max_ms: int,
    ) -> tuple[int, int]:
        next_position = position + 1
        if next_position >= len(sequence):
            return 0, 0

        account_name, group = sequence[position]
        next_account_name, next_group = sequence[next_position]

        account_changed = str(account_name or "") != str(next_account_name or "")
        group_changed = str(getattr(group, "group_id", "") or "") != str(
            getattr(next_group, "group_id", "") or ""
        )

        if traversal_mode == "group_major":
            if group_changed:
                return 0, self._random_delay_ms(group_delay_min_ms, group_delay_max_ms)
            if account_changed:
                return self._random_delay_ms(account_delay_min_ms, account_delay_max_ms), 0
            return 0, 0

        if account_changed:
            return self._random_delay_ms(account_delay_min_ms, account_delay_max_ms), 0

        if group_changed:
            return 0, self._random_delay_ms(group_delay_min_ms, group_delay_max_ms)

        return 0, 0

    @staticmethod
    def _apply_actual_transition_delay(
        result: SendResult | None,
        account_delay_ms: int,
        group_delay_ms: int,
    ) -> None:
        if result is None:
            return

        setattr(result, "actual_account_delay_ms", max(0, int(account_delay_ms or 0)))
        setattr(result, "actual_group_delay_ms", max(0, int(group_delay_ms or 0)))

    async def _sleep_after_transition(
        self,
        task: SendTaskConfig,
        account_name: str,
        group: GroupConfig,
        account_delay_ms: int,
        group_delay_ms: int,
        traversal_mode: str,
    ) -> None:
        if account_delay_ms > 0:
            self._log(
                "info",
                f"账号切换等待 {account_delay_ms} 毫秒 | task={task.task_name} | "
                f"account={account_name} | group={group.group_name} | traversal_mode={traversal_mode}",
            )
            await self._sleep_ms(account_delay_ms)
            return

        if group_delay_ms > 0:
            self._log(
                "info",
                f"群组切换等待 {group_delay_ms} 毫秒 | task={task.task_name} | "
                f"account={account_name} | group={group.group_name} | traversal_mode={traversal_mode}",
            )
            await self._sleep_ms(group_delay_ms)
            return

        await self._sleep_ms(0)

    def _append_results_to_log(self, results: list[SendResult]) -> None:
        for result in results:
            self.task_log_service.append_result(result)

    def _build_task_snapshot(
        self,
        task: SendTaskConfig,
        account_name: str,
        group_id: str,
        account_index: int,
        group_index: int,
    ) -> SendTaskConfig:
        return replace(
            task,
            account_name=account_name,
            group_id=group_id,
            current_account_index=account_index,
            current_group_index=group_index,
        )

    def _build_failed_result(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account_name: str,
        account_index: int,
        group_index: int,
        error: str,
    ) -> SendResult:
        now_text = self._iso_ms()
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
            account_index=account_index,
            selected_account_name=account_name,
            account_pool=account_names,
            account_pool_size=len(account_names),
            group_rotate_mode=self._get_task_group_rotate_mode(task),
            group_index=group_index,
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
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run + timedelta(days=1)
            return self._iso_ms(next_run)

        interval_ms = self._safe_non_negative_int(getattr(task, "interval_ms", 3600000), 3600000)
        return self._iso_ms(now + timedelta(milliseconds=interval_ms))

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

            task.next_run_at = self._iso_ms(now)
            self._save_tasks_safely()
            return True

        try:
            next_run_at = datetime.fromisoformat(task.next_run_at)
        except ValueError:
            task.next_run_at = self._iso_ms(now)
            self._save_tasks_safely()
            return True

        return next_run_at <= now

    def _mark_task_finished(self, task: SendTaskConfig) -> None:
        now = datetime.now()
        task.last_run_at = self._iso_ms(now)
        task.next_run_at = self.calculate_next_run(task, now)
        self._save_tasks_safely()

    def _seconds_until_nearest_task(self, now: datetime) -> float | None:
        nearest: datetime | None = None
        changed = False

        for task in list(self.tasks):
            if not getattr(task, "enabled", True):
                continue
            if str(getattr(task, "task_id", "") or "") in self._running_task_ids:
                continue

            next_run_at = self._get_or_create_next_run_at(task, now)
            if next_run_at is None:
                continue

            if nearest is None or next_run_at < nearest:
                nearest = next_run_at

            if not getattr(task, "next_run_at", ""):
                changed = True

        if changed:
            self._save_tasks_safely()

        if nearest is None:
            return None

        return max(0.0, (nearest - now).total_seconds())

    def _get_or_create_next_run_at(self, task: SendTaskConfig, now: datetime) -> datetime | None:
        if not getattr(task, "next_run_at", ""):
            if task.schedule_mode == SCHEDULE_MODE_DAILY:
                task.next_run_at = self.calculate_next_run(task, now)
            else:
                task.next_run_at = self._iso_ms(now)

        try:
            return datetime.fromisoformat(task.next_run_at)
        except ValueError:
            task.next_run_at = self._iso_ms(now)
            return now

    def _get_effective_task_account_names(self, task: SendTaskConfig) -> list[str]:
        account_names = self._get_task_account_names(task)
        if not account_names:
            return []

        account_rotate_mode = self._get_task_account_rotate_mode(task)
        if account_rotate_mode == ACCOUNT_ROTATE_MODE_SINGLE:
            return [account_names[0]]

        start_index = self._normalize_current_account_index(task=task, account_count=len(account_names))
        return account_names[start_index:] + account_names[:start_index]

    def _get_effective_task_groups(self, task: SendTaskConfig) -> list[GroupConfig]:
        group_ids = self._get_task_group_ids(task)
        if not group_ids:
            return []

        group_rotate_mode = self._get_task_group_rotate_mode(task)
        if group_rotate_mode == GROUP_ROTATE_MODE_ROUND_ROBIN:
            start_index = self._normalize_current_group_index(task=task, group_count=len(group_ids))
            group_ids = group_ids[start_index:] + group_ids[:start_index]
        else:
            group_ids = group_ids[:1]

        groups: list[GroupConfig] = []
        for group_id in group_ids:
            group = self._find_group(group_id)
            if group is None:
                self._log(
                    "error",
                    f"任务目标群不存在，已跳过 | task={task.task_name} | group_id={group_id}",
                )
                continue
            groups.append(group)
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
        return template_ids

    @staticmethod
    def _get_task_account_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE) or "").strip()
        if rotate_mode not in {ACCOUNT_ROTATE_MODE_SINGLE, ACCOUNT_ROTATE_MODE_ROUND_ROBIN}:
            return ACCOUNT_ROTATE_MODE_SINGLE
        return rotate_mode

    @staticmethod
    def _get_task_group_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(getattr(task, "group_rotate_mode", GROUP_ROTATE_MODE_SINGLE) or "").strip()
        if rotate_mode not in {GROUP_ROTATE_MODE_SINGLE, GROUP_ROTATE_MODE_ROUND_ROBIN}:
            return GROUP_ROTATE_MODE_SINGLE
        return rotate_mode

    def _normalize_current_account_index(self, task: SendTaskConfig, account_count: int) -> int:
        if account_count <= 0:
            task.current_account_index = 0
            return 0

        current_index = self._safe_int(getattr(task, "current_account_index", 0), 0)
        if current_index < 0:
            current_index = 0
        current_index = current_index % account_count
        task.current_account_index = current_index
        return current_index

    def _normalize_current_group_index(self, task: SendTaskConfig, group_count: int) -> int:
        if group_count <= 0:
            task.current_group_index = 0
            return 0

        current_index = self._safe_int(getattr(task, "current_group_index", 0), 0)
        if current_index < 0:
            current_index = 0
        current_index = current_index % group_count
        task.current_group_index = current_index
        return current_index

    def _source_account_index(self, task: SendTaskConfig, account_name: str) -> int:
        account_names = self._get_task_account_names(task)
        if not account_names:
            return 0

        selected = str(account_name or "").strip()
        if selected in account_names:
            return account_names.index(selected)
        return self._normalize_current_account_index(task, len(account_names))

    def _source_group_index(self, task: SendTaskConfig, group_id: str) -> int:
        group_ids = self._get_task_group_ids(task)
        if not group_ids:
            return 0

        selected = str(group_id or "").strip()
        if selected in group_ids:
            return group_ids.index(selected)
        return self._normalize_current_group_index(task, len(group_ids))

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
        min_ms = self._safe_non_negative_int(getattr(task, "account_delay_min_ms", 0), 0)
        max_ms = self._safe_non_negative_int(getattr(task, "account_delay_max_ms", min_ms), min_ms)
        if max_ms < min_ms:
            max_ms = min_ms
        return min_ms, max_ms

    def _get_group_delay_range_ms(self, task: SendTaskConfig) -> tuple[int, int]:
        min_ms = self._safe_non_negative_int(getattr(task, "group_delay_min_ms", 0), 0)
        max_ms = self._safe_non_negative_int(getattr(task, "group_delay_max_ms", min_ms), min_ms)
        if max_ms < min_ms:
            max_ms = min_ms
        return min_ms, max_ms

    @staticmethod
    def _random_delay_ms(delay_min_ms: int, delay_max_ms: int) -> int:
        safe_min = max(0, int(delay_min_ms or 0))
        safe_max = max(0, int(delay_max_ms or 0))
        if safe_max < safe_min:
            safe_max = safe_min
        if safe_max <= 0:
            return 0
        return random.randint(safe_min, safe_max)

    async def _sleep_after_group(
        self,
        task: SendTaskConfig,
        account_name: str,
        group: GroupConfig,
        delay_ms: int,
        group_position: int,
        group_count: int,
    ) -> None:
        if delay_ms > 0:
            self._log(
                "info",
                f"群组发送动作后等待 {delay_ms} 毫秒 | task={task.task_name} | "
                f"account={account_name} | group={group.group_name} | "
                f"group_index={group_position + 1}/{group_count}",
            )
        await self._sleep_ms(delay_ms)

    async def _sleep_after_account(
        self,
        task: SendTaskConfig,
        account_name: str,
        delay_ms: int,
    ) -> None:
        if delay_ms > 0:
            self._log(
                "info",
                f"账号群组流程结束后等待 {delay_ms} 毫秒 | task={task.task_name} | account={account_name}",
            )
        await self._sleep_ms(delay_ms)

    async def _sleep_ms(self, delay_ms: int) -> None:
        safe_delay_ms = max(0, int(delay_ms or 0))
        if safe_delay_ms <= 0:
            await asyncio.sleep(0)
            return

        deadline = datetime.now() + timedelta(milliseconds=safe_delay_ms)
        while not self._stop_event.is_set():
            remaining_seconds = (deadline - datetime.now()).total_seconds()
            if remaining_seconds <= 0:
                return

            timeout_seconds = min(self.INTERRUPTIBLE_SLEEP_SLICE_SECONDS, remaining_seconds)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=timeout_seconds)
                return
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _apply_actual_group_delay(result: SendResult | None, delay_ms: int) -> None:
        if result is not None:
            setattr(result, "actual_group_delay_ms", max(0, int(delay_ms or 0)))

    @staticmethod
    def _apply_actual_account_delay(results: list[SendResult], delay_ms: int) -> None:
        safe_delay_ms = max(0, int(delay_ms or 0))
        for result in results:
            setattr(result, "actual_account_delay_ms", safe_delay_ms)

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
        safe_account_name = str(account_name or "").strip()
        return next(
            (
                account
                for account in self.accounts
                if str(account.account_name or "").strip() == safe_account_name
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

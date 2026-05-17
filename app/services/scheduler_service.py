from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta

from app.core.models import (
    AccountConfig,
    GroupConfig,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    SCHEDULE_MODE_MANUAL,
    SendTaskConfig,
    Settings,
)
from app.services.group_send_service import GroupSendService, SendResult
from app.services.task_log_service import TaskLogService


class SchedulerService:
    def __init__(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        tasks: list[SendTaskConfig],
        settings: Settings,
        client_manager,
        group_send_service: GroupSendService,
        task_log_service: TaskLogService,
        save_tasks_callback,
        log_func=None,
    ):
        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.settings = settings
        self.client_manager = client_manager
        self.group_send_service = group_send_service
        self.task_log_service = task_log_service
        self.save_tasks_callback = save_tasks_callback
        self.log_func = log_func

        self._stop_event = asyncio.Event()
        self._runner_task: asyncio.Task | None = None
        self._running_task_ids: set[str] = set()
        self._semaphore = asyncio.Semaphore(max(1, int(settings.max_concurrent_tasks)))

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    def update_configuration(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        tasks: list[SendTaskConfig],
        settings: Settings,
    ) -> None:
        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.settings = settings
        self._semaphore = asyncio.Semaphore(max(1, int(settings.max_concurrent_tasks)))

    def is_running(self) -> bool:
        return self._runner_task is not None and not self._runner_task.done()

    async def start(self) -> None:
        if self.is_running():
            self._log("warning", "群发调度器已经在运行")
            return

        self._stop_event = asyncio.Event()
        self._runner_task = asyncio.create_task(self.run_loop())
        self._log("info", "群发调度器已启动")

    async def stop(self) -> None:
        if not self.is_running():
            self._log("info", "群发调度器未运行")
            return

        self._stop_event.set()

        if self._runner_task is not None:
            await self._runner_task

        self._runner_task = None
        self._log("info", "群发调度器已停止")

    async def run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_due_tasks()
            except Exception as exc:
                self._log("error", f"群发调度循环异常: {exc}")

            tick_seconds = max(0.2, float(self.settings.scheduler_tick_seconds))

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=tick_seconds)
            except asyncio.TimeoutError:
                pass

    async def run_due_tasks(self) -> None:
        now = datetime.now()

        for task in list(self.tasks):
            if not task.enabled:
                continue

            if task.schedule_mode == SCHEDULE_MODE_MANUAL:
                continue

            if task.task_id in self._running_task_ids:
                continue

            if not self._is_task_due(task, now):
                continue

            asyncio.create_task(self._execute_scheduled_task(task))

    async def send_task_once(self, task_id: str) -> SendResult | None:
        task = self._find_task(task_id)

        if task is None:
            self._log("error", f"手动发送失败，任务不存在 | task_id={task_id}")
            return None

        return await self._execute_task(task)

    async def _execute_scheduled_task(self, task: SendTaskConfig) -> None:
        await self._execute_task(task)

    async def _execute_task(self, task: SendTaskConfig) -> SendResult | None:
        self._running_task_ids.add(task.task_id)

        try:
            async with self._semaphore:
                await self._apply_random_delay(task)

                account = self._find_account(task.account_name)
                if account is None:
                    self._log(
                        "error",
                        f"任务账号不存在 | task={task.task_name} | account={task.account_name}",
                    )
                    return None

                group = self._find_group(task.group_id)
                if group is None:
                    self._log(
                        "error",
                        f"任务目标群不存在 | task={task.task_name} | group_id={task.group_id}",
                    )
                    return None

                client = await self.client_manager.ensure_account_started(task.account_name)
                result = await self.group_send_service.execute_task(
                    account_name=account.account_name,
                    client=client,
                    group=group,
                    task=task,
                )

                self.task_log_service.append_result(result)

                now = datetime.now()
                task.last_run_at = now.isoformat(timespec="seconds")
                task.next_run_at = self.calculate_next_run(task, now)

                self.save_tasks_callback(self.tasks)

                return result

        finally:
            self._running_task_ids.discard(task.task_id)

    async def _apply_random_delay(self, task: SendTaskConfig) -> None:
        delay_min = max(0, int(task.random_delay_min))
        delay_max = max(0, int(task.random_delay_max))

        if delay_max < delay_min:
            delay_min, delay_max = delay_max, delay_min

        if delay_max <= 0:
            return

        delay_seconds = random.randint(delay_min, delay_max)

        if delay_seconds > 0:
            self._log(
                "info",
                f"任务随机延迟 {delay_seconds} 秒 | task={task.task_name}",
            )
            await asyncio.sleep(delay_seconds)

    def calculate_next_run(self, task: SendTaskConfig, now: datetime | None = None) -> str:
        now = now or datetime.now()

        if task.schedule_mode == SCHEDULE_MODE_INTERVAL:
            interval_seconds = max(1, int(task.interval_seconds))
            return (now + timedelta(seconds=interval_seconds)).isoformat(timespec="seconds")

        if task.schedule_mode == SCHEDULE_MODE_DAILY:
            hour, minute = self._parse_daily_time(task.daily_time)
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if next_run <= now:
                next_run = next_run + timedelta(days=1)

            return next_run.isoformat(timespec="seconds")

        return ""

    def _is_task_due(self, task: SendTaskConfig, now: datetime) -> bool:
        if not task.next_run_at:
            task.next_run_at = self.calculate_next_run(task, now)
            self.save_tasks_callback(self.tasks)
            return False

        try:
            next_run_at = datetime.fromisoformat(task.next_run_at)
        except ValueError:
            task.next_run_at = self.calculate_next_run(task, now)
            self.save_tasks_callback(self.tasks)
            return False

        return next_run_at <= now

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
            (account for account in self.accounts if account.account_name == account_name),
            None,
        )

    def _find_group(self, group_id: str) -> GroupConfig | None:
        return next(
            (group for group in self.groups if group.group_id == group_id),
            None,
        )

    def _find_task(self, task_id: str) -> SendTaskConfig | None:
        return next(
            (task for task in self.tasks if task.task_id == task_id),
            None,
        )
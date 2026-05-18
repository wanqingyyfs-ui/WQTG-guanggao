from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
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
        self._semaphore = asyncio.Semaphore(
            self._get_max_concurrent_tasks(settings)
        )

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

    @classmethod
    def _get_max_concurrent_tasks(cls, settings: Settings) -> int:
        return max(1, cls._safe_int(settings.max_concurrent_tasks, 1))

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
        settings: Settings,
    ) -> None:
        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.settings = settings
        self._semaphore = asyncio.Semaphore(
            self._get_max_concurrent_tasks(settings)
        )

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
        self._log("info", "群发调度器已停止")

    async def run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_due_tasks()
            except Exception as exc:
                self._log("error", f"群发调度循环异常: {exc}")

            tick_seconds = max(
                0.2,
                float(self.settings.scheduler_tick_seconds or 1.0),
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
            if not task.enabled:
                continue

            if task.schedule_mode == SCHEDULE_MODE_MANUAL:
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
        result: SendResult | None = None
        should_mark_finished = True

        try:
            async with self._semaphore:
                await self._apply_random_delay(task)

                group = self._find_group(task.group_id)
                if group is None:
                    self._log(
                        "error",
                        f"任务目标群不存在 | task={task.task_name} | group_id={task.group_id}",
                    )
                    return None

                result = await self._execute_task_with_selected_account(
                    task=task,
                    group=group,
                )
                return result

        finally:
            if should_mark_finished:
                self._mark_task_finished(task)

            self._running_task_ids.discard(task.task_id)

    async def _execute_task_with_selected_account(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
    ) -> SendResult | None:
        account_names = self._get_task_account_names(task)

        if not account_names:
            self._log(
                "error",
                f"任务没有可用发送账号 | task={task.task_name}",
            )
            return None

        rotate_mode = self._get_task_rotate_mode(task)

        if rotate_mode == ACCOUNT_ROTATE_MODE_ROUND_ROBIN:
            return await self._execute_round_robin_task(
                task=task,
                group=group,
                account_names=account_names,
            )

        return await self._execute_single_account_task(
            task=task,
            group=group,
            account_names=account_names,
        )

    async def _execute_single_account_task(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account_names: list[str],
    ) -> SendResult | None:
        account_name = (task.account_name or "").strip() or account_names[0]
        account = self._find_account(account_name)

        if account is None:
            self._log(
                "error",
                f"任务账号不存在 | task={task.task_name} | account={account_name}",
            )
            return None

        if not account.enabled:
            self._log(
                "warning",
                f"任务账号未启用，已跳过 | task={task.task_name} | account={account_name}",
            )
            return None

        task.account_name = account.account_name

        return await self._execute_task_by_account(
            task=task,
            group=group,
            account=account,
            account_index=self._account_index_in_pool(
                account_names,
                account.account_name,
            ),
        )

    async def _execute_round_robin_task(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account_names: list[str],
    ) -> SendResult | None:
        account_count = len(account_names)

        if account_count <= 0:
            self._log(
                "error",
                f"轮换账号池为空 | task={task.task_name}",
            )
            return None

        start_index = self._normalize_current_account_index(
            task=task,
            account_count=account_count,
        )

        last_failure_result: SendResult | None = None

        for offset in range(account_count):
            account_index = (start_index + offset) % account_count
            account_name = account_names[account_index]
            account = self._find_account(account_name)

            if account is None:
                self._log(
                    "error",
                    f"轮换账号不存在，尝试下一个 | task={task.task_name} | account={account_name}",
                )
                self._advance_account_index(
                    task=task,
                    account_index=account_index,
                    account_count=account_count,
                )
                continue

            if not account.enabled:
                self._log(
                    "warning",
                    f"轮换账号未启用，尝试下一个 | task={task.task_name} | account={account_name}",
                )
                self._advance_account_index(
                    task=task,
                    account_index=account_index,
                    account_count=account_count,
                )
                continue

            task.account_name = account.account_name

            try:
                result = await self._execute_task_by_account(
                    task=task,
                    group=group,
                    account=account,
                    account_index=account_index,
                )
                return result
            except Exception as exc:
                last_failure_result = self._build_failed_result(
                    task=task,
                    group=group,
                    account_name=account.account_name,
                    error=str(exc),
                )
                self.task_log_service.append_result(last_failure_result)
                self._log(
                    "error",
                    f"轮换账号执行异常，尝试下一个 | task={task.task_name} | "
                    f"account={account.account_name} | error={exc}",
                )
            finally:
                self._advance_account_index(
                    task=task,
                    account_index=account_index,
                    account_count=account_count,
                )

        self._log(
            "error",
            f"轮换账号池全部不可用或全部执行失败 | task={task.task_name}",
        )
        return last_failure_result

    async def _execute_task_by_account(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account: AccountConfig,
        account_index: int,
    ) -> SendResult:
        self._log(
            "info",
            f"选择发送账号 | task={task.task_name} | "
            f"account={account.account_name} | "
            f"rotate_mode={self._get_task_rotate_mode(task)} | "
            f"account_index={account_index}",
        )

        try:
            client = await self.client_manager.ensure_account_started(
                account.account_name
            )
        except Exception as exc:
            result = self._build_failed_result(
                task=task,
                group=group,
                account_name=account.account_name,
                error=f"账号启动失败: {exc}",
            )
            self.task_log_service.append_result(result)
            self._log(
                "error",
                f"账号启动失败 | task={task.task_name} | "
                f"account={account.account_name} | error={exc}",
            )
            return result

        result = await self.group_send_service.execute_task(
            account_name=account.account_name,
            client=client,
            group=group,
            task=task,
        )

        self.task_log_service.append_result(result)
        return result

    def _build_failed_result(
        self,
        task: SendTaskConfig,
        group: GroupConfig,
        account_name: str,
        error: str,
    ) -> SendResult:
        now_text = datetime.now().isoformat(timespec="seconds")

        return SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status="failed",
            error=error,
            started_at=now_text,
            finished_at=now_text,
        )

    async def _apply_random_delay(self, task: SendTaskConfig) -> None:
        delay_min = max(0, self._safe_int(task.random_delay_min, 0))
        delay_max = max(0, self._safe_int(task.random_delay_max, 0))

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
            interval_seconds = max(
                1,
                self._safe_int(task.interval_seconds, 3600),
            )
            return (now + timedelta(seconds=interval_seconds)).isoformat(
                timespec="seconds"
            )

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

        return ""

    def _is_task_due(self, task: SendTaskConfig, now: datetime) -> bool:
        if not task.next_run_at:
            task.next_run_at = self.calculate_next_run(task, now)
            self._save_tasks_safely()
            return False

        try:
            next_run_at = datetime.fromisoformat(task.next_run_at)
        except ValueError:
            task.next_run_at = self.calculate_next_run(task, now)
            self._save_tasks_safely()
            return False

        return next_run_at <= now

    def _mark_task_finished(self, task: SendTaskConfig) -> None:
        now = datetime.now()
        task.last_run_at = now.isoformat(timespec="seconds")
        task.next_run_at = self.calculate_next_run(task, now)
        self._save_tasks_safely()

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

    @staticmethod
    def _get_task_rotate_mode(task: SendTaskConfig) -> str:
        rotate_mode = str(
            getattr(task, "account_rotate_mode", ACCOUNT_ROTATE_MODE_SINGLE) or ""
        ).strip()

        if rotate_mode not in {
            ACCOUNT_ROTATE_MODE_SINGLE,
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        }:
            return ACCOUNT_ROTATE_MODE_SINGLE

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

    def _advance_account_index(
        self,
        task: SendTaskConfig,
        account_index: int,
        account_count: int,
    ) -> None:
        if account_count <= 0:
            task.current_account_index = 0
            return

        task.current_account_index = (account_index + 1) % account_count

    @staticmethod
    def _account_index_in_pool(account_names: list[str], account_name: str) -> int:
        try:
            return account_names.index(account_name)
        except ValueError:
            return 0

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
        return next(
            (group for group in self.groups if group.group_id == group_id),
            None,
        )

    def _find_task(self, task_id: str) -> SendTaskConfig | None:
        return next(
            (task for task in self.tasks if task.task_id == task_id),
            None,
        )
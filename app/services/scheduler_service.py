from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Any

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    SEND_STATUS_FAILED,
    SEND_STATUS_SKIPPED,
    SEND_STATUS_SUCCESS,
    AccountConfig,
    GroupConfig,
    SendTaskConfig,
    Settings,
    TemplateConfig,
)
from app.services.group_pairing_runtime_service import GroupPairingRuntimeService
from app.services.group_send_service import GroupSendService, SendResult
from app.services.noise_pool_service import NoisePoolService
from app.services.task_log_service import TaskLogService


class SchedulerService:
    MIN_IDLE_SLEEP_SECONDS = 0.05
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
        self.runtime_state_service = GroupPairingRuntimeService()
        self._stop_event = asyncio.Event()
        self._task_stop_events: dict[str, asyncio.Event] = {}
        self._task_workers: dict[str, asyncio.Task] = {}
        self._account_send_locks: dict[str, asyncio.Lock] = {}

    def _log(self, level: str, message: str) -> None:
        if callable(self.log_func):
            self.log_func(level, message)

    def update_configuration(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        tasks: list[SendTaskConfig],
        templates: list[TemplateConfig],
        settings: Settings,
        noise_pool_service: NoisePoolService,
    ) -> None:
        self.accounts = accounts
        self.groups = groups
        self.tasks = tasks
        self.templates = templates
        self.settings = settings
        self.noise_pool_service = noise_pool_service
        self.group_send_service.noise_pool_service = noise_pool_service

    def is_running(self) -> bool:
        return any(not task.done() for task in self._task_workers.values())

    def is_task_running(self, task_id: str) -> bool:
        worker = self._task_workers.get(str(task_id or "").strip())
        return worker is not None and not worker.done()

    async def start(self) -> None:
        enabled_tasks = [task for task in self.tasks if bool(getattr(task, "enabled", True))]
        self._validate_enabled_account_identities()
        self._validate_enabled_task_account_group_conflicts(enabled_tasks)
        started = 0
        for task in enabled_tasks:
            if await self.start_task(task.task_id, validate_conflict=False):
                started += 1
        self._log("info", f"群发调度器已启动 | tasks={started}")

    async def stop(self) -> None:
        self._stop_event.set()
        for event in self._task_stop_events.values():
            event.set()
        if self._task_workers:
            await asyncio.gather(*self._task_workers.values(), return_exceptions=True)
        self._task_workers.clear()
        self._task_stop_events.clear()
        self._stop_event = asyncio.Event()
        self._log("info", "群发调度器已停止")

    async def start_task(self, task_id: str, validate_conflict: bool = True) -> bool:
        safe_task_id = str(task_id or "").strip()
        task = self._find_task(safe_task_id)
        if task is None:
            raise RuntimeError("任务不存在")
        if not bool(getattr(task, "enabled", True)):
            raise RuntimeError("未启用任务不能启动，请先启用任务")
        if self.is_task_running(safe_task_id):
            self._log("warning", f"任务已经在运行 | task={task.task_name}")
            return False
        self._validate_enabled_account_identities()
        self._validate_task_runnable(task)
        if validate_conflict:
            self._validate_single_task_conflict(task)
        stop_event = asyncio.Event()
        self._task_stop_events[safe_task_id] = stop_event
        worker = asyncio.create_task(self._task_runner(task, stop_event), name=f"group-pairing-task-{safe_task_id}")
        self._task_workers[safe_task_id] = worker
        worker.add_done_callback(lambda done, tid=safe_task_id: self._on_task_done(tid, done))
        self._log("info", f"任务已启动 | task={task.task_name}")
        return True

    async def stop_task(self, task_id: str) -> None:
        safe_task_id = str(task_id or "").strip()
        event = self._task_stop_events.get(safe_task_id)
        if event is not None:
            event.set()
        worker = self._task_workers.get(safe_task_id)
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)
        self.runtime_state_service.set_task_status(safe_task_id, "manually_stopped", "手动停止任务")
        self._task_workers.pop(safe_task_id, None)
        self._task_stop_events.pop(safe_task_id, None)
        self._log("info", f"任务已停止 | task_id={safe_task_id}")

    def _on_task_done(self, task_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            self._log("warning", f"任务已取消 | task_id={task_id}")
        else:
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                exc = None
            if exc is not None:
                self._log("error", f"任务异常结束 | task_id={task_id} | error={exc}")
        self._task_workers.pop(task_id, None)
        self._task_stop_events.pop(task_id, None)

    async def _task_runner(self, task: SendTaskConfig, task_stop_event: asyncio.Event) -> None:
        task_id = str(task.task_id or "").strip()
        try:
            while not self._should_stop(task_stop_event):
                if bool(getattr(task, "daily_window_enabled", False)):
                    if not self._is_in_daily_window(task):
                        wait_seconds = self._seconds_until_next_daily_start(task)
                        self.runtime_state_service.set_task_status(task_id, "waiting_daily_window", f"等待每日开始时间 {task.daily_start_time}")
                        self._log("info", f"任务等待每日开始时间 | task={task.task_name} | start={task.daily_start_time}")
                        await self._sleep_seconds(wait_seconds, task_stop_event)
                        continue
                    window_end = self._current_daily_window_end(task)
                    await self._run_task_window(task, task_stop_event, window_end)
                    if self._should_stop(task_stop_event):
                        break
                    self.runtime_state_service.set_task_status(task_id, "daily_window_finished", "到达每日结束时间停止")
                    await asyncio.sleep(0)
                    continue
                await self._run_task_window(task, task_stop_event, None)
                break
        finally:
            if self._should_stop(task_stop_event):
                self.runtime_state_service.set_task_status(task_id, "manually_stopped", "手动停止或全局停止")

    async def _run_task_window(self, task: SendTaskConfig, task_stop_event: asyncio.Event, window_end: datetime | None) -> None:
        account_group_order = self._task_account_group_names(task)
        group_group_order = self._task_group_group_names(task)
        self.runtime_state_service.init_task(
            task_id=task.task_id,
            task_name=task.task_name,
            account_group_order=account_group_order,
            group_group_order=group_group_order,
            daily_window_enabled=bool(getattr(task, "daily_window_enabled", False)),
            daily_start_time=str(getattr(task, "daily_start_time", "09:00")),
            daily_end_time=str(getattr(task, "daily_end_time", "21:00")),
        )
        workers = []
        for index, account_group in enumerate(account_group_order):
            workers.append(asyncio.create_task(self._account_group_worker(task, task_stop_event, account_group, index, group_group_order, window_end)))
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def _account_group_worker(
        self,
        task: SendTaskConfig,
        task_stop_event: asyncio.Event,
        account_group: str,
        account_group_index: int,
        group_group_order: list[str],
        window_end: datetime | None,
    ) -> None:
        progress = 0
        while not self._should_stop(task_stop_event) and not self._window_expired(window_end):
            target_index = (account_group_index + progress) % len(group_group_order)
            target_group_group = group_group_order[target_index]
            self.runtime_state_service.set_account_group_status(task.task_id, account_group, "running", target_group_group)
            account_names = [account.account_name for account in self._accounts_for_group(account_group)]
            groups = self._groups_for_group(target_group_group)
            if not account_names:
                self.runtime_state_service.set_account_group_status(task.task_id, account_group, "error", target_group_group)
                self._log("error", f"账号组没有可用启用账号，停止该任务 | task={task.task_name} | account_group={account_group}")
                return
            if not groups:
                self.runtime_state_service.set_account_group_status(task.task_id, account_group, "error", target_group_group)
                self._log("error", f"群聊组没有可用启用群组，停止该任务 | task={task.task_name} | group_group={target_group_group}")
                return
            await self._execute_pipeline_matrix_task(task, account_group, target_group_group, account_names, groups, task_stop_event, window_end)
            if self._should_stop(task_stop_event) or self._window_expired(window_end):
                break
            progress += 1
            self.runtime_state_service.complete_round(task.task_id, account_group)
            await self._sleep_ms(getattr(task, "interval_ms", 0), task_stop_event, window_end)
        if self._window_expired(window_end):
            self.runtime_state_service.set_account_group_status(task.task_id, account_group, "daily_window_finished")

    async def _execute_pipeline_matrix_task(
        self,
        task: SendTaskConfig,
        account_group: str,
        group_group: str,
        account_names: list[str],
        groups: list[GroupConfig],
        task_stop_event: asyncio.Event,
        window_end: datetime | None,
    ) -> SendResult | None:
        account_delay_min_ms, account_delay_max_ms = self._delay_range(task.account_delay_min_ms, task.account_delay_max_ms)
        group_delay_min_ms, group_delay_max_ms = self._delay_range(task.group_delay_min_ms, task.group_delay_max_ms)
        offsets: list[int] = []
        current = 0
        for index, _account_name in enumerate(account_names):
            if index == 0:
                offsets.append(0)
            else:
                current += self._random_delay_ms(account_delay_min_ms, account_delay_max_ms)
                offsets.append(current)
        self._log("info", f"开始小轮询 | task={task.task_name} | {account_group} -> {group_group} | accounts={len(account_names)} | groups={len(groups)}")
        workers = [
            asyncio.create_task(self._execute_account_pipeline(task, account_group, group_group, account_name, idx, offsets[idx], account_names, groups, group_delay_min_ms, group_delay_max_ms, task_stop_event, window_end))
            for idx, account_name in enumerate(account_names)
        ]
        gathered = await asyncio.gather(*workers, return_exceptions=True)
        all_results: list[SendResult] = []
        for item in gathered:
            if isinstance(item, BaseException):
                self._log("error", f"账号流水线异常 | task={task.task_name} | error={item}")
            else:
                all_results.extend(item)
        success = sum(1 for result in all_results if getattr(result, "status", "") == SEND_STATUS_SUCCESS)
        skipped = sum(1 for result in all_results if getattr(result, "status", "") == SEND_STATUS_SKIPPED)
        failed = len(all_results) - success - skipped
        self._log("info", f"小轮询结束 | task={task.task_name} | {account_group}->{group_group} | success={success} | failed={failed} | skipped={skipped}")
        return all_results[-1] if all_results else None

    async def _execute_account_pipeline(
        self,
        task: SendTaskConfig,
        account_group: str,
        group_group: str,
        account_name: str,
        account_position: int,
        start_delay_ms: int,
        account_names: list[str],
        groups: list[GroupConfig],
        group_delay_min_ms: int,
        group_delay_max_ms: int,
        task_stop_event: asyncio.Event,
        window_end: datetime | None,
    ) -> list[SendResult]:
        results: list[SendResult] = []
        await self._sleep_ms(start_delay_ms, task_stop_event, window_end)
        for group_position, group in enumerate(groups):
            if self._should_stop(task_stop_event) or self._window_expired(window_end):
                break
            async with self._account_send_lock(account_name):
                result = await self._execute_sequence_item(task, account_group, group_group, account_name, group, account_names, groups, account_position, group_position)
            group_delay_ms = self._random_delay_ms(group_delay_min_ms, group_delay_max_ms)
            setattr(result, "actual_account_delay_ms", start_delay_ms if group_position == 0 else 0)
            setattr(result, "actual_group_delay_ms", group_delay_ms)
            self.task_log_service.append_result(result)
            results.append(result)
            await self._sleep_ms(group_delay_ms, task_stop_event, window_end)
        return results

    async def _execute_sequence_item(
        self,
        task: SendTaskConfig,
        account_group: str,
        group_group: str,
        account_name: str,
        group: GroupConfig,
        account_names: list[str],
        groups: list[GroupConfig],
        account_index: int,
        group_index: int,
    ) -> SendResult:
        account = self._find_account(account_name)
        if account is None or not bool(getattr(account, "enabled", True)):
            return self._build_failed_result(task, group, account_name, account_index, group_index, "账号不存在或未启用")
        try:
            client = await self.client_manager.ensure_account_started(account.account_name)
            task_snapshot = self._build_task_snapshot(task, account.account_name, group.group_id, account_names, groups, account_index, group_index)
            setattr(task_snapshot, "account_group_name", account_group)
            setattr(task_snapshot, "group_group_name", group_group)
            return await self.group_send_service.execute_task(account_name=account.account_name, client=client, group=group, task=task_snapshot, settings=self.settings)
        except Exception as exc:
            return self._build_failed_result(task, group, account_name, account_index, group_index, str(exc))

    def _build_task_snapshot(self, task: SendTaskConfig, account_name: str, group_id: str, account_names: list[str], groups: list[GroupConfig], account_index: int, group_index: int) -> SendTaskConfig:
        return replace(
            task,
            account_name=account_name,
            account_names=list(account_names),
            account_rotate_mode=ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
            current_account_index=account_index,
            group_id=group_id,
            group_ids=[str(group.group_id or "") for group in groups],
            group_rotate_mode=GROUP_ROTATE_MODE_ROUND_ROBIN,
            current_group_index=group_index,
        )

    def _build_failed_result(self, task: SendTaskConfig, group: GroupConfig, account_name: str, account_index: int, group_index: int, error: str) -> SendResult:
        now = datetime.now().isoformat(timespec="milliseconds")
        return SendResult(
            task_id=task.task_id,
            task_name=task.task_name,
            account_name=account_name,
            group_id=group.group_id,
            chat_id=group.chat_id,
            status=SEND_STATUS_FAILED,
            error=error,
            started_at=now,
            finished_at=now,
            account_index=account_index,
            selected_account_name=account_name,
            group_index=group_index,
            selected_group_id=str(group.group_id or ""),
            selected_group_name=str(group.group_name or ""),
            account_delay_min_ms=task.account_delay_min_ms,
            account_delay_max_ms=task.account_delay_max_ms,
            group_delay_min_ms=task.group_delay_min_ms,
            group_delay_max_ms=task.group_delay_max_ms,
        )


    def _account_send_lock(self, account_name: str) -> asyncio.Lock:
        safe_name = str(account_name or "").strip()
        if safe_name not in self._account_send_locks:
            self._account_send_locks[safe_name] = asyncio.Lock()
        return self._account_send_locks[safe_name]

    def _validate_enabled_account_identities(self) -> None:
        enabled_accounts = [account for account in self.accounts if bool(getattr(account, "enabled", True))]
        seen_names: dict[str, str] = {}
        seen_sessions: dict[str, str] = {}
        seen_phones: dict[str, str] = {}
        conflicts: list[str] = []

        for account in enabled_accounts:
            account_name = str(getattr(account, "account_name", "") or "").strip()
            session_name = str(getattr(account, "session_name", "") or "").strip()
            phone = str(getattr(account, "phone", "") or "").strip()

            if not account_name:
                conflicts.append("存在启用账号但账号名称为空")
                continue
            if account_name in seen_names:
                conflicts.append(f"账号名称重复：【{account_name}】")
            else:
                seen_names[account_name] = account_name

            if not session_name:
                conflicts.append(f"账号【{account_name}】Session 为空")
            elif session_name in seen_sessions:
                conflicts.append(f"Session 重复：【{session_name}】被账号【{seen_sessions[session_name]}】和【{account_name}】同时使用")
            else:
                seen_sessions[session_name] = account_name

            if not phone:
                conflicts.append(f"账号【{account_name}】手机号为空")
            elif phone in seen_phones:
                conflicts.append(f"手机号重复：【{phone}】被账号【{seen_phones[phone]}】和【{account_name}】同时使用")
            else:
                seen_phones[phone] = account_name

        if conflicts:
            raise RuntimeError("账号配置存在冲突，已阻止启动：" + "；".join(conflicts))

    def _validate_task_runnable(self, task: SendTaskConfig) -> None:
        account_groups = self._task_account_group_names(task)
        group_groups = self._task_group_group_names(task)
        if not account_groups:
            raise RuntimeError(f"任务【{task.task_name}】没有选择账号组")
        if not group_groups:
            raise RuntimeError(f"任务【{task.task_name}】没有选择群聊组")
        if len(account_groups) != len(group_groups):
            raise RuntimeError(f"任务【{task.task_name}】账号组数量和群聊组数量必须一致")
        missing_accounts = [name for name in account_groups if not self._accounts_for_group(name)]
        if missing_accounts:
            raise RuntimeError("以下账号组没有启用账号：" + "、".join(missing_accounts))
        missing_groups = [name for name in group_groups if not self._groups_for_group(name)]
        if missing_groups:
            raise RuntimeError("以下群聊组没有启用群组：" + "、".join(missing_groups))
        if bool(getattr(task, "daily_window_enabled", False)) and str(task.daily_start_time) == str(task.daily_end_time):
            raise RuntimeError(f"任务【{task.task_name}】每日开始时间不能等于每日结束时间")

    def _validate_enabled_task_account_group_conflicts(self, tasks: list[SendTaskConfig]) -> None:
        owner: dict[str, str] = {}
        conflicts: list[str] = []
        for task in tasks:
            for group_name in self._task_account_group_names(task):
                if group_name in owner:
                    conflicts.append(f"账号组【{group_name}】被任务【{owner[group_name]}】和【{task.task_name}】同时使用")
                else:
                    owner[group_name] = task.task_name
        if conflicts:
            raise RuntimeError("账号组不能被多个启用任务同时使用：" + "；".join(conflicts))

    def _validate_single_task_conflict(self, task: SendTaskConfig) -> None:
        running_groups: dict[str, str] = {}
        for running_id, worker in self._task_workers.items():
            if worker.done():
                continue
            other = self._find_task(running_id)
            if other is None:
                continue
            for group_name in self._task_account_group_names(other):
                running_groups[group_name] = other.task_name
        for group_name in self._task_account_group_names(task):
            if group_name in running_groups:
                raise RuntimeError(f"账号组【{group_name}】已被任务【{running_groups[group_name]}】占用")

    def _task_account_group_names(self, task: SendTaskConfig) -> list[str]:
        return [str(item or "").strip() for item in getattr(task, "account_group_names", []) or [] if str(item or "").strip()]

    def _task_group_group_names(self, task: SendTaskConfig) -> list[str]:
        return [str(item or "").strip() for item in getattr(task, "group_group_names", []) or [] if str(item or "").strip()]

    def _accounts_for_group(self, account_group: str) -> list[AccountConfig]:
        target = str(account_group or "").strip()
        return [account for account in self.accounts if bool(getattr(account, "enabled", True)) and str(getattr(account, "account_group", "") or "").strip() == target]

    def _groups_for_group(self, group_group: str) -> list[GroupConfig]:
        target = str(group_group or "").strip()
        if not target:
            return []

        result: list[GroupConfig] = []
        for group in self.groups:
            if not bool(getattr(group, "enabled", True)):
                continue
            memberships = self._group_group_memberships(group)
            if target in memberships:
                result.append(group)
        return result

    @staticmethod
    def _group_group_memberships(group: GroupConfig) -> list[str]:
        result: list[str] = []
        for item in getattr(group, "group_group_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(group, "group_group", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    def _find_task(self, task_id: str) -> SendTaskConfig | None:
        target = str(task_id or "").strip()
        return next((task for task in self.tasks if str(getattr(task, "task_id", "") or "").strip() == target), None)

    def _find_account(self, account_name: str) -> AccountConfig | None:
        target = str(account_name or "").strip()
        return next((account for account in self.accounts if str(account.account_name or "").strip() == target), None)

    @staticmethod
    def _delay_range(min_ms: Any, max_ms: Any) -> tuple[int, int]:
        left = max(0, int(min_ms or 0))
        right = max(0, int(max_ms or left))
        return left, max(left, right)

    @staticmethod
    def _random_delay_ms(delay_min_ms: int, delay_max_ms: int) -> int:
        safe_min = max(0, int(delay_min_ms or 0))
        safe_max = max(safe_min, int(delay_max_ms or safe_min))
        return 0 if safe_max <= 0 else random.randint(safe_min, safe_max)

    def _should_stop(self, task_stop_event: asyncio.Event) -> bool:
        return self._stop_event.is_set() or task_stop_event.is_set()

    async def _sleep_seconds(self, seconds: float, task_stop_event: asyncio.Event, window_end: datetime | None = None) -> None:
        await self._sleep_ms(int(max(0.0, seconds) * 1000), task_stop_event, window_end)

    async def _sleep_ms(self, delay_ms: int, task_stop_event: asyncio.Event, window_end: datetime | None = None) -> None:
        safe_ms = max(0, int(delay_ms or 0))
        if safe_ms <= 0:
            await asyncio.sleep(self.MIN_IDLE_SLEEP_SECONDS)
            return
        deadline = datetime.now() + timedelta(milliseconds=safe_ms)
        if window_end is not None and window_end < deadline:
            deadline = window_end
        while not self._should_stop(task_stop_event):
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(task_stop_event.wait(), timeout=min(self.INTERRUPTIBLE_SLEEP_SLICE_SECONDS, remaining))
                return
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _parse_time(value: str, default: time) -> time:
        try:
            hour, minute = [int(part) for part in str(value or "").split(":", 1)]
            return time(hour=hour, minute=minute)
        except Exception:
            return default

    def _is_in_daily_window(self, task: SendTaskConfig) -> bool:
        now = datetime.now().time()
        start = self._parse_time(task.daily_start_time, time(9, 0))
        end = self._parse_time(task.daily_end_time, time(21, 0))
        if start < end:
            return start <= now < end
        if start > end:
            return now >= start or now < end
        return False

    def _current_daily_window_end(self, task: SendTaskConfig) -> datetime:
        now = datetime.now()
        start = self._parse_time(task.daily_start_time, time(9, 0))
        end = self._parse_time(task.daily_end_time, time(21, 0))
        end_dt = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
        if start > end and now.time() >= start:
            end_dt += timedelta(days=1)
        if start < end and end_dt <= now:
            end_dt += timedelta(days=1)
        return end_dt

    def _seconds_until_next_daily_start(self, task: SendTaskConfig) -> float:
        now = datetime.now()
        start = self._parse_time(task.daily_start_time, time(9, 0))
        start_dt = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        if start_dt <= now:
            start_dt += timedelta(days=1)
        return max(0.0, (start_dt - now).total_seconds())

    @staticmethod
    def _window_expired(window_end: datetime | None) -> bool:
        return window_end is not None and datetime.now() >= window_end

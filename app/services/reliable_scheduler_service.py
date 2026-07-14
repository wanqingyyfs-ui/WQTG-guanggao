from __future__ import annotations

from datetime import datetime, timedelta

from app.services.scheduler_service import SchedulerService


class ReliableSchedulerService(SchedulerService):
    """Preserves current per-account cadence and enforces Telegram FloodWait cooldowns."""

    FLOOD_WAIT_SAFETY_BUFFER_SECONDS = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        loader = getattr(self.task_log_service, "load_active_flood_waits", None)
        self._account_flood_wait_until: dict[str, datetime] = (
            dict(loader()) if callable(loader) else {}
        )

    async def _execute_account_pipeline(
        self,
        task,
        account_group: str,
        group_group: str,
        account_name: str,
        account_position: int,
        start_delay_ms: int,
        account_names: list[str],
        groups: list,
        group_delay_min_ms: int,
        group_delay_max_ms: int,
        task_stop_event,
        window_end: datetime | None,
    ) -> list:
        results = []
        await self._sleep_ms(start_delay_ms, task_stop_event, window_end)
        for group_position, group in enumerate(groups):
            if self._should_stop(task_stop_event) or self._window_expired(window_end):
                break

            await self._wait_for_account_flood_wait(
                account_name,
                task_stop_event,
                window_end,
            )
            if self._should_stop(task_stop_event) or self._window_expired(window_end):
                break

            async with self._account_send_lock(account_name):
                result = await self._execute_sequence_item(
                    task,
                    account_group,
                    group_group,
                    account_name,
                    group,
                    account_names,
                    groups,
                    account_position,
                    group_position,
                )

            group_delay_ms = self._random_delay_ms(group_delay_min_ms, group_delay_max_ms)
            setattr(result, "actual_account_delay_ms", start_delay_ms if group_position == 0 else 0)
            setattr(result, "actual_group_delay_ms", group_delay_ms)
            self.task_log_service.append_result(result)
            results.append(result)

            if str(getattr(result, "status", "") or "") == "flood_wait":
                self._register_flood_wait(account_name, result)
                cooldown_until = self._account_flood_wait_until.get(account_name)
                remaining_seconds = max(
                    0.0,
                    (cooldown_until - datetime.now()).total_seconds()
                    if cooldown_until is not None else 0.0,
                )
                configured_delay_seconds = max(0.0, group_delay_ms / 1000.0)
                wait_seconds = max(remaining_seconds, configured_delay_seconds)
                self._log(
                    "info",
                    f"[{account_name}] FloodWait 后续等待采用较长值 | "
                    f"flood_wait_remaining={int(remaining_seconds + 0.999)}s | "
                    f"configured_group_delay={configured_delay_seconds:.3f}s | "
                    f"actual_wait={wait_seconds:.3f}s",
                )
                await self._sleep_seconds(wait_seconds, task_stop_event, window_end)
                if cooldown_until is not None and datetime.now() >= cooldown_until:
                    self._account_flood_wait_until.pop(account_name, None)
                continue

            await self._sleep_ms(group_delay_ms, task_stop_event, window_end)
        return results

    def _register_flood_wait(self, account_name: str, result) -> None:
        cooldown_text = str(getattr(result, "cooldown_until", "") or "").strip()
        cooldown_until = None
        if cooldown_text:
            try:
                cooldown_until = datetime.fromisoformat(cooldown_text)
            except ValueError:
                cooldown_until = None
        if cooldown_until is None:
            seconds = max(0, int(getattr(result, "flood_wait_seconds", 0) or 0))
            cooldown_until = datetime.now() + timedelta(
                seconds=seconds + self.FLOOD_WAIT_SAFETY_BUFFER_SECONDS
            )
            setattr(result, "cooldown_until", cooldown_until.isoformat(timespec="seconds"))
        self._account_flood_wait_until[str(account_name or "").strip()] = cooldown_until
        self._log(
            "warning",
            f"[{account_name}] 已进入 FloodWait 冷却 | until={cooldown_until.isoformat(timespec='seconds')} | "
            f"seconds={getattr(result, 'flood_wait_seconds', 0)}",
        )

    async def _wait_for_account_flood_wait(
        self,
        account_name: str,
        task_stop_event,
        window_end: datetime | None,
    ) -> None:
        safe_name = str(account_name or "").strip()
        cooldown_until = self._account_flood_wait_until.get(safe_name)
        if cooldown_until is None:
            return
        remaining = (cooldown_until - datetime.now()).total_seconds()
        if remaining <= 0:
            self._account_flood_wait_until.pop(safe_name, None)
            return
        self._log(
            "info",
            f"[{safe_name}] 正在遵守 FloodWait 冷却，暂停该账号后续发送 | "
            f"remaining={int(remaining + 0.999)}s | until={cooldown_until.isoformat(timespec='seconds')}",
        )
        await self._sleep_seconds(remaining, task_stop_event, window_end)
        if datetime.now() >= cooldown_until:
            self._account_flood_wait_until.pop(safe_name, None)

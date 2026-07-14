from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from app.services.tgapipldc_runner_service import TgapipldcCommandResult
from app.services.tgapipldc_runner_service_cancel_safe import (
    CancelSafeTgapipldcRunnerService,
)


ProfileMapBuilder = Callable[[], Path]


class StrictTgapipldcRunnerService(CancelSafeTgapipldcRunnerService):
    """Use dynamic proxy only for API export and static mappings everywhere else."""

    SCRIPT_STRICT_AUTOMATION_ENTRY = "strict_automation_entry.py"

    def __init__(
        self,
        *args,
        profile_map_builder: ProfileMapBuilder | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.profile_map_builder = profile_map_builder
        self._extra_env: dict[str, str] = {}
        self._extra_env_lock = threading.RLock()

    def _build_subprocess_env(self, *, job_id: str, result_path: Path) -> dict[str, str]:
        env = super()._build_subprocess_env(job_id=job_id, result_path=result_path)
        with self._extra_env_lock:
            env.update(self._extra_env)
        return env

    def _run_with_env(
        self,
        *,
        script_name: str,
        command_name: str,
        log_callback,
        extra_args: list[str],
        job_type: str,
        extra_env: dict[str, str] | None = None,
    ) -> TgapipldcCommandResult:
        with self._extra_env_lock:
            if self._extra_env:
                raise RuntimeError("严格代理运行环境仍被上一任务占用")
            self._extra_env = dict(extra_env or {})
            try:
                return super().run_script(
                    script_name,
                    command_name,
                    log_callback,
                    extra_args=extra_args,
                    job_type=job_type,
                )
            finally:
                self._extra_env = {}

    def run_login_telegram_web(self, log_callback=None) -> TgapipldcCommandResult:
        return self._run_with_env(
            script_name=self.SCRIPT_STRICT_AUTOMATION_ENTRY,
            command_name="批量获取 api_id/api_hash",
            log_callback=log_callback,
            extra_args=["--mode", "login"],
            job_type="api-export",
            extra_env={"WQTG_PROXY_POLICY": "dynamic_api_only"},
        )

    def run_profile_maintenance(self, action: str, log_callback=None) -> TgapipldcCommandResult:
        if self.profile_map_builder is None:
            raise RuntimeError("缺少静态代理运行表生成器，已阻止资料维护直连")
        static_map = Path(self.profile_map_builder()).resolve()
        if not static_map.exists():
            raise RuntimeError(f"静态代理运行表不存在：{static_map}")
        safe_action = str(action or "status").strip().lower() or "status"
        return self._run_with_env(
            script_name=self.SCRIPT_STRICT_AUTOMATION_ENTRY,
            command_name=f"账号资料维护-{safe_action}",
            log_callback=log_callback,
            extra_args=["--mode", "profile", "--action", safe_action],
            job_type="profile-maintenance",
            extra_env={
                "WQTG_PROXY_POLICY": "static_group_only",
                "WQTG_ACCOUNT_PROXY_MAP_OVERRIDE": str(static_map),
            },
        )

    def run_locator_calibration(
        self,
        target_id: str,
        profile_dir: str,
        url: str,
        raw_proxy: str = "",
        log_callback=None,
    ) -> TgapipldcCommandResult:
        proxy = str(raw_proxy or "").strip()
        if not proxy:
            raise RuntimeError(
                f"Profile【{profile_dir}】缺少分组静态代理，定位校准已阻止直连"
            )
        return self._run_with_env(
            script_name=self.SCRIPT_STRICT_AUTOMATION_ENTRY,
            command_name=f"定位校准-{target_id}",
            log_callback=log_callback,
            extra_args=[
                "--mode", "calibrate",
                "--target", str(target_id),
                "--profile-dir", str(profile_dir),
                "--url", str(url or "https://web.telegram.org/k/"),
                "--proxy", proxy,
            ],
            job_type="locator-calibration",
            extra_env={"WQTG_PROXY_POLICY": "static_group_only"},
        )

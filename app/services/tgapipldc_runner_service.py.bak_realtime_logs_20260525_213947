from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class TgapipldcCommandResult:
    command_name: str
    script_path: Path
    return_code: int
    success: bool


class TgapipldcRunnerService:
    """
    tgapipldc 原始脚本运行服务。

    这个文件的作用是把已经迁移到：

        app/vendor/tgapipldc/src/

    里面的旧脚本，以安全、统一、可记录日志的方式运行起来。

    当前支持：
    - test_proxies.py
    - build_proxy_pool.py
    - assign_proxies.py
    - login_telegram_web.py
    - open_account_browser.py
    - update_telegram_profile.py

    说明：
    - 这是 GUI 面板接入前的脚本桥接层；
    - 代理检测和账号绑定已经有服务化版本，但保留脚本运行能力方便校验；
    - login_telegram_web.py 体量很大，当前阶段先使用 runner 调用迁移后的原脚本；
    - update_telegram_profile.py 独立负责账号资料维护，不污染 API 获取流程；
    - 本类不依赖 PySide6，可以在后台线程里被 RuntimeService 或页面 Worker 调用。
    """

    SCRIPT_TEST_PROXIES = "test_proxies.py"
    SCRIPT_BUILD_PROXY_POOL = "build_proxy_pool.py"
    SCRIPT_ASSIGN_PROXIES = "assign_proxies.py"
    SCRIPT_LOGIN_TELEGRAM_WEB = "login_telegram_web.py"
    SCRIPT_OPEN_ACCOUNT_BROWSER = "open_account_browser.py"
    SCRIPT_UPDATE_TELEGRAM_PROFILE = "update_telegram_profile.py"

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()

        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.poll() is None)

    def stop_current_process(self) -> None:
        with self._lock:
            process = self._process

        if process is None:
            return

        if process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass

    def run_test_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_TEST_PROXIES,
            command_name="检测代理",
            log_callback=log_callback,
        )

    def run_build_proxy_pool(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_BUILD_PROXY_POOL,
            command_name="构建可用代理池",
            log_callback=log_callback,
        )

    def run_assign_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_ASSIGN_PROXIES,
            command_name="绑定账号和代理",
            log_callback=log_callback,
        )

    def run_login_telegram_web(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_LOGIN_TELEGRAM_WEB,
            command_name="批量获取 api_id/api_hash",
            log_callback=log_callback,
        )

    def run_open_account_browser(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_OPEN_ACCOUNT_BROWSER,
            command_name="打开账号浏览器",
            log_callback=log_callback,
        )

    def run_profile_maintenance(
        self,
        action: str,
        log_callback: LogCallback | None = None,
    ) -> TgapipldcCommandResult:
        safe_action = str(action or "status").strip().lower() or "status"
        return self.run_script(
            script_name=self.SCRIPT_UPDATE_TELEGRAM_PROFILE,
            command_name=f"账号资料维护-{safe_action}",
            log_callback=log_callback,
            extra_args=["--action", safe_action],
        )

    def run_script(
        self,
        script_name: str,
        command_name: str,
        log_callback: LogCallback | None = None,
        extra_args: list[str] | None = None,
    ) -> TgapipldcCommandResult:
        script_path = self._require_script(script_name)

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("已有 tgapipldc 脚本正在运行，请先停止或等待完成")

        command = [
            sys.executable,
            str(script_path),
            *(extra_args or []),
        ]

        self._emit(log_callback, f"[{command_name}] 开始运行：{script_path}")
        self._emit(log_callback, f"[{command_name}] Python：{sys.executable}")

        env = self._build_subprocess_env()

        process = subprocess.Popen(
            command,
            cwd=str(self.workspace.workspace_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        with self._lock:
            self._process = process

        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self._emit(log_callback, line.rstrip("\n"))

            return_code = process.wait()
            success = return_code == 0

            if success:
                self._emit(log_callback, f"[{command_name}] 运行完成")
            else:
                self._emit(log_callback, f"[{command_name}] 运行失败，退出码：{return_code}")

            return TgapipldcCommandResult(
                command_name=command_name,
                script_path=script_path,
                return_code=return_code,
                success=success,
            )
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    def _require_script(self, script_name: str) -> Path:
        safe_script_name = str(script_name or "").strip()

        if not safe_script_name:
            raise ValueError("脚本名称不能为空")

        if "/" in safe_script_name or "\\" in safe_script_name:
            raise ValueError(f"脚本名称不能包含路径分隔符：{safe_script_name}")

        script_path = self.workspace.src_dir / safe_script_name

        if not script_path.exists():
            raise FileNotFoundError(f"找不到 tgapipldc 脚本：{script_path}")

        if not script_path.is_file():
            raise FileNotFoundError(f"tgapipldc 脚本不是文件：{script_path}")

        return script_path

    def _build_subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)

        src_dir = str(self.workspace.src_dir)
        old_pythonpath = env.get("PYTHONPATH", "")

        if old_pythonpath:
            env["PYTHONPATH"] = src_dir + os.pathsep + old_pythonpath
        else:
            env["PYTHONPATH"] = src_dir

        env["PYTHONIOENCODING"] = "utf-8"

        return env

    @staticmethod
    def _emit(log_callback: LogCallback | None, message: str) -> None:
        safe_message = str(message or "")

        if callable(log_callback):
            log_callback(safe_message)
        else:
            print(safe_message)

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
    tgapipldc 脚本运行服务。

    当前只保留动态轮换代理主流程：
    - 保存 accounts.csv；
    - 保存 data/proxies.csv 中唯一一条 raw_proxy；
    - 生成 account_proxy_map.csv 时所有账号共用这一条动态代理；
    - 登录、打开浏览器、资料维护继续调用原脚本文件名，避免新增 *_dynamic.py 双轨文件。

    旧的“检测代理 -> 构建可用代理池 -> 一账号一代理绑定”流程已从主入口移除。
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
        self._emit(log_callback, "动态轮换代理模式不再使用旧的代理池检测入口，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult(
            command_name="旧代理池检测已移除",
            script_path=self.workspace.src_dir / self.SCRIPT_TEST_PROXIES,
            return_code=0,
            success=True,
        )

    def run_build_proxy_pool(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        self._emit(log_callback, "动态轮换代理模式不再构建可用代理池，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult(
            command_name="旧构建代理池已移除",
            script_path=self.workspace.src_dir / self.SCRIPT_BUILD_PROXY_POOL,
            return_code=0,
            success=True,
        )

    def run_assign_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            script_name=self.SCRIPT_ASSIGN_PROXIES,
            command_name="生成动态代理账号运行表",
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
            "-u",
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
        env["PYTHONUNBUFFERED"] = "1"

        return env

    @staticmethod
    def _emit(log_callback: LogCallback | None, message: str) -> None:
        safe_message = str(message or "")

        if callable(log_callback):
            log_callback(safe_message)
        else:
            print(safe_message)

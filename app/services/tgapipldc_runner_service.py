from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class TgapipldcCommandResult:
    command_name: str
    script_path: Path
    return_code: int
    success: bool
    job_id: str = ""
    job_type: str = ""
    result_path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)


class TgapipldcRunnerService:
    """Run one tgapipldc automation job at a time with structured results."""

    SCRIPT_TEST_PROXIES = "test_proxies.py"
    SCRIPT_BUILD_PROXY_POOL = "build_proxy_pool.py"
    SCRIPT_ASSIGN_PROXIES = "assign_proxies.py"
    SCRIPT_AUTOMATION_ENTRY = "automation_entry.py"
    SCRIPT_OPEN_ACCOUNT_BROWSER = "open_account_browser.py"

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        self._process: subprocess.Popen[str] | None = None
        self._current_job: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def is_running(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.poll() is None)

    def current_job(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._current_job or {})

    def stop_current_process(self) -> bool:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return False
        self._terminate_process_tree(process)
        return True

    def run_test_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        self._emit(log_callback, "动态轮换代理模式不再使用旧的代理池检测入口，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult("旧代理池检测已移除", self.workspace.src_dir / self.SCRIPT_TEST_PROXIES, 0, True, job_type="legacy-proxy-test")

    def run_build_proxy_pool(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        self._emit(log_callback, "动态轮换代理模式不再构建可用代理池，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult("旧构建代理池已移除", self.workspace.src_dir / self.SCRIPT_BUILD_PROXY_POOL, 0, True, job_type="legacy-proxy-pool")

    def run_assign_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(self.SCRIPT_ASSIGN_PROXIES, "生成动态代理账号运行表", log_callback, job_type="assign-proxies")

    def run_login_telegram_web(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            self.SCRIPT_AUTOMATION_ENTRY,
            "批量获取 api_id/api_hash",
            log_callback,
            extra_args=["--mode", "login"],
            job_type="api-export",
        )

    def run_open_account_browser(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(self.SCRIPT_OPEN_ACCOUNT_BROWSER, "打开账号浏览器", log_callback, job_type="open-browser")

    def run_profile_maintenance(self, action: str, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        safe_action = str(action or "status").strip().lower() or "status"
        return self.run_script(
            self.SCRIPT_AUTOMATION_ENTRY,
            f"账号资料维护-{safe_action}",
            log_callback,
            extra_args=["--mode", "profile", "--action", safe_action],
            job_type="profile-maintenance",
        )

    def run_locator_calibration(
        self,
        target_id: str,
        profile_dir: str,
        url: str,
        raw_proxy: str = "",
        log_callback: LogCallback | None = None,
    ) -> TgapipldcCommandResult:
        args = [
            "--mode", "calibrate",
            "--target", str(target_id),
            "--profile-dir", str(profile_dir),
            "--url", str(url or "https://web.telegram.org/k/"),
        ]
        if str(raw_proxy or "").strip():
            args.extend(["--proxy", str(raw_proxy)])
        return self.run_script(
            self.SCRIPT_AUTOMATION_ENTRY,
            f"定位校准-{target_id}",
            log_callback,
            extra_args=args,
            job_type="locator-calibration",
        )

    def run_script(
        self,
        script_name: str,
        command_name: str,
        log_callback: LogCallback | None = None,
        extra_args: list[str] | None = None,
        job_type: str = "script",
    ) -> TgapipldcCommandResult:
        script_path = self._require_script(script_name)
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                active = dict(self._current_job or {})
                raise RuntimeError(f"已有 tgapipldc 脚本正在运行，请先停止或等待完成：{active.get('command_name', '')}")

        job_id = uuid.uuid4().hex[:12]
        result_dir = self.workspace.logs_dir / "job_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        result_path = result_dir / f"{job_id}.json"
        command = [sys.executable, "-u", str(script_path), *(extra_args or [])]
        env = self._build_subprocess_env(job_id=job_id, result_path=result_path)
        self._emit(log_callback, f"[{job_type}][{job_id}] 开始运行：{script_path}")
        self._emit(log_callback, f"[{job_type}][{job_id}] Python：{sys.executable}")

        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.workspace.workspace_dir),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        job_lock = self._acquire_global_job_lock(job_id)
        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except Exception:
            job_lock.release()
            raise

        with self._lock:
            self._process = process
            self._current_job = {
                "job_id": job_id,
                "job_type": job_type,
                "command_name": command_name,
                "script_path": str(script_path),
                "result_path": str(result_path),
            }

        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self._emit(log_callback, line.rstrip("\n"))
            return_code = process.wait()
            details = self._read_result(result_path)
            declared_status = str(details.get("status") or "").strip().lower()
            success = return_code == 0 and declared_status in {"", "success"}
            if success:
                self._emit(log_callback, f"[{job_type}][{job_id}] 运行完成")
            else:
                self._emit(log_callback, f"[{job_type}][{job_id}] 运行未完全成功，退出码：{return_code}，状态：{declared_status or 'unknown'}")
            return TgapipldcCommandResult(
                command_name=command_name,
                script_path=script_path,
                return_code=return_code,
                success=success,
                job_id=job_id,
                job_type=job_type,
                result_path=result_path,
                details=details,
            )
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
                    self._current_job = None
            job_lock.release()

    def _acquire_global_job_lock(self, job_id: str):
        src_dir = str(self.workspace.src_dir)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from profile_lock import ProfileLock
        try:
            return ProfileLock(
                self.workspace.workspace_dir,
                self.workspace.data_dir / "job_locks",
                timeout_seconds=0,
                job_id=job_id,
            ).acquire()
        except Exception as exc:
            raise RuntimeError(f"另一个 WQTG 实例正在运行 tgapipldc 自动化任务：{exc}") from exc

    def _require_script(self, script_name: str) -> Path:
        safe_script_name = str(script_name or "").strip()
        if not safe_script_name:
            raise ValueError("脚本名称不能为空")
        if "/" in safe_script_name or "\\" in safe_script_name:
            raise ValueError(f"脚本名称不能包含路径分隔符：{safe_script_name}")
        script_path = self.workspace.src_dir / safe_script_name
        if not script_path.exists() or not script_path.is_file():
            raise FileNotFoundError(f"找不到 tgapipldc 脚本：{script_path}")
        return script_path

    def _build_subprocess_env(self, *, job_id: str, result_path: Path) -> dict[str, str]:
        env = dict(os.environ)
        src_dir = str(self.workspace.src_dir)
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_dir + (os.pathsep + old_pythonpath if old_pythonpath else "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["WQTG_JOB_ID"] = job_id
        env["WQTG_JOB_RESULT"] = str(result_path)
        env["WQTG_LOCATOR_CONFIG"] = str(self.workspace.data_dir / "automation_locators.json")
        env["WQTG_LOCATOR_DIAGNOSTICS"] = str(self.workspace.logs_dir / "automation_failures")
        return env

    @staticmethod
    def _read_result(result_path: Path) -> dict[str, Any]:
        if not result_path.exists():
            return {}
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                )
                return
            except Exception:
                pass
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=10)
                return
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    return
                except Exception:
                    pass
            except Exception:
                pass
        try:
            process.terminate(); process.wait(timeout=5)
        except Exception:
            try: process.kill()
            except Exception: pass

    @staticmethod
    def _emit(log_callback: LogCallback | None, message: str) -> None:
        safe_message = str(message or "")
        if callable(log_callback):
            log_callback(safe_message)
        else:
            print(safe_message)

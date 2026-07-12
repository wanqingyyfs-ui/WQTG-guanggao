from __future__ import annotations

import multiprocessing
import os
import queue as queue_module
import runpy
import sys
import threading
import traceback
from dataclasses import dataclass
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


class _QueueTextWriter:
    """Line-buffered stdout/stderr writer used by the spawned worker process."""

    def __init__(self, output_queue: Any):
        self.output_queue = output_queue
        self.buffer = ""

    def write(self, value: object) -> int:
        text = str(value or "")
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.output_queue.put(("log", line.rstrip("\r")))
        return len(text)

    def flush(self) -> None:
        if self.buffer:
            self.output_queue.put(("log", self.buffer.rstrip("\r")))
            self.buffer = ""

    def isatty(self) -> bool:
        return False


def _run_vendor_script_child(
    script_path_text: str,
    extra_args: list[str],
    workspace_dir_text: str,
    src_dir_text: str,
    child_env: dict[str, str],
    output_queue: Any,
) -> None:
    """Execute one bundled vendor script in a real spawned Python process.

    This target is top-level and therefore compatible with Windows spawn and
    PyInstaller multiprocessing.freeze_support(). It intentionally avoids
    launching ``sys.executable script.py`` because sys.executable is the frozen
    application bootloader inside a PyInstaller build.
    """

    writer = _QueueTextWriter(output_queue)
    sys.stdout = writer
    sys.stderr = writer

    try:
        os.environ.update(child_env)
        os.chdir(workspace_dir_text)
        if src_dir_text not in sys.path:
            sys.path.insert(0, src_dir_text)

        script_path = Path(script_path_text)
        sys.argv = [str(script_path), *list(extra_args or [])]
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        writer.flush()
        code = exc.code
        if code is None:
            raise SystemExit(0)
        if isinstance(code, int):
            raise
        output_queue.put(("log", str(code)))
        raise SystemExit(1)
    except BaseException:
        traceback.print_exc()
        writer.flush()
        raise SystemExit(1)
    finally:
        writer.flush()
        output_queue.put(("done", ""))


class TgapipldcRunnerService:
    """Run the tgapipldc automation scripts in spawned worker processes."""

    SCRIPT_TEST_PROXIES = "test_proxies.py"
    SCRIPT_BUILD_PROXY_POOL = "build_proxy_pool.py"
    SCRIPT_ASSIGN_PROXIES = "assign_proxies.py"
    SCRIPT_LOGIN_TELEGRAM_WEB = "wqtg_api_entry.py"
    SCRIPT_OPEN_ACCOUNT_BROWSER = "open_account_browser.py"
    SCRIPT_UPDATE_TELEGRAM_PROFILE = "wqtg_profile_entry.py"

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        self._process: multiprocessing.Process | None = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.is_alive())

    def stop_current_process(self) -> None:
        with self._lock:
            process = self._process

        if process is None or not process.is_alive():
            return

        process.terminate()
        process.join(timeout=10)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=5)

    def run_test_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        self._emit(log_callback, "动态轮换代理模式不再使用旧的代理池检测入口，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult(
            "旧代理池检测已移除",
            self.workspace.src_dir / self.SCRIPT_TEST_PROXIES,
            0,
            True,
        )

    def run_build_proxy_pool(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        self._emit(log_callback, "动态轮换代理模式不再构建可用代理池，请直接保存动态代理并生成运行表。")
        return TgapipldcCommandResult(
            "旧构建代理池已移除",
            self.workspace.src_dir / self.SCRIPT_BUILD_PROXY_POOL,
            0,
            True,
        )

    def run_assign_proxies(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            self.SCRIPT_ASSIGN_PROXIES,
            "生成动态代理账号运行表",
            log_callback,
        )

    def run_login_telegram_web(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            self.SCRIPT_LOGIN_TELEGRAM_WEB,
            "批量获取 api_id/api_hash",
            log_callback,
        )

    def run_open_account_browser(self, log_callback: LogCallback | None = None) -> TgapipldcCommandResult:
        return self.run_script(
            self.SCRIPT_OPEN_ACCOUNT_BROWSER,
            "打开账号浏览器",
            log_callback,
        )

    def run_profile_maintenance(
        self,
        action: str,
        log_callback: LogCallback | None = None,
    ) -> TgapipldcCommandResult:
        safe_action = str(action or "status").strip().lower() or "status"
        return self.run_script(
            self.SCRIPT_UPDATE_TELEGRAM_PROFILE,
            f"账号资料维护-{safe_action}",
            log_callback,
            extra_args=["--action", safe_action],
        )

    def run_script(
        self,
        script_name: str,
        command_name: str,
        log_callback: LogCallback | None = None,
        extra_args: list[str] | None = None,
    ) -> TgapipldcCommandResult:
        self.workspace.ensure_structure()
        script_path = self._require_script(script_name)

        with self._lock:
            if self._process is not None and self._process.is_alive():
                raise RuntimeError("已有 tgapipldc 脚本正在运行，请先停止或等待完成")

        context = multiprocessing.get_context("spawn")
        output_queue = context.Queue()
        child_env = self._build_child_env()
        process = context.Process(
            target=_run_vendor_script_child,
            args=(
                str(script_path),
                list(extra_args or []),
                str(self.workspace.workspace_dir),
                str(self.workspace.src_dir),
                child_env,
                output_queue,
            ),
            name=f"wqtg-{script_path.stem}",
            daemon=False,
        )

        self._emit(log_callback, f"[{command_name}] 开始运行：{script_path}")
        mode = "PyInstaller spawn" if getattr(sys, "frozen", False) else "Python spawn"
        self._emit(log_callback, f"[{command_name}] 运行模式：{mode}")
        self._emit(log_callback, f"[{command_name}] 工作目录：{self.workspace.workspace_dir}")

        process.start()
        with self._lock:
            self._process = process

        try:
            done_received = False
            while process.is_alive() or not done_received:
                try:
                    kind, payload = output_queue.get(timeout=0.2)
                except queue_module.Empty:
                    if not process.is_alive():
                        break
                    continue

                if kind == "done":
                    done_received = True
                    continue
                self._emit(log_callback, str(payload or ""))

            process.join()
            while True:
                try:
                    kind, payload = output_queue.get_nowait()
                except queue_module.Empty:
                    break
                if kind == "log":
                    self._emit(log_callback, str(payload or ""))

            return_code = int(process.exitcode or 0)
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
            try:
                output_queue.close()
                output_queue.join_thread()
            except Exception:
                pass

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

    def _build_child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["WQTG_TGAPIPLDC_WORKSPACE"] = str(self.workspace.workspace_dir)
        if getattr(sys, "frozen", False):
            env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        return env

    @staticmethod
    def _emit(log_callback: LogCallback | None, message: str) -> None:
        safe_message = str(message or "")
        if callable(log_callback):
            log_callback(safe_message)
        else:
            print(safe_message)

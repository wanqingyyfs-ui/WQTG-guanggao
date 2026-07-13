from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from pathlib import Path
from typing import IO, Any


class ProfileBusyError(RuntimeError):
    pass


class ProfileLock:
    """Cross-process lock for a Playwright persistent profile directory."""

    def __init__(
        self,
        profile_dir: str | Path,
        lock_root: str | Path,
        *,
        timeout_seconds: float = 0.0,
        poll_seconds: float = 0.25,
        job_id: str = "",
    ):
        self.profile_dir = Path(profile_dir).expanduser().resolve()
        self.lock_root = Path(lock_root).expanduser().resolve()
        digest = hashlib.sha256(str(self.profile_dir).casefold().encode("utf-8")).hexdigest()[:24]
        self.lock_path = self.lock_root / f"{digest}.lock"
        self.timeout_seconds = max(0.0, float(timeout_seconds))
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.job_id = str(job_id or "")
        self._file: IO[str] | None = None
        self._locked = False

    def acquire(self) -> "ProfileLock":
        self.lock_root.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        file = self.lock_path.open("a+", encoding="utf-8")
        self._file = file
        while True:
            try:
                self._lock_file(file)
                self._locked = True
                self._write_metadata(file)
                return self
            except (BlockingIOError, OSError) as exc:
                if time.monotonic() >= deadline:
                    metadata = self.read_metadata(self.lock_path)
                    file.close()
                    self._file = None
                    detail = f"，占用信息：{metadata}" if metadata else ""
                    raise ProfileBusyError(
                        f"浏览器 Profile 正在被其他任务占用：{self.profile_dir}{detail}"
                    ) from exc
                time.sleep(self.poll_seconds)

    def release(self) -> None:
        file = self._file
        if file is None:
            return
        try:
            if self._locked:
                try:
                    file.seek(0)
                    file.truncate(0)
                    file.write("{}\n")
                    file.flush()
                    os.fsync(file.fileno())
                except Exception:
                    pass
                self._unlock_file(file)
        finally:
            self._locked = False
            self._file = None
            file.close()

    def __enter__(self) -> "ProfileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def _write_metadata(self, file: IO[str]) -> None:
        payload: dict[str, Any] = {
            "profile_dir": str(self.profile_dir),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "job_id": self.job_id,
            "locked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        file.seek(0)
        file.truncate(0)
        json.dump(payload, file, ensure_ascii=False)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())

    @staticmethod
    def read_metadata(lock_path: str | Path) -> dict[str, Any]:
        try:
            text = Path(lock_path).read_text(encoding="utf-8").strip()
            data = json.loads(text or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _lock_file(file: IO[str]) -> None:
        if os.name == "nt":
            import msvcrt

            file.seek(0)
            if file.read(1) == "":
                file.seek(0)
                file.write("0")
                file.flush()
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_file(file: IO[str]) -> None:
        if os.name == "nt":
            import msvcrt

            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)

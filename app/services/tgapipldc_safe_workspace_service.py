from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


@contextmanager
def _locked_file(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    lock_dir = path.parent / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
    lock_path = lock_dir / f"{digest}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    if handle.read(1) == "":
                        handle.seek(0)
                        handle.write("0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待文件锁超时：{path}")
                time.sleep(0.1)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        handle.close()


class SafeTgapipldcWorkspaceService(TgapipldcWorkspaceService):
    """Workspace service with cross-process locks, backups, and atomic replacements."""

    def save_profile_maintenance_config(self, config: dict[str, Any]) -> dict[str, Any]:
        self.ensure_structure()
        normalized = self._normalize_profile_maintenance_config(config)
        self._atomic_write_text(
            self.profile_maintenance_config_path,
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        )
        return normalized

    @staticmethod
    def _rewrite_csv_with_header_and_rows(
        file_path: Path,
        header: list[str],
        rows: list[list[str]],
    ) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with _locked_file(file_path):
            SafeTgapipldcWorkspaceService._backup(file_path)
            fd, temp_name = tempfile.mkstemp(
                prefix=file_path.name + ".",
                suffix=".tmp",
                dir=str(file_path.parent),
            )
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(header)
                    writer.writerows(rows)
                    file.flush()
                    os.fsync(file.fileno())
                temp_path.replace(file_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise

    @staticmethod
    def _atomic_write_text(file_path: Path, text: str) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with _locked_file(file_path):
            SafeTgapipldcWorkspaceService._backup(file_path)
            fd, temp_name = tempfile.mkstemp(
                prefix=file_path.name + ".",
                suffix=".tmp",
                dir=str(file_path.parent),
            )
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
                    file.write(text)
                    file.flush()
                    os.fsync(file.fileno())
                temp_path.replace(file_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise

    @staticmethod
    def _backup(file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            return
        try:
            shutil.copy2(file_path, file_path.with_suffix(file_path.suffix + ".bak"))
        except Exception:
            pass

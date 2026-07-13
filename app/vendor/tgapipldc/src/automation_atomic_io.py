from __future__ import annotations

import csv
import hashlib
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator


@contextmanager
def locked_path(file_path: str | Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    path = Path(file_path).expanduser().resolve()
    lock_root = path.parent / ".locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:24]
    lock_path = lock_root / f"{digest}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    acquired = False
    try:
        while True:
            try:
                _lock_file(handle)
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
                _unlock_file(handle)
            except Exception:
                pass
        handle.close()


def atomic_write_csv(
    file_path: str | Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, Any]],
    *,
    encoding: str = "utf-8-sig",
) -> Path:
    path = Path(file_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        backup = path.with_suffix(path.suffix + ".bak")
        if path.exists() and path.is_file():
            try:
                shutil.copy2(path, backup)
            except Exception:
                pass
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding=encoding, newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({name: str(row.get(name, "") or "") for name in fieldnames})
                file.flush()
                os.fsync(file.fileno())
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    return path


def append_csv_row_locked(
    file_path: str | Path,
    fieldnames: list[str],
    row: dict[str, Any],
    *,
    encoding: str = "utf-8-sig",
) -> Path:
    path = Path(file_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", encoding=encoding, newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({name: str(row.get(name, "") or "") for name in fieldnames})
            file.flush()
            os.fsync(file.fileno())
    return path


def read_csv_rows(file_path: str | Path, *, encoding: str = "utf-8-sig") -> tuple[list[str], list[dict[str, str]]]:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return [], []
    with locked_path(path):
        with path.open("r", encoding=encoding, newline="") as file:
            reader = csv.DictReader(file)
            return list(reader.fieldnames or []), [dict(row) for row in reader]


def _lock_file(file) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0)
        if file.read(1) == "":
            file.seek(0)
            file.write("0")
            file.flush()
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)

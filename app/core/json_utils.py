from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def read_json_file(path: str | Path, default: Any = None) -> Any:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"配置文件不存在: {file_path}")
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _backup_existing_file(file_path: Path) -> None:
    if not file_path.exists() or not file_path.is_file():
        return
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup_path)


def atomic_write_json(path: str | Path, data: Any) -> None:
    file_path = Path(path).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.",
        suffix=".tmp",
        dir=str(file_path.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        _backup_existing_file(file_path)
        temp_path.replace(file_path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


class SafeTgapipldcWorkspaceService(TgapipldcWorkspaceService):
    """Workspace service with atomic replacement and .bak recovery files."""

    def save_profile_maintenance_config(self, config: dict[str, Any]) -> dict[str, Any]:
        self.ensure_structure()
        normalized = self._normalize_profile_maintenance_config(config)
        self._atomic_write_text(
            self.profile_maintenance_config_path,
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        )
        return normalized

    @staticmethod
    def _rewrite_csv_with_header_and_rows(file_path: Path, header: list[str], rows: list[list[str]]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        SafeTgapipldcWorkspaceService._backup(file_path)
        fd, temp_name = tempfile.mkstemp(prefix=file_path.name + ".", suffix=".tmp", dir=str(file_path.parent))
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
        SafeTgapipldcWorkspaceService._backup(file_path)
        fd, temp_name = tempfile.mkstemp(prefix=file_path.name + ".", suffix=".tmp", dir=str(file_path.parent))
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
        if file_path.exists() and file_path.is_file():
            try:
                shutil.copy2(file_path, file_path.with_suffix(file_path.suffix + ".bak"))
            except Exception:
                pass

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.database import Database
from app.core.paths import AppPaths


class DiagnosticsService:
    def __init__(self, db: Database, paths: AppPaths):
        self.db = db
        self.paths = paths

    def run(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["python"] = sys.version.split()[0]
        result["database_integrity"] = self.db.scalar("PRAGMA integrity_check", default="unknown")
        result["profiles_writable"] = self._writable(self.paths.profiles)
        result["assets_writable"] = self._writable(self.paths.assets)
        result["playwright_cli"] = shutil.which("playwright") or "python -m playwright"
        result["chromium"] = self._chromium_status()
        result["orphan_environment_profiles"] = int(
            self.db.scalar(
                """SELECT COUNT(*) FROM environment_profiles e
                   LEFT JOIN accounts a ON a.id=e.account_id WHERE a.id IS NULL""",
                default=0,
            )
        )
        result["duplicate_profile_dirs"] = int(
            self.db.scalar(
                """SELECT COUNT(*) FROM (
                   SELECT profile_dir FROM accounts GROUP BY profile_dir HAVING COUNT(*)>1)""",
                default=0,
            )
        )
        return result

    @staticmethod
    def _writable(path: Path) -> bool:
        probe = path / ".write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False

    @staticmethod
    def _chromium_status() -> str:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return (proc.stdout or proc.stderr).strip()[:1000]
        except Exception as exc:
            return str(exc)

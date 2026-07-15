from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.database import Database
from app.core.paths import AppPaths


class ProfileBackupError(RuntimeError):
    pass


class ProfileBackupService:
    def __init__(self, db: Database, paths: AppPaths):
        self.db = db
        self.paths = paths

    def backup(self, account_id: int) -> Path:
        account = self.db.query_one("SELECT phone,profile_dir FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise ProfileBackupError("Account does not exist")
        browser_status = self.db.scalar(
            "SELECT status FROM browser_instances WHERE account_id=?", (account_id,), "stopped"
        )
        if browser_status not in {"stopped", "not_created", None}:
            raise ProfileBackupError("Stop the account browser before backing up its profile")
        source = Path(account["profile_dir"])
        if not source.exists():
            raise ProfileBackupError("Profile directory is missing")
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        destination = self.paths.backups / f"profile-{account['phone'].lstrip('+')}-{stamp}"
        shutil.copytree(source, destination)
        return destination

    def restore(self, account_id: int, backup_dir: Path) -> None:
        account = self.db.query_one("SELECT profile_dir FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise ProfileBackupError("Account does not exist")
        browser_status = self.db.scalar(
            "SELECT status FROM browser_instances WHERE account_id=?", (account_id,), "stopped"
        )
        if browser_status not in {"stopped", "not_created", None}:
            raise ProfileBackupError("Stop the account browser before restoring its profile")
        source = Path(backup_dir).resolve()
        if not source.is_dir() or not (source / "environment.json").exists():
            raise ProfileBackupError("Backup directory is not a valid account profile")
        destination = Path(account["profile_dir"])
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

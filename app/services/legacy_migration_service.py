from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.account_service import AccountService
from app.services.group_service import GroupService


class LegacyMigrationService:
    """One-way data migration. It imports useful data but never imports legacy client credentials or session files."""

    def __init__(self, accounts: AccountService, groups: GroupService):
        self.accounts = accounts
        self.groups = groups

    def backup_legacy_root(self, legacy_root: Path, backup_root: Path) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        destination = backup_root / f"pre-browser-refactor-{stamp}"
        shutil.copytree(legacy_root, destination)
        return destination

    def migrate(self, legacy_config_dir: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"accounts": [], "groups": [], "skipped": []}
        accounts_file = legacy_config_dir / "accounts.json"
        if accounts_file.exists():
            rows = json.loads(accounts_file.read_text(encoding="utf-8"))
            for row in rows if isinstance(rows, list) else rows.get("accounts", []):
                phone = str(row.get("phone") or "").strip()
                verification_url = str(row.get("verification_url") or row.get("yanzheng") or "").strip()
                if not phone or not verification_url:
                    result["skipped"].append({"type": "account", "reason": "missing phone or verification URL"})
                    continue
                try:
                    result["accounts"].append(
                        self.accounts.create(phone, verification_url, country=str(row.get("country") or "US"))
                    )
                except Exception as exc:
                    result["skipped"].append({"type": "account", "phone": phone, "reason": str(exc)})
        groups_file = legacy_config_dir / "groups.json"
        if groups_file.exists():
            rows = json.loads(groups_file.read_text(encoding="utf-8"))
            links = []
            for row in rows if isinstance(rows, list) else rows.get("groups", []):
                link = row.get("username") or row.get("link")
                if link:
                    links.append(str(link))
            if links:
                result["groups"] = self.groups.import_links("\n".join(links))
        return result

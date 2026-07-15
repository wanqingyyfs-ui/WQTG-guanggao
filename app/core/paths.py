from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    profiles: Path
    assets: Path
    logs: Path
    backups: Path
    secrets: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.getenv("WQTG_HOME", "").strip()
        if override:
            root = Path(override).expanduser().resolve()
        elif os.name == "nt":
            root = Path(os.getenv("LOCALAPPDATA", Path.home())) / "WQTG浏览器原生版"
        else:
            root = Path.home() / ".local" / "share" / "wqtg-browser-native"
        paths = cls(
            root=root,
            database=root / "data" / "wqtg.db",
            profiles=root / "profiles",
            assets=root / "assets",
            logs=root / "logs",
            backups=root / "backups",
            secrets=root / "secrets",
        )
        paths.ensure()
        return paths

    def ensure(self) -> None:
        for path in (
            self.root,
            self.database.parent,
            self.profiles,
            self.assets,
            self.logs,
            self.backups,
            self.secrets,
        ):
            path.mkdir(parents=True, exist_ok=True)

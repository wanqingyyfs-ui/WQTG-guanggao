from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


@dataclass(frozen=True)
class LocatorProfileItem:
    profile_dir: str
    display_name: str
    raw_proxy: str = ""
    phone: str = ""


class TgapipldcLocatorService:
    """GUI-facing locator configuration and calibration metadata service."""

    CONFIG_FILE_NAME = "automation_locators.json"

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        self.src_dir = self.workspace.src_dir
        self.config_path = self.workspace.data_dir / self.CONFIG_FILE_NAME

    def _store(self):
        import sys

        src_text = str(self.src_dir)
        if src_text not in sys.path:
            sys.path.insert(0, src_text)
        from automation_locator_engine import LocatorConfigStore

        return LocatorConfigStore(self.config_path)

    def load_config(self) -> dict[str, Any]:
        return self._store().load()

    def load_targets(self) -> dict[str, dict[str, Any]]:
        return dict(self.load_config().get("targets") or {})

    def save_target(self, target_id: str, target_config: dict[str, Any]) -> dict[str, Any]:
        return self._store().save_target(target_id, target_config)

    def reset_target(self, target_id: str) -> dict[str, Any]:
        return self._store().reset_target(target_id)

    def validate_target_json(self, target_id: str, raw_text: str) -> dict[str, Any]:
        try:
            target_config = json.loads(str(raw_text or "{}"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"目标配置不是有效 JSON：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}") from exc
        if not isinstance(target_config, dict):
            raise ValueError("目标配置必须是 JSON 对象")
        store = self._store()
        config = store.load()
        if target_id not in (config.get("targets") or {}):
            raise ValueError(f"未知定位目标：{target_id}")
        candidate = dict(config)
        candidate["targets"] = dict(candidate.get("targets") or {})
        candidate["targets"][target_id] = target_config
        normalized = store.validate(candidate)
        return dict(normalized["targets"][target_id])

    def list_profiles(self) -> list[LocatorProfileItem]:
        rows_by_profile: dict[str, LocatorProfileItem] = {}
        map_path = self.workspace.account_proxy_map_csv_path
        if map_path.exists():
            try:
                with map_path.open("r", encoding="utf-8-sig", newline="") as file:
                    for row in csv.DictReader(file):
                        profile_dir = str(row.get("profile_dir") or "").strip()
                        if not profile_dir:
                            continue
                        phone = str(row.get("phone") or "").strip()
                        raw_proxy = str(row.get("raw_proxy") or "").strip()
                        label = f"{phone or '未命名账号'} — {profile_dir}"
                        rows_by_profile[profile_dir] = LocatorProfileItem(
                            profile_dir=profile_dir,
                            display_name=label,
                            raw_proxy=raw_proxy,
                            phone=phone,
                        )
            except Exception:
                pass

        if self.workspace.profiles_dir.exists():
            for child in sorted(self.workspace.profiles_dir.iterdir()):
                if not child.is_dir():
                    continue
                relative = child.relative_to(self.workspace.workspace_dir).as_posix()
                rows_by_profile.setdefault(
                    relative,
                    LocatorProfileItem(profile_dir=relative, display_name=relative),
                )
        return sorted(rows_by_profile.values(), key=lambda item: item.display_name.casefold())

    def proxy_for_profile(self, profile_dir: str) -> str:
        target = str(profile_dir or "").strip().replace("\\", "/")
        for item in self.list_profiles():
            if item.profile_dir.replace("\\", "/") == target:
                return item.raw_proxy
        return ""

    def open_directory(self) -> Path:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        return self.config_path.parent

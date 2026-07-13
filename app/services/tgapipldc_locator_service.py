from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


@dataclass(frozen=True)
class LocatorProfileItem:
    profile_dir: str
    display_name: str
    raw_proxy: str = ""


class TgapipldcLocatorService:
    CONFIG_FILE_NAME = "automation_locators.json"

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None) -> None:
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        self.src_dir = self.workspace.src_dir
        self.config_path = self.workspace.data_dir / self.CONFIG_FILE_NAME
        self._install_profile_behavior_manager_if_available()

    def _install_profile_behavior_manager_if_available(self) -> None:
        """Attach behavior management to the already-created profile page.

        The locator service is constructed immediately after the profile page is
        added to the main window. Looking up the page through QApplication keeps
        this integration isolated and leaves non-GUI/CLI usage unchanged.
        """
        profile_page = None
        try:
            from PySide6.QtWidgets import QApplication

            application = QApplication.instance()
            if application is None:
                return
            profile_page = next((
                widget for widget in application.allWidgets()
                if hasattr(widget, "get_profile_maintenance_config")
                and hasattr(widget, "set_profile_maintenance_config")
                and hasattr(widget, "profile_maintenance_requested")
                and not hasattr(widget, "behavior_manager_button")
            ), None)
            if profile_page is None:
                return

            original_get_config = profile_page.get_profile_maintenance_config

            def get_merged_config() -> dict[str, Any]:
                current = self.workspace.read_profile_maintenance_config()
                current.update(dict(original_get_config() or {}))
                return current

            profile_page.get_profile_maintenance_config = get_merged_config

            from app.gui.tgapipldc_behavior_manager import install_profile_behavior_manager
            from app.gui import tgapipldc_panel_bootstrap as panel_bootstrap

            window = profile_page.window()
            run_callback = None
            if window is not None and hasattr(window, "runtime_service"):
                run_callback = lambda action, config: panel_bootstrap._run_profile_maintenance(
                    window, action, config
                )
            install_profile_behavior_manager(
                profile_page,
                self.workspace,
                run_callback=run_callback,
                parent=window or profile_page,
            )
        except Exception as exc:
            try:
                if profile_page is not None and hasattr(profile_page, "append_log"):
                    profile_page.append_log(f"行为与步骤管理器加载失败：{exc}")
            except Exception:
                pass

    def _store(self):
        src = str(self.src_dir)
        if src not in sys.path:
            sys.path.insert(0, src)
        from automation_locator_engine import LocatorConfigStore

        return LocatorConfigStore(self.config_path)

    def load_config(self) -> dict[str, Any]:
        return self._store().load()

    def load_targets(self) -> dict[str, dict[str, Any]]:
        return dict(self.load_config().get("targets") or {})

    def validate_target_json(self, target_id: str, raw_text: str) -> dict[str, Any]:
        try:
            target = json.loads(str(raw_text or "{}"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"目标配置不是有效 JSON：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}"
            ) from exc
        if not isinstance(target, dict):
            raise ValueError("目标配置必须是 JSON 对象")
        config = self.load_config()
        if target_id not in config["targets"]:
            raise KeyError(f"未知定位目标：{target_id}")
        candidate = dict(config)
        candidate["targets"] = dict(config["targets"])
        candidate["targets"][target_id] = target
        normalized = self._store().validate(candidate)
        return dict(normalized["targets"][target_id])

    def save_target(self, target_id: str, target: dict[str, Any]) -> dict[str, Any]:
        return self._store().save_target(target_id, target)

    def reset_target(self, target_id: str) -> dict[str, Any]:
        return self._store().reset_target(target_id)

    def list_profiles(self) -> list[LocatorProfileItem]:
        result: dict[str, LocatorProfileItem] = {}
        map_path = self.workspace.account_proxy_map_csv_path
        if map_path.exists():
            try:
                with map_path.open("r", encoding="utf-8-sig", newline="") as file:
                    for row in csv.DictReader(file):
                        profile_dir = str(row.get("profile_dir") or "").strip()
                        if not profile_dir:
                            continue
                        phone = str(row.get("phone") or "").strip()
                        result[profile_dir] = LocatorProfileItem(
                            profile_dir=profile_dir,
                            display_name=f"{phone or '未命名账号'} — {profile_dir}",
                            raw_proxy=str(row.get("raw_proxy") or "").strip(),
                        )
            except Exception:
                pass
        if self.workspace.profiles_dir.exists():
            for child in sorted(self.workspace.profiles_dir.iterdir()):
                if child.is_dir():
                    relative = child.relative_to(self.workspace.workspace_dir).as_posix()
                    result.setdefault(relative, LocatorProfileItem(relative, relative))
        return sorted(result.values(), key=lambda item: item.display_name.casefold())

    def proxy_for_profile(self, profile_dir: str) -> str:
        """Return a proxy only when calibration proxy mode is explicitly enabled.

        Locator calibration is a visual maintenance tool. It defaults to direct
        networking so an expired rotating proxy cannot block element picking.
        API export and profile maintenance use their own strict proxy path and
        are not affected by this setting.
        """
        enabled = os.environ.get("WQTG_CALIBRATION_USE_PROXY", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return ""

        normalized = str(profile_dir or "").replace("\\", "/")
        for item in self.list_profiles():
            if item.profile_dir.replace("\\", "/") == normalized:
                return item.raw_proxy
        return ""

    def open_directory(self) -> Path:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        return self.config_path.parent

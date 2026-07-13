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

    def _behavior_service(self):
        from app.services.tgapipldc_behavior_service import TgapipldcBehaviorService

        return TgapipldcBehaviorService(self.workspace)

    def _install_profile_behavior_manager_if_available(self) -> None:
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

            from app.gui.tgapipldc_behavior_manager_v2 import (
                install_profile_behavior_manager_v2,
            )
            from app.gui import tgapipldc_panel_bootstrap as panel_bootstrap

            window = profile_page.window()
            run_callback = None
            locator_callback = None
            if window is not None and hasattr(window, "runtime_service"):
                run_callback = lambda action, config: panel_bootstrap._run_profile_maintenance(
                    window, action, config
                )

                def open_locator_target(target_id: str) -> None:
                    panel_bootstrap._reload_locator_config(window, silent=True)
                    locator_page = getattr(window, "tgapipldc_locator_page", None)
                    if locator_page is None:
                        raise RuntimeError("自动化定位设置页面尚未创建")
                    index = locator_page.target_combo.findData(target_id)
                    if index < 0:
                        raise RuntimeError(f"自动化定位设置中未找到步骤目标：{target_id}")
                    if hasattr(window, "tabs"):
                        window.tabs.setCurrentWidget(locator_page)
                    locator_page.target_combo.setCurrentIndex(index)
                    locator_page.append_log(f"已从行为步骤跳转到定位目标：{target_id}")

                locator_callback = open_locator_target

            install_profile_behavior_manager_v2(
                profile_page,
                self.workspace,
                run_callback=run_callback,
                locator_callback=locator_callback,
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
        try:
            self._behavior_service().load_config()
        except Exception:
            pass
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
        try:
            return self._store().reset_target(target_id)
        except KeyError:
            if self._behavior_service().reset_managed_locator_target(target_id):
                return self.load_config()
            raise

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
        """Return a proxy only when calibration proxy mode is explicitly enabled."""
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

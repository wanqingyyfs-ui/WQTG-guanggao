from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


class TgapipldcBehaviorServiceV2:
    """Persist atomic profile behaviors and keep all page steps in locator settings."""

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None) -> None:
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        src = str(self.workspace.src_dir)
        if src not in sys.path:
            sys.path.insert(0, src)

        from profile_behavior_locator_bridge import (
            LOCATOR_CLICK_TYPE,
            MANAGED_BY,
            MANAGED_TARGET_PREFIX,
            PAGE_STEP_TYPES,
            blank_managed_target,
            ensure_locator_click_support,
            locator_target_for_step,
            make_custom_click_step,
            make_custom_page_step,
            managed_target_id,
        )

        ensure_locator_click_support()

        from profile_behavior_workflow import (
            BUILTIN_BEHAVIOR_IDS,
            CONFIG_KEY,
            STEP_TYPE_LABELS,
            behavior_name,
            normalize_behaviors,
            normalize_workflow_config,
        )

        self._builtin_ids = set(BUILTIN_BEHAVIOR_IDS)
        self._config_key = CONFIG_KEY
        self._step_types = dict(STEP_TYPE_LABELS)
        self._behavior_name = behavior_name
        self._normalize_behaviors = normalize_behaviors
        self._normalize_config = normalize_workflow_config
        self._make_custom_click_step = make_custom_click_step
        self._make_custom_page_step = make_custom_page_step
        self._locator_target_for_step = locator_target_for_step
        self._managed_target_id = managed_target_id
        self._blank_managed_target = blank_managed_target
        self._page_step_types = set(PAGE_STEP_TYPES)
        self._locator_click_type = LOCATOR_CLICK_TYPE
        self._managed_prefix = MANAGED_TARGET_PREFIX
        self._managed_by = MANAGED_BY
        self.locator_config_path = Path(self.workspace.data_dir) / "automation_locators.json"

    @property
    def step_types(self) -> dict[str, str]:
        return dict(self._step_types)

    @property
    def page_step_types(self) -> set[str]:
        return set(self._page_step_types)

    @property
    def builtin_behavior_ids(self) -> set[str]:
        return set(self._builtin_ids)

    def make_custom_click_step(self, behavior_id: str, step_id: str, name: str) -> dict[str, Any]:
        return self._make_custom_click_step(behavior_id, step_id, name)

    def make_custom_page_step(
        self,
        behavior_id: str,
        step_id: str,
        name: str,
        step_type: str,
        value_source: str = "",
    ) -> dict[str, Any]:
        return self._make_custom_page_step(
            behavior_id,
            step_id,
            name,
            step_type,
            value_source=value_source,
        )

    def locator_target_for_step(self, behavior_id: str, step: dict[str, Any] | None) -> str:
        return self._locator_target_for_step(behavior_id, step)

    def _ensure_managed_target_ids(self, config: dict[str, Any]) -> dict[str, Any]:
        for behavior in config.get(self._config_key) or []:
            behavior_id = str(behavior.get("id") or "")
            for item in behavior.get("steps") or []:
                if str(item.get("type") or "") not in self._page_step_types:
                    continue
                expected = self._managed_target_id(behavior_id, str(item.get("id") or "step"))
                params = dict(item.get("params") or {})
                current = str(params.get("target_id") or "").strip()
                if not current or current.startswith(self._managed_prefix):
                    params["target_id"] = expected
                item["params"] = params
        return config

    def load_config(self) -> dict[str, Any]:
        raw = self.workspace.read_profile_maintenance_config()
        normalized = self._ensure_managed_target_ids(self._normalize_config(raw))
        if normalized != raw:
            self.workspace.save_profile_maintenance_config(normalized)
        self.sync_locator_targets(normalized)
        return normalized

    def load_behaviors(self) -> list[dict[str, Any]]:
        return deepcopy(self.load_config().get(self._config_key) or [])

    def behavior_name(self, behavior_id: str) -> str:
        return self._behavior_name(self.load_config(), behavior_id)

    def save_behaviors(
        self,
        behaviors: list[dict[str, Any]],
        base_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.load_config()
        current.update(dict(base_config or {}))
        current[self._config_key] = self._normalize_behaviors(behaviors, current)
        flag_map = {
            "photo": "update_photo",
            "name": "update_name",
            "username": "update_username",
            "bio": "update_bio",
            "folder": "add_chat_folder",
        }
        by_id = {item["id"]: item for item in current[self._config_key]}
        for behavior_id, flag in flag_map.items():
            if behavior_id in by_id:
                current[flag] = bool(by_id[behavior_id].get("enabled", True))
        normalized = self._ensure_managed_target_ids(self._normalize_config(current))
        saved = self.workspace.save_profile_maintenance_config(normalized)
        self.sync_locator_targets(saved)
        return saved

    def sync_locator_targets(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        from automation_locator_engine import LocatorConfigStore

        behavior_config = self._ensure_managed_target_ids(self._normalize_config(
            config if config is not None else self.workspace.read_profile_maintenance_config()
        ))
        store = LocatorConfigStore(self.locator_config_path)
        locator_config = store.load()
        targets = locator_config["targets"]
        before = deepcopy(targets)
        referenced: set[str] = set()

        for behavior in behavior_config.get(self._config_key) or []:
            behavior_id = str(behavior.get("id") or "")
            behavior_name = str(behavior.get("name") or behavior_id)
            for item in behavior.get("steps") or []:
                step_type = str(item.get("type") or "")
                if step_type not in self._page_step_types:
                    continue
                target_id = self.locator_target_for_step(behavior_id, item)
                if not target_id or not target_id.startswith(self._managed_prefix):
                    continue
                referenced.add(target_id)
                targets[target_id] = self._blank_managed_target(
                    target_id=target_id,
                    behavior_id=behavior_id,
                    behavior_name=behavior_name,
                    step_id=str(item.get("id") or ""),
                    step_name=str(item.get("name") or item.get("id") or ""),
                    previous=targets.get(target_id),
                    step_type=step_type,
                )

        for target_id, target in list(targets.items()):
            if (
                isinstance(target, dict)
                and target.get("managed_by") == self._managed_by
                and target_id not in referenced
            ):
                targets.pop(target_id, None)

        if targets != before:
            locator_config = store.save(locator_config)
        return locator_config

    def reset_managed_locator_target(self, target_id: str) -> bool:
        from automation_locator_engine import LocatorConfigStore

        store = LocatorConfigStore(self.locator_config_path)
        config = store.load()
        current = config.get("targets", {}).get(target_id)
        if not isinstance(current, dict) or current.get("managed_by") != self._managed_by:
            return False
        config["targets"][target_id] = self._blank_managed_target(
            target_id=target_id,
            behavior_id=str(current.get("behavior_id") or "custom"),
            behavior_name=str(current.get("category") or "自定义行为").removeprefix("行为："),
            step_id=str(current.get("step_id") or "step"),
            step_name=str(current.get("description") or "自定义步骤"),
            previous=None,
            step_type=str(current.get("step_type") or self._locator_click_type),
        )
        store.save(config)
        return True


TgapipldcBehaviorService = TgapipldcBehaviorServiceV2

from __future__ import annotations

import sys
from copy import deepcopy
from typing import Any

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


class TgapipldcBehaviorService:
    """Read, validate and persist configurable profile-maintenance behaviors."""

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None) -> None:
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        src = str(self.workspace.src_dir)
        if src not in sys.path:
            sys.path.insert(0, src)
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

    @property
    def step_types(self) -> dict[str, str]:
        return dict(self._step_types)

    @property
    def builtin_behavior_ids(self) -> set[str]:
        return set(self._builtin_ids)

    def load_config(self) -> dict[str, Any]:
        raw = self.workspace.read_profile_maintenance_config()
        normalized = self._normalize_config(raw)
        if normalized != raw:
            self.workspace.save_profile_maintenance_config(normalized)
        return normalized

    def load_behaviors(self) -> list[dict[str, Any]]:
        return deepcopy(self.load_config().get(self._config_key) or [])

    def behavior_name(self, behavior_id: str) -> str:
        return self._behavior_name(self.load_config(), behavior_id)

    def save_behaviors(self, behaviors: list[dict[str, Any]], base_config: dict[str, Any] | None = None) -> dict[str, Any]:
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
        normalized = self._normalize_config(current)
        return self.workspace.save_profile_maintenance_config(normalized)

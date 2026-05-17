from __future__ import annotations

import os
from pathlib import Path

from app.core.config_loader import (
    load_accounts,
    load_groups,
    load_settings,
    load_tasks,
    load_templates,
    save_accounts,
    save_groups,
    save_settings,
    save_tasks,
    save_templates,
)
from app.core.models import (
    AccountConfig,
    GroupConfig,
    SendTaskConfig,
    Settings,
    TemplateConfig,
)


def get_appdata_base_dir(app_name: str = "万青TG群发任务") -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / app_name
    return Path.home() / "AppData" / "Local" / app_name


class ConfigService:
    def __init__(self, base_dir: str = "."):
        self.base_dir = get_appdata_base_dir()
        self.config_dir = self.base_dir / "config"
        self.logs_dir = self.base_dir / "logs"
        self.sessions_dir = self.base_dir / "sessions"
        self.data_dir = self.base_dir / "data"

        self.accounts_path = self.config_dir / "accounts.json"
        self.groups_path = self.config_dir / "groups.json"
        self.tasks_path = self.config_dir / "tasks.json"
        self.templates_path = self.config_dir / "templates.json"
        self.settings_path = self.config_dir / "settings.json"
        self.template_cache_dir = self.data_dir / "template_cache"
        self.app_name = "万青TG群发任务"

        self._ensure_structure()

    def _ensure_structure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.template_cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.accounts_path.exists():
            save_accounts(str(self.accounts_path), [])

        if not self.groups_path.exists():
            save_groups(str(self.groups_path), [])

        if not self.tasks_path.exists():
            save_tasks(str(self.tasks_path), [])

        if not self.templates_path.exists():
            save_templates(str(self.templates_path), [])

        if not self.settings_path.exists():
            save_settings(str(self.settings_path), Settings())

    def load_all(
        self,
    ) -> tuple[
        list[AccountConfig],
        list[GroupConfig],
        list[SendTaskConfig],
        list[TemplateConfig],
        Settings,
    ]:
        accounts = load_accounts(str(self.accounts_path))
        groups = load_groups(str(self.groups_path))
        tasks = load_tasks(str(self.tasks_path))
        templates = load_templates(str(self.templates_path))
        settings = load_settings(str(self.settings_path))
        return accounts, groups, tasks, templates, settings

    def save_accounts(self, accounts: list[AccountConfig]) -> None:
        save_accounts(str(self.accounts_path), accounts)

    def save_groups(self, groups: list[GroupConfig]) -> None:
        save_groups(str(self.groups_path), groups)

    def save_tasks(self, tasks: list[SendTaskConfig]) -> None:
        save_tasks(str(self.tasks_path), tasks)

    def save_templates(self, templates: list[TemplateConfig]) -> None:
        save_templates(str(self.templates_path), templates)

    def save_settings(self, settings: Settings) -> None:
        save_settings(str(self.settings_path), settings)
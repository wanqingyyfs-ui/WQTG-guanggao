from __future__ import annotations

import os
from pathlib import Path

from app.core.config_loader import (
    load_accounts,
    load_groups,
    load_noise_pool,
    load_settings,
    load_tasks,
    load_templates,
    save_accounts,
    save_groups,
    save_noise_pool,
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


APP_NAME = "万青TG群发任务"


def get_appdata_base_dir(app_name: str = APP_NAME) -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")

    if local_appdata:
        return Path(local_appdata).expanduser() / app_name

    return Path.home() / "AppData" / "Local" / app_name


def resolve_base_dir(base_dir: str | Path | None = None) -> Path:
    """
    默认使用 Windows 用户级 AppData 目录。

    兼容旧调用：
    - RuntimeService() 默认传入 "."
    - 旧 ConfigService(base_dir=".") 过去实际也是使用 AppData

    所以这里把 None、空字符串、"." 都解析为 AppData，
    避免升级后数据目录突然变到项目根目录。
    """
    if base_dir is None:
        return get_appdata_base_dir()

    base_dir_text = str(base_dir).strip()

    if not base_dir_text or base_dir_text == ".":
        return get_appdata_base_dir()

    return Path(base_dir_text).expanduser()


class ConfigService:
    def __init__(self, base_dir: str | Path | None = None):
        self.app_name = APP_NAME
        self.base_dir = resolve_base_dir(base_dir)

        self.config_dir = self.base_dir / "config"
        self.logs_dir = self.base_dir / "logs"
        self.sessions_dir = self.base_dir / "sessions"
        self.data_dir = self.base_dir / "data"
        self.template_cache_dir = self.data_dir / "template_cache"

        self.accounts_path = self.config_dir / "accounts.json"
        self.groups_path = self.config_dir / "groups.json"
        self.tasks_path = self.config_dir / "tasks.json"
        self.templates_path = self.config_dir / "templates.json"
        self.settings_path = self.config_dir / "settings.json"
        self.noise_pool_path = self.config_dir / "noise_pool.json"

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

        if not self.noise_pool_path.exists():
            save_noise_pool(str(self.noise_pool_path), [])

        if not self.settings_path.exists():
            settings = Settings()
            settings.log_file = str(self.logs_dir / "app.log")
            settings.sessions_dir = str(self.sessions_dir)
            save_settings(str(self.settings_path), settings)

    def load_all(
        self,
    ) -> tuple[
        list[AccountConfig],
        list[GroupConfig],
        list[SendTaskConfig],
        list[TemplateConfig],
        Settings,
        list[str],
    ]:
        accounts = load_accounts(str(self.accounts_path))
        groups = load_groups(str(self.groups_path))
        tasks = load_tasks(str(self.tasks_path))
        templates = load_templates(str(self.templates_path))
        settings = load_settings(str(self.settings_path))
        noise_pool = load_noise_pool(str(self.noise_pool_path))

        settings.log_file = str(self.logs_dir / "app.log")
        settings.sessions_dir = str(self.sessions_dir)

        return accounts, groups, tasks, templates, settings, noise_pool

    def reload_settings(self) -> Settings:
        settings = load_settings(str(self.settings_path))
        settings.log_file = str(self.logs_dir / "app.log")
        settings.sessions_dir = str(self.sessions_dir)
        return settings

    def load_noise_pool(self) -> list[str]:
        return load_noise_pool(str(self.noise_pool_path))

    def save_accounts(self, accounts: list[AccountConfig]) -> None:
        save_accounts(str(self.accounts_path), accounts)

    def save_groups(self, groups: list[GroupConfig]) -> None:
        save_groups(str(self.groups_path), groups)

    def save_tasks(self, tasks: list[SendTaskConfig]) -> None:
        save_tasks(str(self.tasks_path), tasks)

    def save_templates(self, templates: list[TemplateConfig]) -> None:
        save_templates(str(self.templates_path), templates)

    def save_settings(self, settings: Settings) -> None:
        settings.log_file = str(self.logs_dir / "app.log")
        settings.sessions_dir = str(self.sessions_dir)
        save_settings(str(self.settings_path), settings)

    def save_noise_pool(self, noise_pool: list[str]) -> None:
        save_noise_pool(str(self.noise_pool_path), noise_pool)
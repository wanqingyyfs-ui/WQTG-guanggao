from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.json_utils import atomic_write_json, read_json_file
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
from app.core.proxy_utils import normalize_proxy_config, validate_proxy_config


APP_NAME = "万青TG群发任务"


def get_appdata_base_dir(app_name: str = APP_NAME) -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser() / app_name
    return Path.home() / "AppData" / "Local" / app_name


def resolve_base_dir(base_dir: str | Path | None = None) -> Path:
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
        self.group_sets_path = self.config_dir / "group_sets.json"
        self.account_group_proxies_path = self.config_dir / "account_group_proxies.json"
        self.group_pairing_runtime_state_path = self.data_dir / "group_pairing_runtime_state.json"

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
        if not self.group_sets_path.exists():
            self.save_group_sets({"account_groups": [], "group_groups": []})
        if not self.account_group_proxies_path.exists():
            self.save_account_group_proxies({})
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

    @staticmethod
    def _normalize_group_set_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = [value]
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            return []

        result: list[str] = []
        for item in raw_items:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def load_group_sets(self) -> dict[str, list[str]]:
        if not self.group_sets_path.exists():
            return {"account_groups": [], "group_groups": []}
        try:
            data = read_json_file(self.group_sets_path, default={})
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "account_groups": self._normalize_group_set_values(data.get("account_groups")),
            "group_groups": self._normalize_group_set_values(data.get("group_groups")),
        }

    def save_group_sets(self, group_sets: dict[str, Any]) -> None:
        data = group_sets if isinstance(group_sets, dict) else {}
        payload = {
            "account_groups": self._normalize_group_set_values(data.get("account_groups")),
            "group_groups": self._normalize_group_set_values(data.get("group_groups")),
        }
        atomic_write_json(self.group_sets_path, payload)


    def load_account_group_proxies(self) -> dict[str, dict[str, Any]]:
        if not self.account_group_proxies_path.exists():
            return {}
        try:
            data = read_json_file(self.account_group_proxies_path, default={})
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        raw_items = data.get("account_group_proxies", data)
        if not isinstance(raw_items, dict):
            raw_items = {}

        result: dict[str, dict[str, Any]] = {}
        for group_name, raw_config in raw_items.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                continue
            try:
                result[safe_group_name] = normalize_proxy_config(raw_config, strict=False)
            except Exception:
                result[safe_group_name] = {
                    "enabled": False,
                    "proxy_type": "socks5",
                    "host": "",
                    "port": 0,
                    "username": "",
                    "password": "",
                    "raw_proxy": "",
                    "remark": "",
                }
        return result

    def save_account_group_proxies(self, account_group_proxies: dict[str, Any]) -> None:
        raw_items = account_group_proxies if isinstance(account_group_proxies, dict) else {}
        payload_items: dict[str, dict[str, Any]] = {}
        for group_name, raw_config in raw_items.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                continue
            config = normalize_proxy_config(raw_config, strict=True)
            if not config.get("enabled") and not str(config.get("raw_proxy", "") or "").strip() and not str(config.get("remark", "") or "").strip():
                continue
            validate_proxy_config(config)
            payload_items[safe_group_name] = config

        payload = {
            "version": 1,
            "account_group_proxies": payload_items,
        }
        atomic_write_json(self.account_group_proxies_path, payload)

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

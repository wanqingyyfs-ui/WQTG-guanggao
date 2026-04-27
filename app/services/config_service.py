from __future__ import annotations

import os
from pathlib import Path

from app.core.config_loader import (
    load_accounts,
    load_rules,
    load_settings,
    load_templates,
    save_accounts,
    save_rules,
    save_settings,
    save_templates,
)
from app.core.models import (
    AccountConfig,
    RuleConfig,
    Settings,
    TemplateConfig,
    RULE_TYPE_FIRST_CONTACT,
    RULE_TYPE_KEYWORD,
    FIRST_CONTACT_WELCOME,
    FIRST_CONTACT_BUSINESS_HOURS,
    REPLY_MODE_TEXT,
)
def get_appdata_base_dir(app_name: str = "万青TG自动回复") -> Path:
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
        self.rules_path = self.config_dir / "rules.json"
        self.templates_path = self.config_dir / "templates.json"
        self.settings_path = self.config_dir / "settings.json"
        self.users_path = self.data_dir / "users.json"
        self.template_cache_dir = self.data_dir / "template_cache"
        self.app_name = "万青TG自动回复"

        self._ensure_structure()

    def _ensure_structure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.template_cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.accounts_path.exists():
            save_accounts(str(self.accounts_path), [])

        if not self.rules_path.exists():
            default_rules = [
                RuleConfig(
                    rule_name="欢迎语",
                    rule_type=RULE_TYPE_FIRST_CONTACT,
                    trigger_name=FIRST_CONTACT_WELCOME,
                    reply_text="您好，欢迎咨询。",
                    enabled=True,
                    reply_mode=REPLY_MODE_TEXT,
                ),
                RuleConfig(
                    rule_name="营业时间",
                    rule_type=RULE_TYPE_FIRST_CONTACT,
                    trigger_name=FIRST_CONTACT_BUSINESS_HOURS,
                    reply_text="我们的营业时间为每天 10:00 - 22:00。",
                    enabled=True,
                    reply_mode=REPLY_MODE_TEXT,
                ),
                RuleConfig(
                    rule_name="菜单",
                    rule_type=RULE_TYPE_KEYWORD,
                    keywords=["菜单", "有什么菜", "有菜单吗"],
                    reply_text="您好，这里是菜单信息。",
                    match_type="contains",
                    enabled=True,
                    reply_mode=REPLY_MODE_TEXT,
                ),
                RuleConfig(
                    rule_name="价格说明",
                    rule_type=RULE_TYPE_KEYWORD,
                    keywords=["价格", "多少钱", "怎么收费"],
                    reply_text="您好，关于价格请告诉我具体项目，我发给您。",
                    match_type="contains",
                    enabled=True,
                    reply_mode=REPLY_MODE_TEXT,
                ),
            ]
            save_rules(str(self.rules_path), default_rules)

        if not self.templates_path.exists():
            save_templates(str(self.templates_path), [])

        if not self.settings_path.exists():
            save_settings(str(self.settings_path), Settings())

        if not self.users_path.exists():
            self.users_path.write_text("{}", encoding="utf-8")

    def load_all(self) -> tuple[list[AccountConfig], list[RuleConfig], list[TemplateConfig], Settings]:
        accounts = load_accounts(str(self.accounts_path))
        rules = load_rules(str(self.rules_path))
        templates = load_templates(str(self.templates_path))
        settings = load_settings(str(self.settings_path))
        return accounts, rules, templates, settings

    def save_accounts(self, accounts: list[AccountConfig]) -> None:
        save_accounts(str(self.accounts_path), accounts)

    def save_rules(self, rules: list[RuleConfig]) -> None:
        save_rules(str(self.rules_path), rules)

    def save_templates(self, templates: list[TemplateConfig]) -> None:
        save_templates(str(self.templates_path), templates)

    def save_settings(self, settings: Settings) -> None:
        save_settings(str(self.settings_path), settings)
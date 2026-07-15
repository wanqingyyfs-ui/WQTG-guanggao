from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class AccountStatus(StrEnum):
    PENDING = "pending"
    PROXY_MISSING = "proxy_missing"
    PROXY_BLOCKED = "proxy_blocked"
    ENVIRONMENT_READY = "environment_ready"
    BROWSER_STARTING = "browser_starting"
    LOGIN_REQUIRED = "login_required"
    WAITING_CODE = "waiting_code"
    WAITING_2FA = "waiting_2fa"
    LOGGED_IN = "logged_in"
    READY = "ready"
    BUSY = "busy"
    MANUAL_TAKEOVER = "manual_takeover"
    ERROR = "error"
    STOPPED = "stopped"


class BrowserStatus(StrEnum):
    NOT_CREATED = "not_created"
    STARTING = "starting"
    RUNNING = "running"
    UNRESPONSIVE = "unresponsive"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"


class AttemptStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    NAVIGATING = "navigating"
    VALIDATING_TARGET = "validating_target"
    COMPOSING = "composing"
    UPLOADING = "uploading"
    SENDING = "sending"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ProxyConfig:
    id: int
    protocol: str
    host: str
    port: int
    username: str | None
    password: str | None
    expected_ip: str | None
    country: str | None
    region: str | None
    timezone: str | None

    @property
    def server(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"

    def requests_url(self) -> str:
        auth = ""
        if self.username:
            from urllib.parse import quote

            auth = quote(self.username, safe="")
            if self.password:
                auth += ":" + quote(self.password, safe="")
            auth += "@"
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    def playwright_dict(self) -> dict[str, str]:
        value = {"server": self.server}
        if self.username:
            value["username"] = self.username
        if self.password:
            value["password"] = self.password
        return value


@dataclass(frozen=True)
class AccountRuntimeConfig:
    account_id: int
    phone: str
    profile_dir: Path
    proxy: ProxyConfig
    environment: dict[str, Any]
    proxy_check_url: str

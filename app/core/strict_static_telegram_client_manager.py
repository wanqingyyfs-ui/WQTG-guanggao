from __future__ import annotations

import asyncio
import threading
from typing import Any
from urllib.parse import quote

import requests
from telethon import TelegramClient

from app.core.models import AccountConfig
from app.core.proxy_utils import mask_proxy_config, normalize_proxy_config, proxy_identity
from app.core.reliable_telegram_client_manager import ReliableTelegramClientManager


class StrictStaticTelegramClientManager(ReliableTelegramClientManager):
    """Fail-closed Telegram manager that requires one unique static proxy per account."""

    IP_CHECK_URLS = (
        "https://api.ipify.org?format=json",
        "https://ipinfo.io/json",
    )

    def __init__(self, *args, **kwargs) -> None:
        self._verified_proxy_exits: dict[tuple[Any, ...], str] = {}
        self._exit_ip_owner: dict[str, str] = {}
        self._proxy_verify_lock = threading.RLock()
        super().__init__(*args, **kwargs)

    def update_configuration(self, *args, **kwargs) -> None:
        super().update_configuration(*args, **kwargs)
        with self._proxy_verify_lock:
            self._verified_proxy_exits.clear()
            self._exit_ip_owner.clear()

    def _normalize_account_group_proxies(
        self,
        raw_items: dict | None,
    ) -> dict[str, dict[str, Any]]:
        if raw_items is None:
            return {}
        if not isinstance(raw_items, dict):
            raise RuntimeError("账号组静态代理配置格式错误，已阻止直连启动")

        result: dict[str, dict[str, Any]] = {}
        for group_name, raw_config in raw_items.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                raise RuntimeError("账号组静态代理存在空分组名称，已阻止直连启动")
            try:
                result[safe_group_name] = normalize_proxy_config(
                    raw_config,
                    strict=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"账号组【{safe_group_name}】静态代理配置无效，已阻止直连启动：{exc}"
                ) from exc
        return result

    def _require_static_proxy_for_account(
        self,
        account: AccountConfig,
    ) -> dict[str, Any]:
        account_name = str(getattr(account, "account_name", "") or "").strip()
        account_group = str(getattr(account, "account_group", "") or "").strip()
        if not account_group:
            raise RuntimeError(
                f"账号【{account_name}】未分配账号组，禁止登录、启动或发送，"
                "请先在分组管理中分配带静态代理的账号组"
            )

        raw_config = self._account_group_proxies.get(account_group)
        if raw_config is None:
            raise RuntimeError(
                f"账号【{account_name}】所属账号组【{account_group}】没有静态代理，"
                "禁止回退到真实 IP"
            )
        try:
            config = normalize_proxy_config(raw_config, strict=True)
        except Exception as exc:
            raise RuntimeError(
                f"账号【{account_name}】所属账号组【{account_group}】静态代理无效，"
                f"禁止回退到真实 IP：{exc}"
            ) from exc
        if not config.get("enabled"):
            raise RuntimeError(
                f"账号【{account_name}】所属账号组【{account_group}】静态代理未启用，"
                "禁止回退到真实 IP"
            )
        return config

    def _proxy_config_for_account(self, account: AccountConfig) -> dict[str, Any]:
        return self._require_static_proxy_for_account(account)

    def _validate_account_identity(self, account: AccountConfig) -> None:
        super()._validate_account_identity(account)
        account_name = str(getattr(account, "account_name", "") or "").strip()
        current_proxy = self._require_static_proxy_for_account(account)
        current_identity = proxy_identity(current_proxy)

        duplicate_accounts: list[str] = []
        for other in self.accounts.values():
            other_name = str(getattr(other, "account_name", "") or "").strip()
            if not other_name or other_name == account_name:
                continue
            if not bool(getattr(other, "enabled", True)):
                continue
            try:
                other_identity = proxy_identity(
                    self._require_static_proxy_for_account(other)
                )
            except RuntimeError:
                continue
            if other_identity == current_identity:
                duplicate_accounts.append(other_name)

        if duplicate_accounts:
            raise RuntimeError(
                "静态代理重复，禁止启动："
                f"账号【{account_name}】与账号【{'、'.join(duplicate_accounts)}】"
                "使用同一个静态代理。请为每个启用账号配置不同的静态代理。"
            )

    def validate_enabled_account_identities(self) -> None:
        errors: list[str] = []
        for account in self.accounts.values():
            if not bool(getattr(account, "enabled", True)):
                continue
            try:
                self._validate_account_identity(account)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            unique_errors = list(dict.fromkeys(errors))
            raise RuntimeError("启用账号静态代理安全检查失败：\n- " + "\n- ".join(unique_errors))

        exit_errors: list[str] = []
        for account in self.accounts.values():
            if not bool(getattr(account, "enabled", True)):
                continue
            try:
                self._verify_static_exit_ip(
                    account,
                    self._require_static_proxy_for_account(account),
                )
            except Exception as exc:
                exit_errors.append(str(exc))
        if exit_errors:
            raise RuntimeError(
                "启用账号静态代理出口检查失败：\n- "
                + "\n- ".join(dict.fromkeys(exit_errors))
            )

    @staticmethod
    def _requests_proxies(config: dict[str, Any]) -> dict[str, str]:
        data = normalize_proxy_config(config, strict=True)
        scheme = str(data.get("proxy_type") or "socks5")
        if scheme == "socks5":
            scheme = "socks5h"
        host = str(data.get("host") or "").strip()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        username = str(data.get("username") or "")
        password = str(data.get("password") or "")
        auth = ""
        if username:
            auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
        proxy_url = f"{scheme}://{auth}{host}:{int(data.get('port') or 0)}"
        return {"http": proxy_url, "https": proxy_url}

    def _verify_static_exit_ip(
        self,
        account: AccountConfig,
        config: dict[str, Any],
    ) -> str:
        identity = proxy_identity(config)
        account_name = str(getattr(account, "account_name", "") or "").strip()
        with self._proxy_verify_lock:
            cached = self._verified_proxy_exits.get(identity)
            if cached:
                owner = self._exit_ip_owner.get(cached)
                if owner and owner != account_name:
                    raise RuntimeError(
                        f"静态代理出口 IP 重复：账号【{account_name}】与账号【{owner}】"
                        f"当前都使用出口 {cached}，已禁止连接"
                    )
                self._exit_ip_owner[cached] = account_name
                return cached

        last_error = ""
        exit_ip = ""
        proxies = self._requests_proxies(config)
        for url in self.IP_CHECK_URLS:
            try:
                response = requests.get(url, proxies=proxies, timeout=20)
                response.raise_for_status()
                data = response.json()
                exit_ip = str(data.get("ip") or "").strip()
                if exit_ip:
                    break
                last_error = f"{url} 返回中没有 ip 字段"
            except Exception as exc:
                last_error = str(exc)
        if not exit_ip:
            raise RuntimeError(
                f"账号【{account_name}】静态代理出口检测失败，已阻止连接：{last_error}"
            )

        with self._proxy_verify_lock:
            owner = self._exit_ip_owner.get(exit_ip)
            if owner and owner != account_name:
                raise RuntimeError(
                    f"静态代理出口 IP 重复：账号【{account_name}】与账号【{owner}】"
                    f"当前都使用出口 {exit_ip}，已禁止连接"
                )
            self._verified_proxy_exits[identity] = exit_ip
            self._exit_ip_owner[exit_ip] = account_name
        return exit_ip

    async def _get_or_create_client(self, account: AccountConfig) -> TelegramClient:
        proxy_config = self._require_static_proxy_for_account(account)
        exit_ip = await asyncio.to_thread(
            self._verify_static_exit_ip,
            account,
            proxy_config,
        )
        self._emit_log(
            "info",
            f"[{account.account_name}] 已锁定账号组静态代理，任何代理错误都将直接终止 | "
            f"account_group={getattr(account, 'account_group', '')} | "
            f"proxy={mask_proxy_config(proxy_config)} | exit_ip={exit_ip}",
        )
        return await super()._get_or_create_client(account)

from __future__ import annotations

from typing import Any

from telethon import TelegramClient

from app.core.models import AccountConfig
from app.core.proxy_utils import mask_proxy_config, normalize_proxy_config
from app.core.safe_telegram_client_manager import SafeTelegramClientManager
from app.core.telegram_client_manager import LoginInputProvider


class ReliableTelegramClientManager(SafeTelegramClientManager):
    """Telegram client manager with strict proxy use and conservative retries."""

    @staticmethod
    def _proxy_payload(config: dict[str, Any] | None) -> dict[str, Any] | None:
        data = normalize_proxy_config(config or {}, strict=True)
        if not data.get("enabled"):
            return None

        try:
            from python_socks.async_.asyncio import Proxy  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "账号组已启用代理，但当前环境缺少 python-socks。"
                "请先执行 pip install -r requirements.txt；程序不会静默改为直连。"
            ) from exc

        return {
            "proxy_type": str(data.get("proxy_type") or "socks5"),
            "addr": str(data.get("host") or "").strip(),
            "port": int(data.get("port") or 0),
            "username": str(data.get("username") or "").strip() or None,
            "password": str(data.get("password") or "") or None,
            "rdns": True,
        }

    async def _get_or_create_client(self, account: AccountConfig) -> TelegramClient:
        account_name = str(account.account_name or "").strip()
        if not account_name:
            raise RuntimeError("账号名称不能为空")

        client_key = self._build_client_key(account)
        existing_client = self.clients.get(account_name)
        existing_key = self.client_keys.get(account_name)

        if existing_client is not None and existing_key == client_key:
            return existing_client

        if existing_client is not None:
            self._emit_log(
                "warning",
                f"[{account_name}] 账号或代理配置已变化，正在重建 TelegramClient",
            )
            await self._disconnect_client(account_name, emit_status=False)

        session_path, api_id, api_hash = client_key[:3]
        proxy_config = self._proxy_config_for_account(account)
        proxy = self._proxy_payload(proxy_config) if proxy_config else None

        if proxy_config:
            self._emit_log(
                "info",
                f"[{account_name}] 账号组代理配置已严格校验，连接失败将直接报错而不会回退直连 | "
                f"account_group={getattr(account, 'account_group', '')} | "
                f"proxy={mask_proxy_config(proxy_config)}",
            )

        client = TelegramClient(
            session_path,
            api_id,
            api_hash,
            proxy=proxy,
            receive_updates=self._receive_updates_for_account(account),
            sequential_updates=True,
            request_retries=1,
            connection_retries=3,
            retry_delay=2,
            flood_sleep_threshold=0,
            raise_last_call_error=True,
        )

        self.clients[account_name] = client
        self.client_keys[account_name] = client_key
        return client

    def _emit_proxy_connected(self, account: AccountConfig) -> None:
        proxy_config = self._proxy_config_for_account(account)
        if not proxy_config:
            return
        self._emit_log(
            "info",
            f"[{account.account_name}] Telegram 连接已通过账号组代理建立 | "
            f"account_group={getattr(account, 'account_group', '')} | "
            f"proxy={mask_proxy_config(proxy_config)}",
        )

    async def _start_account_unlocked(
        self,
        account: AccountConfig,
        input_provider: LoginInputProvider | None = None,
        allow_interactive_login: bool = True,
    ) -> None:
        await super()._start_account_unlocked(
            account=account,
            input_provider=input_provider,
            allow_interactive_login=allow_interactive_login,
        )
        self._emit_proxy_connected(account)

    async def login_account(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> None:
        await super().login_account(account_name, input_provider=input_provider)
        self._emit_proxy_connected(self._get_account_or_raise(account_name))

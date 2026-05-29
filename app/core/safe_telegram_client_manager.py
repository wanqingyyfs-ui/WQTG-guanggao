from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncIterator

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.core.models import AccountConfig
from app.core.proxy_utils import (
    mask_proxy_config,
    normalize_proxy_config,
    proxy_identity,
    proxy_to_telethon,
)
from app.core.telegram_client_manager import LoginInputProvider
from app.core.telegram_client_manager import TelegramClientManager as BaseTelegramClientManager


class _WrongSessionIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "Server replied with a wrong session ID" not in message


class SafeTelegramClientManager(BaseTelegramClientManager):
    """
    TelegramClientManager 的安全包装版。

    重点：
    - 同一账号 / 同一 session 文件加锁，避免程序内部重复使用同一个 session。
    - 批量启动连接限速，避免一次性拉起大量 MTProto 连接。
    - 非素材监听账号默认关闭 Telethon updates 接收，降低大量账号在线时的后台消息压力。
    - 对 Telethon wrong session ID 安全警告做降噪，避免刷屏拖慢 UI。
    """

    DEFAULT_MAX_CONCURRENT_ACCOUNT_STARTS = 1
    DEFAULT_ACCOUNT_START_GAP_SECONDS = 2.0

    def __init__(self, *args, account_group_proxies: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._account_locks: dict[str, asyncio.Lock] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._start_semaphore = asyncio.Semaphore(self._max_concurrent_account_starts())
        self._start_semaphore_size = self._max_concurrent_account_starts()
        self._last_account_start_at: datetime | None = None
        self._start_gap_lock = asyncio.Lock()
        self._account_group_proxies: dict[str, dict] = self._normalize_account_group_proxies(account_group_proxies)
        self._install_telethon_log_filter()

    def update_configuration(self, *args, account_group_proxies: dict | None = None, **kwargs) -> None:
        super().update_configuration(*args, **kwargs)
        if account_group_proxies is not None:
            self._account_group_proxies = self._normalize_account_group_proxies(account_group_proxies)
        new_size = self._max_concurrent_account_starts()
        if new_size != self._start_semaphore_size:
            self._start_semaphore = asyncio.Semaphore(new_size)
            self._start_semaphore_size = new_size

    @staticmethod
    def _install_telethon_log_filter() -> None:
        target_loggers = (
            "telethon",
            "telethon.network",
            "telethon.network.mtprotosender",
        )
        for logger_name in target_loggers:
            logger = logging.getLogger(logger_name)
            if not any(isinstance(item, _WrongSessionIdFilter) for item in logger.filters):
                logger.addFilter(_WrongSessionIdFilter())

    def _max_concurrent_account_starts(self) -> int:
        raw_value = getattr(
            self.settings,
            "max_concurrent_account_starts",
            self.DEFAULT_MAX_CONCURRENT_ACCOUNT_STARTS,
        )
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = self.DEFAULT_MAX_CONCURRENT_ACCOUNT_STARTS
        return max(1, min(10, value))

    def _account_start_gap_seconds(self) -> float:
        raw_value = getattr(
            self.settings,
            "account_start_gap_seconds",
            self.DEFAULT_ACCOUNT_START_GAP_SECONDS,
        )
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = self.DEFAULT_ACCOUNT_START_GAP_SECONDS
        return max(0.0, min(30.0, value))


    def _normalize_account_group_proxies(self, raw_items: dict | None) -> dict[str, dict]:
        if not isinstance(raw_items, dict):
            return {}
        result: dict[str, dict] = {}
        for group_name, raw_config in raw_items.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                continue
            try:
                result[safe_group_name] = normalize_proxy_config(raw_config, strict=False)
            except Exception as exc:
                self._emit_log("warning", f"账号组【{safe_group_name}】代理配置无效，已按直连处理: {exc}")
        return result

    def _proxy_config_for_account(self, account: AccountConfig) -> dict | None:
        account_group = str(getattr(account, "account_group", "") or "").strip()
        if not account_group:
            return None
        config = self._account_group_proxies.get(account_group)
        if not config:
            return None
        normalized = normalize_proxy_config(config, strict=False)
        if not normalized.get("enabled"):
            return None
        return normalized

    def _build_client_key(self, account: AccountConfig) -> tuple:
        base_key = super()._build_client_key(account)
        return (*base_key, proxy_identity(self._proxy_config_for_account(account)))

    async def _wait_account_start_gap(self) -> None:
        gap_seconds = self._account_start_gap_seconds()
        if gap_seconds <= 0:
            return

        async with self._start_gap_lock:
            if self._last_account_start_at is not None:
                elapsed = (datetime.now() - self._last_account_start_at).total_seconds()
                remaining = gap_seconds - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_account_start_at = datetime.now()

    def _account_lock(self, account_name: str) -> asyncio.Lock:
        safe_name = str(account_name or "").strip()
        if safe_name not in self._account_locks:
            self._account_locks[safe_name] = asyncio.Lock()
        return self._account_locks[safe_name]

    def _session_lock_key(self, account: AccountConfig) -> str:
        return self._build_session_path(account.session_name)

    def _session_lock(self, account: AccountConfig) -> asyncio.Lock:
        key = self._session_lock_key(account)
        if key not in self._session_locks:
            self._session_locks[key] = asyncio.Lock()
        return self._session_locks[key]

    @asynccontextmanager
    async def _account_session_guard(self, account: AccountConfig) -> AsyncIterator[None]:
        account_name = str(getattr(account, "account_name", "") or "").strip()
        account_lock = self._account_lock(account_name)
        async with account_lock:
            self._validate_account_identity(account)
            session_lock = self._session_lock(account)
            async with session_lock:
                yield

    def _receive_updates_for_account(self, account: AccountConfig) -> bool:
        account_name = str(getattr(account, "account_name", "") or "").strip()
        source_account = str(
            getattr(self.settings, "template_source_account_name", "") or ""
        ).strip()
        return bool(source_account and account_name == source_account)

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
                f"[{account_name}] 账号配置已变化，正在重建 TelegramClient",
            )
            await self._disconnect_client(account_name, emit_status=False)

        session_path, api_id, api_hash = client_key[:3]
        proxy_config = self._proxy_config_for_account(account)
        proxy = proxy_to_telethon(proxy_config) if proxy_config else None
        if proxy_config:
            self._emit_log(
                "info",
                f"[{account_name}] 使用账号组静态代理启动 | "
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
        )

        self.clients[account_name] = client
        self.client_keys[account_name] = client_key
        return client

    def _register_template_handler(self, account_name: str, client: TelegramClient) -> None:
        safe_name = str(account_name or "").strip()
        source_account = str(
            getattr(self.settings, "template_source_account_name", "") or ""
        ).strip()
        if not source_account or safe_name != source_account:
            self._remove_template_handler(safe_name, client)
            return
        super()._register_template_handler(safe_name, client)

    def _validate_account_identity(self, account: AccountConfig) -> None:
        account_name = str(getattr(account, "account_name", "") or "").strip()
        session_path = self._build_session_path(getattr(account, "session_name", ""))
        phone = str(getattr(account, "phone", "") or "").strip()

        duplicated_sessions: list[str] = []
        duplicated_phones: list[str] = []
        for other in self.accounts.values():
            other_name = str(getattr(other, "account_name", "") or "").strip()
            if not other_name or other_name == account_name:
                continue
            if not bool(getattr(other, "enabled", True)):
                continue
            other_session = self._build_session_path(getattr(other, "session_name", ""))
            if other_session == session_path:
                duplicated_sessions.append(other_name)
            other_phone = str(getattr(other, "phone", "") or "").strip()
            if phone and other_phone and other_phone == phone:
                duplicated_phones.append(other_name)

        if duplicated_sessions:
            raise RuntimeError(
                "Session 重复，禁止启动："
                f"账号【{account_name}】与账号【{'、'.join(duplicated_sessions)}】使用同一个 Session。"
                "请在账号管理里修改 Session，确保每个账号唯一。"
            )
        if duplicated_phones:
            raise RuntimeError(
                "手机号重复，禁止启动："
                f"账号【{account_name}】与账号【{'、'.join(duplicated_phones)}】手机号相同。"
                "请删除重复账号或修正手机号。"
            )

    def validate_enabled_account_identities(self) -> None:
        for account in self.accounts.values():
            if bool(getattr(account, "enabled", True)):
                self._validate_account_identity(account)

    async def ensure_account_started(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ):
        account = self._get_account_or_raise(account_name)
        async with self._account_session_guard(account):
            client = await self._get_or_create_client(account)

            if client.is_connected():
                if await client.is_user_authorized():
                    self._register_template_handler(account.account_name, client)
                    return client

                if input_provider is None:
                    self._emit_status(account.account_name, "error", "账号未登录")
                    raise RuntimeError(
                        f"账号未登录，请先在界面登录账号: {account.account_name}"
                    )

            await self._start_account_unlocked(
                account=account,
                input_provider=input_provider,
                allow_interactive_login=input_provider is not None,
            )
            return self.get_running_client(account.account_name)

    async def login_account(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> None:
        account = self._get_account_or_raise(account_name)
        async with self._account_session_guard(account):
            client = await self._get_or_create_client(account)
            try:
                async with self._start_semaphore:
                    await self._wait_account_start_gap()
                    await self._interactive_login(
                        client,
                        account,
                        input_provider=input_provider,
                    )
                self._register_template_handler(account.account_name, client)
            except Exception as exc:
                self._emit_log("error", f"[{account.account_name}] 登录失败: {exc}")
                raise

    async def start_account(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
        allow_interactive_login: bool = True,
    ) -> None:
        account = self._get_account_or_raise(account_name)
        async with self._account_session_guard(account):
            await self._start_account_unlocked(
                account=account,
                input_provider=input_provider,
                allow_interactive_login=allow_interactive_login,
            )

    async def _start_account_unlocked(
        self,
        account: AccountConfig,
        input_provider: LoginInputProvider | None = None,
        allow_interactive_login: bool = True,
    ) -> None:
        client = await self._get_or_create_client(account)

        try:
            self._emit_status(account.account_name, "starting", "启动中")
            async with self._start_semaphore:
                await self._wait_account_start_gap()
                await client.connect()

                if not await client.is_user_authorized():
                    if not allow_interactive_login:
                        self._emit_status(account.account_name, "error", "账号未登录")
                        raise RuntimeError(
                            f"账号未登录，请先在界面登录账号: {account.account_name}"
                        )

                    await self._interactive_login(
                        client,
                        account,
                        input_provider=input_provider,
                    )

            self._register_template_handler(account.account_name, client)
            self._emit_status(account.account_name, "running", "运行中")
            self._emit_log(
                "info",
                f"[{account.account_name}] 客户端启动成功，账号运行中",
            )

        except FloodWaitError as exc:
            self._emit_status(account.account_name, "error", f"FloodWait {exc.seconds}s")
            self._emit_log("error", f"[{account.account_name}] 启动失败: FloodWait {exc.seconds}s")
            raise
        except Exception as exc:
            self._emit_status(account.account_name, "error", str(exc))
            self._emit_log("error", f"[{account.account_name}] 启动失败: {exc}")
            raise

    async def stop_account(self, account_name: str) -> None:
        safe_name = str(account_name or "").strip()
        account = self.accounts.get(safe_name)
        if account is None:
            await super().stop_account(safe_name)
            return

        account_lock = self._account_lock(safe_name)
        async with account_lock:
            session_lock = self._session_lock(account)
            async with session_lock:
                await super().stop_account(safe_name)

    async def start_all(self, input_provider: LoginInputProvider | None = None) -> None:
        self.validate_enabled_account_identities()
        for account in list(self.accounts.values()):
            if not account.enabled:
                self._emit_status(account.account_name, "disabled", "未启用")
                continue

            try:
                await self.start_account(
                    account.account_name,
                    input_provider=input_provider,
                    allow_interactive_login=input_provider is not None,
                )
            except Exception as exc:
                self._emit_log(
                    "error",
                    f"[{account.account_name}] 批量启动跳过: {exc}",
                )
                continue

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Protocol

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from app.core.models import AccountConfig, Settings


class LoginInputProvider(Protocol):
    async def request_code(self, account: AccountConfig) -> str | None:
        ...

    async def request_password(self, account: AccountConfig) -> str | None:
        ...


class ConsoleLoginInputProvider:
    async def request_code(self, account: AccountConfig) -> str | None:
        return input(f"[{account.account_name}] 请输入 Telegram 验证码: ").strip()

    async def request_password(self, account: AccountConfig) -> str | None:
        return getpass.getpass(f"[{account.account_name}] 请输入二步验证密码: ").strip()


class TelegramClientManager:
    def __init__(
        self,
        accounts: list[AccountConfig],
        settings: Settings,
        logger,
        log_callback=None,
        status_callback=None,
        template_collector=None,
        **_: object,
    ):
        self.accounts: dict[str, AccountConfig] = {
            item.account_name: item for item in accounts
        }
        self.settings = settings
        self.logger = logger
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.template_collector = template_collector

        self.clients: dict[str, TelegramClient] = {}
        self.template_handler_callbacks: dict[str, object] = {}

    def update_configuration(
        self,
        accounts: list[AccountConfig],
        settings: Settings,
        **_: object,
    ) -> None:
        self.accounts = {item.account_name: item for item in accounts}
        self.settings = settings

        if self.template_collector is not None:
            self.template_collector.settings = settings

    def _emit_log(self, level: str, message: str) -> None:
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)

        if callable(self.log_callback):
            self.log_callback(level.upper(), message)

    def _emit_status(self, account_name: str, status: str, detail: str = "") -> None:
        if callable(self.status_callback):
            self.status_callback(account_name, status, detail)

    def _build_session_path(self, session_name: str) -> str:
        base_dir_text = self.settings.sessions_dir.strip()
        if base_dir_text:
            base_dir = Path(base_dir_text).expanduser()
        else:
            base_dir = Path("sessions")

        base_dir.mkdir(parents=True, exist_ok=True)
        return str(base_dir / session_name)

    def _get_account_or_raise(self, account_name: str) -> AccountConfig:
        account = self.accounts.get(account_name)
        if account is None:
            raise RuntimeError(f"账号不存在: {account_name}")
        return account

    async def _get_or_create_client(self, account: AccountConfig) -> TelegramClient:
        client = self.clients.get(account.account_name)
        if client is not None:
            return client

        session_path = self._build_session_path(account.session_name)
        client = TelegramClient(session_path, account.api_id, account.api_hash)
        self.clients[account.account_name] = client
        return client

    async def _interactive_login(
        self,
        client: TelegramClient,
        account: AccountConfig,
        input_provider: LoginInputProvider | None = None,
    ) -> None:
        provider = input_provider or ConsoleLoginInputProvider()

        await client.connect()

        if await client.is_user_authorized():
            self._emit_log("info", f"[{account.account_name}] 已复用现有 session，无需重新登录")
            self._emit_status(account.account_name, "logged_in", "已登录")
            return

        self._emit_log("info", f"[{account.account_name}] 当前未登录，开始用户号登录流程")
        self._emit_status(account.account_name, "logging_in", "登录中")

        try:
            sent = await client.send_code_request(account.phone)
            code = await provider.request_code(account)

            if not code:
                raise RuntimeError("验证码输入已取消或为空")

            try:
                await client.sign_in(
                    phone=account.phone,
                    code=code,
                    phone_code_hash=sent.phone_code_hash,
                )
            except SessionPasswordNeededError:
                password = await provider.request_password(account)

                if not password:
                    raise RuntimeError("二步验证密码输入已取消或为空")

                await client.sign_in(password=password)

            if not await client.is_user_authorized():
                raise RuntimeError("登录失败，账号仍未授权")

            self._emit_log("info", f"[{account.account_name}] 登录成功，session 已保存")
            self._emit_status(account.account_name, "logged_in", "已登录")

        except FloodWaitError as exc:
            self._emit_status(account.account_name, "error", f"FloodWait {exc.seconds}s")
            raise RuntimeError(f"登录阶段触发 FloodWait，需要等待 {exc.seconds} 秒") from exc
        except PhoneCodeInvalidError as exc:
            self._emit_status(account.account_name, "error", "验证码错误")
            raise RuntimeError("验证码错误") from exc
        except PhoneCodeExpiredError as exc:
            self._emit_status(account.account_name, "error", "验证码已过期")
            raise RuntimeError("验证码已过期") from exc
        except PhoneCodeEmptyError as exc:
            self._emit_status(account.account_name, "error", "验证码为空")
            raise RuntimeError("验证码为空") from exc

    def _register_template_handler(self, account_name: str, client: TelegramClient) -> None:
        if self.template_collector is None:
            return

        if account_name in self.template_handler_callbacks:
            return

        async def on_template_message(event):
            await self.template_collector.handle(
                account_name=account_name,
                client=client,
                event=event,
            )

        client.add_event_handler(on_template_message, events.NewMessage())
        self.template_handler_callbacks[account_name] = on_template_message

    def is_account_running(self, account_name: str) -> bool:
        client = self.clients.get(account_name)
        return bool(client and client.is_connected())

    def get_running_client(self, account_name: str) -> TelegramClient:
        client = self.clients.get(account_name)

        if client is None or not client.is_connected():
            raise RuntimeError(f"账号未启动: {account_name}")

        return client

    async def ensure_account_started(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> TelegramClient:
        if not self.is_account_running(account_name):
            await self.start_account(account_name, input_provider=input_provider)

        return self.get_running_client(account_name)

    async def login_account(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> None:
        account = self._get_account_or_raise(account_name)
        client = await self._get_or_create_client(account)

        try:
            await self._interactive_login(client, account, input_provider=input_provider)
        except Exception as exc:
            self._emit_log("error", f"[{account.account_name}] 登录失败: {exc}")
            raise

    async def start_account(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> None:
        account = self._get_account_or_raise(account_name)
        client = await self._get_or_create_client(account)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                await self._interactive_login(
                    client,
                    account,
                    input_provider=input_provider,
                )

            self._register_template_handler(account.account_name, client)

            self._emit_status(account.account_name, "running", "运行中")
            self._emit_log("info", f"[{account.account_name}] 客户端启动成功，账号运行中")
        except Exception as exc:
            self._emit_status(account.account_name, "error", str(exc))
            self._emit_log("error", f"[{account.account_name}] 启动失败: {exc}")
            raise

    async def stop_account(self, account_name: str) -> None:
        client = self.clients.get(account_name)

        if client is None:
            self._emit_status(account_name, "stopped", "未启动")
            return

        try:
            template_callback = self.template_handler_callbacks.pop(account_name, None)
            if template_callback is not None:
                client.remove_event_handler(template_callback)

            await client.disconnect()
            self.clients.pop(account_name, None)

            self._emit_status(account_name, "stopped", "已停止")
            self._emit_log("info", f"[{account_name}] 客户端已停止")
        except Exception as exc:
            self._emit_status(account_name, "error", str(exc))
            self._emit_log("error", f"[{account_name}] 停止失败: {exc}")
            raise

    async def start_all(self, input_provider: LoginInputProvider | None = None) -> None:
        for account in self.accounts.values():
            if not account.enabled:
                self._emit_status(account.account_name, "disabled", "未启用")
                continue

            try:
                await self.start_account(
                    account.account_name,
                    input_provider=input_provider,
                )
            except Exception:
                continue

    async def stop_all(self) -> None:
        account_names = list(self.clients.keys())

        for account_name in account_names:
            try:
                await self.stop_account(account_name)
            except Exception:
                continue
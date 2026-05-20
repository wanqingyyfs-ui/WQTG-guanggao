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
        self.accounts: dict[str, AccountConfig] = self._build_accounts_map(accounts)
        self.settings = settings
        self.logger = logger
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.template_collector = template_collector

        self.clients: dict[str, TelegramClient] = {}
        self.client_keys: dict[str, tuple[str, int, str]] = {}
        self.template_handler_callbacks: dict[str, object] = {}

    @staticmethod
    def _build_accounts_map(accounts: list[AccountConfig]) -> dict[str, AccountConfig]:
        result: dict[str, AccountConfig] = {}

        for account in accounts or []:
            account_name = str(account.account_name or "").strip()

            if account_name:
                result[account_name] = account

        return result

    def update_configuration(
        self,
        accounts: list[AccountConfig],
        settings: Settings,
        **_: object,
    ) -> None:
        self.accounts = self._build_accounts_map(accounts)
        self.settings = settings

        if self.template_collector is not None:
            self.template_collector.settings = settings

    def _emit_log(self, level: str, message: str) -> None:
        safe_level = str(level or "info").lower()
        safe_message = str(message or "")

        if callable(self.log_callback):
            self.log_callback(safe_level.upper(), safe_message)
            return

        if self.logger is not None:
            log_method = getattr(self.logger, safe_level, self.logger.info)
            log_method(safe_message)

    def _emit_status(self, account_name: str, status: str, detail: str = "") -> None:
        if callable(self.status_callback):
            self.status_callback(
                str(account_name or ""),
                str(status or ""),
                str(detail or ""),
            )

    def _build_session_path(self, session_name: str) -> str:
        safe_session_name = str(session_name or "").strip()

        if not safe_session_name:
            raise RuntimeError("Session 名称不能为空")

        base_dir_text = str(getattr(self.settings, "sessions_dir", "") or "").strip()

        if base_dir_text:
            base_dir = Path(base_dir_text).expanduser()
        else:
            base_dir = Path("sessions").expanduser()

        base_dir.mkdir(parents=True, exist_ok=True)
        return str(base_dir / safe_session_name)

    def _build_client_key(self, account: AccountConfig) -> tuple[str, int, str]:
        return (
            self._build_session_path(account.session_name),
            int(account.api_id),
            str(account.api_hash or ""),
        )

    def _get_account_or_raise(self, account_name: str) -> AccountConfig:
        safe_account_name = str(account_name or "").strip()
        account = self.accounts.get(safe_account_name)

        if account is None:
            raise RuntimeError(f"账号不存在: {safe_account_name}")

        return account

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

        session_path, api_id, api_hash = client_key
        client = TelegramClient(session_path, api_id, api_hash)

        self.clients[account_name] = client
        self.client_keys[account_name] = client_key

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
            self._emit_log(
                "info",
                f"[{account.account_name}] 已复用现有 session，无需重新登录",
            )
            self._emit_status(account.account_name, "logged_in", "已登录")
            return

        self._emit_log(
            "info",
            f"[{account.account_name}] 当前未登录，开始用户号登录流程",
        )
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
            self._emit_status(
                account.account_name,
                "error",
                f"FloodWait {exc.seconds}s",
            )
            raise RuntimeError(
                f"登录阶段触发 FloodWait，需要等待 {exc.seconds} 秒"
            ) from exc
        except PhoneCodeInvalidError as exc:
            self._emit_status(account.account_name, "error", "验证码错误")
            raise RuntimeError("验证码错误") from exc
        except PhoneCodeExpiredError as exc:
            self._emit_status(account.account_name, "error", "验证码已过期")
            raise RuntimeError("验证码已过期") from exc
        except PhoneCodeEmptyError as exc:
            self._emit_status(account.account_name, "error", "验证码为空")
            raise RuntimeError("验证码为空") from exc

    def _remove_template_handler(self, account_name: str, client: TelegramClient) -> None:
        callback = self.template_handler_callbacks.pop(account_name, None)

        if callback is not None:
            try:
                client.remove_event_handler(callback)
            except Exception as exc:
                self._emit_log(
                    "warning",
                    f"[{account_name}] 移除模板采集事件失败: {exc}",
                )

    def _register_template_handler(self, account_name: str, client: TelegramClient) -> None:
        if self.template_collector is None:
            return

        if account_name in self.template_handler_callbacks:
            return

        async def on_template_message(event):
            try:
                await self.template_collector.handle(
                    account_name=account_name,
                    client=client,
                    event=event,
                )
            except Exception as exc:
                self._emit_log(
                    "error",
                    f"[{account_name}] 模板采集事件处理失败: {exc}",
                )

        client.add_event_handler(on_template_message, events.NewMessage())
        self.template_handler_callbacks[account_name] = on_template_message

    def is_account_running(self, account_name: str) -> bool:
        safe_account_name = str(account_name or "").strip()
        client = self.clients.get(safe_account_name)
        return bool(client and client.is_connected())

    def get_running_client(self, account_name: str) -> TelegramClient:
        safe_account_name = str(account_name or "").strip()
        client = self.clients.get(safe_account_name)

        if client is None or not client.is_connected():
            raise RuntimeError(f"账号未启动: {safe_account_name}")

        return client

    async def ensure_account_started(
        self,
        account_name: str,
        input_provider: LoginInputProvider | None = None,
    ) -> TelegramClient:
        account = self._get_account_or_raise(account_name)
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

        await self.start_account(
            account.account_name,
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
        client = await self._get_or_create_client(account)

        try:
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
        client = await self._get_or_create_client(account)

        try:
            self._emit_status(account.account_name, "starting", "启动中")
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

        except Exception as exc:
            self._emit_status(account.account_name, "error", str(exc))
            self._emit_log("error", f"[{account.account_name}] 启动失败: {exc}")
            raise

    async def _disconnect_client(
        self,
        account_name: str,
        emit_status: bool = True,
    ) -> None:
        safe_account_name = str(account_name or "").strip()
        client = self.clients.get(safe_account_name)

        if client is None:
            if emit_status:
                self._emit_status(safe_account_name, "stopped", "未启动")
            return

        self._remove_template_handler(safe_account_name, client)

        try:
            if client.is_connected():
                await client.disconnect()
        finally:
            self.clients.pop(safe_account_name, None)
            self.client_keys.pop(safe_account_name, None)

        if emit_status:
            self._emit_status(safe_account_name, "stopped", "已停止")

    async def stop_account(self, account_name: str) -> None:
        safe_account_name = str(account_name or "").strip()

        try:
            await self._disconnect_client(safe_account_name, emit_status=True)
            self._emit_log("info", f"[{safe_account_name}] 客户端已停止")
        except Exception as exc:
            self._emit_status(safe_account_name, "error", str(exc))
            self._emit_log("error", f"[{safe_account_name}] 停止失败: {exc}")
            raise

    async def start_all(self, input_provider: LoginInputProvider | None = None) -> None:
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

    async def stop_all(self) -> None:
        account_names = list(self.clients.keys())

        for account_name in account_names:
            try:
                await self.stop_account(account_name)
            except Exception:
                continue
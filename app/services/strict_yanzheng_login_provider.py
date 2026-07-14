from __future__ import annotations

import time
from typing import Callable

import requests

from app.core.models import AccountConfig
from app.services.static_account_proxy_service import StaticAccountProxyService
from app.services.yanzheng_login_provider import YanzhengLoginInputProvider


ProxyProvider = Callable[[AccountConfig], dict[str, str]]


class StrictStaticYanzhengLoginInputProvider(YanzhengLoginInputProvider):
    """Read login code and 2FA through the same account static proxy only."""

    def __init__(
        self,
        *args,
        static_proxy_service: StaticAccountProxyService,
        group_proxies: dict | None = None,
        proxy_provider: ProxyProvider | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.static_proxy_service = static_proxy_service
        self.group_proxies = group_proxies
        self.proxy_provider = proxy_provider

    def _requests_proxies(self, account: AccountConfig) -> dict[str, str]:
        if self.proxy_provider is not None:
            proxies = self.proxy_provider(account)
        else:
            proxies = self.static_proxy_service.requests_proxies_for_account(
                account,
                self.group_proxies,
            )
        if not isinstance(proxies, dict) or not proxies.get("https"):
            raise RuntimeError(
                f"账号【{getattr(account, 'account_name', '')}】没有可用静态代理，"
                "禁止直连读取验证码"
            )
        return proxies

    def _wait_for_account_yanzheng_value(
        self,
        account,
        input_id: str,
        label: str,
    ) -> str:
        phone = str(getattr(account, "phone", "") or "").strip()
        account_name = str(getattr(account, "account_name", "") or "").strip()
        yanzheng_url = self.find_yanzheng_url_for_phone(phone)
        if not yanzheng_url:
            raise RuntimeError(f"没有找到账号 {account_name or phone} 对应的 yanzheng 地址")

        proxies = self._requests_proxies(account)
        self._log(
            f"[{account_name or phone}] 正在通过该账号分组静态代理读取 {label}：input#{input_id}"
        )
        deadline = time.time() + self.timeout_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                response = requests.get(
                    yanzheng_url,
                    proxies=proxies,
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0 TelegramLoginHelper/1.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
                value = self.extract_yanzheng_input_value(response.text, input_id)
                if value:
                    self._log(f"[{account_name or phone}] {label} 已通过静态代理读取到。")
                    return value
                last_error = f"input#{input_id} 为空或不存在"
            except Exception as exc:
                last_error = str(exc)
            self._log(
                f"[{account_name or phone}] {label} 暂未读取到，继续等待。原因：{last_error}"
            )
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"等待 [{account_name or phone}] {label} 超时：{last_error}")

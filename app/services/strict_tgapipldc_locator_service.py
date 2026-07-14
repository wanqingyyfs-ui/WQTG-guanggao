from __future__ import annotations

from typing import Callable, ClassVar

from app.services.tgapipldc_locator_service import (
    LocatorProfileItem,
    TgapipldcLocatorService,
)


ProxyProvider = Callable[[str], str]


class StrictTgapipldcLocatorService(TgapipldcLocatorService):
    """Locator service that requires the selected profile's static group proxy."""

    _default_proxy_provider: ClassVar[ProxyProvider | None] = None

    @classmethod
    def set_default_proxy_provider(cls, provider: ProxyProvider | None) -> None:
        cls._default_proxy_provider = provider

    def __init__(self, *args, proxy_provider: ProxyProvider | None = None, **kwargs) -> None:
        if proxy_provider is not None:
            type(self)._default_proxy_provider = proxy_provider
        self._strict_proxy_provider = (
            proxy_provider
            or type(self)._default_proxy_provider
            or self._discover_proxy_provider()
        )
        super().__init__(*args, **kwargs)

    @staticmethod
    def _discover_proxy_provider() -> ProxyProvider | None:
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None
            for window in app.topLevelWidgets():
                runtime = getattr(window, "runtime_service", None)
                provider = getattr(runtime, "resolve_static_proxy_for_profile", None)
                if callable(provider):
                    return provider
        except Exception:
            return None
        return None

    @staticmethod
    def _normalize_profile_dir(value: object) -> str:
        return str(value or "").replace("\\", "/").strip().strip("/").casefold()

    @classmethod
    def _same_profile_dir(cls, left: object, right: object) -> bool:
        left_key = cls._normalize_profile_dir(left)
        right_key = cls._normalize_profile_dir(right)
        if not left_key or not right_key:
            return False
        if left_key == right_key:
            return True
        return left_key.endswith("/" + right_key) or right_key.endswith("/" + left_key)

    @classmethod
    def _resolve_selected_profile_proxy(
        cls,
        runtime,
        profile_dir: str,
    ) -> str:
        service = getattr(runtime, "static_account_proxy_service", None)
        accounts_loader = getattr(runtime, "_accounts_from_disk", None)
        proxies_loader = getattr(runtime, "_load_account_group_proxies_for_runtime", None)
        if service is None or not callable(accounts_loader) or not callable(proxies_loader):
            raise RuntimeError("定位校准无法读取静态代理运行配置，已阻止直连")

        matching_rows = [
            row
            for row in service._metadata_rows()
            if cls._same_profile_dir(row.get("profile_dir"), profile_dir)
        ]
        if not matching_rows:
            raise RuntimeError(
                f"Profile【{profile_dir}】不在 API 账号运行表中，无法匹配静态代理"
            )

        row_phones = {
            str(row.get("phone") or row.get("telegram_phone") or "").strip()
            for row in matching_rows
        }
        row_phones.discard("")
        if len(row_phones) > 1:
            raise RuntimeError(
                f"Profile【{profile_dir}】同时对应多个手机号，已阻止校准以避免串号"
            )

        metadata_keys: set[str] = set()
        for row in matching_rows:
            for field in (
                "phone",
                "telegram_phone",
                "phone_for_web",
                "national_number",
            ):
                metadata_keys.update(service._phone_keys(row.get(field)))

        matched_accounts = []
        for account in accounts_loader():
            account_keys = service._phone_keys(getattr(account, "phone", ""))
            if account_keys & metadata_keys:
                matched_accounts.append(account)

        if not matched_accounts:
            raise RuntimeError(
                f"Profile【{profile_dir}】没有匹配到 WQTG 账号，无法读取分组静态代理"
            )
        account_names = {
            str(getattr(account, "account_name", "") or "").strip()
            for account in matched_accounts
        }
        if len(matched_accounts) > 1 and len(account_names) > 1:
            raise RuntimeError(
                f"Profile【{profile_dir}】匹配到多个 WQTG 账号，已阻止校准以避免串号"
            )

        account = matched_accounts[0]
        proxy_config = service.proxy_for_account(account, proxies_loader())
        return str(service._proxy_url(proxy_config) or "").strip()

    def proxy_for_profile(self, profile_dir: str) -> str:
        provider = (
            self._strict_proxy_provider
            or type(self)._default_proxy_provider
            or self._discover_proxy_provider()
        )
        if provider is None:
            raise RuntimeError("无法解析分组静态代理，定位校准已阻止直连")

        runtime = getattr(provider, "__self__", None)
        if runtime is not None and hasattr(runtime, "static_account_proxy_service"):
            raw_proxy = self._resolve_selected_profile_proxy(runtime, profile_dir)
        else:
            raw_proxy = str(provider(str(profile_dir or "")) or "").strip()

        if not raw_proxy:
            raise RuntimeError(
                f"Profile【{profile_dir}】没有分组静态代理，定位校准已阻止直连"
            )
        return raw_proxy

    def list_profiles(self) -> list[LocatorProfileItem]:
        # Profile 下拉列表只展示本地目录，不在 GUI 主线程执行代理联网检测。
        # 真正开始校准时只校验所选 Profile 对应账号，不扫描无关账号。
        return [
            LocatorProfileItem(
                profile_dir=item.profile_dir,
                display_name=item.display_name,
                raw_proxy="",
            )
            for item in super().list_profiles()
        ]

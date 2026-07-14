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

    def proxy_for_profile(self, profile_dir: str) -> str:
        provider = (
            self._strict_proxy_provider
            or type(self)._default_proxy_provider
            or self._discover_proxy_provider()
        )
        if provider is None:
            raise RuntimeError("无法解析分组静态代理，定位校准已阻止直连")
        raw_proxy = str(provider(str(profile_dir or "")) or "").strip()
        if not raw_proxy:
            raise RuntimeError(
                f"Profile【{profile_dir}】没有分组静态代理，定位校准已阻止直连"
            )
        return raw_proxy

    def list_profiles(self) -> list[LocatorProfileItem]:
        items = super().list_profiles()
        result: list[LocatorProfileItem] = []
        for item in items:
            raw_proxy = ""
            try:
                raw_proxy = self.proxy_for_profile(item.profile_dir)
            except Exception:
                pass
            result.append(
                LocatorProfileItem(
                    profile_dir=item.profile_dir,
                    display_name=item.display_name,
                    raw_proxy=raw_proxy,
                )
            )
        return result

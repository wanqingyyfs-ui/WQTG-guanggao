from __future__ import annotations

import contextvars
import os
from pathlib import Path

import requests

import automation_entry as base
from automation_adapter import (
    install_login_adapter as original_install_login_adapter,
    install_profile_adapter as original_install_profile_adapter,
)
from proxy_utils import parse_raw_proxy


_ACTIVE_PROXY = contextvars.ContextVar("wqtg_active_proxy", default=None)


def _strict_fetch_yanzheng_html(yanzheng_url: str, timeout: int = 20) -> str:
    parsed_proxy = _ACTIVE_PROXY.get()
    if parsed_proxy is None:
        raise RuntimeError("当前账号没有活动代理，禁止直连读取 yanzheng 验证码")
    url = str(yanzheng_url or "").strip()
    if not url:
        raise ValueError("当前账号缺少 yanzheng 验证码网页地址")
    response = requests.get(
        url,
        proxies=parsed_proxy.requests_proxies,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 TelegramLoginHelper/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    response.raise_for_status()
    return response.text


def _patch_yanzheng_fetch(module) -> None:
    if module is not None and callable(getattr(module, "fetch_yanzheng_html", None)):
        module.fetch_yanzheng_html = _strict_fetch_yanzheng_html


def _set_active_proxy(account: dict):
    raw_proxy = str((account or {}).get("raw_proxy") or "").strip()
    if not raw_proxy:
        raise RuntimeError("当前账号代理为空，禁止直连")
    return _ACTIVE_PROXY.set(parse_raw_proxy(raw_proxy))


def install_login_adapter(module):
    _patch_yanzheng_fetch(module)
    original_read = module.read_account_proxy_map

    def strict_read_account_proxy_map():
        rows = original_read()
        phone_owner: dict[str, str] = {}
        profile_owner: dict[str, str] = {}
        for row in rows:
            phone = str(row.get("phone") or "").strip()
            profile_dir = str(row.get("profile_dir") or "").replace("\\", "/").strip("/")
            if not profile_dir:
                raise RuntimeError(f"账号【{phone}】缺少独立 Profile 目录")
            previous_phone = profile_owner.get(profile_dir)
            if previous_phone and previous_phone != phone:
                raise RuntimeError(
                    f"Profile 目录重复：账号【{phone}】与账号【{previous_phone}】"
                    f"共用 {profile_dir}，已阻止 API 获取"
                )
            profile_owner[profile_dir] = phone
            digits = "".join(character for character in phone if character.isdigit())
            if digits:
                previous_profile = phone_owner.get(digits)
                if previous_profile and previous_profile != profile_dir:
                    raise RuntimeError(
                        f"手机号【{phone}】被配置到多个 Profile，已阻止 API 获取"
                    )
                phone_owner[digits] = profile_dir
        return rows

    module.read_account_proxy_map = strict_read_account_proxy_map
    state = original_install_login_adapter(module)
    original_open = module.open_telegram_web_for_login

    def strict_open(account: dict[str, str]):
        token = _set_active_proxy(account)
        try:
            return original_open(account)
        finally:
            _ACTIVE_PROXY.reset(token)

    strict_open._wqtg_strict_proxy = True
    module.open_telegram_web_for_login = strict_open
    return state


def install_profile_adapter(module):
    override = str(os.environ.get("WQTG_ACCOUNT_PROXY_MAP_OVERRIDE") or "").strip()
    if not override:
        raise RuntimeError("资料维护缺少静态代理运行表，禁止直连")
    map_path = Path(override).expanduser().resolve()
    if not map_path.exists():
        raise FileNotFoundError(f"静态代理运行表不存在：{map_path}")
    module.ACCOUNT_PROXY_MAP_FILE = map_path

    _patch_yanzheng_fetch(module)
    try:
        import login_telegram_web
        _patch_yanzheng_fetch(login_telegram_web)
    except Exception:
        pass

    state = original_install_profile_adapter(module)
    original_process = module.process_account

    def strict_process(action, config, account, account_index, total, used_photos):
        token = _set_active_proxy(account)
        try:
            return original_process(
                action,
                config,
                account,
                account_index,
                total,
                used_photos,
            )
        finally:
            _ACTIVE_PROXY.reset(token)

    strict_process._wqtg_strict_proxy = True
    module.process_account = strict_process
    return state


def _open_calibration_browser_strict(
    playwright,
    *,
    profile_path,
    viewport,
    target_id,
    url,
    raw_proxy,
    save_locator,
):
    proxy_text = str(raw_proxy or "").strip()
    if not proxy_text:
        raise RuntimeError("定位校准缺少静态代理，禁止直连")
    parsed_proxy = parse_raw_proxy(proxy_text)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_path),
        headless=False,
        viewport=viewport,
        proxy=parsed_proxy.playwright_proxy,
        args=[
            "--disable-quic",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ],
    )
    succeeded = False
    try:
        installer = base._configure_calibration_context(context, target_id, save_locator)
        page = context.pages[0] if context.pages else context.new_page()
        target_url = url or "https://web.telegram.org/k/"
        page.goto(target_url, wait_until="commit", timeout=20000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        if not installer.ensure_page(page):
            raise RuntimeError("定位拾取器未能注入当前页面")
        succeeded = True
        return context, page, False
    except Exception as exc:
        raise RuntimeError(
            f"定位校准静态代理连接失败，已禁止回退直连：{exc}"
        ) from exc
    finally:
        if not succeeded:
            try:
                context.close()
            except Exception:
                pass


base.install_login_adapter = install_login_adapter
base.install_profile_adapter = install_profile_adapter
base._open_calibration_browser = _open_calibration_browser_strict


if __name__ == "__main__":
    raise SystemExit(base.main())

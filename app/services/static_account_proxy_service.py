from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import requests

from app.core.models import AccountConfig
from app.core.proxy_utils import mask_proxy_config, normalize_proxy_config, proxy_identity
from app.services.config_service import ConfigService
from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


STATIC_MAP_FIELDS = [
    "phone",
    "country",
    "country_code",
    "national_number",
    "telegram_phone",
    "phone_for_web",
    "profile_dir",
    "yanzheng",
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
    "status",
    "note",
]


class StaticAccountProxyService:
    """Build strict per-account static proxy mappings from WQTG group settings."""

    def __init__(
        self,
        config_service: ConfigService,
        workspace_service: TgapipldcWorkspaceService,
    ) -> None:
        self.config_service = config_service
        self.workspace = workspace_service
        self.workspace.ensure_structure()
        self.static_map_path = self.workspace.data_dir / "static_account_proxy_map.csv"

    def load_group_proxies_strict(self) -> dict[str, dict[str, Any]]:
        path = self.config_service.account_group_proxies_path
        if not path.exists():
            raise FileNotFoundError(
                f"找不到账号组静态代理配置：{path}。禁止使用真实 IP 继续。"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise RuntimeError(
                f"账号组静态代理配置读取失败：{exc}。禁止使用真实 IP 继续。"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError("账号组静态代理配置必须是 JSON 对象，已阻止直连")
        raw_items = data.get("account_group_proxies", data)
        if not isinstance(raw_items, dict):
            raise RuntimeError("account_group_proxies 必须是对象，已阻止直连")

        result: dict[str, dict[str, Any]] = {}
        for group_name, raw_config in raw_items.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                raise RuntimeError("账号组静态代理配置存在空分组名，已阻止直连")
            try:
                result[safe_group_name] = normalize_proxy_config(
                    raw_config,
                    strict=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"账号组【{safe_group_name}】静态代理配置无效：{exc}。已阻止直连。"
                ) from exc
        return result

    @staticmethod
    def _phone_keys(value: object) -> set[str]:
        text = str(value or "").strip()
        digits = re.sub(r"\D", "", text)
        keys: set[str] = set()
        if text:
            keys.add(text)
        if digits:
            keys.add(digits)
            keys.add(f"+{digits}")
        return keys

    def _metadata_rows(self) -> list[dict[str, str]]:
        path = self.workspace.account_proxy_map_csv_path
        if not path.exists():
            raise FileNotFoundError(
                f"找不到 API 账号运行表：{path}。请先完成 API 获取和导入。"
            )
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]

    def _metadata_index(self) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for row in self._metadata_rows():
            keys: set[str] = set()
            for field in ("phone", "telegram_phone", "phone_for_web", "national_number"):
                keys.update(self._phone_keys(row.get(field)))
            for key in keys:
                result.setdefault(key, row)
        return result

    @staticmethod
    def _proxy_url(config: dict[str, Any], *, for_requests: bool = False) -> str:
        data = normalize_proxy_config(config, strict=True)
        if not data.get("enabled"):
            raise RuntimeError("静态代理未启用")
        scheme = str(data.get("proxy_type") or "socks5")
        if for_requests and scheme == "socks5":
            scheme = "socks5h"
        host = str(data.get("host") or "").strip()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        username = str(data.get("username") or "")
        password = str(data.get("password") or "")
        auth = ""
        if username:
            auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
        return f"{scheme}://{auth}{host}:{int(data.get('port') or 0)}"

    def proxy_for_account(
        self,
        account: AccountConfig,
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        account_name = str(getattr(account, "account_name", "") or "").strip()
        group_name = str(getattr(account, "account_group", "") or "").strip()
        if not group_name:
            raise RuntimeError(
                f"账号【{account_name}】未分配账号组，禁止使用真实 IP"
            )
        proxies = group_proxies if group_proxies is not None else self.load_group_proxies_strict()
        raw_config = proxies.get(group_name)
        if raw_config is None:
            raise RuntimeError(
                f"账号【{account_name}】所属账号组【{group_name}】没有静态代理"
            )
        config = normalize_proxy_config(raw_config, strict=True)
        if not config.get("enabled"):
            raise RuntimeError(
                f"账号【{account_name}】所属账号组【{group_name}】静态代理未启用"
            )
        return config

    def validate_enabled_accounts(
        self,
        accounts: Iterable[AccountConfig],
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        proxies = group_proxies if group_proxies is not None else self.load_group_proxies_strict()
        identity_owner: dict[tuple[Any, ...], str] = {}
        session_owner: dict[str, str] = {}
        phone_owner: dict[str, str] = {}
        errors: list[str] = []

        for account in accounts:
            if not bool(getattr(account, "enabled", True)):
                continue
            name = str(getattr(account, "account_name", "") or "").strip()
            try:
                config = self.proxy_for_account(account, proxies)
                identity = proxy_identity(config)
                owner = identity_owner.get(identity)
                if owner and owner != name:
                    errors.append(
                        f"账号【{name}】与账号【{owner}】使用同一个静态代理"
                    )
                else:
                    identity_owner[identity] = name
            except Exception as exc:
                errors.append(str(exc))

            session_name = str(getattr(account, "session_name", "") or "").strip()
            if session_name:
                owner = session_owner.get(session_name)
                if owner and owner != name:
                    errors.append(f"账号【{name}】与账号【{owner}】使用同一个 Session")
                else:
                    session_owner[session_name] = name

            phone_digits = re.sub(r"\D", "", str(getattr(account, "phone", "") or ""))
            if phone_digits:
                owner = phone_owner.get(phone_digits)
                if owner and owner != name:
                    errors.append(f"账号【{name}】与账号【{owner}】使用同一个手机号")
                else:
                    phone_owner[phone_digits] = name

        if errors:
            raise RuntimeError(
                "静态代理与账号隔离检查失败：\n- "
                + "\n- ".join(dict.fromkeys(errors))
            )

    def verify_unique_exit_ips(
        self,
        accounts: Iterable[AccountConfig],
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        proxies = group_proxies if group_proxies is not None else self.load_group_proxies_strict()
        exit_owner: dict[str, str] = {}
        result: dict[str, str] = {}
        for account in accounts:
            if not bool(getattr(account, "enabled", True)):
                continue
            name = str(getattr(account, "account_name", "") or "").strip()
            config = self.proxy_for_account(account, proxies)
            request_proxies = {
                "http": self._proxy_url(config, for_requests=True),
                "https": self._proxy_url(config, for_requests=True),
            }
            last_error = ""
            exit_ip = ""
            for url in ("https://api.ipify.org?format=json", "https://ipinfo.io/json"):
                try:
                    response = requests.get(url, proxies=request_proxies, timeout=20)
                    response.raise_for_status()
                    exit_ip = str(response.json().get("ip") or "").strip()
                    if exit_ip:
                        break
                    last_error = f"{url} 返回中没有 ip 字段"
                except Exception as exc:
                    last_error = str(exc)
            if not exit_ip:
                raise RuntimeError(
                    f"账号【{name}】静态代理出口检测失败，已阻止继续：{last_error}"
                )
            owner = exit_owner.get(exit_ip)
            if owner and owner != name:
                raise RuntimeError(
                    f"静态代理实际出口重复：账号【{name}】与账号【{owner}】"
                    f"都使用出口 {exit_ip}，已阻止继续"
                )
            exit_owner[exit_ip] = name
            result[name] = exit_ip
        return result

    def build_static_profile_map(
        self,
        accounts: Iterable[AccountConfig],
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> Path:
        account_list = list(accounts)
        proxies = group_proxies if group_proxies is not None else self.load_group_proxies_strict()
        self.validate_enabled_accounts(account_list, proxies)
        verified_exit_ips = self.verify_unique_exit_ips(account_list, proxies)
        metadata_index = self._metadata_index()

        rows: list[dict[str, str]] = []
        profile_owner: dict[str, str] = {}
        for account in account_list:
            if not bool(getattr(account, "enabled", True)):
                continue
            metadata: dict[str, str] | None = None
            for key in self._phone_keys(getattr(account, "phone", "")):
                metadata = metadata_index.get(key)
                if metadata:
                    break
            if metadata is None:
                continue

            profile_dir = str(metadata.get("profile_dir") or "").strip()
            if not profile_dir:
                raise RuntimeError(
                    f"账号【{account.account_name}】缺少独立 Profile 目录，禁止资料维护或校准"
                )
            previous = profile_owner.get(profile_dir)
            if previous and previous != account.account_name:
                raise RuntimeError(
                    f"Profile 目录重复：账号【{account.account_name}】与账号【{previous}】"
                    f"共用 {profile_dir}，已禁止继续"
                )
            profile_owner[profile_dir] = account.account_name

            proxy_config = self.proxy_for_account(account, proxies)
            rows.append({
                "phone": str(metadata.get("phone") or account.phone),
                "country": str(metadata.get("country") or ""),
                "country_code": str(metadata.get("country_code") or ""),
                "national_number": str(metadata.get("national_number") or ""),
                "telegram_phone": str(metadata.get("telegram_phone") or account.phone),
                "phone_for_web": str(metadata.get("phone_for_web") or account.phone),
                "profile_dir": profile_dir,
                "yanzheng": str(metadata.get("yanzheng") or ""),
                "raw_proxy": self._proxy_url(proxy_config),
                "masked_proxy": mask_proxy_config(proxy_config),
                "exit_ip": str(verified_exit_ips.get(account.account_name) or ""),
                "status": "static_group_proxy_verified",
                "note": f"account_group={account.account_group}; static_proxy_only",
            })

        if not rows:
            raise RuntimeError(
                "没有可生成静态代理运行表的启用账号。请先为导入账号分配账号组静态代理并启用账号。"
            )

        self.static_map_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.static_map_path.with_suffix(self.static_map_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=STATIC_MAP_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(self.static_map_path)
        return self.static_map_path

    def proxy_for_profile(
        self,
        profile_dir: str,
        accounts: Iterable[AccountConfig],
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        path = self.build_static_profile_map(accounts, group_proxies)
        normalized = str(profile_dir or "").replace("\\", "/").strip("/")
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                current = str(row.get("profile_dir") or "").replace("\\", "/").strip("/")
                if current == normalized:
                    raw_proxy = str(row.get("raw_proxy") or "").strip()
                    if not raw_proxy:
                        break
                    return raw_proxy
        raise RuntimeError(
            f"Profile【{profile_dir}】没有对应的分组静态代理，禁止定位校准直连"
        )

    def requests_proxies_for_account(
        self,
        account: AccountConfig,
        group_proxies: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        config = self.proxy_for_account(account, group_proxies)
        url = self._proxy_url(config, for_requests=True)
        return {"http": url, "https": url}

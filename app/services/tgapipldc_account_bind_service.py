from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


COUNTRY_CODE_BY_COUNTRY = {
    "US": "1",
    "CA": "1",
    "GB": "44",
    "UK": "44",
    "SG": "65",
    "HK": "852",
    "KH": "855",
    "CN": "86",
    "TH": "66",
}

ACCOUNT_PROXY_MAP_FIELDS = [
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


@dataclass(frozen=True)
class AccountBindResult:
    account_count: int
    proxy_count: int
    assigned_count: int
    account_proxy_map_path: Path


class TgapipldcAccountBindService:
    """
    tgapipldc 动态轮换代理账号运行表生成服务。

    当前规则已经改为动态轮换代理模式：
    - accounts.csv 仍然提供账号、国家、profile_dir、status、yanzheng；
    - proxies.csv 只允许配置一条 raw_proxy；
    - 生成 account_proxy_map.csv 时，每个账号都写入同一条动态轮换代理；
    - 不再依赖 usable_proxies.csv，也不再要求一个账号绑定一条独立代理。
    """

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()

    def assign_accounts_to_proxies(self) -> AccountBindResult:
        accounts = self.read_pending_accounts()
        proxy = self.read_dynamic_proxy()

        rows: list[dict[str, str]] = []

        for account in accounts:
            account_note = self._clean(account.get("note"))
            note_parts = [part for part in [account_note, "shared_dynamic_proxy"] if part]

            rows.append(
                {
                    "phone": account["phone"],
                    "country": account["country"],
                    "country_code": account["country_code"],
                    "national_number": account["national_number"],
                    "telegram_phone": account["telegram_phone"],
                    "phone_for_web": account["phone_for_web"],
                    "profile_dir": account["profile_dir"],
                    "yanzheng": account["yanzheng"],
                    "raw_proxy": proxy["raw_proxy"],
                    "masked_proxy": proxy["masked_proxy"],
                    "exit_ip": "",
                    "status": "dynamic_proxy_assigned",
                    "note": " | ".join(note_parts),
                }
            )

        self._write_account_proxy_map(rows)

        return AccountBindResult(
            account_count=len(accounts),
            proxy_count=1,
            assigned_count=len(rows),
            account_proxy_map_path=self.workspace.account_proxy_map_csv_path,
        )

    def read_pending_accounts(self) -> list[dict[str, str]]:
        path = self.workspace.accounts_csv_path

        if not path.exists():
            raise FileNotFoundError(f"找不到账号文件：{path}")

        accounts: list[dict[str, str]] = []

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = set(reader.fieldnames or [])

            required_fields = {"phone", "country", "profile_dir", "status", "yanzheng"}
            missing_fields = required_fields - fieldnames
            if missing_fields:
                raise ValueError(f"accounts.csv 缺少字段：{missing_fields}")

            for line_number, row in enumerate(reader, start=2):
                status = self._clean(row.get("status"))
                if status not in {"", "pending", "proxy_required", "new", "unused"}:
                    continue

                try:
                    accounts.append(self._normalize_account_row(row))
                except Exception as exc:
                    raise ValueError(f"accounts.csv 第 {line_number} 行格式错误：{exc}") from exc

        if not accounts:
            raise ValueError("accounts.csv 里没有 pending / proxy_required / new / unused 状态的账号")

        return accounts

    def read_dynamic_proxy(self) -> dict[str, str]:
        path = self.workspace.proxies_csv_path

        if not path.exists():
            raise FileNotFoundError(f"找不到动态代理文件：{path}")

        raw_proxies: list[str] = []

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = set(reader.fieldnames or [])

            if "raw_proxy" not in fieldnames:
                raise ValueError("proxies.csv 第一行表头必须是：raw_proxy")

            for row in reader:
                raw_proxy = self._clean(row.get("raw_proxy"))
                if raw_proxy:
                    raw_proxies.append(raw_proxy)

        if not raw_proxies:
            raise ValueError("proxies.csv 里没有动态轮换代理")

        if len(raw_proxies) > 1:
            raise ValueError("当前动态轮换代理模式只允许配置一条 raw_proxy，请删除多余代理后重新保存")

        raw_proxy = raw_proxies[0]
        masked_proxy = self._mask_raw_proxy(raw_proxy)
        return {
            "raw_proxy": raw_proxy,
            "masked_proxy": masked_proxy,
        }

    def _normalize_account_row(self, row: dict[str, str]) -> dict[str, str]:
        phone = self._clean(row.get("phone"))
        country = self._clean(row.get("country")).upper()
        profile_dir = self._clean(row.get("profile_dir"))
        status = self._clean(row.get("status")) or "pending"
        yanzheng = self._clean(row.get("yanzheng"))
        note = self._clean(row.get("note"))

        if not phone:
            raise ValueError("phone 为空")
        if not country:
            raise ValueError("country 为空")
        if not profile_dir:
            raise ValueError("profile_dir 为空")
        if not yanzheng:
            raise ValueError("yanzheng 为空")

        country_code = self._normalize_country_code(country)
        phone_digits = self._only_digits(phone)

        if not phone_digits:
            raise ValueError(f"手机号没有数字：{phone}")

        country_code_digits = self._only_digits(country_code)
        if country_code_digits:
            if phone_digits.startswith(country_code_digits) and len(phone_digits) > len(country_code_digits):
                national_number = phone_digits[len(country_code_digits):]
                telegram_phone = f"+{phone_digits}"
            else:
                national_number = phone_digits
                telegram_phone = f"+{country_code_digits}{national_number}"
        else:
            national_number = phone_digits
            telegram_phone = f"+{phone_digits}"

        if not national_number:
            raise ValueError(f"手机号缺少本地号码部分：{phone}")

        phone_for_web = telegram_phone.replace(" ", "")

        return {
            "phone": phone_for_web,
            "country": country,
            "country_code": country_code,
            "national_number": national_number,
            "telegram_phone": phone_for_web,
            "phone_for_web": phone_for_web,
            "profile_dir": profile_dir,
            "yanzheng": yanzheng,
            "status": status,
            "note": note,
        }

    def _write_account_proxy_map(self, rows: list[dict[str, str]]) -> None:
        path = self.workspace.account_proxy_map_csv_path
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=ACCOUNT_PROXY_MAP_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        temp_path.replace(path)

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _only_digits(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _normalize_country_code(self, country: str) -> str:
        digits = COUNTRY_CODE_BY_COUNTRY.get(self._clean(country).upper(), "")
        if not digits:
            return ""
        return f"+{digits}"

    @staticmethod
    def _mask_raw_proxy(raw_proxy: str) -> str:
        normalized_proxy = str(raw_proxy or "").strip()

        if normalized_proxy.startswith("http://"):
            normalized_proxy = normalized_proxy[len("http://"):]

        if normalized_proxy.startswith("https://"):
            normalized_proxy = normalized_proxy[len("https://"):]

        if "@" not in normalized_proxy:
            raise ValueError(f"动态代理格式错误，缺少 @：{normalized_proxy}")

        auth_part, host_part = normalized_proxy.rsplit("@", 1)

        if ":" not in auth_part:
            raise ValueError(f"动态代理格式错误，账号密码部分缺少冒号：{normalized_proxy}")

        username, password = auth_part.split(":", 1)

        if ":" not in host_part:
            raise ValueError(f"动态代理格式错误，host 端口部分缺少冒号：{normalized_proxy}")

        host, port_text = host_part.rsplit(":", 1)

        if not username:
            raise ValueError("动态代理用户名为空")
        if not password:
            raise ValueError("动态代理密码为空")
        if not host:
            raise ValueError("动态代理 host 为空")

        try:
            int(port_text)
        except ValueError as exc:
            raise ValueError(f"动态代理端口不是数字：{port_text}") from exc

        return f"{username}:******@{host}:{port_text}"

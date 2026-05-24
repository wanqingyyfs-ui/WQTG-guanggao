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

USABLE_PROXY_REQUIRED_FIELDS = {
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
    "assigned_phone",
    "status",
    "note",
}


@dataclass(frozen=True)
class AccountBindResult:
    account_count: int
    proxy_count: int
    assigned_count: int
    account_proxy_map_path: Path


class TgapipldcAccountBindService:
    """
    tgapipldc 账号代理绑定服务。

    对应原命令：

        python src\\assign_proxies.py

    输入：
    - data/accounts.csv
      当前 WQTG 面板固定格式：
      phone,country,profile_dir,status,yanzheng

    - data/usable_proxies.csv
      来自 TgapipldcProxyService.build_proxy_pool()

    输出：
    - data/account_proxy_map.csv

    绑定规则：
    - 只读取 accounts.csv 中 status 属于 pending/proxy_required/new/unused/空 的账号；
    - 只读取 usable_proxies.csv 中 status == unused 的代理；
    - 按顺序一对一绑定；
    - 可用代理少于账号时，只绑定前 N 个账号；
    - 输出字段兼容 tgapipldc 原 login_telegram_web.py。
    """

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()

    def assign_accounts_to_proxies(self) -> AccountBindResult:
        accounts = self.read_pending_accounts()
        proxies = self.read_usable_proxies()

        assign_count = min(len(accounts), len(proxies))
        rows: list[dict[str, str]] = []

        for index in range(assign_count):
            account = accounts[index]
            proxy = proxies[index]

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
                    "exit_ip": proxy["exit_ip"],
                    "status": "proxy_assigned",
                    "note": account["note"],
                }
            )

        self._write_account_proxy_map(rows)

        return AccountBindResult(
            account_count=len(accounts),
            proxy_count=len(proxies),
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

    def read_usable_proxies(self) -> list[dict[str, str]]:
        path = self.workspace.usable_proxies_csv_path

        if not path.exists():
            raise FileNotFoundError(f"找不到可用代理文件：{path}")

        proxies: list[dict[str, str]] = []
        seen_exit_ips: set[str] = set()

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            current_fields = set(reader.fieldnames or [])
            missing_fields = USABLE_PROXY_REQUIRED_FIELDS - current_fields

            if missing_fields:
                raise ValueError(f"usable_proxies.csv 缺少字段：{missing_fields}")

            for row in reader:
                status = self._clean(row.get("status"))
                raw_proxy = self._clean(row.get("raw_proxy"))
                masked_proxy = self._clean(row.get("masked_proxy"))
                exit_ip = self._clean(row.get("exit_ip"))

                if status != "unused":
                    continue
                if not raw_proxy or not exit_ip:
                    continue
                if exit_ip in seen_exit_ips:
                    continue

                seen_exit_ips.add(exit_ip)

                proxies.append(
                    {
                        "raw_proxy": raw_proxy,
                        "masked_proxy": masked_proxy,
                        "exit_ip": exit_ip,
                        "status": status,
                    }
                )

        if not proxies:
            raise ValueError("usable_proxies.csv 里没有可分配代理")

        return proxies

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

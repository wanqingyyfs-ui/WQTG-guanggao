from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.core.models import AccountConfig
from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


API_CSV_REQUIRED_FIELDS = {
    "phone",
    "api_id",
    "api_hash",
}

ACCOUNT_PROXY_MAP_MIN_FIELDS = {
    "phone",
    "country",
    "profile_dir",
    "yanzheng",
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
}


@dataclass(frozen=True)
class TgapipldcImportedAccount:
    phone: str
    api_id: int
    api_hash: str
    account_name: str
    session_name: str

    country: str = ""
    country_code: str = ""
    national_number: str = ""
    telegram_phone: str = ""
    phone_for_web: str = ""
    profile_dir: str = ""
    yanzheng: str = ""
    raw_proxy: str = ""
    masked_proxy: str = ""
    exit_ip: str = ""
    source_status: str = ""
    source_note: str = ""


@dataclass(frozen=True)
class TgapipldcImportResult:
    imported_rows: list[TgapipldcImportedAccount]
    accounts: list[AccountConfig]
    created_count: int
    updated_count: int
    skipped_count: int
    api_csv_path: Path
    account_proxy_map_path: Path


class TgapipldcImportService:
    """
    tgapipldc API CSV 导入服务。

    当前职责：
    1. 读取 app/vendor/tgapipldc/csv/api.csv；
    2. 读取 app/vendor/tgapipldc/data/account_proxy_map.csv；
    3. 按手机号合并 api_id/api_hash 与 yanzheng/profile/proxy 等来源信息；
    4. 转换为 WQTG 的 AccountConfig；
    5. 返回合并后的账号列表，由 RuntimeService/MainWindow 保存。

    说明：
    - 当前 AccountConfig 还没有扩展 tgapipldc 专属字段，所以本服务会先把 WQTG 可用的字段导入：
      account_name/api_id/api_hash/phone/session_name/enabled。
    - tgapipldc 专属信息会保留在 TgapipldcImportedAccount 中。
    - 等后续扩展 AccountConfig 后，这个文件再升级为完整持久化 profile_dir/yanzheng/proxy。
    """

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()

    def import_accounts(
        self,
        existing_accounts: Iterable[AccountConfig],
        enabled: bool = True,
    ) -> TgapipldcImportResult:
        imported_rows = self.load_imported_accounts()

        existing_list = list(existing_accounts or [])
        output_accounts = list(existing_list)

        existing_by_phone = {
            self._normalize_phone_key(getattr(account, "phone", "")): index
            for index, account in enumerate(output_accounts)
            if self._normalize_phone_key(getattr(account, "phone", ""))
        }
        existing_by_name = {
            str(getattr(account, "account_name", "") or "").strip(): index
            for index, account in enumerate(output_accounts)
            if str(getattr(account, "account_name", "") or "").strip()
        }

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for row in imported_rows:
            if not row.phone or not row.api_id or not row.api_hash:
                skipped_count += 1
                continue

            account = self._to_account_config(row, enabled=enabled)

            phone_key = self._normalize_phone_key(account.phone)
            existing_index = existing_by_phone.get(phone_key)

            if existing_index is None:
                existing_index = existing_by_name.get(account.account_name)

            if existing_index is None:
                output_accounts.append(account)
                new_index = len(output_accounts) - 1
                existing_by_phone[phone_key] = new_index
                existing_by_name[account.account_name] = new_index
                created_count += 1
                continue

            output_accounts[existing_index] = account
            existing_by_phone[phone_key] = existing_index
            existing_by_name[account.account_name] = existing_index
            updated_count += 1

        return TgapipldcImportResult(
            imported_rows=imported_rows,
            accounts=output_accounts,
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            api_csv_path=self.workspace.api_csv_path,
            account_proxy_map_path=self.workspace.account_proxy_map_csv_path,
        )

    def load_imported_accounts(self) -> list[TgapipldcImportedAccount]:
        api_rows = self._read_api_csv()
        map_rows = self._read_account_proxy_map_csv()
        map_index = self._build_phone_index(map_rows)

        imported_rows: list[TgapipldcImportedAccount] = []

        for api_row in api_rows:
            phone = self._clean(api_row.get("phone"))
            api_id = self._parse_api_id(api_row.get("api_id"))
            api_hash = self._clean(api_row.get("api_hash"))

            if not phone or not api_id or not api_hash:
                continue

            match_row = self._find_matching_phone_row(phone, map_index) or {}
            merged_phone = (
                self._clean(match_row.get("phone"))
                or self._clean(match_row.get("telegram_phone"))
                or phone
            )

            account_name = self._build_account_name(merged_phone)
            session_name = account_name

            imported_rows.append(
                TgapipldcImportedAccount(
                    phone=merged_phone,
                    api_id=api_id,
                    api_hash=api_hash,
                    account_name=account_name,
                    session_name=session_name,
                    country=self._clean(match_row.get("country")),
                    country_code=self._clean(match_row.get("country_code")),
                    national_number=self._clean(match_row.get("national_number")),
                    telegram_phone=self._clean(match_row.get("telegram_phone")),
                    phone_for_web=self._clean(match_row.get("phone_for_web")),
                    profile_dir=self._clean(match_row.get("profile_dir")),
                    yanzheng=self._clean(match_row.get("yanzheng")),
                    raw_proxy=self._clean(match_row.get("raw_proxy")),
                    masked_proxy=self._clean(match_row.get("masked_proxy")),
                    exit_ip=self._clean(match_row.get("exit_ip")),
                    source_status=self._clean(match_row.get("status")),
                    source_note=self._clean(match_row.get("note")),
                )
            )

        if not imported_rows:
            raise ValueError("api.csv 里没有可导入的账号")

        return imported_rows

    def _read_api_csv(self) -> list[dict[str, str]]:
        path = self.workspace.api_csv_path

        if not path.exists():
            raise FileNotFoundError(f"找不到 API CSV：{path}")

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            current_fields = set(reader.fieldnames or [])
            missing_fields = API_CSV_REQUIRED_FIELDS - current_fields

            if missing_fields:
                raise ValueError(f"api.csv 缺少字段：{missing_fields}")

            return [dict(row) for row in reader]

    def _read_account_proxy_map_csv(self) -> list[dict[str, str]]:
        path = self.workspace.account_proxy_map_csv_path

        if not path.exists():
            return []

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            current_fields = set(reader.fieldnames or [])

            if not current_fields:
                return []

            missing_fields = ACCOUNT_PROXY_MAP_MIN_FIELDS - current_fields
            if missing_fields:
                raise ValueError(f"account_proxy_map.csv 缺少字段：{missing_fields}")

            return [dict(row) for row in reader]

    def _to_account_config(
        self,
        row: TgapipldcImportedAccount,
        enabled: bool,
    ) -> AccountConfig:
        return AccountConfig(
            account_name=row.account_name,
            api_id=row.api_id,
            api_hash=row.api_hash,
            phone=row.phone,
            session_name=row.session_name,
            enabled=enabled,
        )

    def _build_phone_index(
        self,
        rows: list[dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        index: dict[str, dict[str, str]] = {}

        for row in rows:
            for key in self._phone_match_keys(row):
                index.setdefault(key, row)

        return index

    def _find_matching_phone_row(
        self,
        phone: str,
        index: dict[str, dict[str, str]],
    ) -> dict[str, str] | None:
        keys = self._phone_match_keys({"phone": phone})

        for key in keys:
            if key in index:
                return index[key]

        return None

    def _phone_match_keys(self, row: dict[str, str]) -> set[str]:
        keys: set[str] = set()

        for field_name in (
            "phone",
            "telegram_phone",
            "phone_for_web",
            "national_number",
        ):
            value = self._clean(row.get(field_name))
            self._add_phone_keys(keys, value)

        country_code = self._only_digits(self._clean(row.get("country_code")))
        national_number = self._only_digits(self._clean(row.get("national_number")))

        if country_code and national_number:
            self._add_phone_keys(keys, f"+{country_code}{national_number}")
            self._add_phone_keys(keys, f"{country_code}{national_number}")

        return keys

    def _add_phone_keys(self, keys: set[str], value: str) -> None:
        text = self._clean(value)
        digits = self._only_digits(text)

        if text:
            keys.add(text)
        if digits:
            keys.add(digits)
            keys.add(f"+{digits}")

    def _build_account_name(self, phone: str) -> str:
        digits = self._only_digits(phone)

        if digits:
            return f"tg_{digits}"

        safe_text = re.sub(r"[^A-Za-z0-9_]+", "_", self._clean(phone)).strip("_")
        if safe_text:
            return f"tg_{safe_text}"

        raise ValueError("无法根据手机号生成账号名称")

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _only_digits(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _normalize_phone_key(self, value: object) -> str:
        digits = self._only_digits(self._clean(value))
        return f"+{digits}" if digits else ""

    def _parse_api_id(self, value: object) -> int:
        raw_text = self._clean(value)

        if not raw_text:
            return 0

        try:
            number = int(raw_text)
        except ValueError:
            raise ValueError(f"api_id 不是数字：{raw_text}") from None

        if number <= 0:
            raise ValueError(f"api_id 必须大于 0：{raw_text}")

        return number

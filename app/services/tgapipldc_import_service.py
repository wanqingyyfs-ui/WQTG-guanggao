from __future__ import annotations

import csv
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.core.models import AccountConfig
from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


API_CSV_REQUIRED_FIELDS = {"phone", "api_id", "api_hash"}
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
    """Import from api.csv plus durable per-account API records."""

    def __init__(self, workspace_service: TgapipldcWorkspaceService | None = None):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()

    def import_accounts(
        self,
        existing_accounts: Iterable[AccountConfig],
        enabled: bool = True,
    ) -> TgapipldcImportResult:
        imported_rows = self.load_imported_accounts()
        output_accounts = list(existing_accounts or [])
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
            else:
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
        api_rows = self._read_all_api_rows()
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
            imported_rows.append(
                TgapipldcImportedAccount(
                    phone=merged_phone,
                    api_id=api_id,
                    api_hash=api_hash,
                    account_name=account_name,
                    session_name=account_name,
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
            raise ValueError("api.csv 和 api_records 里都没有可导入的账号")
        return imported_rows

    def _read_all_api_rows(self) -> list[dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        for row in self._read_api_csv_if_available():
            key = self._normalize_phone_key(row.get("phone"))
            if key:
                merged[key] = row
        for row in self._read_api_record_files():
            key = self._normalize_phone_key(row.get("phone"))
            if key:
                merged[key] = row
        rows = list(merged.values())
        if rows:
            self._rewrite_api_summary_best_effort(rows)
        return rows

    def _read_api_csv_if_available(self) -> list[dict[str, str]]:
        path = self.workspace.api_csv_path
        if not path.exists() or path.stat().st_size <= 0:
            return []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if API_CSV_REQUIRED_FIELDS - set(reader.fieldnames or []):
                    return []
                return [
                    {
                        "phone": self._clean(row.get("phone")),
                        "api_id": self._clean(row.get("api_id")),
                        "api_hash": self._clean(row.get("api_hash")),
                    }
                    for row in reader
                    if self._clean(row.get("phone"))
                ]
        except (PermissionError, OSError):
            return []

    def _read_api_record_files(self) -> list[dict[str, str]]:
        record_dir = self.workspace.api_records_dir
        record_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, str]] = []
        for path in sorted(record_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            phone = self._clean(data.get("phone"))
            api_id = self._clean(data.get("api_id"))
            api_hash = self._clean(data.get("api_hash"))
            if phone and api_id and api_hash:
                rows.append({"phone": phone, "api_id": api_id, "api_hash": api_hash})
        return rows

    def _rewrite_api_summary_best_effort(self, rows: list[dict[str, str]]) -> None:
        path = self.workspace.api_csv_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["phone", "api_id", "api_hash"])
                writer.writeheader()
                writer.writerows(rows)
                file.flush()
                os.fsync(file.fileno())
            temp_path.replace(path)
        except (PermissionError, OSError):
            pass
        finally:
            temp_path.unlink(missing_ok=True)

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

    def _to_account_config(self, row: TgapipldcImportedAccount, enabled: bool) -> AccountConfig:
        return AccountConfig(
            account_name=row.account_name,
            api_id=row.api_id,
            api_hash=row.api_hash,
            phone=row.phone,
            session_name=row.session_name,
            enabled=enabled,
        )

    def _build_phone_index(self, rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
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
        for key in self._phone_match_keys({"phone": phone}):
            if key in index:
                return index[key]
        return None

    def _phone_match_keys(self, row: dict[str, str]) -> set[str]:
        keys: set[str] = set()
        for field_name in ("phone", "telegram_phone", "phone_for_web", "national_number"):
            self._add_phone_keys(keys, self._clean(row.get(field_name)))
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

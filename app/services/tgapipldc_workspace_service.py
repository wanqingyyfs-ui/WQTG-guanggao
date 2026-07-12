from __future__ import annotations

import csv
import json
import os
import shutil
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Sequence


APP_NAME = "万青TG群发任务"
WORKSPACE_DIR_NAME = "tgapipldc"
WORKSPACE_MARKER_NAME = ".workspace_v2"

ACCOUNTS_CSV_HEADER = ["phone", "country", "profile_dir", "status", "yanzheng"]
PROXIES_CSV_HEADER = ["raw_proxy"]

PROFILE_MAINTENANCE_DEFAULT_CONFIG: dict[str, Any] = {
    "update_photo": True,
    "photo_mode": "random",
    "photo_library_dir": "assets/profile_photos",
    "update_name": True,
    "name_pool": [],
    "update_username": True,
    "username_keyword": "",
    "username_start_index": 1,
    "update_bio": True,
    "bio_text": "",
    "add_chat_folder": True,
    "chat_folder_link": "",
    "account_delay_ms": 3000,
    "stop_on_error": False,
}

PROFILE_MAINTENANCE_RESULT_HEADER = [
    "phone", "profile_dir", "masked_proxy", "action", "photo_status",
    "name_status", "username_status", "bio_status", "folder_status",
    "final_status", "note", "updated_at",
]
PROFILE_MAINTENANCE_FAILED_HEADER = [
    "phone", "profile_dir", "masked_proxy", "action", "failed_steps",
    "unfinished_steps", "error_message", "updated_at",
]
PROFILE_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class CsvOverwriteResult:
    path: Path
    header: list[str]
    row_count: int


@dataclass(frozen=True)
class ProfilePhotoCopyResult:
    library_dir: Path
    copied_paths: list[Path]
    skipped_paths: list[Path]

    @property
    def copied_count(self) -> int:
        return len(self.copied_paths)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def get_local_appdata_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser()
    return Path.home() / "AppData" / "Local"


def get_bundled_workspace_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor" / WORKSPACE_DIR_NAME


class TgapipldcWorkspaceService:
    """Keep packaged scripts read-only and all mutable data in LocalAppData."""

    def __init__(self, workspace_dir: str | Path | None = None):
        self.template_workspace_dir = get_bundled_workspace_dir().resolve()
        if workspace_dir is None:
            workspace_dir = get_local_appdata_dir() / APP_NAME / WORKSPACE_DIR_NAME

        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.workspace_marker_path = self.workspace_dir / WORKSPACE_MARKER_NAME
        self.src_dir = self.workspace_dir / "src"
        self.data_dir = self.workspace_dir / "data"
        self.csv_dir = self.workspace_dir / "csv"
        self.api_records_dir = self.csv_dir / "api_records"
        self.logs_dir = self.workspace_dir / "logs"
        self.profiles_dir = self.workspace_dir / "profiles"
        self.assets_dir = self.workspace_dir / "assets"
        self.profile_photos_dir = self.assets_dir / "profile_photos"

        self.accounts_csv_path = self.data_dir / "accounts.csv"
        self.proxies_csv_path = self.data_dir / "proxies.csv"
        self.proxy_test_results_csv_path = self.data_dir / "proxy_test_results.csv"
        self.usable_proxies_csv_path = self.data_dir / "usable_proxies.csv"
        self.account_proxy_map_csv_path = self.data_dir / "account_proxy_map.csv"
        self.telegram_login_status_csv_path = self.data_dir / "telegram_login_status.csv"
        self.profile_maintenance_config_path = self.data_dir / "profile_maintenance_config.json"
        self.profile_maintenance_results_csv_path = self.data_dir / "profile_maintenance_results.csv"
        self.profile_maintenance_failed_csv_path = self.data_dir / "profile_maintenance_failed.csv"
        self.api_csv_path = self.csv_dir / "api.csv"
        self.failure_csv_path = self.csv_dir / "失败.csv"

    def ensure_structure(self) -> None:
        for directory in (
            self.workspace_dir,
            self.src_dir,
            self.data_dir,
            self.csv_dir,
            self.api_records_dir,
            self.logs_dir,
            self.profiles_dir,
            self.assets_dir,
            self.profile_photos_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._sync_runtime_sources()
        self._migrate_legacy_workspace_once()
        self._ensure_csv_exists(self.accounts_csv_path, ACCOUNTS_CSV_HEADER)
        self._ensure_csv_exists(self.proxies_csv_path, PROXIES_CSV_HEADER)
        self._ensure_profile_maintenance_config_exists()

    def _sync_runtime_sources(self) -> None:
        source_dir = self.template_workspace_dir / "src"
        if not source_dir.exists() or source_dir.resolve() == self.src_dir.resolve():
            return
        for source_path in source_dir.rglob("*"):
            if not source_path.is_file():
                continue
            destination = self.src_dir / source_path.relative_to(source_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)

    def _migrate_legacy_workspace_once(self) -> None:
        if self.workspace_marker_path.exists():
            return
        source_root = self.template_workspace_dir
        if source_root.exists() and source_root.resolve() != self.workspace_dir.resolve():
            for directory_name in ("data", "csv", "profiles", "assets"):
                self._copy_tree_missing(source_root / directory_name, self.workspace_dir / directory_name)
        self.workspace_marker_path.write_text("writable workspace initialized\n", encoding="utf-8")

    @staticmethod
    def _copy_tree_missing(source_dir: Path, destination_dir: Path) -> None:
        if not source_dir.exists() or not source_dir.is_dir():
            return
        for source_path in source_dir.rglob("*"):
            destination = destination_dir / source_path.relative_to(source_dir)
            if source_path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)

    def overwrite_accounts_csv_data(self, raw_text: str) -> CsvOverwriteResult:
        self.ensure_structure()
        header = self._require_exact_header(self.accounts_csv_path, ACCOUNTS_CSV_HEADER)
        rows = self._parse_accounts_input(raw_text)
        self._rewrite_csv_with_header_and_rows(self.accounts_csv_path, header, rows)
        return CsvOverwriteResult(self.accounts_csv_path, header, len(rows))

    def overwrite_proxies_csv_data(self, raw_text: str) -> CsvOverwriteResult:
        self.ensure_structure()
        header = self._require_exact_header(self.proxies_csv_path, PROXIES_CSV_HEADER)
        rows = self._parse_proxies_input(raw_text)
        self._rewrite_csv_with_header_and_rows(self.proxies_csv_path, header, rows)
        return CsvOverwriteResult(self.proxies_csv_path, header, len(rows))

    def read_accounts_csv_text(self) -> str:
        self.ensure_structure()
        return self._read_text(self.accounts_csv_path)

    def read_proxies_csv_text(self) -> str:
        self.ensure_structure()
        return self._read_text(self.proxies_csv_path)

    def read_api_csv_text(self) -> str:
        self.ensure_structure()
        return self._read_text(self.api_csv_path)

    def read_account_proxy_map_csv_text(self) -> str:
        self.ensure_structure()
        return self._read_text(self.account_proxy_map_csv_path)

    def read_profile_maintenance_config(self) -> dict[str, Any]:
        self.ensure_structure()
        try:
            raw_data = json.loads(self.profile_maintenance_config_path.read_text(encoding="utf-8"))
        except Exception:
            raw_data = {}
        return self._normalize_profile_maintenance_config(raw_data)

    def save_profile_maintenance_config(self, config: dict[str, Any]) -> dict[str, Any]:
        self.ensure_structure()
        normalized = self._normalize_profile_maintenance_config(config)
        self._atomic_write_text(
            self.profile_maintenance_config_path,
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def copy_profile_photo_files(self, source_paths: Sequence[str | Path]) -> ProfilePhotoCopyResult:
        self.ensure_structure()
        copied_paths: list[Path] = []
        skipped_paths: list[Path] = []
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        serial = 1
        for raw_path in source_paths:
            source_path = Path(raw_path).expanduser()
            if not source_path.exists() or not source_path.is_file():
                skipped_paths.append(source_path)
                continue
            suffix = source_path.suffix.lower()
            if suffix not in PROFILE_PHOTO_EXTENSIONS:
                skipped_paths.append(source_path)
                continue
            while True:
                target_path = self.profile_photos_dir / f"photo_{timestamp}_{serial:06d}{suffix}"
                serial += 1
                if not target_path.exists():
                    break
            shutil.copy2(source_path, target_path)
            copied_paths.append(target_path)
        return ProfilePhotoCopyResult(self.profile_photos_dir, copied_paths, skipped_paths)

    def clear_profile_maintenance_results(self) -> None:
        self.ensure_structure()
        for file_path in (
            self.profile_maintenance_results_csv_path,
            self.profile_maintenance_failed_csv_path,
        ):
            try:
                file_path.unlink(missing_ok=True)
            except PermissionError as exc:
                raise PermissionError(f"文件正在被占用，无法清空：{file_path}") from exc

    @staticmethod
    def _read_text(file_path: Path) -> str:
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8-sig")

    @staticmethod
    def _normalize_header(header: Iterable[str]) -> list[str]:
        return [str(item or "").strip() for item in header]

    @staticmethod
    def _is_same_header(left: Iterable[str], right: Iterable[str]) -> bool:
        return [str(item or "").strip().lower() for item in left] == [
            str(item or "").strip().lower() for item in right
        ]

    def _ensure_csv_exists(self, file_path: Path, default_header: list[str]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and file_path.stat().st_size > 0:
            return
        self._rewrite_csv_with_header_and_rows(file_path, list(default_header), [])

    def _ensure_profile_maintenance_config_exists(self) -> None:
        self.profile_maintenance_config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.profile_maintenance_config_path.exists() and self.profile_maintenance_config_path.stat().st_size > 0:
            return
        self._atomic_write_text(
            self.profile_maintenance_config_path,
            json.dumps(PROFILE_MAINTENANCE_DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_existing_header_or_default(self, file_path: Path, default_header: list[str]) -> list[str]:
        self._ensure_csv_exists(file_path, default_header)
        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            header = next(csv.reader(file), [])
        header = self._normalize_header(header)
        if not header:
            header = list(default_header)
            self._rewrite_csv_with_header_and_rows(file_path, header, [])
        return header

    def _require_exact_header(self, file_path: Path, expected_header: list[str]) -> list[str]:
        header = self._read_existing_header_or_default(file_path, expected_header)
        if not self._is_same_header(header, expected_header):
            raise ValueError(
                f"{file_path.name} 第一行表头必须是：{','.join(expected_header)}；"
                f"当前表头是：{','.join(header)}"
            )
        return header

    def _parse_accounts_input(self, raw_text: str) -> list[list[str]]:
        rows = self._parse_raw_csv_text(raw_text)
        result: list[list[str]] = []
        for row_index, row in enumerate(rows, start=1):
            normalized_row = [str(item or "").strip() for item in row]
            if row_index == 1 and self._is_same_header(normalized_row, ACCOUNTS_CSV_HEADER):
                continue
            if len(normalized_row) != len(ACCOUNTS_CSV_HEADER):
                raise ValueError(
                    "accounts.csv 数据格式错误："
                    f"第 {row_index} 行必须是 {len(ACCOUNTS_CSV_HEADER)} 列，"
                    f"当前是 {len(normalized_row)} 列。"
                    "正确格式：phone,country,profile_dir,status,yanzheng"
                )
            phone, country, profile_dir, status, yanzheng = normalized_row
            if not phone:
                raise ValueError(f"accounts.csv 第 {row_index} 行手机号为空")
            if not country:
                raise ValueError(f"accounts.csv 第 {row_index} 行国家为空")
            if not profile_dir:
                raise ValueError(f"accounts.csv 第 {row_index} 行 profile_dir 为空")
            if not status:
                status = "pending"
            if not yanzheng:
                raise ValueError(f"accounts.csv 第 {row_index} 行 yanzheng 为空")
            result.append([phone, country, profile_dir, status, yanzheng])
        return result

    def _parse_proxies_input(self, raw_text: str) -> list[list[str]]:
        rows = self._parse_raw_csv_text(raw_text)
        result: list[list[str]] = []
        for row_index, row in enumerate(rows, start=1):
            normalized_row = [str(item or "").strip() for item in row]
            if row_index == 1 and self._is_same_header(normalized_row, PROXIES_CSV_HEADER):
                continue
            if len(normalized_row) != 1:
                raise ValueError(
                    "动态代理数据格式错误："
                    f"第 {row_index} 行必须是 1 列 raw_proxy，当前是 {len(normalized_row)} 列"
                )
            raw_proxy = normalized_row[0]
            if not raw_proxy:
                raise ValueError(f"动态代理第 {row_index} 行代理为空")
            if "@" not in raw_proxy or ":" not in raw_proxy:
                raise ValueError(f"动态代理第 {row_index} 行代理格式错误：{raw_proxy}")
            result.append([raw_proxy])
        if len(result) > 1:
            raise ValueError("当前动态轮换代理模式只允许保存一条 raw_proxy，请删除多余代理")
        return result

    @staticmethod
    def _parse_raw_csv_text(raw_text: str) -> list[list[str]]:
        safe_text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not safe_text.strip():
            return []
        rows: list[list[str]] = []
        for row in csv.reader(StringIO(safe_text)):
            normalized_row = [str(item or "").strip() for item in row]
            if any(normalized_row):
                rows.append(normalized_row)
        return rows

    @classmethod
    def _rewrite_csv_with_header_and_rows(
        cls,
        file_path: Path,
        header: list[str],
        rows: list[list[str]],
    ) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_name(f".{file_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(header)
                writer.writerows(rows)
                file.flush()
                os.fsync(file.fileno())
            temp_path.replace(file_path)
        except PermissionError as exc:
            raise PermissionError(f"文件正在被 WPS/Excel 或其他程序占用：{file_path}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_text(file_path: Path, text: str, encoding: str = "utf-8") -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_name(f".{file_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temp_path.write_text(text, encoding=encoding)
            temp_path.replace(file_path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _normalize_profile_maintenance_config(config: dict[str, Any] | None) -> dict[str, Any]:
        normalized = dict(PROFILE_MAINTENANCE_DEFAULT_CONFIG)
        normalized.update(dict(config or {}))
        normalized["update_photo"] = bool(normalized.get("update_photo"))
        normalized["photo_mode"] = str(normalized.get("photo_mode") or "random").strip() or "random"
        if normalized["photo_mode"] not in {"random", "sequential", "unique_random"}:
            normalized["photo_mode"] = "random"
        normalized["photo_library_dir"] = str(
            normalized.get("photo_library_dir") or "assets/profile_photos"
        ).strip() or "assets/profile_photos"
        normalized["update_name"] = bool(normalized.get("update_name"))
        name_pool = normalized.get("name_pool") or []
        if isinstance(name_pool, str):
            name_pool = [
                line.strip()
                for line in name_pool.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                if line.strip()
            ]
        elif isinstance(name_pool, Sequence):
            name_pool = [str(item or "").strip() for item in name_pool if str(item or "").strip()]
        else:
            name_pool = []
        normalized["name_pool"] = name_pool
        normalized["update_username"] = bool(normalized.get("update_username"))
        normalized["username_keyword"] = str(normalized.get("username_keyword") or "").strip()
        try:
            normalized["username_start_index"] = max(1, int(normalized.get("username_start_index") or 1))
        except Exception:
            normalized["username_start_index"] = 1
        normalized["update_bio"] = bool(normalized.get("update_bio"))
        normalized["bio_text"] = str(normalized.get("bio_text") or "")
        normalized["add_chat_folder"] = bool(normalized.get("add_chat_folder"))
        normalized["chat_folder_link"] = str(normalized.get("chat_folder_link") or "").strip()
        try:
            normalized["account_delay_ms"] = max(0, int(normalized.get("account_delay_ms") or 3000))
        except Exception:
            normalized["account_delay_ms"] = 3000
        normalized["stop_on_error"] = bool(normalized.get("stop_on_error"))
        return normalized

from __future__ import annotations

import csv
import json
import shutil
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Sequence


ACCOUNTS_CSV_HEADER = [
    "phone",
    "country",
    "profile_dir",
    "status",
    "yanzheng",
]

PROXIES_CSV_HEADER = [
    "raw_proxy",
]

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
    "phone",
    "profile_dir",
    "masked_proxy",
    "action",
    "photo_status",
    "name_status",
    "username_status",
    "bio_status",
    "folder_status",
    "final_status",
    "note",
    "updated_at",
]

PROFILE_MAINTENANCE_FAILED_HEADER = [
    "phone",
    "profile_dir",
    "masked_proxy",
    "action",
    "failed_steps",
    "unfinished_steps",
    "error_message",
    "updated_at",
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


class TgapipldcWorkspaceService:
    """
    WQTG 内置 tgapipldc 工作目录服务。

    当前文件只负责：
    1. 定位 app/vendor/tgapipldc 工作目录；
    2. 确保 src/data/csv/logs/profiles/assets/profile_photos 目录存在；
    3. 管理常用 CSV / JSON 路径；
    4. 按“保留第一行表头，清空第二行开始旧数据，再写入新数据”的规则覆盖 accounts.csv / proxies.csv；
    5. 管理账号资料维护配置、图片库、结果 CSV。

    注意：
    - 这里不调用 Playwright；
    - 这里不调用 tgapipldc 原脚本；
    - 这里不依赖 PySide6；
    - GUI 面板按钮通过 RuntimeService / RunnerService 调用本服务即可。
    """

    def __init__(self, workspace_dir: str | Path | None = None):
        if workspace_dir is None:
            app_dir = Path(__file__).resolve().parents[1]
            workspace_dir = app_dir / "vendor" / "tgapipldc"

        self.workspace_dir = Path(workspace_dir).expanduser().resolve()

        self.src_dir = self.workspace_dir / "src"
        self.data_dir = self.workspace_dir / "data"
        self.csv_dir = self.workspace_dir / "csv"
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
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.profile_photos_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_csv_exists(
            file_path=self.accounts_csv_path,
            default_header=ACCOUNTS_CSV_HEADER,
        )
        self._ensure_csv_exists(
            file_path=self.proxies_csv_path,
            default_header=PROXIES_CSV_HEADER,
        )
        self._ensure_profile_maintenance_config_exists()

    def overwrite_accounts_csv_data(self, raw_text: str) -> CsvOverwriteResult:
        """
        覆盖 accounts.csv 的数据行。

        面板输入格式固定为每行 5 列：

        phone,country,profile_dir,status,yanzheng

        示例：

        14255871436,US,profiles/14255871436,pending,https://accac.cc/xxx/GetHTML

        覆盖规则：
        - 保留 accounts.csv 第一行表头；
        - 删除第二行开始的所有旧数据；
        - 将 raw_text 中的新数据写入第二行开始；
        - 如果 raw_text 第一行本身是表头，会自动跳过。
        """
        self.ensure_structure()
        header = self._require_exact_header(
            file_path=self.accounts_csv_path,
            expected_header=ACCOUNTS_CSV_HEADER,
        )
        rows = self._parse_accounts_input(raw_text)
        self._rewrite_csv_with_header_and_rows(
            file_path=self.accounts_csv_path,
            header=header,
            rows=rows,
        )
        return CsvOverwriteResult(
            path=self.accounts_csv_path,
            header=header,
            row_count=len(rows),
        )

    def overwrite_proxies_csv_data(self, raw_text: str) -> CsvOverwriteResult:
        """
        覆盖 proxies.csv 的数据行。

        面板输入格式固定为每行 1 列：

        raw_proxy

        示例：

        Qg8Ajet4-res-th-sid-843678599-sidtime-70:GlVF6XC@proxy.global.ip2up.com:12348

        覆盖规则：
        - 保留 proxies.csv 第一行表头；
        - 删除第二行开始的所有旧数据；
        - 将 raw_text 中的新代理写入第二行开始；
        - 如果 raw_text 第一行本身是表头，会自动跳过。
        """
        self.ensure_structure()
        header = self._require_exact_header(
            file_path=self.proxies_csv_path,
            expected_header=PROXIES_CSV_HEADER,
        )
        rows = self._parse_proxies_input(raw_text)
        self._rewrite_csv_with_header_and_rows(
            file_path=self.proxies_csv_path,
            header=header,
            rows=rows,
        )
        return CsvOverwriteResult(
            path=self.proxies_csv_path,
            header=header,
            row_count=len(rows),
        )

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
            raw_data = json.loads(
                self.profile_maintenance_config_path.read_text(encoding="utf-8")
            )
        except Exception:
            raw_data = {}
        return self._normalize_profile_maintenance_config(raw_data)

    def save_profile_maintenance_config(self, config: dict[str, Any]) -> dict[str, Any]:
        self.ensure_structure()
        normalized_config = self._normalize_profile_maintenance_config(config)
        self.profile_maintenance_config_path.write_text(
            json.dumps(normalized_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized_config

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

        return ProfilePhotoCopyResult(
            library_dir=self.profile_photos_dir,
            copied_paths=copied_paths,
            skipped_paths=skipped_paths,
        )

    def clear_profile_maintenance_results(self) -> None:
        self.ensure_structure()
        for file_path in (
            self.profile_maintenance_results_csv_path,
            self.profile_maintenance_failed_csv_path,
        ):
            try:
                if file_path.exists():
                    file_path.unlink()
            except FileNotFoundError:
                pass

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
        left_items = [str(item or "").strip().lower() for item in left]
        right_items = [str(item or "").strip().lower() for item in right]
        return left_items == right_items

    def _ensure_csv_exists(self, file_path: Path, default_header: list[str]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists() and file_path.stat().st_size > 0:
            return

        self._rewrite_csv_with_header_and_rows(
            file_path=file_path,
            header=list(default_header),
            rows=[],
        )

    def _ensure_profile_maintenance_config_exists(self) -> None:
        self.profile_maintenance_config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.profile_maintenance_config_path.exists() and self.profile_maintenance_config_path.stat().st_size > 0:
            return
        self.profile_maintenance_config_path.write_text(
            json.dumps(PROFILE_MAINTENANCE_DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_existing_header_or_default(
        self,
        file_path: Path,
        default_header: list[str],
    ) -> list[str]:
        self._ensure_csv_exists(file_path, default_header)

        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            try:
                header = next(reader)
            except StopIteration:
                header = []

        header = self._normalize_header(header)

        if not header:
            header = list(default_header)
            self._rewrite_csv_with_header_and_rows(
                file_path=file_path,
                header=header,
                rows=[],
            )

        return header

    def _require_exact_header(
        self,
        file_path: Path,
        expected_header: list[str],
    ) -> list[str]:
        header = self._read_existing_header_or_default(
            file_path=file_path,
            default_header=expected_header,
        )

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
                    "proxies.csv 数据格式错误："
                    f"第 {row_index} 行必须是 1 列 raw_proxy，"
                    f"当前是 {len(normalized_row)} 列"
                )

            raw_proxy = normalized_row[0]

            if not raw_proxy:
                raise ValueError(f"proxies.csv 第 {row_index} 行代理为空")

            if "@" not in raw_proxy:
                raise ValueError(f"proxies.csv 第 {row_index} 行代理格式错误，缺少 @：{raw_proxy}")

            if ":" not in raw_proxy:
                raise ValueError(f"proxies.csv 第 {row_index} 行代理格式错误，缺少冒号：{raw_proxy}")

            result.append([raw_proxy])

        return result

    @staticmethod
    def _parse_raw_csv_text(raw_text: str) -> list[list[str]]:
        safe_text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")

        if not safe_text.strip():
            return []

        reader = csv.reader(StringIO(safe_text))
        rows: list[list[str]] = []

        for row in reader:
            normalized_row = [str(item or "").strip() for item in row]

            if not any(normalized_row):
                continue

            rows.append(normalized_row)

        return rows

    @staticmethod
    def _rewrite_csv_with_header_and_rows(
        file_path: Path,
        header: list[str],
        rows: list[list[str]],
    ) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(rows)

        temp_path.replace(file_path)

    @staticmethod
    def _normalize_profile_maintenance_config(config: dict[str, Any] | None) -> dict[str, Any]:
        raw_config = dict(config or {})
        normalized = dict(PROFILE_MAINTENANCE_DEFAULT_CONFIG)
        normalized.update(raw_config)

        normalized["update_photo"] = bool(normalized.get("update_photo"))
        normalized["photo_mode"] = str(normalized.get("photo_mode") or "random").strip() or "random"
        if normalized["photo_mode"] not in {"random", "sequential", "unique_random"}:
            normalized["photo_mode"] = "random"
        normalized["photo_library_dir"] = str(normalized.get("photo_library_dir") or "assets/profile_photos").strip() or "assets/profile_photos"

        normalized["update_name"] = bool(normalized.get("update_name"))
        name_pool = normalized.get("name_pool") or []
        if isinstance(name_pool, str):
            name_pool = [line.strip() for line in name_pool.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
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

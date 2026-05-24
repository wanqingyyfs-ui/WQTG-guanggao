from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable


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


@dataclass(frozen=True)
class CsvOverwriteResult:
    path: Path
    header: list[str]
    row_count: int


class TgapipldcWorkspaceService:
    """
    WQTG 内置 tgapipldc 工作目录服务。

    当前文件只负责：
    1. 定位 app/vendor/tgapipldc 工作目录；
    2. 确保 src/data/csv/logs/profiles 目录存在；
    3. 管理常用 CSV 路径；
    4. 按“保留第一行表头，清空第二行开始旧数据，再写入新数据”的规则覆盖 accounts.csv / proxies.csv。

    注意：
    - 这里不调用 Playwright；
    - 这里不调用 tgapipldc 原脚本；
    - 这里不依赖 PySide6；
    - 后续 GUI 面板按钮直接调用本服务即可。
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

        self.accounts_csv_path = self.data_dir / "accounts.csv"
        self.proxies_csv_path = self.data_dir / "proxies.csv"
        self.proxy_test_results_csv_path = self.data_dir / "proxy_test_results.csv"
        self.usable_proxies_csv_path = self.data_dir / "usable_proxies.csv"
        self.account_proxy_map_csv_path = self.data_dir / "account_proxy_map.csv"
        self.telegram_login_status_csv_path = self.data_dir / "telegram_login_status.csv"

        self.api_csv_path = self.csv_dir / "api.csv"
        self.failure_csv_path = self.csv_dir / "失败.csv"

    def ensure_structure(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_csv_exists(
            file_path=self.accounts_csv_path,
            default_header=ACCOUNTS_CSV_HEADER,
        )
        self._ensure_csv_exists(
            file_path=self.proxies_csv_path,
            default_header=PROXIES_CSV_HEADER,
        )

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

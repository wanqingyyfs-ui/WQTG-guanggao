from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import requests

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


IP_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]

PROXY_TEST_RESULT_HEADER = [
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
    "duplicate",
    "status",
    "note",
]

USABLE_PROXIES_HEADER = [
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
    "assigned_phone",
    "status",
    "note",
]


@dataclass(frozen=True)
class ParsedProxy:
    raw_proxy: str
    username: str
    password: str
    host: str
    port: int

    @property
    def requests_proxy_url(self) -> str:
        return f"http://{self.username}:{self.password}@{self.host}:{self.port}"

    @property
    def requests_proxies(self) -> dict[str, str]:
        proxy_url = self.requests_proxy_url
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    @property
    def playwright_proxy(self) -> dict[str, str]:
        return {
            "server": f"http://{self.host}:{self.port}",
            "username": self.username,
            "password": self.password,
        }

    @property
    def masked_raw_proxy(self) -> str:
        return f"{self.username}:******@{self.host}:{self.port}"


@dataclass(frozen=True)
class ProxyCheckResult:
    ok: bool
    exit_ip: str
    error: str


@dataclass(frozen=True)
class ProxyTestRow:
    raw_proxy: str
    masked_proxy: str
    exit_ip: str
    duplicate: str
    status: str
    note: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "raw_proxy": self.raw_proxy,
            "masked_proxy": self.masked_proxy,
            "exit_ip": self.exit_ip,
            "duplicate": self.duplicate,
            "status": self.status,
            "note": self.note,
        }


@dataclass(frozen=True)
class UsableProxyRow:
    raw_proxy: str
    masked_proxy: str
    exit_ip: str
    assigned_phone: str = ""
    status: str = "unused"
    note: str = ""

    def to_csv_row(self) -> dict[str, str]:
        return {
            "raw_proxy": self.raw_proxy,
            "masked_proxy": self.masked_proxy,
            "exit_ip": self.exit_ip,
            "assigned_phone": self.assigned_phone,
            "status": self.status,
            "note": self.note,
        }


@dataclass(frozen=True)
class ProxyTestSummary:
    total: int
    ok_count: int
    duplicate_ip_count: int
    bad_count: int
    parse_failed_count: int
    result_path: Path


@dataclass(frozen=True)
class ProxyPoolSummary:
    usable_count: int
    source_path: Path
    output_path: Path


ProgressCallback = Callable[[str], None]


class TgapipldcProxyService:
    """
    tgapipldc 代理检测服务。

    对应原 tgapipldc 命令：
    - python src\test_proxies.py
    - python src\build_proxy_pool.py

    当前服务只负责：
    1. 读取 data/proxies.csv；
    2. 检测代理出口 IP；
    3. 生成 data/proxy_test_results.csv；
    4. 从检测结果生成 data/usable_proxies.csv。

    不负责：
    - GUI；
    - 账号绑定；
    - Playwright 浏览器；
    - Telegram 登录。
    """

    def __init__(
        self,
        workspace_service: TgapipldcWorkspaceService | None = None,
        request_timeout_seconds: int = 20,
        per_proxy_sleep_seconds: float = 1.0,
    ):
        self.workspace_service = workspace_service or TgapipldcWorkspaceService()
        self.request_timeout_seconds = int(request_timeout_seconds)
        self.per_proxy_sleep_seconds = float(per_proxy_sleep_seconds)

    def read_raw_proxies(self) -> list[str]:
        self.workspace_service.ensure_structure()
        file_path = self.workspace_service.proxies_csv_path

        if not file_path.exists():
            raise FileNotFoundError(f"找不到代理文件：{file_path}")

        raw_proxies: list[str] = []

        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = list(reader.fieldnames or [])

            if "raw_proxy" not in fieldnames:
                raise ValueError("data\\proxies.csv 第一行必须是：raw_proxy")

            for row in reader:
                raw_proxy = str(row.get("raw_proxy") or "").strip()
                if raw_proxy:
                    raw_proxies.append(raw_proxy)

        if not raw_proxies:
            raise ValueError("data\\proxies.csv 里没有代理")

        return raw_proxies

    def test_proxies(self, progress_callback: ProgressCallback | None = None) -> ProxyTestSummary:
        raw_proxies = self.read_raw_proxies()
        results: list[ProxyTestRow] = []
        seen_ips: set[str] = set()

        self._emit(progress_callback, f"读取到 {len(raw_proxies)} 条代理")

        for index, raw_proxy in enumerate(raw_proxies, start=1):
            self._emit(progress_callback, f"[{index}/{len(raw_proxies)}] 开始检测代理")

            try:
                parsed_proxy = self.parse_raw_proxy(raw_proxy)
                check_result = self.check_exit_ip(parsed_proxy)

                if check_result.ok:
                    duplicate = "yes" if check_result.exit_ip in seen_ips else "no"
                    seen_ips.add(check_result.exit_ip)

                    status = "ok" if duplicate == "no" else "duplicate_ip"

                    self._emit(progress_callback, f"代理：{parsed_proxy.masked_raw_proxy}")
                    self._emit(progress_callback, f"出口 IP：{check_result.exit_ip}")
                    self._emit(progress_callback, f"是否重复：{duplicate}")
                    self._emit(progress_callback, f"状态：{status}")

                    results.append(
                        ProxyTestRow(
                            raw_proxy=raw_proxy,
                            masked_proxy=parsed_proxy.masked_raw_proxy,
                            exit_ip=check_result.exit_ip,
                            duplicate=duplicate,
                            status=status,
                            note="",
                        )
                    )
                else:
                    self._emit(progress_callback, f"代理：{parsed_proxy.masked_raw_proxy}")
                    self._emit(progress_callback, "状态：bad")
                    self._emit(progress_callback, f"错误：{check_result.error}")

                    results.append(
                        ProxyTestRow(
                            raw_proxy=raw_proxy,
                            masked_proxy=parsed_proxy.masked_raw_proxy,
                            exit_ip="",
                            duplicate="",
                            status="bad",
                            note=check_result.error,
                        )
                    )

            except Exception as exc:
                self._emit(progress_callback, "状态：parse_failed")
                self._emit(progress_callback, f"错误：{exc}")

                results.append(
                    ProxyTestRow(
                        raw_proxy=raw_proxy,
                        masked_proxy="",
                        exit_ip="",
                        duplicate="",
                        status="parse_failed",
                        note=str(exc),
                    )
                )

            if self.per_proxy_sleep_seconds > 0 and index < len(raw_proxies):
                time.sleep(self.per_proxy_sleep_seconds)

        result_path = self.workspace_service.proxy_test_results_csv_path
        self._write_proxy_test_results(result_path, results)

        ok_count = sum(1 for item in results if item.status == "ok")
        duplicate_ip_count = sum(1 for item in results if item.status == "duplicate_ip")
        bad_count = sum(1 for item in results if item.status == "bad")
        parse_failed_count = sum(1 for item in results if item.status == "parse_failed")

        self._emit(progress_callback, f"检测完成，结果已保存到：{result_path}")

        return ProxyTestSummary(
            total=len(results),
            ok_count=ok_count,
            duplicate_ip_count=duplicate_ip_count,
            bad_count=bad_count,
            parse_failed_count=parse_failed_count,
            result_path=result_path,
        )

    def build_proxy_pool(self, progress_callback: ProgressCallback | None = None) -> ProxyPoolSummary:
        self.workspace_service.ensure_structure()
        source_path = self.workspace_service.proxy_test_results_csv_path
        output_path = self.workspace_service.usable_proxies_csv_path

        if not source_path.exists():
            raise FileNotFoundError(f"找不到文件：{source_path}")

        usable_rows: list[UsableProxyRow] = []

        with source_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            current_fields = set(reader.fieldnames or [])
            required_fields = set(PROXY_TEST_RESULT_HEADER)
            missing_fields = required_fields - current_fields

            if missing_fields:
                raise ValueError(f"proxy_test_results.csv 缺少字段：{missing_fields}")

            for row in reader:
                status = str(row.get("status") or "").strip()
                duplicate = str(row.get("duplicate") or "").strip()

                if status == "ok" and duplicate == "no":
                    usable_rows.append(
                        UsableProxyRow(
                            raw_proxy=str(row.get("raw_proxy") or "").strip(),
                            masked_proxy=str(row.get("masked_proxy") or "").strip(),
                            exit_ip=str(row.get("exit_ip") or "").strip(),
                        )
                    )

        self._write_usable_proxies(output_path, usable_rows)

        self._emit(progress_callback, f"可用代理数量：{len(usable_rows)}")
        self._emit(progress_callback, f"已生成：{output_path}")

        if not usable_rows:
            self._emit(progress_callback, "没有可用代理。请先更换代理或重新检测代理。")

        return ProxyPoolSummary(
            usable_count=len(usable_rows),
            source_path=source_path,
            output_path=output_path,
        )

    def read_proxy_test_results(self) -> list[dict[str, str]]:
        return self._read_csv_dicts(self.workspace_service.proxy_test_results_csv_path)

    def read_usable_proxies(self) -> list[dict[str, str]]:
        return self._read_csv_dicts(self.workspace_service.usable_proxies_csv_path)

    def check_exit_ip(self, parsed_proxy: ParsedProxy) -> ProxyCheckResult:
        last_error = ""

        for url in IP_CHECK_URLS:
            try:
                response = requests.get(
                    url,
                    proxies=parsed_proxy.requests_proxies,
                    timeout=self.request_timeout_seconds,
                )
                response.raise_for_status()

                data = response.json()
                exit_ip = str(data.get("ip") or "").strip()

                if not exit_ip:
                    last_error = f"{url} 返回中没有 ip 字段"
                    continue

                return ProxyCheckResult(ok=True, exit_ip=exit_ip, error="")

            except Exception as exc:
                last_error = str(exc)

        return ProxyCheckResult(ok=False, exit_ip="", error=last_error)

    @staticmethod
    def parse_raw_proxy(raw_proxy: str) -> ParsedProxy:
        if not raw_proxy:
            raise ValueError("代理为空")

        normalized_proxy = str(raw_proxy or "").strip()

        if normalized_proxy.startswith("http://"):
            normalized_proxy = normalized_proxy[len("http://"):]

        if normalized_proxy.startswith("https://"):
            normalized_proxy = normalized_proxy[len("https://"):]

        if "@" not in normalized_proxy:
            raise ValueError(f"代理格式错误，缺少 @：{normalized_proxy}")

        auth_part, host_part = normalized_proxy.rsplit("@", 1)

        if ":" not in auth_part:
            raise ValueError(f"代理格式错误，账号密码部分缺少冒号：{normalized_proxy}")

        username, password = auth_part.split(":", 1)

        if ":" not in host_part:
            raise ValueError(f"代理格式错误，host 端口部分缺少冒号：{normalized_proxy}")

        host, port_text = host_part.rsplit(":", 1)

        if not username:
            raise ValueError("代理用户名为空")

        if not password:
            raise ValueError("代理密码为空")

        if not host:
            raise ValueError("代理 host 为空")

        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(f"代理端口不是数字：{port_text}") from exc

        return ParsedProxy(
            raw_proxy=normalized_proxy,
            username=username,
            password=password,
            host=host,
            port=port,
        )

    @staticmethod
    def _write_proxy_test_results(file_path: Path, rows: Iterable[ProxyTestRow]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=PROXY_TEST_RESULT_HEADER)
            writer.writeheader()
            writer.writerows(row.to_csv_row() for row in rows)

    @staticmethod
    def _write_usable_proxies(file_path: Path, rows: Iterable[UsableProxyRow]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=USABLE_PROXIES_HEADER)
            writer.writeheader()
            writer.writerows(row.to_csv_row() for row in rows)

    @staticmethod
    def _read_csv_dicts(file_path: Path) -> list[dict[str, str]]:
        if not file_path.exists():
            return []

        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return [
                {str(key or ""): str(value or "") for key, value in row.items()}
                for row in reader
            ]

    @staticmethod
    def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
        if callable(progress_callback):
            progress_callback(str(message or ""))

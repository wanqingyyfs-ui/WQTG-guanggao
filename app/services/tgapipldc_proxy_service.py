from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    动态轮换代理服务。

    旧的多代理检测、去重、构建可用代理池流程已经移除。
    当前只读取 data/proxies.csv 中唯一一条 raw_proxy，用于快速验证代理是否可连。
    """

    def __init__(
        self,
        workspace_service: TgapipldcWorkspaceService | None = None,
        request_timeout_seconds: int = 20,
        per_proxy_sleep_seconds: float = 0.0,
    ):
        self.workspace_service = workspace_service or TgapipldcWorkspaceService()
        self.request_timeout_seconds = int(request_timeout_seconds)
        self.per_proxy_sleep_seconds = float(per_proxy_sleep_seconds)

    def read_raw_proxies(self) -> list[str]:
        self.workspace_service.ensure_structure()
        file_path = self.workspace_service.proxies_csv_path

        if not file_path.exists():
            raise FileNotFoundError(f"找不到动态代理文件：{file_path}")

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
            raise ValueError("data\\proxies.csv 里没有动态轮换代理")

        if len(raw_proxies) > 1:
            raise ValueError("动态轮换代理模式只允许配置一条 raw_proxy，请删除多余代理")

        return raw_proxies

    def test_proxies(self, progress_callback: ProgressCallback | None = None) -> ProxyTestSummary:
        raw_proxy = self.read_raw_proxies()[0]
        result_path = self.workspace_service.proxy_test_results_csv_path
        result_path.parent.mkdir(parents=True, exist_ok=True)

        ok_count = 0
        bad_count = 0
        parse_failed_count = 0
        row: dict[str, str]

        self._emit(progress_callback, "动态轮换代理模式：只检测当前保存的一条 raw_proxy")

        try:
            parsed_proxy = self.parse_raw_proxy(raw_proxy)
            check_result = self.check_exit_ip(parsed_proxy)
            if check_result.ok:
                ok_count = 1
                self._emit(progress_callback, f"动态代理：{parsed_proxy.masked_raw_proxy}")
                self._emit(progress_callback, f"requests 检测出口 IP：{check_result.exit_ip}")
                self._emit(progress_callback, "状态：ok")
                row = {
                    "raw_proxy": raw_proxy,
                    "masked_proxy": parsed_proxy.masked_raw_proxy,
                    "exit_ip": check_result.exit_ip,
                    "duplicate": "dynamic",
                    "status": "ok",
                    "note": "dynamic_proxy_checked",
                }
            else:
                bad_count = 1
                self._emit(progress_callback, f"状态：bad，错误：{check_result.error}")
                row = {
                    "raw_proxy": raw_proxy,
                    "masked_proxy": parsed_proxy.masked_raw_proxy,
                    "exit_ip": "",
                    "duplicate": "dynamic",
                    "status": "bad",
                    "note": check_result.error,
                }
        except Exception as exc:
            parse_failed_count = 1
            self._emit(progress_callback, f"状态：parse_failed，错误：{exc}")
            row = {
                "raw_proxy": raw_proxy,
                "masked_proxy": "",
                "exit_ip": "",
                "duplicate": "dynamic",
                "status": "parse_failed",
                "note": str(exc),
            }

        with result_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=PROXY_TEST_RESULT_HEADER)
            writer.writeheader()
            writer.writerow(row)

        self._emit(progress_callback, f"检测结果已保存到：{result_path}")
        return ProxyTestSummary(
            total=1,
            ok_count=ok_count,
            duplicate_ip_count=0,
            bad_count=bad_count,
            parse_failed_count=parse_failed_count,
            result_path=result_path,
        )

    def build_proxy_pool(self, progress_callback: ProgressCallback | None = None) -> ProxyPoolSummary:
        self.workspace_service.ensure_structure()
        raw_proxy = self.read_raw_proxies()[0]
        parsed_proxy = self.parse_raw_proxy(raw_proxy)
        source_path = self.workspace_service.proxy_test_results_csv_path
        output_path = self.workspace_service.usable_proxies_csv_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=USABLE_PROXIES_HEADER)
            writer.writeheader()
            writer.writerow({
                "raw_proxy": raw_proxy,
                "masked_proxy": parsed_proxy.masked_raw_proxy,
                "exit_ip": "dynamic",
                "assigned_phone": "",
                "status": "dynamic",
                "note": "dynamic_proxy_mode_no_pool",
            })

        self._emit(progress_callback, "动态轮换代理模式不再构建多代理池；已写入兼容占位文件。")
        self._emit(progress_callback, f"兼容文件：{output_path}")
        return ProxyPoolSummary(
            usable_count=1,
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
    def _read_csv_dicts(file_path: Path) -> list[dict[str, str]]:
        if not file_path.exists():
            return []

        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return [dict(row) for row in reader]

    @staticmethod
    def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
        safe_message = str(message or "")
        if callable(progress_callback):
            progress_callback(safe_message)
        else:
            print(safe_message)

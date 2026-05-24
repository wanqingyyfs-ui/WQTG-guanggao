from __future__ import annotations

import asyncio
import csv
import re
import time
from html import unescape
from pathlib import Path
from typing import Callable

import requests

from app.services.tgapipldc_workspace_service import TgapipldcWorkspaceService


LogFunc = Callable[[str], None]


class YanzhengLoginInputProvider:
    """
    WQTG Telethon 登录用的 yanzheng 自动验证码提供器。

    作用：替代 GUI 弹窗输入验证码。

    request_code(account)：
        从 account_proxy_map.csv 按手机号找到 yanzheng URL，读取 input#code。

    request_password(account)：
        从 account_proxy_map.csv 按手机号找到 yanzheng URL，读取 input#pass2fa。
    """

    def __init__(
        self,
        workspace_service: TgapipldcWorkspaceService | None = None,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 2.0,
        log_func: LogFunc | None = None,
    ):
        self.workspace = workspace_service or TgapipldcWorkspaceService()
        self.workspace.ensure_structure()
        self.timeout_seconds = max(10, int(timeout_seconds or 120))
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds or 2.0))
        self.log_func = log_func

    async def request_code(self, account) -> str | None:
        return await asyncio.to_thread(
            self._wait_for_account_yanzheng_value,
            account,
            "code",
            "Telegram 登录验证码",
        )

    async def request_password(self, account) -> str | None:
        return await asyncio.to_thread(
            self._wait_for_account_yanzheng_value,
            account,
            "pass2fa",
            "Telegram 2FA 二步密码",
        )

    def _wait_for_account_yanzheng_value(
        self,
        account,
        input_id: str,
        label: str,
    ) -> str:
        phone = str(getattr(account, "phone", "") or "").strip()
        account_name = str(getattr(account, "account_name", "") or "").strip()

        yanzheng_url = self.find_yanzheng_url_for_phone(phone)
        if not yanzheng_url:
            raise RuntimeError(f"没有找到账号 {account_name or phone} 对应的 yanzheng 地址")

        self._log(f"[{account_name or phone}] 正在从 yanzheng 读取 {label}：input#{input_id}")
        return self.wait_for_yanzheng_value(
            yanzheng_url=yanzheng_url,
            input_id=input_id,
            label=f"[{account_name or phone}] {label}",
        )

    def find_yanzheng_url_for_phone(self, phone: str) -> str:
        index = self._read_account_proxy_map_index()
        keys = self._phone_keys(phone)

        for key in keys:
            row = index.get(key)
            if row:
                return str(row.get("yanzheng") or "").strip()

        return ""

    def wait_for_yanzheng_value(
        self,
        yanzheng_url: str,
        input_id: str,
        label: str,
    ) -> str:
        deadline = time.time() + self.timeout_seconds
        last_error = ""

        while time.time() < deadline:
            try:
                html = self.fetch_yanzheng_html(yanzheng_url)
                value = self.extract_yanzheng_input_value(html, input_id)
                if value:
                    self._log(f"{label} 已读取到。")
                    return value
                last_error = f"input#{input_id} 为空或不存在"
            except Exception as exc:
                last_error = str(exc)

            self._log(f"{label} 暂未读取到，继续等待。原因：{last_error}")
            time.sleep(self.poll_interval_seconds)

        raise TimeoutError(f"等待 {label} 超时：{last_error}")

    @staticmethod
    def fetch_yanzheng_html(yanzheng_url: str) -> str:
        url = str(yanzheng_url or "").strip()
        if not url:
            raise ValueError("yanzheng URL 为空")

        response = requests.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    @staticmethod
    def extract_yanzheng_input_value(html: str, input_id: str) -> str:
        safe_input_id = re.escape(str(input_id or "").strip())
        if not safe_input_id:
            return ""

        patterns = [
            rf'<input[^>]*id=["\\\']{safe_input_id}["\\\'][^>]*value=["\\\']([^"\\\']*)["\\\'][^>]*>',
            rf'<input[^>]*value=["\\\']([^"\\\']*)["\\\'][^>]*id=["\\\']{safe_input_id}["\\\'][^>]*>',
            rf'<textarea[^>]*id=["\\\']{safe_input_id}["\\\'][^>]*>(.*?)</textarea>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html or "", re.IGNORECASE | re.DOTALL)
            if match:
                return unescape(match.group(1)).strip()

        return ""

    def _read_account_proxy_map_index(self) -> dict[str, dict[str, str]]:
        path = self.workspace.account_proxy_map_csv_path
        if not path.exists():
            raise FileNotFoundError(f"找不到 account_proxy_map.csv：{path}")

        index: dict[str, dict[str, str]] = {}

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if "yanzheng" not in set(reader.fieldnames or []):
                raise ValueError("account_proxy_map.csv 缺少 yanzheng 字段")

            for row in reader:
                for key in self._row_phone_keys(row):
                    index.setdefault(key, row)

        return index

    def _row_phone_keys(self, row: dict[str, str]) -> set[str]:
        keys: set[str] = set()
        for field_name in ("phone", "telegram_phone", "phone_for_web", "national_number"):
            keys.update(self._phone_keys(str(row.get(field_name) or "")))

        country_code = self._only_digits(str(row.get("country_code") or ""))
        national_number = self._only_digits(str(row.get("national_number") or ""))
        if country_code and national_number:
            keys.update(self._phone_keys(f"+{country_code}{national_number}"))
            keys.update(self._phone_keys(f"{country_code}{national_number}"))
        return keys

    def _phone_keys(self, phone: str) -> set[str]:
        text = str(phone or "").strip()
        digits = self._only_digits(text)
        keys: set[str] = set()
        if text:
            keys.add(text)
        if digits:
            keys.add(digits)
            keys.add(f"+{digits}")
        return keys

    @staticmethod
    def _only_digits(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _log(self, message: str) -> None:
        if callable(self.log_func):
            self.log_func(str(message or ""))

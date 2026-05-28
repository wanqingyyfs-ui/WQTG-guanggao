from __future__ import annotations

import json
from pathlib import Path

import requests

from proxy_utils import parse_raw_proxy


SCRIPT_VERSION = "dynamic-proxy-single-check-v1"
BASE_DIR = Path(__file__).resolve().parent.parent
PROXIES_FILE = BASE_DIR / "data" / "proxies.csv"
PROXY_TEST_RESULTS_FILE = BASE_DIR / "data" / "proxy_test_results.csv"
IP_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]


def read_dynamic_proxy() -> str:
    if not PROXIES_FILE.exists():
        raise FileNotFoundError(f"找不到动态代理文件：{PROXIES_FILE}")
    lines = PROXIES_FILE.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rows = [line.strip() for line in lines if line.strip()]
    if rows and rows[0].lower() == "raw_proxy":
        rows = rows[1:]
    if not rows:
        raise ValueError("proxies.csv 里没有动态轮换代理")
    if len(rows) > 1:
        raise ValueError("动态轮换代理模式只允许配置一条 raw_proxy，请删除多余代理")
    return rows[0]


def detect_exit_ip(parsed_proxy, timeout: int = 20) -> tuple[bool, str, str]:
    last_error = ""
    for url in IP_CHECK_URLS:
        try:
            response = requests.get(url, proxies=parsed_proxy.requests_proxies, timeout=timeout)
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = {}
            exit_ip = str(data.get("ip") or "").strip()
            if exit_ip:
                return True, exit_ip, ""
            last_error = f"{url} 返回中没有 ip 字段"
        except Exception as exc:
            last_error = str(exc)
    return False, "", last_error


def main() -> int:
    print(f"代理检测脚本版本：{SCRIPT_VERSION}")
    print("当前模式：只检测面板保存的一条动态轮换代理，不再检测多代理池。")
    raw_proxy = read_dynamic_proxy()
    parsed_proxy = parse_raw_proxy(raw_proxy)
    ok, exit_ip, error = detect_exit_ip(parsed_proxy)
    PROXY_TEST_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    status = "ok" if ok else "bad"
    note = "dynamic_proxy_checked" if ok else error
    with PROXY_TEST_RESULTS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        file.write("raw_proxy,masked_proxy,exit_ip,duplicate,status,note\n")
        safe_note = str(note).replace("\n", " ").replace("\r", " ")
        file.write(f"{raw_proxy},{parsed_proxy.masked_raw_proxy},{exit_ip},dynamic,{status},{safe_note}\n")
    print(f"动态代理：{parsed_proxy.masked_raw_proxy}")
    if ok:
        print(f"requests 检测出口 IP：{exit_ip}")
        print("状态：ok")
        return 0
    print(f"状态：bad，错误：{error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

from proxy_utils import parse_raw_proxy


SCRIPT_VERSION = "dynamic-proxy-no-pool-v1"
BASE_DIR = Path(__file__).resolve().parent.parent
PROXIES_FILE = BASE_DIR / "data" / "proxies.csv"
USABLE_PROXIES_FILE = BASE_DIR / "data" / "usable_proxies.csv"


def read_dynamic_proxy() -> str:
    if not PROXIES_FILE.exists():
        raise FileNotFoundError(f"找不到动态代理文件：{PROXIES_FILE}")
    rows = [
        line.strip()
        for line in PROXIES_FILE.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    if rows and rows[0].lower() == "raw_proxy":
        rows = rows[1:]
    if not rows:
        raise ValueError("proxies.csv 里没有动态轮换代理")
    if len(rows) > 1:
        raise ValueError("动态轮换代理模式只允许配置一条 raw_proxy，请删除多余代理")
    return rows[0]


def main() -> int:
    print(f"构建代理池脚本版本：{SCRIPT_VERSION}")
    print("当前模式：不再构建多代理池，只写入兼容占位 usable_proxies.csv。")
    raw_proxy = read_dynamic_proxy()
    parsed_proxy = parse_raw_proxy(raw_proxy)
    USABLE_PROXIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USABLE_PROXIES_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        file.write("raw_proxy,masked_proxy,exit_ip,assigned_phone,status,note\n")
        file.write(f"{raw_proxy},{parsed_proxy.masked_raw_proxy},dynamic,,dynamic,dynamic_proxy_mode_no_pool\n")
    print(f"动态代理：{parsed_proxy.masked_raw_proxy}")
    print(f"兼容文件已写入：{USABLE_PROXIES_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

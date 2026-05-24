import csv
import time
from pathlib import Path

import requests

from proxy_utils import parse_raw_proxy


BASE_DIR = Path(__file__).resolve().parent.parent
PROXIES_FILE = BASE_DIR / "data" / "proxies.csv"
RESULT_FILE = BASE_DIR / "data" / "proxy_test_results.csv"

IP_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]


def read_raw_proxies() -> list[str]:
    if not PROXIES_FILE.exists():
        raise FileNotFoundError(f"找不到代理文件：{PROXIES_FILE}")

    raw_proxies = []

    with open(PROXIES_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if "raw_proxy" not in reader.fieldnames:
            raise ValueError("data\\proxies.csv 第一行必须是：raw_proxy")

        for row in reader:
            raw_proxy = (row.get("raw_proxy") or "").strip()
            if raw_proxy:
                raw_proxies.append(raw_proxy)

    if not raw_proxies:
        raise ValueError("data\\proxies.csv 里没有代理")

    return raw_proxies


def check_exit_ip(parsed_proxy, timeout: int = 20) -> tuple[bool, str, str]:
    last_error = ""

    for url in IP_CHECK_URLS:
        try:
            response = requests.get(
                url,
                proxies=parsed_proxy.requests_proxies,
                timeout=timeout,
            )
            response.raise_for_status()

            data = response.json()

            exit_ip = data.get("ip")

            if not exit_ip:
                last_error = f"{url} 返回中没有 ip 字段"
                continue

            return True, exit_ip, ""

        except Exception as e:
            last_error = str(e)

    return False, "", last_error


def main():
    raw_proxies = read_raw_proxies()

    print(f"读取到 {len(raw_proxies)} 条代理")
    print("-" * 80)

    results = []
    seen_ips = set()

    for index, raw_proxy in enumerate(raw_proxies, start=1):
        print(f"[{index}/{len(raw_proxies)}] 开始检测代理")

        try:
            parsed_proxy = parse_raw_proxy(raw_proxy)

            ok, exit_ip, error = check_exit_ip(parsed_proxy)

            if ok:
                duplicate = "yes" if exit_ip in seen_ips else "no"
                seen_ips.add(exit_ip)

                status = "ok" if duplicate == "no" else "duplicate_ip"

                print(f"代理：{parsed_proxy.masked_raw_proxy}")
                print(f"出口 IP：{exit_ip}")
                print(f"是否重复：{duplicate}")
                print(f"状态：{status}")

                results.append({
                    "raw_proxy": raw_proxy,
                    "masked_proxy": parsed_proxy.masked_raw_proxy,
                    "exit_ip": exit_ip,
                    "duplicate": duplicate,
                    "status": status,
                    "note": "",
                })

            else:
                print(f"代理：{parsed_proxy.masked_raw_proxy}")
                print(f"状态：bad")
                print(f"错误：{error}")

                results.append({
                    "raw_proxy": raw_proxy,
                    "masked_proxy": parsed_proxy.masked_raw_proxy,
                    "exit_ip": "",
                    "duplicate": "",
                    "status": "bad",
                    "note": error,
                })

        except Exception as e:
            print("状态：parse_failed")
            print(f"错误：{e}")

            results.append({
                "raw_proxy": raw_proxy,
                "masked_proxy": "",
                "exit_ip": "",
                "duplicate": "",
                "status": "parse_failed",
                "note": str(e),
            })

        print("-" * 80)
        time.sleep(1)

    with open(RESULT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "raw_proxy",
                "masked_proxy",
                "exit_ip",
                "duplicate",
                "status",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"检测完成，结果已保存到：{RESULT_FILE}")


if __name__ == "__main__":
    main()
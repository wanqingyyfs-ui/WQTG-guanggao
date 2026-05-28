import csv
import json
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from proxy_utils import parse_raw_proxy


BASE_DIR = Path(__file__).resolve().parent.parent
ACCOUNT_PROXY_MAP_FILE = BASE_DIR / "data" / "account_proxy_map.csv"
BROWSER_PROXY_CHECK_FILE = BASE_DIR / "data" / "browser_proxy_check.csv"

IP_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]


def read_account_proxy_map() -> list[dict]:
    if not ACCOUNT_PROXY_MAP_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{ACCOUNT_PROXY_MAP_FILE}")

    rows = []

    with open(ACCOUNT_PROXY_MAP_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_fields = {
            "phone",
            "country",
            "profile_dir",
            "raw_proxy",
            "masked_proxy",
            "exit_ip",
            "status",
            "note",
        }

        current_fields = set(reader.fieldnames or [])
        missing_fields = required_fields - current_fields

        if missing_fields:
            raise ValueError(f"account_proxy_map.csv 缺少字段：{missing_fields}")

        for row in reader:
            phone = (row.get("phone") or "").strip()
            raw_proxy = (row.get("raw_proxy") or "").strip()
            profile_dir = (row.get("profile_dir") or "").strip()
            exit_ip = (row.get("exit_ip") or "").strip()

            if not phone or not raw_proxy or not profile_dir:
                continue

            rows.append({
                "phone": phone,
                "country": (row.get("country") or "").strip(),
                "profile_dir": profile_dir,
                "raw_proxy": raw_proxy,
                "masked_proxy": (row.get("masked_proxy") or "").strip(),
                "historical_exit_ip": exit_ip,
                "status": (row.get("status") or "").strip(),
                "note": (row.get("note") or "").strip(),
            })

    if not rows:
        raise ValueError("account_proxy_map.csv 里没有可用账号代理绑定")

    return rows


def select_account(rows: list[dict]) -> dict:
    if len(sys.argv) >= 2:
        target_phone = sys.argv[1].strip()

        for row in rows:
            if row["phone"] == target_phone:
                return row

        raise ValueError(f"没有找到手机号：{target_phone}")

    print("可用账号列表：")
    for index, row in enumerate(rows, start=1):
        print(
            f"{index}. {row['phone']} -> "
            f"{row['masked_proxy']} -> 历史IP {row['historical_exit_ip']}"
        )

    selected = input("请输入要打开的账号序号：").strip()

    try:
        selected_index = int(selected)
    except ValueError:
        raise ValueError("请输入数字序号")

    if selected_index < 1 or selected_index > len(rows):
        raise ValueError("账号序号超出范围")

    return rows[selected_index - 1]


def detect_exit_ip_by_requests(parsed_proxy, timeout: int = 30) -> tuple[bool, str, str]:
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

            if exit_ip:
                return True, exit_ip, ""

            last_error = f"{url} 返回中没有 ip 字段"

        except Exception as e:
            last_error = str(e)

    return False, "", last_error


def detect_exit_ip_by_browser(page, timeout: int = 60000) -> tuple[bool, str, str]:
    last_error = ""

    for url in IP_CHECK_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            body_text = page.inner_text("body").strip()

            try:
                data = json.loads(body_text)
            except json.JSONDecodeError:
                last_error = f"{url} 返回不是 JSON：{body_text[:200]}"
                continue

            exit_ip = data.get("ip")

            if exit_ip:
                return True, exit_ip, ""

            last_error = f"{url} 返回中没有 ip 字段"

        except Exception as e:
            last_error = str(e)

    return False, "", last_error


def append_browser_proxy_check(row: dict):
    file_exists = BROWSER_PROXY_CHECK_FILE.exists()

    with open(BROWSER_PROXY_CHECK_FILE, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "phone",
                "masked_proxy",
                "historical_exit_ip",
                "realtime_requests_ip",
                "browser_ip",
                "status",
                "note",
                "checked_at",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def update_account_proxy_map_exit_ip(phone: str, new_exit_ip: str):
    if not ACCOUNT_PROXY_MAP_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{ACCOUNT_PROXY_MAP_FILE}")

    with open(ACCOUNT_PROXY_MAP_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if "phone" not in fieldnames or "exit_ip" not in fieldnames:
        raise ValueError("account_proxy_map.csv 缺少 phone 或 exit_ip 字段")

    updated = False

    for row in rows:
        if (row.get("phone") or "").strip() == phone:
            row["exit_ip"] = new_exit_ip
            row["status"] = "proxy_verified"
            row["note"] = "exit_ip_updated_by_browser_check"
            updated = True
            break

    if not updated:
        raise ValueError(f"没有在 account_proxy_map.csv 找到手机号：{phone}")

    with open(ACCOUNT_PROXY_MAP_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已更新 account_proxy_map.csv：{phone} -> {new_exit_ip}")


def open_browser_for_account(account: dict):
    parsed_proxy = parse_raw_proxy(account["raw_proxy"])

    print("-" * 80)
    print(f"当前账号：{account['phone']}")
    print(f"代理：{parsed_proxy.masked_raw_proxy}")
    print(f"历史出口 IP：{account['historical_exit_ip']}")
    print("正在用 requests 实时检测当前代理出口 IP...")
    print("-" * 80)

    ok, realtime_ip, error = detect_exit_ip_by_requests(parsed_proxy)

    if not ok:
        print("实时检测失败，不能继续打开浏览器。")
        print(f"错误：{error}")
        append_browser_proxy_check({
            "phone": account["phone"],
            "masked_proxy": parsed_proxy.masked_raw_proxy,
            "historical_exit_ip": account["historical_exit_ip"],
            "realtime_requests_ip": "",
            "browser_ip": "",
            "status": "requests_check_failed",
            "note": error,
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        return

    print(f"实时出口 IP：{realtime_ip}")

    if account["historical_exit_ip"] and realtime_ip != account["historical_exit_ip"]:
        print("提示：实时出口 IP 与历史出口 IP 不一致。")
        print("这通常是动态住宅代理 sticky 会话过期或重新分配导致的。")
        print("后续判断以实时出口 IP 为准。")

    profile_dir = BASE_DIR / account["profile_dir"]
    profile_dir.mkdir(parents=True, exist_ok=True)

    print("-" * 80)
    print(f"Profile：{profile_dir}")
    print("正在启动浏览器...")
    print("-" * 80)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            proxy=parsed_proxy.playwright_proxy,
            viewport={"width": 1200, "height": 900},
        )

        page = context.new_page()

        browser_ok, browser_ip, browser_error = detect_exit_ip_by_browser(page)

        if not browser_ok:
            print("浏览器出口 IP 检测失败。")
            print(f"错误：{browser_error}")
            append_browser_proxy_check({
                "phone": account["phone"],
                "masked_proxy": parsed_proxy.masked_raw_proxy,
                "historical_exit_ip": account["historical_exit_ip"],
                "realtime_requests_ip": realtime_ip,
                "browser_ip": "",
                "status": "browser_check_failed",
                "note": browser_error,
                "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            input("按 Enter 关闭浏览器...")
            context.close()
            return

        print("-" * 80)
        print(f"历史出口 IP：{account['historical_exit_ip']}")
        print(f"实时出口 IP：{realtime_ip}")
        print(f"浏览器出口 IP：{browser_ip}")

        status = "ok"
        note = f"dynamic_proxy，requests={realtime_ip}, browser={browser_ip}"
        if browser_ip != realtime_ip:
            print("动态轮换代理模式：requests 出口 IP 与浏览器出口 IP 不一致，允许继续。")
        print("状态：通过。浏览器代理已生效。")

        if account["historical_exit_ip"] != browser_ip:
            update_account_proxy_map_exit_ip(
                phone=account["phone"],
                new_exit_ip=browser_ip,
            )

        print("可以继续用这个窗口做 Telegram Web 登录测试。")

        append_browser_proxy_check({
            "phone": account["phone"],
            "masked_proxy": parsed_proxy.masked_raw_proxy,
            "historical_exit_ip": account["historical_exit_ip"],
            "realtime_requests_ip": realtime_ip,
            "browser_ip": browser_ip,
            "status": status,
            "note": note,
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        print("-" * 80)
        print(f"检测结果已记录到：{BROWSER_PROXY_CHECK_FILE}")
        print("确认后回到这里按 Enter 关闭浏览器。")

        input()

        context.close()


def main():
    rows = read_account_proxy_map()
    account = select_account(rows)
    open_browser_for_account(account)


if __name__ == "__main__":
    main()
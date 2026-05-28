import csv
import re
from pathlib import Path

from proxy_utils import parse_raw_proxy


SCRIPT_VERSION = "dynamic-proxy-assignment-v1"

BASE_DIR = Path(__file__).resolve().parent.parent

ACCOUNTS_FILE = BASE_DIR / "data" / "accounts.csv"
PROXIES_FILE = BASE_DIR / "data" / "proxies.csv"
ACCOUNT_PROXY_MAP_FILE = BASE_DIR / "data" / "account_proxy_map.csv"

COUNTRY_CODE_BY_COUNTRY = {
    "US": "1",
    "CA": "1",
    "GB": "44",
    "UK": "44",
    "SG": "65",
    "HK": "852",
    "KH": "855",
    "CN": "86",
    "TH": "66",
}

OUTPUT_FIELDS = [
    "phone",
    "country",
    "country_code",
    "national_number",
    "telegram_phone",
    "phone_for_web",
    "profile_dir",
    "yanzheng",
    "raw_proxy",
    "masked_proxy",
    "exit_ip",
    "status",
    "note",
]

PENDING_STATUSES = {"", "pending", "proxy_required", "new", "unused"}


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_country(country: str) -> str:
    return (country or "").strip().upper()


def normalize_country_code(country_code: str, country: str = "") -> str:
    digits = only_digits(country_code)

    if not digits:
        digits = COUNTRY_CODE_BY_COUNTRY.get(normalize_country(country), "")

    if not digits:
        return ""

    return f"+{digits}"


def normalize_account_phone(row: dict) -> dict:
    raw_phone = (
        row.get("phone_for_web")
        or row.get("telegram_phone")
        or row.get("phone")
        or ""
    ).strip()
    country = normalize_country(row.get("country") or "")
    country_code = normalize_country_code(row.get("country_code") or "", country)
    national_number = only_digits(row.get("national_number") or "")
    phone_digits = only_digits(raw_phone)
    yanzheng = (row.get("yanzheng") or "").strip()

    if not yanzheng:
        raise ValueError("缺少 yanzheng 验证码网页地址")

    if national_number:
        if not country_code and raw_phone.startswith("+"):
            raw_digits = only_digits(raw_phone)
            if len(raw_digits) > len(national_number):
                country_code = f"+{raw_digits[:-len(national_number)]}"

        if country_code:
            telegram_phone = f"{country_code}{national_number}"
        else:
            telegram_phone = f"+{national_number}" if not raw_phone.startswith("+") else raw_phone.replace(" ", "")
    else:
        if not phone_digits:
            raise ValueError("账号行缺少手机号：phone / telegram_phone / phone_for_web / national_number 至少要填一个")

        country_code_digits = only_digits(country_code)

        if country_code_digits:
            if phone_digits.startswith(country_code_digits) and len(phone_digits) > len(country_code_digits):
                national_number = phone_digits[len(country_code_digits):]
                telegram_phone = f"+{phone_digits}"
            else:
                national_number = phone_digits
                telegram_phone = f"+{country_code_digits}{national_number}"
        else:
            telegram_phone = f"+{phone_digits}"
            if phone_digits.startswith("1") and len(phone_digits) == 11:
                country_code = "+1"
                national_number = phone_digits[1:]
            else:
                national_number = phone_digits

    telegram_digits = only_digits(telegram_phone)

    if not telegram_digits:
        raise ValueError(f"手机号格式错误：{raw_phone}")

    if not national_number:
        raise ValueError(f"手机号缺少本地号码部分：{raw_phone}")

    country_code_digits = only_digits(country_code)

    if country_code_digits and not telegram_digits.startswith(country_code_digits):
        telegram_phone = f"+{country_code_digits}{national_number}"

    phone_for_web = telegram_phone.replace(" ", "")
    profile_dir = (row.get("profile_dir") or "").strip()

    if not profile_dir:
        safe_phone = only_digits(phone_for_web)
        profile_dir = f"profiles/{safe_phone}"

    return {
        "phone": phone_for_web,
        "country": country,
        "country_code": country_code,
        "national_number": national_number,
        "telegram_phone": phone_for_web,
        "phone_for_web": phone_for_web,
        "profile_dir": profile_dir,
        "yanzheng": yanzheng,
        "status": (row.get("status") or "pending").strip() or "pending",
        "note": (row.get("note") or "").strip(),
    }


def read_accounts() -> list[dict]:
    if not ACCOUNTS_FILE.exists():
        raise FileNotFoundError(f"找不到账号文件：{ACCOUNTS_FILE}")

    accounts = []

    with open(ACCOUNTS_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        accepted_phone_fields = {"phone", "telegram_phone", "phone_for_web", "national_number"}
        if not fieldnames & accepted_phone_fields:
            raise ValueError(
                "accounts.csv 至少需要包含 phone / telegram_phone / phone_for_web / national_number 其中一个字段"
            )

        if "yanzheng" not in fieldnames:
            raise ValueError("accounts.csv 必须包含 yanzheng 字段")

        for line_number, row in enumerate(reader, start=2):
            try:
                account = normalize_account_phone(row)
            except Exception as e:
                raise ValueError(f"accounts.csv 第 {line_number} 行格式错误：{e}")

            if account["status"] not in PENDING_STATUSES:
                continue

            accounts.append(account)

    if not accounts:
        raise ValueError("accounts.csv 里没有 pending / proxy_required 状态的账号")

    return accounts


def read_dynamic_proxy() -> dict:
    if not PROXIES_FILE.exists():
        raise FileNotFoundError(f"找不到动态代理文件：{PROXIES_FILE}")

    raw_proxies = []

    with open(PROXIES_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        if "raw_proxy" not in fieldnames:
            raise ValueError("proxies.csv 第一行必须是：raw_proxy")

        for row in reader:
            raw_proxy = (row.get("raw_proxy") or "").strip()
            if raw_proxy:
                raw_proxies.append(raw_proxy)

    if not raw_proxies:
        raise ValueError("proxies.csv 里没有动态轮换代理")

    if len(raw_proxies) > 1:
        raise ValueError("动态轮换代理模式只允许配置一条 raw_proxy，请删除多余代理")

    parsed_proxy = parse_raw_proxy(raw_proxies[0])
    return {
        "raw_proxy": raw_proxies[0],
        "masked_proxy": parsed_proxy.masked_raw_proxy,
    }


def main():
    print(f"分配代理脚本版本：{SCRIPT_VERSION}")
    print("当前模式：accounts.csv + 一条动态轮换代理 -> account_proxy_map.csv。")

    accounts = read_accounts()
    proxy = read_dynamic_proxy()

    print(f"待生成账号数量：{len(accounts)}")
    print(f"动态代理：{proxy['masked_proxy']}")

    rows = []

    for account in accounts:
        account_note = account.get("note") or ""
        note_parts = [part for part in [account_note, "shared_dynamic_proxy"] if part]
        rows.append({
            "phone": account["phone"],
            "country": account["country"],
            "country_code": account["country_code"],
            "national_number": account["national_number"],
            "telegram_phone": account["telegram_phone"],
            "phone_for_web": account["phone_for_web"],
            "profile_dir": account["profile_dir"],
            "yanzheng": account["yanzheng"],
            "raw_proxy": proxy["raw_proxy"],
            "masked_proxy": proxy["masked_proxy"],
            "exit_ip": "",
            "status": "dynamic_proxy_assigned",
            "note": " | ".join(note_parts),
        })

    with open(ACCOUNT_PROXY_MAP_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已生成账号运行表数量：{len(rows)}")
    print(f"已生成：{ACCOUNT_PROXY_MAP_FILE}")
    print("-" * 80)

    for row in rows:
        print(
            f"{row['phone']} / {row['country_code']} / {row['national_number']} -> "
            f"{row['masked_proxy']} -> dynamic -> {row['yanzheng']}"
        )


if __name__ == "__main__":
    main()

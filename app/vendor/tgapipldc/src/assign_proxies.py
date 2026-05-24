import csv
import re
from pathlib import Path


SCRIPT_VERSION = "accounts-yanzheng-chain-v9"

BASE_DIR = Path(__file__).resolve().parent.parent

ACCOUNTS_FILE = BASE_DIR / "data" / "accounts.csv"
USABLE_PROXIES_FILE = BASE_DIR / "data" / "usable_proxies.csv"
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


def read_usable_proxies() -> list[dict]:
    if not USABLE_PROXIES_FILE.exists():
        raise FileNotFoundError(f"找不到可用代理文件：{USABLE_PROXIES_FILE}")

    proxies = []

    with open(USABLE_PROXIES_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_fields = {
            "raw_proxy",
            "masked_proxy",
            "exit_ip",
            "assigned_phone",
            "status",
            "note",
        }
        current_fields = set(reader.fieldnames or [])

        missing_fields = required_fields - current_fields
        if missing_fields:
            raise ValueError(f"usable_proxies.csv 缺少字段：{missing_fields}")

        seen_exit_ips = set()

        for row in reader:
            status = (row.get("status") or "").strip()
            raw_proxy = (row.get("raw_proxy") or "").strip()
            masked_proxy = (row.get("masked_proxy") or "").strip()
            exit_ip = (row.get("exit_ip") or "").strip()

            if status != "unused":
                continue

            if not raw_proxy or not exit_ip:
                continue

            if exit_ip in seen_exit_ips:
                continue

            seen_exit_ips.add(exit_ip)

            proxies.append({
                "raw_proxy": raw_proxy,
                "masked_proxy": masked_proxy,
                "exit_ip": exit_ip,
                "status": status,
            })

    if not proxies:
        raise ValueError("usable_proxies.csv 里没有可分配代理")

    return proxies


def main():
    print(f"分配代理脚本版本：{SCRIPT_VERSION}")
    print("文件编号：009，accounts.csv -> account_proxy_map.csv 会保留 yanzheng 字段。")

    accounts = read_accounts()
    proxies = read_usable_proxies()

    print(f"待分配账号数量：{len(accounts)}")
    print(f"可用代理数量：{len(proxies)}")

    if len(proxies) < len(accounts):
        print("可用代理数量不足。")
        print(f"当前待分配账号数量：{len(accounts)}")
        print(f"当前可用代理数量：{len(proxies)}")
        print("本次只会按可用代理数量分配一部分账号。")

    assign_count = min(len(accounts), len(proxies))
    rows = []

    for index in range(assign_count):
        account = accounts[index]
        proxy = proxies[index]

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
            "exit_ip": proxy["exit_ip"],
            "status": "proxy_assigned",
            "note": account["note"],
        })

    with open(ACCOUNT_PROXY_MAP_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已分配账号数量：{len(rows)}")
    print(f"已生成：{ACCOUNT_PROXY_MAP_FILE}")
    print("-" * 80)

    for row in rows:
        print(
            f"{row['phone']} / {row['country_code']} / {row['national_number']} -> "
            f"{row['masked_proxy']} -> {row['exit_ip']} -> {row['yanzheng']}"
        )


if __name__ == "__main__":
    main()

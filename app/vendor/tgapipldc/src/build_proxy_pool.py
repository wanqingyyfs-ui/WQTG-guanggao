import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PROXY_TEST_RESULT_FILE = BASE_DIR / "data" / "proxy_test_results.csv"
USABLE_PROXIES_FILE = BASE_DIR / "data" / "usable_proxies.csv"


def main():
    if not PROXY_TEST_RESULT_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{PROXY_TEST_RESULT_FILE}")

    usable_rows = []

    with open(PROXY_TEST_RESULT_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_fields = {"raw_proxy", "masked_proxy", "exit_ip", "duplicate", "status", "note"}
        current_fields = set(reader.fieldnames or [])

        missing_fields = required_fields - current_fields
        if missing_fields:
            raise ValueError(f"proxy_test_results.csv 缺少字段：{missing_fields}")

        for row in reader:
            status = (row.get("status") or "").strip()
            duplicate = (row.get("duplicate") or "").strip()

            if status == "ok" and duplicate == "no":
                usable_rows.append({
                    "raw_proxy": row["raw_proxy"],
                    "masked_proxy": row["masked_proxy"],
                    "exit_ip": row["exit_ip"],
                    "assigned_phone": "",
                    "status": "unused",
                    "note": "",
                })

    with open(USABLE_PROXIES_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "raw_proxy",
                "masked_proxy",
                "exit_ip",
                "assigned_phone",
                "status",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(usable_rows)

    print(f"可用代理数量：{len(usable_rows)}")
    print(f"已生成：{USABLE_PROXIES_FILE}")

    if len(usable_rows) == 0:
        print("没有可用代理。请先更换代理或重新运行 test_proxies.py。")


if __name__ == "__main__":
    main()
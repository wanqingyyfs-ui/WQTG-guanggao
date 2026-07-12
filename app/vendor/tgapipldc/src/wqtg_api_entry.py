from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

import login_telegram_web as implementation


ENTRY_VERSION = "wqtg-api-entry-2026-07-durable-records-v2"
_ORIGINAL_WRITE = implementation.write_mytelegram_api_credentials_csv


def _phone_key(phone: str) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits or "unknown"


def _atomic_write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_api_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows: list[dict[str, str]] = []
        for row in reader:
            phone = str(row.get("phone") or "").strip()
            api_id = str(row.get("api_id") or "").strip()
            api_hash = str(row.get("api_hash") or "").strip()
            if phone and api_id and api_hash:
                rows.append({"phone": phone, "api_id": api_id, "api_hash": api_hash})
        return rows


def _atomic_write_api_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["phone", "api_id", "api_hash"])
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_api_credentials_durably(
    phone: str,
    api_id: str,
    api_hash: str,
    app_title: str = "",
    app_shortname: str = "",
) -> Path:
    """Persist each account independently before updating the human-readable CSV.

    WPS/Excel locks CSV files on Windows. A locked summary CSV must not turn a
    successfully retrieved Telegram API credential into an account failure.
    The per-account JSON record is the durable source of truth; api.csv is a
    best-effort summary and can be rebuilt by the import service.
    """

    output_dir = implementation.CSV_OUTPUT_DIR
    record_dir = output_dir / "api_records"
    record_path = record_dir / f"{_phone_key(phone)}.json"
    payload = {
        "phone": str(phone or "").strip(),
        "api_id": str(api_id or "").strip(),
        "api_hash": str(api_hash or "").strip(),
        "app_title": str(app_title or "").strip(),
        "app_shortname": str(app_shortname or "").strip(),
        "updated_at": implementation.now_text(),
    }
    _atomic_write_json(record_path, payload)
    print(f"API 凭据已先写入独立安全记录：{record_path}")

    summary_path = output_dir / "api.csv"
    last_error = ""
    for attempt in range(1, 6):
        try:
            existing_rows = _read_api_csv(summary_path)
            by_phone = {str(row["phone"]).strip(): row for row in existing_rows}
            by_phone[payload["phone"]] = {
                "phone": payload["phone"],
                "api_id": payload["api_id"],
                "api_hash": payload["api_hash"],
            }
            _atomic_write_api_csv(summary_path, list(by_phone.values()))
            print(f"api_id/api_hash 已写入统一汇总 CSV：{summary_path}")
            return summary_path
        except PermissionError as exc:
            last_error = str(exc)
            print(
                f"api.csv 正被 WPS/Excel 占用，写入重试 {attempt}/5；"
                "独立安全记录已经保存，不会丢失。"
            )
            time.sleep(1.2)
        except OSError as exc:
            last_error = str(exc)
            print(f"api.csv 汇总写入临时失败，重试 {attempt}/5：{exc}")
            time.sleep(1.2)

    print(
        "警告：api.csv 当前无法更新，但本账号 API 已成功保存到独立记录，"
        f"稍后点击“导入 API”仍可读取。最后错误：{last_error}"
    )
    return record_path


def main() -> int:
    implementation.write_mytelegram_api_credentials_csv = write_api_credentials_durably
    implementation.SCRIPT_VERSION = f"{implementation.SCRIPT_VERSION}+{ENTRY_VERSION}"
    print(f"API 批量兼容入口：{ENTRY_VERSION}")
    implementation.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

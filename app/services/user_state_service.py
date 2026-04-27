from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path


class UserStateStore:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).expanduser()
        self.lock = threading.Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, dict[str, dict[str, str]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            self.data = {}
            self._save()
            return

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    self.data = raw
                else:
                    self.data = {}
        except Exception:
            self.data = {}

    def _save(self) -> None:
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_first_contact(self, account_name: str, user_id: int) -> bool:
        with self.lock:
            account_bucket = self.data.get(account_name, {})
            return str(user_id) not in account_bucket

    def mark_contacted(
        self,
        account_name: str,
        user_id: int,
        sender_display: str = "",
        last_message: str = "",
    ) -> None:
        with self.lock:
            account_bucket = self.data.setdefault(account_name, {})
            account_bucket[str(user_id)] = {
                "sender_display": sender_display,
                "last_message": last_message,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save()

    def reset_account(self, account_name: str) -> None:
        with self.lock:
            self.data[account_name] = {}
            self._save()
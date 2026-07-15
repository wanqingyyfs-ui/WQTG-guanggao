from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


SCHEMA = r"""
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS static_proxies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  protocol TEXT NOT NULL CHECK(protocol IN ('http','https','socks5')),
  host TEXT NOT NULL,
  port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
  username TEXT,
  password_encrypted TEXT,
  expected_ip TEXT,
  country TEXT,
  region TEXT,
  timezone TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_status TEXT NOT NULL DEFAULT 'unknown',
  last_checked_at TEXT,
  UNIQUE(protocol, host, port, username)
);

CREATE TABLE IF NOT EXISTS account_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  static_proxy_id INTEGER,
  default_country TEXT NOT NULL DEFAULT 'US',
  default_language TEXT NOT NULL DEFAULT 'en-US',
  default_timezone TEXT NOT NULL DEFAULT 'UTC',
  max_concurrent_browsers INTEGER NOT NULL DEFAULT 1 CHECK(max_concurrent_browsers > 0),
  min_action_interval_seconds INTEGER NOT NULL DEFAULT 480 CHECK(min_action_interval_seconds >= 60),
  daily_task_limit INTEGER NOT NULL DEFAULT 20 CHECK(daily_task_limit >= 0),
  enabled INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(static_proxy_id) REFERENCES static_proxies(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS environment_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER UNIQUE,
  schema_version INTEGER NOT NULL DEFAULT 1,
  browser_channel TEXT NOT NULL DEFAULT 'chromium',
  browser_version TEXT,
  user_agent TEXT,
  platform_family TEXT NOT NULL,
  viewport_width INTEGER NOT NULL,
  viewport_height INTEGER NOT NULL,
  screen_width INTEGER NOT NULL,
  screen_height INTEGER NOT NULL,
  device_scale_factor REAL NOT NULL,
  locale TEXT NOT NULL,
  language_list_json TEXT NOT NULL,
  timezone TEXT NOT NULL,
  hardware_concurrency INTEGER NOT NULL,
  device_memory INTEGER NOT NULL,
  webrtc_policy TEXT NOT NULL DEFAULT 'disable_non_proxied_udp',
  runtime_snapshot_json TEXT,
  runtime_fingerprint_sha256 TEXT,
  finalized INTEGER NOT NULL DEFAULT 0,
  generated_at TEXT NOT NULL,
  last_verified_at TEXT,
  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL UNIQUE,
  verification_url_encrypted TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'US',
  account_group_id INTEGER,
  proxy_override_id INTEGER,
  profile_dir TEXT NOT NULL UNIQUE,
  environment_profile_id INTEGER,
  enabled INTEGER NOT NULL DEFAULT 0,
  account_status TEXT NOT NULL DEFAULT 'pending',
  login_status TEXT NOT NULL DEFAULT 'unknown',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(account_group_id) REFERENCES account_groups(id) ON DELETE SET NULL,
  FOREIGN KEY(proxy_override_id) REFERENCES static_proxies(id) ON DELETE SET NULL,
  FOREIGN KEY(environment_profile_id) REFERENCES environment_profiles(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS browser_instances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL UNIQUE,
  pid INTEGER,
  status TEXT NOT NULL DEFAULT 'not_created',
  selected_visible INTEGER NOT NULL DEFAULT 0,
  current_url TEXT,
  current_title TEXT,
  exit_ip TEXT,
  started_at TEXT,
  last_heartbeat_at TEXT,
  last_error TEXT,
  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS telegram_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_link TEXT NOT NULL,
  canonical_link TEXT NOT NULL UNIQUE,
  username TEXT,
  link_type TEXT NOT NULL,
  title TEXT,
  description TEXT,
  visible_member_count TEXT,
  observed_chat_id TEXT,
  chat_type TEXT,
  joined INTEGER NOT NULL DEFAULT 0,
  can_send INTEGER NOT NULL DEFAULT 0,
  read_only INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  category_id INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  last_verified_at TEXT,
  last_error TEXT,
  FOREIGN KEY(category_id) REFERENCES group_categories(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  template_type TEXT NOT NULL,
  text_content TEXT,
  telegram_message_link TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS template_assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  mime_type TEXT,
  size_bytes INTEGER,
  sha256 TEXT,
  FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  account_group_id INTEGER NOT NULL,
  template_id INTEGER NOT NULL,
  schedule_mode TEXT NOT NULL DEFAULT 'manual',
  schedule_value TEXT,
  min_interval_seconds INTEGER NOT NULL DEFAULT 480 CHECK(min_interval_seconds >= 60),
  daily_limit INTEGER NOT NULL DEFAULT 20 CHECK(daily_limit >= 0),
  dedupe_window_seconds INTEGER NOT NULL DEFAULT 86400 CHECK(dedupe_window_seconds >= 0),
  require_preview INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(account_group_id) REFERENCES account_groups(id),
  FOREIGN KEY(template_id) REFERENCES templates(id)
);

CREATE TABLE IF NOT EXISTS task_targets (
  task_id INTEGER NOT NULL,
  telegram_group_id INTEGER NOT NULL,
  PRIMARY KEY(task_id, telegram_group_id),
  FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
  FOREIGN KEY(telegram_group_id) REFERENCES telegram_groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  stop_reason TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS task_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  telegram_group_id INTEGER NOT NULL,
  template_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  screenshot_path TEXT,
  error_code TEXT,
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(run_id) REFERENCES task_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(account_id) REFERENCES accounts(id),
  FOREIGN KEY(telegram_group_id) REFERENCES telegram_groups(id),
  FOREIGN KEY(template_id) REFERENCES templates(id)
);

CREATE TABLE IF NOT EXISTS workflow_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_key TEXT NOT NULL,
  step_key TEXT NOT NULL,
  step_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  UNIQUE(workflow_key, step_key)
);

CREATE TABLE IF NOT EXISTS locator_targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_key TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  strategies_json TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 2,
  timeout_ms INTEGER NOT NULL DEFAULT 12000,
  enabled INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proxy_health_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proxy_id INTEGER NOT NULL,
  checked_at TEXT NOT NULL,
  success INTEGER NOT NULL,
  http_exit_ip TEXT,
  browser_exit_ip TEXT,
  latency_ms INTEGER,
  webrtc_safe INTEGER,
  dns_request_safe INTEGER,
  error TEXT,
  FOREIGN KEY(proxy_id) REFERENCES static_proxies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  detail_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_group ON accounts(account_group_id);
CREATE INDEX IF NOT EXISTS idx_groups_status ON telegram_groups(status, approved, enabled);
CREATE INDEX IF NOT EXISTS idx_attempts_account_time ON task_attempts(account_id, started_at);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self.initialize()

    def initialize(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.execute(
                "INSERT OR REPLACE INTO app_meta(key,value) VALUES('schema_version','2')"
            )
            self._conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, params: Sequence[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, params)
            self._conn.commit()

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row else default

    def close(self) -> None:
        with self._lock:
            self._conn.close()

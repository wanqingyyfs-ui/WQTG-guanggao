from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.database import Database
from app.core.paths import AppPaths


ENV_SCHEMA_VERSION = 2

ENVIRONMENT_TEMPLATES = (
    {
        "platform_family": "Windows 11",
        "viewport_width": 1920,
        "viewport_height": 1080,
        "screen_width": 1920,
        "screen_height": 1080,
        "device_scale_factor": 1.0,
        "hardware_concurrency": 8,
        "device_memory": 8,
    },
    {
        "platform_family": "Windows 10",
        "viewport_width": 1536,
        "viewport_height": 864,
        "screen_width": 1536,
        "screen_height": 864,
        "device_scale_factor": 1.25,
        "hardware_concurrency": 4,
        "device_memory": 8,
    },
    {
        "platform_family": "Windows 11",
        "viewport_width": 1600,
        "viewport_height": 900,
        "screen_width": 1600,
        "screen_height": 900,
        "device_scale_factor": 1.0,
        "hardware_concurrency": 8,
        "device_memory": 16,
    },
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class EnvironmentProfileError(RuntimeError):
    pass


class EnvironmentProfileService:
    def __init__(self, db: Database, paths: AppPaths):
        self.db = db
        self.paths = paths

    def create_for_account(
        self,
        account_id: int,
        phone: str,
        *,
        locale: str = "en-US",
        timezone: str = "UTC",
    ) -> int:
        existing = self.db.query_one(
            "SELECT id FROM environment_profiles WHERE account_id=?", (account_id,)
        )
        if existing:
            return int(existing["id"])
        seed = int(hashlib.sha256(phone.encode("utf-8")).hexdigest()[:8], 16)
        template = ENVIRONMENT_TEMPLATES[seed % len(ENVIRONMENT_TEMPLATES)]
        languages = [locale, locale.split("-")[0]]
        cur = self.db.execute(
            """
            INSERT INTO environment_profiles(
              account_id,schema_version,browser_channel,platform_family,
              viewport_width,viewport_height,screen_width,screen_height,
              device_scale_factor,locale,language_list_json,timezone,
              hardware_concurrency,device_memory,webrtc_policy,generated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                account_id,
                ENV_SCHEMA_VERSION,
                "chromium",
                template["platform_family"],
                template["viewport_width"],
                template["viewport_height"],
                template["screen_width"],
                template["screen_height"],
                template["device_scale_factor"],
                locale,
                json.dumps(languages),
                timezone,
                template["hardware_concurrency"],
                template["device_memory"],
                "disable_non_proxied_udp",
                utc_now(),
            ),
        )
        env_id = int(cur.lastrowid)
        self.db.execute(
            "UPDATE accounts SET environment_profile_id=?, account_status='environment_ready' WHERE id=?",
            (env_id, account_id),
        )
        self.write_environment_file(account_id)
        return env_id

    def get_for_account(self, account_id: int) -> dict[str, Any]:
        row = self.db.query_one(
            "SELECT * FROM environment_profiles WHERE account_id=?", (account_id,)
        )
        if not row:
            raise EnvironmentProfileError("Environment profile is missing")
        data = dict(row)
        data["language_list"] = json.loads(data.pop("language_list_json"))
        if data.get("runtime_snapshot_json"):
            data["runtime_snapshot"] = json.loads(data["runtime_snapshot_json"])
        else:
            data["runtime_snapshot"] = None
        data.pop("runtime_snapshot_json", None)
        return data

    def finalize_runtime_snapshot(
        self,
        account_id: int,
        snapshot: dict[str, Any],
        *,
        browser_version: str,
        user_agent: str,
    ) -> None:
        row = self.db.query_one(
            """
            SELECT finalized,runtime_fingerprint_sha256,browser_version,user_agent
            FROM environment_profiles WHERE account_id=?
            """,
            (account_id,),
        )
        if not row:
            raise EnvironmentProfileError("Environment profile is missing")
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if int(row["finalized"]):
            if row["browser_version"] != browser_version or row["user_agent"] != user_agent:
                raise EnvironmentProfileError(
                    "Installed Chromium version or actual User-Agent changed after finalization"
                )
            if row["runtime_fingerprint_sha256"] != digest:
                raise EnvironmentProfileError(
                    "Runtime fingerprint changed after finalization; browser startup was blocked"
                )
            self.db.execute(
                "UPDATE environment_profiles SET last_verified_at=? WHERE account_id=?",
                (utc_now(), account_id),
            )
            return
        navigator = snapshot.get("navigator") or {}
        screen = snapshot.get("screen") or {}
        runtime_locale = str(snapshot.get("locale") or "")
        runtime_timezone = str(snapshot.get("timezone") or "")
        self.db.execute(
            """
            UPDATE environment_profiles
            SET browser_version=?,user_agent=?,platform_family=?,
                screen_width=?,screen_height=?,device_scale_factor=?,
                locale=?,language_list_json=?,timezone=?,hardware_concurrency=?,device_memory=?,
                runtime_snapshot_json=?,runtime_fingerprint_sha256=?,finalized=1,last_verified_at=?
            WHERE account_id=?
            """,
            (
                browser_version,
                user_agent,
                str(navigator.get("platform") or "unknown"),
                int(screen.get("width") or 0),
                int(screen.get("height") or 0),
                float(screen.get("devicePixelRatio") or 1.0),
                runtime_locale or str(navigator.get("language") or "en-US"),
                json.dumps(list(navigator.get("languages") or [])),
                runtime_timezone or "UTC",
                int(navigator.get("hardwareConcurrency") or 1),
                int(navigator.get("deviceMemory") or 0),
                canonical,
                digest,
                utc_now(),
                account_id,
            ),
        )
        self.write_environment_file(account_id)


    def align_to_account_group(self, account_id: int) -> None:
        row = self.db.query_one(
            """
            SELECT e.finalized,g.default_language,g.default_timezone,p.timezone proxy_timezone
            FROM environment_profiles e
            JOIN accounts a ON a.id=e.account_id
            LEFT JOIN account_groups g ON g.id=a.account_group_id
            LEFT JOIN static_proxies p ON p.id=COALESCE(a.proxy_override_id,g.static_proxy_id)
            WHERE e.account_id=?
            """,
            (account_id,),
        )
        if not row or row["default_language"] is None:
            return
        timezone = row["proxy_timezone"] or row["default_timezone"] or "UTC"
        locale = row["default_language"] or "en-US"
        if int(row["finalized"]):
            current = self.db.query_one(
                "SELECT locale,timezone FROM environment_profiles WHERE account_id=?", (account_id,)
            )
            if current and (current["locale"] != locale or current["timezone"] != timezone):
                raise EnvironmentProfileError(
                    "Finalized environment conflicts with the assigned proxy/group locale or timezone"
                )
            return
        self.db.execute(
            """
            UPDATE environment_profiles
            SET locale=?,language_list_json=?,timezone=?
            WHERE account_id=?
            """,
            (locale, json.dumps([locale, locale.split('-')[0]]), timezone, account_id),
        )
        self.write_environment_file(account_id)

    def write_environment_file(self, account_id: int) -> Path:
        account = self.db.query_one("SELECT profile_dir FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise EnvironmentProfileError("Account does not exist")
        path = Path(account["profile_dir"]) / "environment.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.get_for_account(account_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def regenerate(
        self,
        account_id: int,
        *,
        browser_stopped: bool,
        no_active_tasks: bool,
        profile_backup_exists: bool,
    ) -> None:
        if not (browser_stopped and no_active_tasks and profile_backup_exists):
            raise EnvironmentProfileError(
                "Regeneration requires a stopped browser, no active task, and a completed profile backup"
            )
        account = self.db.query_one("SELECT phone,country FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise EnvironmentProfileError("Account does not exist")
        self.db.execute("DELETE FROM environment_profiles WHERE account_id=?", (account_id,))
        self.create_for_account(account_id, account["phone"])

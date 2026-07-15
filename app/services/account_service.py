from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from app.core.audit import AuditLogger
from app.core.database import Database
from app.core.paths import AppPaths
from app.core.secrets import SecretStore
from app.services.environment_service import EnvironmentProfileService


class AccountImportError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_phone(raw: str, default_country: str = "US") -> str:
    del default_country  # Reserved for future libphonenumber integration.
    text = raw.strip()
    has_plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not 8 <= len(digits) <= 15:
        raise AccountImportError(f"Invalid phone number: {raw}")
    return "+" + digits if has_plus or digits else digits


def validate_verification_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AccountImportError("Verification URL must be an absolute HTTP/HTTPS URL")
    return value


class AccountService:
    def __init__(
        self,
        db: Database,
        paths: AppPaths,
        secrets: SecretStore,
        environments: EnvironmentProfileService,
        audit: AuditLogger,
    ):
        self.db = db
        self.paths = paths
        self.secrets = secrets
        self.environments = environments
        self.audit = audit

    def import_lines(self, text: str, *, default_country: str = "US") -> dict[str, object]:
        created: list[int] = []
        errors: list[str] = []
        for line_no, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                if "|" not in line:
                    raise AccountImportError("Expected phone|verification_url")
                raw_phone, raw_url = line.split("|", 1)
                phone = normalize_phone(raw_phone, default_country)
                verification_url = validate_verification_url(raw_url)
                created.append(
                    self.create(phone, verification_url, country=default_country)
                )
            except Exception as exc:
                errors.append(f"Line {line_no}: {exc}")
        return {"created_ids": created, "errors": errors}

    def create(self, phone: str, verification_url: str, *, country: str = "US") -> int:
        phone = normalize_phone(phone, country)
        verification_url = validate_verification_url(verification_url)
        profile_dir = (self.paths.profiles / phone.lstrip("+")).resolve()
        if self.db.query_one("SELECT id FROM accounts WHERE phone=?", (phone,)):
            raise AccountImportError(f"Phone already exists: {phone}")
        if self.db.query_one("SELECT id FROM accounts WHERE profile_dir=?", (str(profile_dir),)):
            raise AccountImportError(f"Profile directory already exists: {profile_dir}")
        now = utc_now()
        encrypted_url = self.secrets.encrypt(verification_url)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO accounts(
                  phone,verification_url_encrypted,country,profile_dir,enabled,
                  account_status,login_status,created_at,updated_at
                ) VALUES(?,?,?,?,0,'pending','unknown',?,?)
                """,
                (phone, encrypted_url, country, str(profile_dir), now, now),
            )
            account_id = int(cur.lastrowid)
        for folder in ("chromium-data", "screenshots", "browser-logs"):
            (profile_dir / folder).mkdir(parents=True, exist_ok=True)
        self.environments.create_for_account(account_id, phone)
        (profile_dir / "account.json").write_text(
            '{\n  "account_id": %d,\n  "phone": "%s"\n}\n' % (account_id, phone),
            encoding="utf-8",
        )
        self.audit.write(
            "account.created",
            entity_type="account",
            entity_id=account_id,
            detail={"phone": phone, "profile_dir": str(profile_dir)},
        )
        return account_id

    def assign_group(self, account_id: int, group_id: int | None) -> None:
        if group_id is not None:
            compatibility = self.db.query_one(
                """
                SELECT e.finalized,e.locale environment_locale,e.timezone environment_timezone,
                       g.default_language,COALESCE(p.timezone,g.default_timezone) target_timezone
                FROM accounts a
                JOIN environment_profiles e ON e.account_id=a.id
                JOIN account_groups g ON g.id=?
                LEFT JOIN static_proxies p ON p.id=g.static_proxy_id
                WHERE a.id=?
                """,
                (group_id, account_id),
            )
            if not compatibility:
                raise AccountImportError("Account or account group does not exist")
            if int(compatibility["finalized"]) and (
                compatibility["environment_locale"] != compatibility["default_language"]
                or compatibility["environment_timezone"] != compatibility["target_timezone"]
            ):
                raise AccountImportError(
                    "Finalized environment conflicts with this account group; back up the profile and regenerate first"
                )
        self.db.execute(
            "UPDATE accounts SET account_group_id=?,enabled=0,updated_at=? WHERE id=?",
            (group_id, utc_now(), account_id),
        )
        self.environments.align_to_account_group(account_id)
        self.audit.write(
            "account.group_assigned",
            entity_type="account",
            entity_id=account_id,
            detail={"group_id": group_id},
        )

    def set_enabled(self, account_id: int, enabled: bool) -> None:
        if enabled:
            row = self.db.query_one(
                """
                SELECT a.account_group_id,COALESCE(a.proxy_override_id,g.static_proxy_id) proxy_id,
                       p.enabled proxy_enabled,p.last_status,p.expected_ip,p.timezone proxy_timezone,
                       e.timezone environment_timezone
                FROM accounts a
                LEFT JOIN account_groups g ON g.id=a.account_group_id
                LEFT JOIN static_proxies p ON p.id=COALESCE(a.proxy_override_id,g.static_proxy_id)
                LEFT JOIN environment_profiles e ON e.account_id=a.id
                WHERE a.id=?
                """,
                (account_id,),
            )
            if not row or not row["account_group_id"]:
                raise AccountImportError("Account must belong to an account group")
            if not row["proxy_id"] or not row["proxy_enabled"]:
                raise AccountImportError("Account requires an enabled static proxy")
            if not row["expected_ip"]:
                raise AccountImportError("Static proxy requires an expected exit IP before enabling")
            if row["last_status"] != "healthy":
                raise AccountImportError("Static proxy must pass health verification before enabling")
            if row["proxy_timezone"] and row["environment_timezone"] != row["proxy_timezone"]:
                raise AccountImportError("Environment timezone conflicts with the assigned static proxy")
        self.db.execute(
            "UPDATE accounts SET enabled=?,updated_at=? WHERE id=?",
            (1 if enabled else 0, utc_now(), account_id),
        )

    def list_accounts(self) -> list[dict[str, object]]:
        rows = self.db.query_all(
            """
            SELECT a.*,g.name group_name,b.status browser_status,b.current_url,b.exit_ip
            FROM accounts a
            LEFT JOIN account_groups g ON g.id=a.account_group_id
            LEFT JOIN browser_instances b ON b.account_id=a.id
            ORDER BY a.id
            """
        )
        return [dict(row) for row in rows]

    def delete(self, account_id: int, *, profile_deleted: bool = False) -> None:
        row = self.db.query_one("SELECT profile_dir FROM accounts WHERE id=?", (account_id,))
        if not row:
            return
        if not profile_deleted and Path(row["profile_dir"]).exists():
            raise AccountImportError("Profile still exists; back it up and delete it explicitly first")
        self.db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.audit.write("account.deleted", entity_type="account", entity_id=account_id)

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.audit import AuditLogger
from app.core.database import Database


class TaskPolicyError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TaskService:
    """Fail-closed task policy. It never auto-joins groups or bypasses platform warnings."""

    def __init__(self, db: Database, audit: AuditLogger):
        self.db = db
        self.audit = audit

    def validate_target(self, group_id: int) -> dict[str, object]:
        row = self.db.query_one("SELECT * FROM telegram_groups WHERE id=?", (group_id,))
        if not row:
            raise TaskPolicyError("Target group does not exist")
        if not int(row["enabled"]):
            raise TaskPolicyError("Target group is disabled")
        if not int(row["approved"]):
            raise TaskPolicyError("Target group is not on the authorized whitelist")
        if row["status"] != "verified" or not int(row["joined"]) or not int(row["can_send"]):
            raise TaskPolicyError("Target group is not verified as joined and writable")
        return dict(row)

    def validate_account_quota(self, account_id: int, *, min_interval_seconds: int, daily_limit: int) -> None:
        since_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        count = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM task_attempts WHERE account_id=? AND status='success' AND started_at>=?",
                (account_id, since_day),
                0,
            )
        )
        if daily_limit >= 0 and count >= daily_limit:
            raise TaskPolicyError("Daily account task limit reached")
        last = self.db.query_one(
            "SELECT started_at FROM task_attempts WHERE account_id=? ORDER BY started_at DESC LIMIT 1",
            (account_id,),
        )
        if last:
            last_dt = datetime.fromisoformat(last["started_at"])
            if datetime.now(UTC) - last_dt < timedelta(seconds=min_interval_seconds):
                raise TaskPolicyError("Account cooldown has not elapsed")

    def preflight(self, task_id: int, account_id: int, group_id: int) -> dict[str, object]:
        task = self.db.query_one(
            """
            SELECT t.*,g.daily_task_limit group_daily_limit,g.min_action_interval_seconds group_interval
            FROM tasks t JOIN account_groups g ON g.id=t.account_group_id
            WHERE t.id=? AND t.enabled=1
            """,
            (task_id,),
        )
        if not task:
            raise TaskPolicyError("Task is missing or disabled")
        account = self.db.query_one(
            "SELECT * FROM accounts WHERE id=? AND enabled=1 AND account_group_id=?",
            (account_id, task["account_group_id"]),
        )
        if not account:
            raise TaskPolicyError("Account is disabled or outside the task account group")
        target = self.validate_target(group_id)
        linked = self.db.query_one(
            "SELECT 1 FROM task_targets WHERE task_id=? AND telegram_group_id=?",
            (task_id, group_id),
        )
        if not linked:
            raise TaskPolicyError("Target is not assigned to this task")
        min_interval = max(int(task["min_interval_seconds"]), int(task["group_interval"]))
        daily_limit = min(int(task["daily_limit"]), int(task["group_daily_limit"]))
        self.validate_account_quota(
            account_id, min_interval_seconds=min_interval, daily_limit=daily_limit
        )
        last_target = self.db.query_one(
            """
            SELECT started_at FROM task_attempts
            WHERE telegram_group_id=? AND status='success'
            ORDER BY started_at DESC LIMIT 1
            """,
            (group_id,),
        )
        if last_target:
            last_target_dt = datetime.fromisoformat(last_target["started_at"])
            if datetime.now(UTC) - last_target_dt < timedelta(seconds=min_interval):
                raise TaskPolicyError("Target group cooldown has not elapsed")
        dedupe_window = int(task["dedupe_window_seconds"])
        if dedupe_window > 0:
            duplicate = self.db.query_one(
                """
                SELECT started_at FROM task_attempts
                WHERE telegram_group_id=? AND template_id=? AND status='success'
                ORDER BY started_at DESC LIMIT 1
                """,
                (group_id, task["template_id"]),
            )
            if duplicate:
                duplicate_dt = datetime.fromisoformat(duplicate["started_at"])
                if datetime.now(UTC) - duplicate_dt < timedelta(seconds=dedupe_window):
                    raise TaskPolicyError("Duplicate template suppression window is still active for this group")
        return {"task": dict(task), "account": dict(account), "target": target}

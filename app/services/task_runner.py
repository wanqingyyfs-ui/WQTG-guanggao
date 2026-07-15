from __future__ import annotations

import itertools
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.browser_runtime.manager import BrowserRuntimeManager
from app.core.audit import AuditLogger
from app.core.database import Database
from app.services.task_service import TaskPolicyError, TaskService


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TaskRunner:
    def __init__(
        self,
        db: Database,
        policy: TaskService,
        browsers: BrowserRuntimeManager,
        audit: AuditLogger,
    ):
        self.db = db
        self.policy = policy
        self.browsers = browsers
        self.audit = audit
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run_task(self, task_id: int, *, preview_confirmed: bool = False) -> dict[str, Any]:
        self._cancel.clear()
        task = self.db.query_one("SELECT * FROM tasks WHERE id=? AND enabled=1", (task_id,))
        if not task:
            raise TaskPolicyError("Task is missing or disabled")
        if int(task["require_preview"]) and not preview_confirmed:
            raise TaskPolicyError("This task requires an explicit send preview confirmation")
        accounts = self.db.query_all(
            "SELECT id FROM accounts WHERE account_group_id=? AND enabled=1 ORDER BY id",
            (task["account_group_id"],),
        )
        targets = self.db.query_all(
            """
            SELECT g.id,g.canonical_link FROM task_targets tt
            JOIN telegram_groups g ON g.id=tt.telegram_group_id
            WHERE tt.task_id=? ORDER BY g.id
            """,
            (task_id,),
        )
        template = self.db.query_one("SELECT * FROM templates WHERE id=? AND enabled=1", (task["template_id"],))
        if not accounts or not targets or not template:
            raise TaskPolicyError("Task requires enabled accounts, targets, and a template")
        assets = [
            row["file_path"]
            for row in self.db.query_all(
                "SELECT file_path FROM template_assets WHERE template_id=? ORDER BY sort_order,id",
                (template["id"],),
            )
            if Path(row["file_path"]).exists()
        ]
        run_id = int(
            self.db.execute(
                "INSERT INTO task_runs(task_id,started_at,status) VALUES(?,?,'running')",
                (task_id, utc_now()),
            ).lastrowid
        )
        success_count = 0
        failure_count = 0
        stop_reason = None
        account_cycle = itertools.cycle([int(row["id"]) for row in accounts])
        try:
            for target in targets:
                if self._cancel.is_set():
                    stop_reason = "cancelled_by_user"
                    break
                account_id = next(account_cycle)
                attempt_id = int(
                    self.db.execute(
                        """
                        INSERT INTO task_attempts(
                          run_id,account_id,telegram_group_id,template_id,status,started_at
                        ) VALUES(?,?,?,?, 'preflight',?)
                        """,
                        (run_id, account_id, int(target["id"]), int(template["id"]), utc_now()),
                    ).lastrowid
                )
                try:
                    self.policy.preflight(task_id, account_id, int(target["id"]))
                    self.browsers.start(account_id)
                    deadline = time.monotonic() + 75
                    while time.monotonic() < deadline:
                        status = self.db.scalar(
                            "SELECT status FROM browser_instances WHERE account_id=?", (account_id,)
                        )
                        if status == "running":
                            break
                        if status == "crashed":
                            raise RuntimeError("Browser failed during task preflight")
                        time.sleep(0.5)
                    else:
                        raise TimeoutError("Browser did not become ready")
                    self.db.execute(
                        "UPDATE task_attempts SET status='sending' WHERE id=?", (attempt_id,)
                    )
                    if template["template_type"] == "telegram_message_link":
                        source_link = str(template["telegram_message_link"] or "").strip()
                        if not source_link:
                            raise RuntimeError("Telegram message-link template is missing its source link")
                        result = self.browsers.request(
                            account_id,
                            "forward_message",
                            timeout_seconds=90,
                            source_link=source_link,
                            target_link=target["canonical_link"],
                        )
                    else:
                        result = self.browsers.request(
                            account_id,
                            "send_message",
                            timeout_seconds=90,
                            link=target["canonical_link"],
                            text=template["text_content"] or "",
                            asset_paths=assets,
                        )
                    status = str(result.get("status") or "failed")
                    if status == "success":
                        success_count += 1
                        self.db.execute(
                            "UPDATE task_attempts SET status='success',ended_at=? WHERE id=?",
                            (utc_now(), attempt_id),
                        )
                    elif status == "manual_required":
                        failure_count += 1
                        stop_reason = str(result.get("reason") or "manual_required")
                        self.db.execute(
                            """
                            UPDATE task_attempts SET status='manual_required',ended_at=?,error_code=?,error_message=?
                            WHERE id=?
                            """,
                            (utc_now(), stop_reason, str(result), attempt_id),
                        )
                        break
                    else:
                        failure_count += 1
                        self.db.execute(
                            """
                            UPDATE task_attempts SET status='failed',ended_at=?,error_code=?,error_message=?
                            WHERE id=?
                            """,
                            (utc_now(), str(result.get("reason") or "send_failed"), str(result), attempt_id),
                        )
                except Exception as exc:
                    failure_count += 1
                    self.db.execute(
                        """
                        UPDATE task_attempts SET status='failed',ended_at=?,error_code='exception',error_message=?
                        WHERE id=?
                        """,
                        (utc_now(), str(exc), attempt_id),
                    )
            final_status = "cancelled" if stop_reason == "cancelled_by_user" else "completed"
        except Exception as exc:
            final_status = "failed"
            stop_reason = str(exc)
            raise
        finally:
            self.db.execute(
                """
                UPDATE task_runs SET ended_at=?,status=?,success_count=?,failure_count=?,stop_reason=?
                WHERE id=?
                """,
                (utc_now(), final_status, success_count, failure_count, stop_reason, run_id),
            )
            self.audit.write(
                "task.run_completed",
                entity_type="task_run",
                entity_id=run_id,
                detail={
                    "task_id": task_id,
                    "status": final_status,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "stop_reason": stop_reason,
                },
            )
        return {
            "run_id": run_id,
            "status": final_status,
            "success_count": success_count,
            "failure_count": failure_count,
            "stop_reason": stop_reason,
        }

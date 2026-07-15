from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.browser_runtime.protocol import BrowserCommand
from app.browser_runtime.worker import browser_worker_main
from app.core.audit import AuditLogger
from app.core.database import Database
from app.core.models import AccountRuntimeConfig
from app.services.environment_service import EnvironmentProfileService, EnvironmentProfileError
from app.services.proxy_service import ProxyPolicyError, ProxyService


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class WorkerHandle:
    process: mp.Process
    connection: Any
    listener: threading.Thread


class BrowserRuntimeManager:
    def __init__(
        self,
        *,
        db: Database,
        environments: EnvironmentProfileService,
        proxies: ProxyService,
        audit: AuditLogger,
    ):
        self.db = db
        self.environments = environments
        self.proxies = proxies
        self.audit = audit
        self._workers: dict[int, WorkerHandle] = {}
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._lock = threading.RLock()
        self._pending_condition = threading.Condition(self._lock)
        self._pending_results: dict[str, dict[str, Any]] = {}
        self._selected: int | None = None
        self.proxy_check_url = "https://api.ipify.org?format=json"
        self.dns_check_url = "https://dns.google/resolve?name=telegram.org&type=A"

    def _runtime_config(self, account_id: int) -> AccountRuntimeConfig:
        account = self.db.query_one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise RuntimeError("Account does not exist")
        if not int(account["enabled"]):
            raise RuntimeError("Account is disabled")
        proxy = self.proxies.resolve_for_account(account_id)
        if self.db.scalar("SELECT last_status FROM static_proxies WHERE id=?", (proxy.id,)) != "healthy":
            raise ProxyPolicyError("Proxy has not passed HTTP health verification")
        environment = self.environments.get_for_account(account_id)
        return AccountRuntimeConfig(
            account_id=account_id,
            phone=account["phone"],
            profile_dir=Path(account["profile_dir"]),
            proxy=proxy,
            environment=environment,
            proxy_check_url=self.proxy_check_url,
        )

    def start(self, account_id: int) -> None:
        with self._lock:
            existing = self._workers.get(account_id)
            if existing and existing.process.is_alive():
                return
            config = self._runtime_config(account_id)
            parent_conn, child_conn = mp.Pipe(duplex=True)
            payload = {
                "account_id": config.account_id,
                "phone": config.phone,
                "profile_dir": str(config.profile_dir),
                "proxy": config.proxy.playwright_dict(),
                "expected_ip": config.proxy.expected_ip,
                "proxy_id": config.proxy.id,
                "proxy_check_url": config.proxy_check_url,
                "dns_check_url": self.dns_check_url,
                "environment": config.environment,
            }
            process = mp.Process(
                target=browser_worker_main,
                args=(child_conn, payload),
                name=f"BrowserWorker-{account_id}",
                daemon=True,
            )
            process.start()
            child_conn.close()
            listener = threading.Thread(
                target=self._listen,
                args=(account_id, parent_conn),
                name=f"BrowserListener-{account_id}",
                daemon=True,
            )
            listener.start()
            self._workers[account_id] = WorkerHandle(process, parent_conn, listener)
            self.db.execute(
                """
                INSERT INTO browser_instances(account_id,pid,status,started_at,last_heartbeat_at)
                VALUES(?,?, 'starting',?,?)
                ON CONFLICT(account_id) DO UPDATE SET pid=excluded.pid,status='starting',
                  started_at=excluded.started_at,last_heartbeat_at=excluded.last_heartbeat_at,last_error=NULL
                """,
                (account_id, process.pid, utc_now(), utc_now()),
            )
            self.db.execute(
                "UPDATE accounts SET account_status='browser_starting',updated_at=? WHERE id=?",
                (utc_now(), account_id),
            )
            self.audit.write("browser.start_requested", entity_type="account", entity_id=account_id)
            if self._selected is None:
                self.select(account_id)

    def _listen(self, account_id: int, connection: Any) -> None:
        try:
            while True:
                try:
                    event = connection.recv()
                except (EOFError, OSError):
                    break
                self._handle_event(event)
                self._events.put(event)
                if event.get("name") == "stopped":
                    break
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _handle_event(self, event: dict[str, Any]) -> None:
        account_id = int(event["account_id"])
        name = event["name"]
        payload = event.get("payload") or {}
        if name == "runtime_ready":
            environment_error = None
            try:
                self.environments.finalize_runtime_snapshot(
                    account_id,
                    payload["snapshot"],
                    browser_version=payload["browser_version"],
                    user_agent=payload["user_agent"],
                )
            except EnvironmentProfileError as exc:
                environment_error = str(exc)
                try:
                    self.send(account_id, "stop")
                except Exception:
                    pass
            proxy_id = self.db.scalar(
                """SELECT COALESCE(a.proxy_override_id,g.static_proxy_id)
                   FROM accounts a LEFT JOIN account_groups g ON g.id=a.account_group_id WHERE a.id=?""",
                (account_id,),
            )
            if proxy_id is not None:
                self.proxies.record_browser_check(
                    int(proxy_id),
                    success=environment_error is None,
                    browser_exit_ip=payload.get("exit_ip"),
                    webrtc_safe=bool(payload.get("webrtc_safe")),
                    dns_request_safe=bool(payload.get("dns_request_safe")),
                    error=environment_error,
                )
            if environment_error:
                self.db.execute(
                    "UPDATE browser_instances SET status='crashed',last_error=? WHERE account_id=?",
                    (environment_error, account_id),
                )
                self.db.execute(
                    "UPDATE accounts SET account_status='error',updated_at=? WHERE id=?",
                    (utc_now(), account_id),
                )
            else:
                self.db.execute(
                    "UPDATE browser_instances SET status='running',exit_ip=?,last_heartbeat_at=? WHERE account_id=?",
                    (payload.get("exit_ip"), utc_now(), account_id),
                )
        elif name == "heartbeat":
            self.db.execute(
                "UPDATE browser_instances SET last_heartbeat_at=? WHERE account_id=?",
                (utc_now(), account_id),
            )
        elif name == "page_state":
            login_status = "logged_in" if payload.get("logged_in") else "login_required"
            account_status = "ready" if payload.get("logged_in") else "login_required"
            self.db.execute(
                "UPDATE browser_instances SET current_url=?,current_title=?,last_heartbeat_at=? WHERE account_id=?",
                (payload.get("url"), payload.get("title"), utc_now(), account_id),
            )
            self.db.execute(
                "UPDATE accounts SET login_status=?,account_status=?,updated_at=? WHERE id=?",
                (login_status, account_status, utc_now(), account_id),
            )
        elif name == "command_result":
            request_id = payload.get("request_id")
            if request_id:
                with self._pending_condition:
                    self._pending_results[str(request_id)] = payload
                    self._pending_condition.notify_all()
        elif name == "fatal_error":
            self.audit.write(
                "browser.fatal_error",
                entity_type="account",
                entity_id=account_id,
                detail={"error": payload.get("error")},
            )
            self.db.execute(
                "UPDATE browser_instances SET status='crashed',last_error=? WHERE account_id=?",
                (payload.get("error"), account_id),
            )
            self.db.execute(
                "UPDATE accounts SET account_status='error',updated_at=? WHERE id=?",
                (utc_now(), account_id),
            )
        elif name == "stopped":
            self.audit.write("browser.stopped", entity_type="account", entity_id=account_id)
            self.db.execute(
                "UPDATE browser_instances SET status='stopped',selected_visible=0 WHERE account_id=?",
                (account_id,),
            )
            self.db.execute(
                "UPDATE accounts SET account_status='stopped',updated_at=? WHERE id=?",
                (utc_now(), account_id),
            )

    def send(self, account_id: int, name: str, **payload: Any) -> None:
        with self._lock:
            handle = self._workers.get(account_id)
            if not handle or not handle.process.is_alive():
                raise RuntimeError("Browser worker is not running")
            handle.connection.send(BrowserCommand(name, payload).as_dict())

    def request(
        self, account_id: int, name: str, *, timeout_seconds: float = 60.0, **payload: Any
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        payload["request_id"] = request_id
        self.send(account_id, name, **payload)
        deadline = time.monotonic() + timeout_seconds
        with self._pending_condition:
            while request_id not in self._pending_results:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Browser command timed out: {name}")
                self._pending_condition.wait(timeout=min(remaining, 1.0))
            event_payload = self._pending_results.pop(request_id)
        return dict(event_payload.get("result") or {})

    def select(self, account_id: int) -> None:
        with self._lock:
            if account_id not in self._workers:
                raise RuntimeError("Browser worker is not running")
            for current_id, handle in self._workers.items():
                if handle.process.is_alive():
                    handle.connection.send(
                        BrowserCommand("set_visible", {"visible": current_id == account_id}).as_dict()
                    )
            self.db.execute("UPDATE browser_instances SET selected_visible=0")
            self.db.execute(
                "UPDATE browser_instances SET selected_visible=1 WHERE account_id=?", (account_id,)
            )
            self._selected = account_id

    def stop(self, account_id: int) -> None:
        with self._lock:
            handle = self._workers.get(account_id)
            if not handle:
                return
            if handle.process.is_alive():
                try:
                    handle.connection.send(BrowserCommand("stop").as_dict())
                    handle.process.join(timeout=8)
                except Exception:
                    pass
                if handle.process.is_alive():
                    handle.process.terminate()
                    handle.process.join(timeout=3)
            try:
                handle.connection.close()
            except Exception:
                pass
            self._workers.pop(account_id, None)
            if self._selected == account_id:
                self._selected = None

    def start_all(self) -> list[tuple[int, str]]:
        errors: list[tuple[int, str]] = []
        for row in self.db.query_all("SELECT id FROM accounts WHERE enabled=1 ORDER BY id"):
            try:
                self.start(int(row["id"]))
            except Exception as exc:
                errors.append((int(row["id"]), str(exc)))
        return errors

    def stop_all(self) -> None:
        for account_id in list(self._workers):
            self.stop(account_id)

    def poll_events(self, limit: int = 100) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for _ in range(limit):
            try:
                result.append(self._events.get_nowait())
            except queue.Empty:
                break
        return result

    @property
    def selected_account_id(self) -> int | None:
        return self._selected

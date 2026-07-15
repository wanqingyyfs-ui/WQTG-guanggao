from __future__ import annotations

import ipaddress
import time
from datetime import UTC, datetime
from typing import Any

import requests

from app.core.audit import AuditLogger
from app.core.database import Database
from app.core.models import ProxyConfig
from app.core.secrets import SecretStore


class ProxyPolicyError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ProxyService:
    def __init__(self, db: Database, secrets: SecretStore, audit: AuditLogger):
        self.db = db
        self.secrets = secrets
        self.audit = audit

    def create(
        self,
        *,
        protocol: str,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        expected_ip: str = "",
        country: str = "",
        region: str = "",
        timezone: str = "UTC",
    ) -> int:
        protocol = protocol.lower().strip()
        if protocol not in {"http", "https", "socks5"}:
            raise ProxyPolicyError("Unsupported proxy protocol")
        if not host.strip() or not 1 <= int(port) <= 65535:
            raise ProxyPolicyError("Invalid proxy host or port")
        if expected_ip:
            ipaddress.ip_address(expected_ip.strip())
        encrypted = self.secrets.encrypt(password) if password else None
        cur = self.db.execute(
            """
            INSERT INTO static_proxies(
              protocol,host,port,username,password_encrypted,expected_ip,country,region,timezone
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                protocol,
                host.strip(),
                int(port),
                username.strip() or None,
                encrypted,
                expected_ip.strip() or None,
                country.strip() or None,
                region.strip() or None,
                timezone.strip() or "UTC",
            ),
        )
        return int(cur.lastrowid)

    def resolve_for_account(self, account_id: int) -> ProxyConfig:
        row = self.db.query_one(
            """
            SELECT p.* FROM accounts a
            LEFT JOIN account_groups g ON g.id=a.account_group_id
            LEFT JOIN static_proxies p ON p.id=COALESCE(a.proxy_override_id,g.static_proxy_id)
            WHERE a.id=?
            """,
            (account_id,),
        )
        if not row or row["id"] is None:
            raise ProxyPolicyError("No static proxy is assigned")
        if not int(row["enabled"]):
            raise ProxyPolicyError("Assigned proxy is disabled")
        return ProxyConfig(
            id=int(row["id"]),
            protocol=row["protocol"],
            host=row["host"],
            port=int(row["port"]),
            username=row["username"],
            password=self.secrets.decrypt(row["password_encrypted"]),
            expected_ip=row["expected_ip"],
            country=row["country"],
            region=row["region"],
            timezone=row["timezone"],
        )

    def test_http(
        self,
        proxy_id: int,
        *,
        check_url: str = "https://api.ipify.org?format=json",
        timeout_seconds: int = 15,
    ) -> dict[str, Any]:
        row = self.db.query_one("SELECT * FROM static_proxies WHERE id=?", (proxy_id,))
        if not row:
            raise ProxyPolicyError("Proxy does not exist")
        config = ProxyConfig(
            id=int(row["id"]),
            protocol=row["protocol"],
            host=row["host"],
            port=int(row["port"]),
            username=row["username"],
            password=self.secrets.decrypt(row["password_encrypted"]),
            expected_ip=row["expected_ip"],
            country=row["country"],
            region=row["region"],
            timezone=row["timezone"],
        )
        proxy_url = config.requests_url()
        started = time.perf_counter()
        success = False
        exit_ip = None
        error = None
        try:
            response = requests.get(
                check_url,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=timeout_seconds,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            exit_ip = str(payload.get("ip") or payload.get("origin") or "").split(",")[0].strip()
            if not exit_ip:
                raise ProxyPolicyError("Proxy check response did not contain an IP")
            ipaddress.ip_address(exit_ip)
            if config.expected_ip and exit_ip != config.expected_ip:
                raise ProxyPolicyError(
                    f"Unexpected exit IP: expected {config.expected_ip}, received {exit_ip}"
                )
            success = True
        except Exception as exc:
            error = str(exc)
        latency_ms = int((time.perf_counter() - started) * 1000)
        status = "healthy" if success else "blocked"
        self.db.execute(
            "UPDATE static_proxies SET last_status=?,last_checked_at=? WHERE id=?",
            (status, utc_now(), proxy_id),
        )
        self.db.execute(
            """
            INSERT INTO proxy_health_records(
              proxy_id,checked_at,success,http_exit_ip,latency_ms,error
            ) VALUES(?,?,?,?,?,?)
            """,
            (proxy_id, utc_now(), 1 if success else 0, exit_ip, latency_ms, error),
        )
        self.audit.write(
            "proxy.http_checked",
            entity_type="proxy",
            entity_id=proxy_id,
            detail={"success": success, "exit_ip": exit_ip, "latency_ms": latency_ms, "error": error},
        )
        return {"success": success, "exit_ip": exit_ip, "latency_ms": latency_ms, "error": error}

    def record_browser_check(
        self,
        proxy_id: int,
        *,
        success: bool,
        browser_exit_ip: str | None,
        webrtc_safe: bool,
        dns_request_safe: bool,
        error: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO proxy_health_records(
              proxy_id,checked_at,success,browser_exit_ip,webrtc_safe,dns_request_safe,error
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                proxy_id,
                utc_now(),
                1 if success else 0,
                browser_exit_ip,
                1 if webrtc_safe else 0,
                1 if dns_request_safe else 0,
                error,
            ),
        )

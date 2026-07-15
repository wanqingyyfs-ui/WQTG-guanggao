from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.core.audit import AuditLogger
from app.core.database import Database


class GroupLinkError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_group_link(raw: str) -> dict[str, str | None]:
    value = raw.strip()
    if not value:
        raise GroupLinkError("Empty group link")
    if value.startswith("@"):
        value = "https://t.me/" + value[1:]
    elif re.fullmatch(r"[A-Za-z0-9_]{5,}", value):
        value = "https://t.me/" + value
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc.lower().split(":")[0]
    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        raise GroupLinkError("Only t.me/telegram.me links are supported")
    path = parsed.path.strip("/")
    if not path:
        raise GroupLinkError("Telegram link does not contain a target")
    first = path.split("/", 1)[0]
    if first == "joinchat" and "/" in path:
        token = path.split("/", 1)[1]
        canonical = f"https://t.me/joinchat/{token}"
        return {"canonical_link": canonical, "username": None, "link_type": "private_invite"}
    if first.startswith("+"):
        return {
            "canonical_link": f"https://t.me/{first}",
            "username": None,
            "link_type": "private_invite",
        }
    if not re.fullmatch(r"[A-Za-z0-9_]{5,}", first):
        raise GroupLinkError("Invalid Telegram username or invite code")
    username = first.lower()
    return {
        "canonical_link": f"https://t.me/{username}",
        "username": username,
        "link_type": "public",
    }


class GroupService:
    def __init__(self, db: Database, audit: AuditLogger):
        self.db = db
        self.audit = audit

    def import_links(self, text: str) -> dict[str, object]:
        created: list[int] = []
        duplicates: list[str] = []
        errors: list[str] = []
        for line_no, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                parsed = normalize_group_link(raw)
                existing = self.db.query_one(
                    "SELECT id FROM telegram_groups WHERE canonical_link=?",
                    (parsed["canonical_link"],),
                )
                if existing:
                    duplicates.append(str(parsed["canonical_link"]))
                    continue
                cur = self.db.execute(
                    """
                    INSERT INTO telegram_groups(raw_link,canonical_link,username,link_type,status)
                    VALUES(?,?,?,?, 'pending')
                    """,
                    (raw.strip(), parsed["canonical_link"], parsed["username"], parsed["link_type"]),
                )
                created.append(int(cur.lastrowid))
            except Exception as exc:
                errors.append(f"Line {line_no}: {exc}")
        self.audit.write(
            "groups.imported",
            entity_type="telegram_group",
            detail={"created_count": len(created), "duplicate_count": len(duplicates), "errors": errors},
        )
        return {"created_ids": created, "duplicates": duplicates, "errors": errors}

    def apply_metadata(self, group_id: int, metadata: dict[str, object]) -> None:
        required = {"title", "current_url", "joined", "can_send", "read_only"}
        missing = required - metadata.keys()
        if missing:
            raise GroupLinkError(f"Incomplete browser metadata: {sorted(missing)}")
        observed = metadata.get("observed_chat_id")
        self.db.execute(
            """
            UPDATE telegram_groups SET
              title=?,description=?,visible_member_count=?,observed_chat_id=?,chat_type=?,
              joined=?,can_send=?,read_only=?,status=?,last_verified_at=?,last_error=NULL
            WHERE id=?
            """,
            (
                metadata.get("title"),
                metadata.get("description"),
                metadata.get("visible_member_count"),
                observed,
                metadata.get("chat_type"),
                1 if metadata.get("joined") else 0,
                1 if metadata.get("can_send") else 0,
                1 if metadata.get("read_only") else 0,
                "verified" if metadata.get("joined") else "manual_required",
                utc_now(),
                group_id,
            ),
        )

    def set_approved(self, group_id: int, approved: bool) -> None:
        row = self.db.query_one(
            "SELECT status,joined,can_send FROM telegram_groups WHERE id=?", (group_id,)
        )
        if not row:
            raise GroupLinkError("Group does not exist")
        if approved and not (
            row["status"] == "verified" and int(row["joined"]) and int(row["can_send"])
        ):
            raise GroupLinkError("Only verified, joined, writable groups can be approved")
        self.db.execute(
            "UPDATE telegram_groups SET approved=? WHERE id=?",
            (1 if approved else 0, group_id),
        )

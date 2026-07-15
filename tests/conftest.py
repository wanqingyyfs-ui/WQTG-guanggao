from __future__ import annotations

from pathlib import Path

import pytest

from app.core.audit import AuditLogger
from app.core.database import Database
from app.core.paths import AppPaths
from app.core.secrets import SecretStore
from app.services.account_service import AccountService
from app.services.environment_service import EnvironmentProfileService
from app.services.group_service import GroupService
from app.services.proxy_service import ProxyService
from app.services.task_service import TaskService


@pytest.fixture()
def services(tmp_path: Path):
    paths = AppPaths(
        root=tmp_path,
        database=tmp_path / "data" / "wqtg.db",
        profiles=tmp_path / "profiles",
        assets=tmp_path / "assets",
        logs=tmp_path / "logs",
        backups=tmp_path / "backups",
        secrets=tmp_path / "secrets",
    )
    paths.ensure()
    db = Database(paths.database)
    secrets = SecretStore(paths.secrets)
    audit = AuditLogger(db)
    environments = EnvironmentProfileService(db, paths)
    accounts = AccountService(db, paths, secrets, environments, audit)
    proxies = ProxyService(db, secrets, audit)
    groups = GroupService(db, audit)
    tasks = TaskService(db, audit)
    yield {
        "paths": paths,
        "db": db,
        "secrets": secrets,
        "audit": audit,
        "environments": environments,
        "accounts": accounts,
        "proxies": proxies,
        "groups": groups,
        "tasks": tasks,
    }
    db.close()

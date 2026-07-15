from __future__ import annotations

from dataclasses import dataclass

from app.browser_runtime.manager import BrowserRuntimeManager
from app.core.audit import AuditLogger
from app.core.database import Database
from app.core.paths import AppPaths
from app.core.secrets import SecretStore
from app.services.account_service import AccountService
from app.services.environment_service import EnvironmentProfileService
from app.services.group_service import GroupService
from app.services.proxy_service import ProxyService
from app.services.task_service import TaskService
from app.services.task_runner import TaskRunner
from app.services.task_scheduler import TaskScheduler


@dataclass
class AppContext:
    paths: AppPaths
    db: Database
    secrets: SecretStore
    audit: AuditLogger
    environments: EnvironmentProfileService
    accounts: AccountService
    proxies: ProxyService
    groups: GroupService
    tasks: TaskService
    browsers: BrowserRuntimeManager
    task_runner: TaskRunner
    scheduler: TaskScheduler

    @classmethod
    def create(cls) -> "AppContext":
        paths = AppPaths.discover()
        db = Database(paths.database)
        secrets = SecretStore(paths.secrets)
        audit = AuditLogger(db)
        environments = EnvironmentProfileService(db, paths)
        accounts = AccountService(db, paths, secrets, environments, audit)
        proxies = ProxyService(db, secrets, audit)
        groups = GroupService(db, audit)
        tasks = TaskService(db, audit)
        browsers = BrowserRuntimeManager(
            db=db,
            environments=environments,
            proxies=proxies,
            audit=audit,
        )
        task_runner = TaskRunner(db, tasks, browsers, audit)
        scheduler = TaskScheduler(db, task_runner, audit)
        return cls(
            paths,
            db,
            secrets,
            audit,
            environments,
            accounts,
            proxies,
            groups,
            tasks,
            browsers,
            task_runner,
            scheduler,
        )

    def close(self) -> None:
        self.scheduler.stop()
        self.browsers.stop_all()
        self.db.close()

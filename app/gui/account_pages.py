from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
import time

from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.context import AppContext
from app.gui.common import DataTable, error, info, selected_id
from app.gui.workers import FunctionThread

class DashboardPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        for label, callback in (
            ("刷新", self.refresh),
            ("全部启动", self.start_all),
            ("全部停止", self.stop_all),
            ("启动任务调度器", self.context.scheduler.start),
            ("停止任务调度器", self.context.scheduler.stop),
            ("紧急停止全部自动化", self.emergency_stop),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = DataTable(
            ["ID", "手机号", "账号组", "账号状态", "登录状态", "浏览器", "出口IP", "当前页面", "最后错误"]
        )
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        accounts = self.context.accounts.list_accounts()
        healthy = self.context.db.scalar("SELECT COUNT(*) FROM static_proxies WHERE last_status='healthy'", default=0)
        running = self.context.db.scalar("SELECT COUNT(*) FROM browser_instances WHERE status='running'", default=0)
        ready = self.context.db.scalar("SELECT COUNT(*) FROM accounts WHERE account_status='ready'", default=0)
        scheduler = "运行中" if self.context.scheduler.running else "已停止"
        self.summary.setText(
            f"账号 {len(accounts)} ｜ 已就绪 {ready} ｜ 浏览器运行 {running} ｜ 健康代理 {healthy} ｜ 调度器 {scheduler}"
        )
        self.table.set_rows(
            [
                [
                    row["id"], row["phone"], row.get("group_name"), row["account_status"],
                    row["login_status"], row.get("browser_status"), row.get("exit_ip"),
                    row.get("current_url"), row.get("last_error"),
                ]
                for row in accounts
            ]
        )

    def start_all(self) -> None:
        failures = self.context.browsers.start_all()
        self.refresh()
        info(self, "已提交全部启用账号。" if not failures else f"部分账号未启动：{failures}")

    def stop_all(self) -> None:
        self.context.browsers.stop_all()
        self.refresh()

    def emergency_stop(self) -> None:
        self.context.scheduler.stop()
        self.context.task_runner.cancel()
        self.context.browsers.stop_all()
        self.refresh()


class AccountsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        layout = QVBoxLayout(self)
        self.import_text = QTextEdit()
        self.import_text.setPlaceholderText("每行：手机号|验证码网址")
        self.import_text.setMaximumHeight(130)
        layout.addWidget(self.import_text)
        controls = QHBoxLayout()
        buttons = (
            ("批量导入", self.import_accounts),
            ("分配账号组", self.assign_group),
            ("启用", lambda: self.toggle_enabled(True)),
            ("禁用", lambda: self.toggle_enabled(False)),
            ("启动浏览器", self.start_selected),
            ("停止浏览器", self.stop_selected),
            ("登录并读取验证码", self.login_selected),
            ("刷新", self.refresh),
        )
        for label, callback in buttons:
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.table = DataTable(
            ["ID", "手机号", "账号组", "启用", "账号状态", "登录状态", "Profile", "环境ID"]
        )
        layout.addWidget(self.table)
        self._threads: list[FunctionThread] = []
        self.refresh()

    def refresh(self) -> None:
        rows = self.context.accounts.list_accounts()
        self.table.set_rows(
            [[r["id"], r["phone"], r.get("group_name"), bool(r["enabled"]), r["account_status"], r["login_status"], r["profile_dir"], r["environment_profile_id"]] for r in rows]
        )

    def import_accounts(self) -> None:
        result = self.context.accounts.import_lines(self.import_text.toPlainText())
        self.refresh()
        info(self, f"导入 {len(result['created_ids'])} 个账号。\n" + "\n".join(result["errors"]))

    def assign_group(self) -> None:
        account_id = selected_id(self.table)
        if account_id is None:
            return
        groups = self.context.db.query_all("SELECT id,name FROM account_groups WHERE enabled=1 ORDER BY name")
        if not groups:
            error(self, "请先在“账号组与静态IP”页面创建账号组。")
            return
        labels = [f"{r['id']} | {r['name']}" for r in groups]
        value, ok = QInputDialog.getItem(self, "分配账号组", "账号组", labels, editable=False)
        if ok:
            self.context.accounts.assign_group(account_id, int(value.split("|", 1)[0]))
            self.refresh()

    def toggle_enabled(self, enabled: bool) -> None:
        account_id = selected_id(self.table)
        if account_id is None:
            return
        try:
            self.context.accounts.set_enabled(account_id, enabled)
            self.refresh()
        except Exception as exc:
            error(self, str(exc))

    def start_selected(self) -> None:
        account_id = selected_id(self.table)
        if account_id is None:
            return
        try:
            self.context.browsers.start(account_id)
        except Exception as exc:
            error(self, str(exc))
        self.refresh()

    def stop_selected(self) -> None:
        account_id = selected_id(self.table)
        if account_id is not None:
            self.context.browsers.stop(account_id)
            self.refresh()

    def login_selected(self) -> None:
        account_id = selected_id(self.table)
        if account_id is None:
            return
        account = self.context.db.query_one("SELECT phone,verification_url_encrypted FROM accounts WHERE id=?", (account_id,))
        def job() -> dict[str, Any]:
            self.context.browsers.start(account_id)
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                status = self.context.db.scalar("SELECT status FROM browser_instances WHERE account_id=?", (account_id,))
                if status == "running":
                    break
                if status == "crashed":
                    raise RuntimeError("浏览器启动失败，请查看诊断和最后错误。")
                time.sleep(0.5)
            self.context.browsers.send(account_id, "login_start", phone=account["phone"])
            time.sleep(2)
            url = self.context.secrets.decrypt(account["verification_url_encrypted"])
            result = self.context.browsers.request(account_id, "read_verification", timeout_seconds=60, url=url)
            if not result.get("code"):
                return {"status": "manual_required", "reason": "验证码页面未识别到验证码"}
            self.context.browsers.send(account_id, "submit_code", code=result["code"])
            if result.get("two_factor_password"):
                time.sleep(2)
                self.context.browsers.send(account_id, "submit_2fa", password=result["two_factor_password"])
            return {"status": "submitted"}
        thread = FunctionThread(job, self)
        thread.succeeded.connect(lambda result: info(self, f"登录流程结果：{result}"))
        thread.failed.connect(lambda text: error(self, text))
        thread.finished.connect(self.refresh)
        self._threads.append(thread)
        thread.start()


class ProxyGroupsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        tabs = QTabWidget(self)
        root = QVBoxLayout(self)
        root.addWidget(tabs)
        proxy_tab = QWidget()
        group_tab = QWidget()
        tabs.addTab(proxy_tab, "静态代理")
        tabs.addTab(group_tab, "账号组")
        p_layout = QVBoxLayout(proxy_tab)
        p_controls = QHBoxLayout()
        for label, callback in (("新增代理", self.add_proxy), ("测试代理", self.test_proxy), ("刷新", self.refresh)):
            button = QPushButton(label); button.clicked.connect(callback); p_controls.addWidget(button)
        p_controls.addStretch(); p_layout.addLayout(p_controls)
        self.proxy_table = DataTable(["ID", "协议", "主机", "端口", "用户名", "预期IP", "地区", "时区", "状态", "最后检测"])
        p_layout.addWidget(self.proxy_table)
        g_layout = QVBoxLayout(group_tab)
        g_controls = QHBoxLayout()
        for label, callback in (("新增账号组", self.add_group), ("刷新", self.refresh)):
            button = QPushButton(label); button.clicked.connect(callback); g_controls.addWidget(button)
        g_controls.addStretch(); g_layout.addLayout(g_controls)
        self.group_table = DataTable(["ID", "名称", "代理ID", "国家", "语言", "时区", "并发", "最小间隔", "每日上限", "启用"])
        g_layout.addWidget(self.group_table)
        self._threads: list[FunctionThread] = []
        self.refresh()

    def refresh(self) -> None:
        proxies = self.context.db.query_all("SELECT * FROM static_proxies ORDER BY id")
        self.proxy_table.set_rows([[r["id"],r["protocol"],r["host"],r["port"],r["username"],r["expected_ip"],r["country"],r["timezone"],r["last_status"],r["last_checked_at"]] for r in proxies])
        groups = self.context.db.query_all("SELECT * FROM account_groups ORDER BY id")
        self.group_table.set_rows([[r["id"],r["name"],r["static_proxy_id"],r["default_country"],r["default_language"],r["default_timezone"],r["max_concurrent_browsers"],r["min_action_interval_seconds"],r["daily_task_limit"],bool(r["enabled"])] for r in groups])

    def add_proxy(self) -> None:
        text, ok = QInputDialog.getText(self, "新增静态代理", "格式：协议://用户名:密码@主机:端口|预期出口IP")
        if not ok or not text.strip(): return
        try:
            proxy_text, _, expected = text.strip().partition("|")
            parsed = urlparse(proxy_text)
            proxy_id = self.context.proxies.create(protocol=parsed.scheme,host=parsed.hostname or "",port=parsed.port or 0,username=parsed.username or "",password=parsed.password or "",expected_ip=expected.strip())
            info(self, f"已创建代理 {proxy_id}")
            self.refresh()
        except Exception as exc: error(self, str(exc))

    def test_proxy(self) -> None:
        proxy_id = selected_id(self.proxy_table)
        if proxy_id is None: return
        thread = FunctionThread(lambda: self.context.proxies.test_http(proxy_id), self)
        thread.succeeded.connect(lambda result: info(self, f"代理检测结果：{result}"))
        thread.failed.connect(lambda text: error(self, text))
        thread.finished.connect(self.refresh)
        self._threads.append(thread); thread.start()

    def add_group(self) -> None:
        name, ok = QInputDialog.getText(self, "新增账号组", "组名称")
        if not ok or not name.strip(): return
        proxies = self.context.db.query_all("SELECT id,host,port FROM static_proxies WHERE enabled=1 ORDER BY id")
        if not proxies: error(self, "请先创建静态代理。" ); return
        labels = [f"{r['id']} | {r['host']}:{r['port']}" for r in proxies]
        proxy_value, ok = QInputDialog.getItem(self, "选择代理", "静态代理", labels, editable=False)
        if not ok: return
        self.context.db.execute("INSERT INTO account_groups(name,static_proxy_id) VALUES(?,?)", (name.strip(), int(proxy_value.split("|",1)[0])))
        self.refresh()



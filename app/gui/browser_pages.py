from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.context import AppContext
from app.gui.common import DataTable, error, info, selected_id
from app.gui.workbench import BrowserCanvas
from app.gui.workers import FunctionThread

class BrowserWorkbenchPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.url = QLineEdit("https://web.telegram.org/k/")
        controls.addWidget(self.url, 1)
        for label, callback in (("启动", self.start), ("停止", self.stop), ("打开", self.navigate), ("刷新页面", self.reload), ("刷新账号", self.refresh_accounts)):
            button=QPushButton(label); button.clicked.connect(callback); controls.addWidget(button)
        self.pick_mode = QCheckBox("定位拾取模式")
        controls.addWidget(self.pick_mode)
        layout.addLayout(controls)
        splitter = QSplitter()
        self.accounts = DataTable(["ID", "手机号", "状态", "当前URL"])
        self.accounts.setMaximumWidth(430)
        self.accounts.itemSelectionChanged.connect(self.select_account)
        self.canvas = BrowserCanvas()
        self.canvas.browser_click.connect(self.click_browser)
        self.canvas.browser_key.connect(self.key_browser)
        self.details = QTextEdit(); self.details.setReadOnly(True); self.details.setMaximumWidth(360)
        self._threads: list[FunctionThread] = []
        splitter.addWidget(self.accounts); splitter.addWidget(self.canvas); splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        self.refresh_accounts()

    def refresh_accounts(self) -> None:
        rows = self.context.db.query_all("""SELECT a.id,a.phone,COALESCE(b.status,'not_created') status,b.current_url FROM accounts a LEFT JOIN browser_instances b ON b.account_id=a.id ORDER BY a.id""")
        self.accounts.set_rows([[r["id"],r["phone"],r["status"],r["current_url"]] for r in rows])

    def current_account(self) -> int | None: return selected_id(self.accounts)
    def start(self) -> None:
        account_id=self.current_account()
        if account_id is None: return
        try: self.context.browsers.start(account_id); self.context.browsers.select(account_id)
        except Exception as exc: error(self,str(exc))
        self.refresh_accounts()
    def stop(self) -> None:
        account_id=self.current_account()
        if account_id is not None: self.context.browsers.stop(account_id); self.refresh_accounts()
    def select_account(self) -> None:
        account_id=self.current_account()
        if account_id is None:return
        try:self.context.browsers.select(account_id)
        except Exception:pass
        row=self.context.db.query_one("""SELECT a.phone,a.profile_dir,a.login_status,e.*,b.* FROM accounts a LEFT JOIN environment_profiles e ON e.account_id=a.id LEFT JOIN browser_instances b ON b.account_id=a.id WHERE a.id=?""",(account_id,))
        if row:self.details.setPlainText(json.dumps(dict(row),ensure_ascii=False,indent=2,default=str))
    def navigate(self) -> None:
        account_id=self.current_account()
        if account_id is not None:
            try:self.context.browsers.send(account_id,"navigate",url=self.url.text().strip())
            except Exception as exc:error(self,str(exc))
    def reload(self) -> None:
        account_id=self.current_account()
        if account_id is not None:
            try:self.context.browsers.send(account_id,"reload")
            except Exception as exc:error(self,str(exc))
    def click_browser(self,x:float,y:float)->None:
        account_id=self.current_account()
        if account_id is None:return
        if self.pick_mode.isChecked():
            thread=FunctionThread(lambda:self.context.browsers.request(account_id,"pick_element",timeout_seconds=20,x=x,y=y),self)
            thread.succeeded.connect(lambda result:self.details.setPlainText(json.dumps(result,ensure_ascii=False,indent=2)))
            thread.failed.connect(lambda text:error(self,text))
            self._threads.append(thread);thread.start()
            return
        try:self.context.browsers.send(account_id,"click",x=x,y=y)
        except Exception:pass
    def key_browser(self,key:str)->None:
        account_id=self.current_account()
        if account_id is None:return
        try:
            if key.startswith("text:"):self.context.browsers.send(account_id,"type",text=key[5:])
            else:self.context.browsers.send(account_id,"press",key=key)
        except Exception:pass
    def handle_event(self,event:dict[str,Any])->None:
        if event["name"]=="frame" and event["account_id"]==self.context.browsers.selected_account_id:
            payload=event["payload"];self.canvas.set_frame(payload["image_base64"],payload["width"],payload["height"])
        elif event["name"] in {"page_state","fatal_error","runtime_ready","stopped"}:self.refresh_accounts()


class GroupsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__(); self.context=context; layout=QVBoxLayout(self)
        self.links=QTextEdit();self.links.setPlaceholderText("每行一个 t.me 群组链接");self.links.setMaximumHeight(120);layout.addWidget(self.links)
        controls=QHBoxLayout()
        for label,cb in (("导入链接",self.import_links),("浏览器解析",self.resolve_selected),("批准白名单",lambda:self.approve(True)),("取消批准",lambda:self.approve(False)),("刷新",self.refresh)):
            b=QPushButton(label);b.clicked.connect(cb);controls.addWidget(b)
        controls.addStretch();layout.addLayout(controls)
        self.table=DataTable(["ID","名称","标准链接","Username","可选ChatID","类型","已加入","可发言","已批准","状态","最后验证"]);layout.addWidget(self.table)
        self._threads=[];self.refresh()
    def refresh(self)->None:
        rows=self.context.db.query_all("SELECT * FROM telegram_groups ORDER BY id")
        self.table.set_rows([[r["id"],r["title"],r["canonical_link"],r["username"],r["observed_chat_id"],r["chat_type"],bool(r["joined"]),bool(r["can_send"]),bool(r["approved"]),r["status"],r["last_verified_at"]] for r in rows])
    def import_links(self)->None:
        result=self.context.groups.import_links(self.links.toPlainText());self.refresh();info(self,f"已导入 {len(result['created_ids'])}，重复 {len(result['duplicates'])}\n"+"\n".join(result["errors"]))
    def resolve_selected(self)->None:
        group_id=selected_id(self.table);account_id=self.context.browsers.selected_account_id
        if group_id is None:return
        if account_id is None:error(self,"请先在浏览器工作台启动并选中一个已登录账号。" );return
        link=self.context.db.scalar("SELECT canonical_link FROM telegram_groups WHERE id=?",(group_id,))
        thread=FunctionThread(lambda:self.context.browsers.request(account_id,"resolve_group",timeout_seconds=75,link=link),self)
        def done(result):self.context.groups.apply_metadata(group_id,result);self.refresh();info(self,f"解析完成：{result}")
        thread.succeeded.connect(done);thread.failed.connect(lambda text:error(self,text));self._threads.append(thread);thread.start()
    def approve(self,value:bool)->None:
        group_id=selected_id(self.table)
        if group_id is None:return
        try:self.context.groups.set_approved(group_id,value);self.refresh()
        except Exception as exc:error(self,str(exc))



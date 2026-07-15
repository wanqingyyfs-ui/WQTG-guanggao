from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.context import AppContext
from app.gui.common import DataTable, error, info, now
from app.gui.workers import FunctionThread
from app.services.diagnostics import DiagnosticsService
from app.services.legacy_migration_service import LegacyMigrationService
from app.services.profile_backup_service import ProfileBackupService

class ProfileMaintenancePage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;layout=QVBoxLayout(self);layout.addWidget(QLabel("资料维护步骤统一进入所选账号 BrowserWorker 串行队列，不会重复打开 Profile。"))
        controls=QHBoxLayout()
        for key,label in (("profile.avatar","修改头像"),("profile.name","修改昵称"),("profile.username","修改用户名"),("profile.bio","修改简介"),("profile.folder","添加文件夹")):
            b=QPushButton(label);b.clicked.connect(lambda checked=False,k=key:self.add_step(k));controls.addWidget(b)
        execute_button=QPushButton("在当前账号执行工作流");execute_button.clicked.connect(self.execute_workflow);controls.addWidget(execute_button)
        controls.addStretch();layout.addLayout(controls)
        self.table=DataTable(["ID","工作流","步骤键","类型","参数","顺序","启用"]);layout.addWidget(self.table);self._threads=[];self.refresh()
    def add_step(self,key:str)->None:
        payload,ok=QInputDialog.getMultiLineText(self,"步骤参数","JSON 参数","{}")
        if not ok:return
        try:json.loads(payload)
        except Exception as exc:error(self,str(exc));return
        step_key=f"{key}.{int(datetime.now().timestamp())}";self.context.db.execute("INSERT INTO workflow_steps(workflow_key,step_key,step_type,payload_json,sort_order) VALUES('profile_maintenance',?,?,?,(SELECT COALESCE(MAX(sort_order),0)+1 FROM workflow_steps WHERE workflow_key='profile_maintenance'))",(step_key,key,payload));self.refresh()
    def execute_workflow(self)->None:
        account_id=self.context.browsers.selected_account_id
        if account_id is None:error(self,"请先在浏览器工作台选择一个运行账号。" );return
        rows=self.context.db.query_all("SELECT * FROM workflow_steps WHERE workflow_key='profile_maintenance' AND enabled=1 ORDER BY sort_order,id")
        if not rows:error(self,"当前没有启用的资料维护步骤。" );return
        steps=[]
        for row in rows:
            payload=json.loads(row["payload_json"])
            target_key=payload.get("target_key") or row["step_type"]
            locator=self.context.db.query_one("SELECT strategies_json,timeout_ms FROM locator_targets WHERE target_key=? AND enabled=1",(target_key,))
            if locator and not payload.get("strategies"):
                payload["strategies"]=json.loads(locator["strategies_json"]);payload.setdefault("timeout_ms",locator["timeout_ms"])
            steps.append({"step_key":row["step_key"],"step_type":row["step_type"],"payload":payload})
        thread=FunctionThread(lambda:self.context.browsers.request(account_id,"execute_workflow",timeout_seconds=180,steps=steps),self)
        thread.succeeded.connect(lambda result:info(self,f"工作流结果：{result}"));thread.failed.connect(lambda text:error(self,text));self._threads.append(thread);thread.start()

    def refresh(self)->None:
        rows=self.context.db.query_all("SELECT * FROM workflow_steps ORDER BY workflow_key,sort_order,id");self.table.set_rows([[r["id"],r["workflow_key"],r["step_key"],r["step_type"],r["payload_json"],r["sort_order"],bool(r["enabled"])] for r in rows])


class LocatorPage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;layout=QVBoxLayout(self);controls=QHBoxLayout()
        for label,cb in (("新增定位目标",self.add),("恢复默认定位",self.defaults),("刷新",self.refresh)):
            b=QPushButton(label);b.clicked.connect(cb);controls.addWidget(b)
        controls.addStretch();layout.addLayout(controls)
        self.table=DataTable(["ID","目标键","分类","策略","重试","超时ms","启用","更新时间"]);layout.addWidget(self.table);self.refresh()
    def add(self)->None:
        key,ok=QInputDialog.getText(self,"定位目标","唯一目标键")
        if not ok or not key.strip():return
        strategies,ok=QInputDialog.getMultiLineText(self,"定位策略","JSON 数组",'[ {"type":"css","value":"div[contenteditable=true]"} ]')
        if not ok:return
        try:json.loads(strategies)
        except Exception as exc:error(self,str(exc));return
        category=key.split('.',1)[0];self.context.db.execute("INSERT INTO locator_targets(target_key,category,strategies_json,updated_at) VALUES(?,?,?,?)",(key.strip(),category,strategies,now()));self.refresh()
    def defaults(self)->None:
        defaults={"login.phone":[{"type":"css","value":"input[type=tel]"}],"login.code":[{"type":"css","value":"input[autocomplete=one-time-code]"}],"message.input":[{"type":"css","value":"div[contenteditable=true]"}],"message.upload":[{"type":"css","value":"input[type=file]"}]}
        for key,value in defaults.items():self.context.db.execute("INSERT INTO locator_targets(target_key,category,strategies_json,updated_at) VALUES(?,?,?,?) ON CONFLICT(target_key) DO UPDATE SET strategies_json=excluded.strategies_json,updated_at=excluded.updated_at",(key,key.split('.',1)[0],json.dumps(value),now()))
        self.refresh()
    def refresh(self)->None:
        rows=self.context.db.query_all("SELECT * FROM locator_targets ORDER BY category,target_key");self.table.set_rows([[r["id"],r["target_key"],r["category"],r["strategies_json"],r["retry_count"],r["timeout_ms"],bool(r["enabled"]),r["updated_at"]] for r in rows])


class SettingsDiagnosticsPage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;layout=QVBoxLayout(self);controls=QHBoxLayout()
        for label,cb in (("运行完整自检",self.run_diagnostics),("备份所选账号Profile",self.backup_profile),("迁移旧版数据",self.migrate_legacy),("数据库路径",self.show_path)):
            b=QPushButton(label);b.clicked.connect(cb);controls.addWidget(b)
        controls.addStretch();layout.addLayout(controls)
        self.output=QTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output);self._threads=[]
    def run_diagnostics(self)->None:
        thread=FunctionThread(lambda:DiagnosticsService(self.context.db,self.context.paths).run(),self);thread.succeeded.connect(lambda r:self.output.setPlainText(json.dumps(r,ensure_ascii=False,indent=2)));thread.failed.connect(lambda t:error(self,t));self._threads.append(thread);thread.start()
    def backup_profile(self)->None:
        account_id,value=QInputDialog.getInt(self,"备份Profile","账号ID",1,1)
        if not value:return
        try:path=ProfileBackupService(self.context.db,self.context.paths).backup(account_id);info(self,f"备份完成：{path}")
        except Exception as exc:error(self,str(exc))
    def migrate_legacy(self)->None:
        directory=QFileDialog.getExistingDirectory(self,"选择旧版 config 目录")
        if not directory:return
        source=Path(directory)
        service=LegacyMigrationService(self.context.accounts,self.context.groups)
        backup=service.backup_legacy_root(source,self.context.paths.backups)
        result=service.migrate(source)
        self.output.setPlainText(json.dumps({"backup":str(backup),"migration":result},ensure_ascii=False,indent=2))
    def show_path(self)->None:self.output.setPlainText(str(self.context.paths.database))

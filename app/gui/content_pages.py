from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.core.context import AppContext
from app.gui.common import DataTable, error, info, now, selected_id
from app.gui.workers import FunctionThread

class TemplatesPage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;layout=QVBoxLayout(self);controls=QHBoxLayout()
        for label,cb in (("新增文本模板",self.add_text),("新增消息链接模板",self.add_message_link),("添加本地素材",self.add_asset),("刷新",self.refresh)):
            b=QPushButton(label);b.clicked.connect(cb);controls.addWidget(b)
        controls.addStretch();layout.addLayout(controls)
        self.table=DataTable(["ID","名称","类型","文本/消息链接","启用","素材数","更新时间"]);layout.addWidget(self.table);self.refresh()
    def refresh(self)->None:
        rows=self.context.db.query_all("""SELECT t.*,COUNT(a.id) asset_count FROM templates t LEFT JOIN template_assets a ON a.template_id=t.id GROUP BY t.id ORDER BY t.id""")
        self.table.set_rows([[r["id"],r["name"],r["template_type"],r["text_content"] or r["telegram_message_link"],bool(r["enabled"]),r["asset_count"],r["updated_at"]] for r in rows])
    def add_text(self)->None:
        name,ok=QInputDialog.getText(self,"模板名称","名称")
        if not ok or not name.strip():return
        text,ok=QInputDialog.getMultiLineText(self,"模板内容","文本")
        if not ok:return
        self.context.db.execute("INSERT INTO templates(name,template_type,text_content,created_at,updated_at) VALUES(?, 'text',?,?,?)",(name.strip(),text,now(),now()));self.refresh()
    def add_message_link(self)->None:
        name,ok=QInputDialog.getText(self,"模板名称","名称")
        if not ok or not name.strip():return
        link,ok=QInputDialog.getText(self,"Telegram消息链接","例如：https://t.me/channel_name/123")
        if not ok or not link.strip():return
        if not link.strip().startswith("https://t.me/"):
            error(self,"只支持完整的 https://t.me/... 消息链接。")
            return
        self.context.db.execute("INSERT INTO templates(name,template_type,telegram_message_link,created_at,updated_at) VALUES(?, 'telegram_message_link',?,?,?)",(name.strip(),link.strip(),now(),now()));self.refresh()

    def add_asset(self)->None:
        template_id=selected_id(self.table)
        if template_id is None:return
        files,_=QFileDialog.getOpenFileNames(self,"选择素材")
        for index,file_path in enumerate(files):
            path=Path(file_path);self.context.db.execute("INSERT INTO template_assets(template_id,file_path,sort_order,size_bytes) VALUES(?,?,?,?)",(template_id,str(path),index,path.stat().st_size))
        self.refresh()


class TasksPage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;self.runner=context.task_runner;layout=QVBoxLayout(self);controls=QHBoxLayout()
        for label,cb in (("新增任务",self.add_task),("分配全部已批准群组",self.assign_targets),("启用/禁用",self.toggle),("运行并确认预览",self.run_selected),("紧急停止",self.runner.cancel),("刷新",self.refresh)):
            b=QPushButton(label);b.clicked.connect(cb);controls.addWidget(b)
        controls.addStretch();layout.addLayout(controls)
        self.table=DataTable(["ID","名称","账号组","模板","最小间隔","每日上限","需预览","启用","目标数"]);layout.addWidget(self.table);self._threads=[];self.refresh()
    def refresh(self)->None:
        rows=self.context.db.query_all("""SELECT t.*,g.name group_name,p.name template_name,COUNT(tt.telegram_group_id) target_count FROM tasks t JOIN account_groups g ON g.id=t.account_group_id JOIN templates p ON p.id=t.template_id LEFT JOIN task_targets tt ON tt.task_id=t.id GROUP BY t.id ORDER BY t.id""")
        self.table.set_rows([[r["id"],r["name"],r["group_name"],r["template_name"],r["min_interval_seconds"],r["daily_limit"],bool(r["require_preview"]),bool(r["enabled"]),r["target_count"]] for r in rows])
    def add_task(self)->None:
        name,ok=QInputDialog.getText(self,"任务名称","名称")
        if not ok or not name.strip():return
        groups=self.context.db.query_all("SELECT id,name FROM account_groups WHERE enabled=1")
        templates=self.context.db.query_all("SELECT id,name FROM templates WHERE enabled=1")
        if not groups or not templates:error(self,"需要先创建账号组和模板。" );return
        glabels=[f"{r['id']} | {r['name']}" for r in groups];gval,ok=QInputDialog.getItem(self,"账号组","账号组",glabels,editable=False)
        if not ok:return
        tlabels=[f"{r['id']} | {r['name']}" for r in templates];tval,ok=QInputDialog.getItem(self,"模板","模板",tlabels,editable=False)
        if not ok:return
        self.context.db.execute("INSERT INTO tasks(name,account_group_id,template_id,created_at,updated_at) VALUES(?,?,?,?,?)",(name.strip(),int(gval.split('|',1)[0]),int(tval.split('|',1)[0]),now(),now()));self.refresh()
    def assign_targets(self)->None:
        task_id=selected_id(self.table)
        if task_id is None:return
        targets=self.context.db.query_all("SELECT id FROM telegram_groups WHERE approved=1 AND enabled=1 AND status='verified'")
        for row in targets:self.context.db.execute("INSERT OR IGNORE INTO task_targets(task_id,telegram_group_id) VALUES(?,?)",(task_id,row["id"]))
        self.refresh()
    def toggle(self)->None:
        task_id=selected_id(self.table)
        if task_id is None:return
        current=int(self.context.db.scalar("SELECT enabled FROM tasks WHERE id=?",(task_id,),0));self.context.db.execute("UPDATE tasks SET enabled=?,updated_at=? WHERE id=?",(0 if current else 1,now(),task_id));self.refresh()
    def run_selected(self)->None:
        task_id=selected_id(self.table)
        if task_id is None:return
        confirm=QMessageBox.question(self,"发送前预览确认","确认模板、账号范围和授权目标群组无误，并立即执行？")
        if confirm!=QMessageBox.StandardButton.Yes:return
        thread=FunctionThread(lambda:self.runner.run_task(task_id,preview_confirmed=True),self);thread.succeeded.connect(lambda r:info(self,f"任务完成：{r}"));thread.failed.connect(lambda t:error(self,t));self._threads.append(thread);thread.start()


class RecordsPage(QWidget):
    def __init__(self,context:AppContext):
        super().__init__();self.context=context;layout=QVBoxLayout(self);b=QPushButton("刷新");b.clicked.connect(self.refresh);layout.addWidget(b)
        self.table=DataTable(["尝试ID","任务运行","账号","目标群","状态","开始","结束","错误码","错误"]);layout.addWidget(self.table);self.refresh()
    def refresh(self)->None:
        rows=self.context.db.query_all("""SELECT a.*,ac.phone,g.title,g.canonical_link FROM task_attempts a JOIN accounts ac ON ac.id=a.account_id JOIN telegram_groups g ON g.id=a.telegram_group_id ORDER BY a.id DESC LIMIT 1000""")
        self.table.set_rows([[r["id"],r["run_id"],r["phone"],r["title"] or r["canonical_link"],r["status"],r["started_at"],r["ended_at"],r["error_code"],r["error_message"]] for r in rows])



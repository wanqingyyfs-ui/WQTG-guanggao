from __future__ import annotations

import concurrent.futures
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QWidget,
    QVBoxLayout,
)

from app.gui.dialogs.login_dialog import LoginConfirmDialog
from app.gui.dialogs.verify_dialog import VerifyInputDialog
from app.gui.pages.account_page import AccountPage
from app.gui.pages.dashboard_page import DashboardPage
from app.gui.pages.group_page import GroupPage
from app.gui.pages.log_page import LogPage
from app.gui.pages.task_page import TaskPage
from app.gui.pages.template_page import TemplatePage
from app.gui.style import APP_QSS
from app.services.runtime_service import RuntimeService


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)
    return str(Path(__file__).resolve().parents[2] / relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Telegram 用户号群发任务面板")
        icon_path = Path(__file__).resolve().parents[2] / "app.ico"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setFixedSize(1280, 860)
        self.setStyleSheet(APP_QSS)

        data_dir = Path(os.getenv("DATA_DIR", "~/.tg_group_sender")).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)

        self.runtime_service = RuntimeService(str(data_dir))
        self.accounts = list(self.runtime_service.accounts)
        self.groups = list(self.runtime_service.groups)
        self.tasks = list(self.runtime_service.tasks)
        self.templates = list(self.runtime_service.templates)
        self.settings = self.runtime_service.settings
        self.status_map = self.runtime_service.get_status_map()
        self.scheduler_status = self.runtime_service.get_scheduler_status()

        self.dashboard_page = DashboardPage()
        self.account_page = AccountPage()
        self.group_page = GroupPage()
        self.task_page = TaskPage()
        self.template_page = TemplatePage()

        log_dir = data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_page = LogPage(str(log_dir))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.addTab(self.dashboard_page, "运行总控")
        self.tabs.addTab(self.account_page, "账号管理")
        self.tabs.addTab(self.group_page, "群组管理")
        self.tabs.addTab(self.task_page, "任务管理")
        self.tabs.addTab(self.template_page, "模板管理")
        self.tabs.addTab(self.log_page, "日志查看")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self.templates_sync_timer = QTimer(self)
        self.templates_sync_timer.setInterval(1500)

        self._connect_signals()
        self.refresh_all_views()

        self.templates_sync_timer.timeout.connect(self.on_templates_sync_timer)
        self.templates_sync_timer.start()

        self.statusBar().showMessage("准备就绪", 3000)

    def _connect_signals(self) -> None:
        self.dashboard_page.save_button.clicked.connect(self.on_save_all_clicked)
        self.dashboard_page.reload_button.clicked.connect(self.on_reload_clicked)
        self.dashboard_page.start_all_button.clicked.connect(self.on_start_all_clicked)
        self.dashboard_page.stop_all_button.clicked.connect(self.on_stop_all_clicked)

        if hasattr(self.dashboard_page, "start_scheduler_button"):
            self.dashboard_page.start_scheduler_button.clicked.connect(self.on_start_scheduler_clicked)
        if hasattr(self.dashboard_page, "stop_scheduler_button"):
            self.dashboard_page.stop_scheduler_button.clicked.connect(self.on_stop_scheduler_clicked)

        self.account_page.add_button.clicked.connect(self.account_page.clear_form)
        self.account_page.save_button.clicked.connect(self.on_save_account_clicked)
        self.account_page.delete_button.clicked.connect(self.on_delete_account_clicked)
        self.account_page.login_button.clicked.connect(self.on_login_account_clicked)
        self.account_page.start_button.clicked.connect(self.on_start_account_clicked)
        self.account_page.stop_button.clicked.connect(self.on_stop_account_clicked)

        self.group_page.add_button.clicked.connect(self.group_page.clear_form)
        self.group_page.save_button.clicked.connect(self.on_save_group_clicked)
        self.group_page.delete_button.clicked.connect(self.on_delete_group_clicked)

        self.task_page.add_button.clicked.connect(self.task_page.clear_form)
        self.task_page.save_button.clicked.connect(self.on_save_task_clicked)
        self.task_page.delete_button.clicked.connect(self.on_delete_task_clicked)
        self.task_page.up_button.clicked.connect(self.on_task_up_clicked)
        self.task_page.down_button.clicked.connect(self.on_task_down_clicked)
        self.task_page.send_once_button.clicked.connect(self.on_send_task_once_clicked)

        self.template_page.add_button.clicked.connect(self.template_page.clear_form)
        self.template_page.save_button.clicked.connect(self.on_save_template_clicked)
        self.template_page.delete_button.clicked.connect(self.on_delete_template_clicked)
        self.template_page.refresh_button.clicked.connect(self.on_reload_clicked)

        self.runtime_service.log_received.connect(self.on_runtime_log_received)
        self.runtime_service.account_status_changed.connect(self.on_account_status_changed)
        self.runtime_service.runtime_hint.connect(self.on_runtime_hint)
        self.runtime_service.templates_changed.connect(self.on_templates_changed)
        self.runtime_service.scheduler_status_changed.connect(self.on_scheduler_status_changed)

        self.runtime_service.input_provider.code_input_required.connect(self.on_code_input_required)
        self.runtime_service.input_provider.password_input_required.connect(self.on_password_input_required)

    def refresh_all_views(self) -> None:
        if hasattr(self.dashboard_page, "update_summary"):
            try:
                self.dashboard_page.update_summary(
                    self.accounts,
                    self.groups,
                    self.tasks,
                    self.settings,
                    self.scheduler_status,
                )
            except TypeError:
                self.dashboard_page.update_summary(self.accounts, [], self.settings)

        if hasattr(self.dashboard_page, "update_status_table"):
            self.dashboard_page.update_status_table(self.accounts, self.status_map)

        self.account_page.set_accounts(self.accounts, self.status_map)
        self.group_page.set_groups(self.groups)
        self.task_page.set_context(self.accounts, self.groups, self.templates)
        self.task_page.set_tasks(self.tasks)
        self.template_page.set_templates(self.templates)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "错误", text)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "提示", text)

    def _sync_settings_from_dashboard(self) -> None:
        if hasattr(self.dashboard_page, "scheduler_tick_spin"):
            self.settings.scheduler_tick_seconds = float(self.dashboard_page.scheduler_tick_spin.value())

        if hasattr(self.dashboard_page, "max_concurrent_tasks_spin"):
            self.settings.max_concurrent_tasks = int(self.dashboard_page.max_concurrent_tasks_spin.value())

        if hasattr(self.dashboard_page, "default_send_interval_spin"):
            self.settings.default_send_interval_seconds = float(
                self.dashboard_page.default_send_interval_spin.value()
            )

        if hasattr(self.dashboard_page, "template_account_edit"):
            self.settings.template_source_account_name = (
                self.dashboard_page.template_account_edit.text().strip()
            )

        if hasattr(self.dashboard_page, "template_chat_id_edit"):
            chat_id_text = self.dashboard_page.template_chat_id_edit.text().strip()
            if chat_id_text:
                try:
                    self.settings.template_source_chat_id = int(chat_id_text)
                except ValueError as exc:
                    raise ValueError("素材群 Chat ID 必须是数字") from exc
            else:
                self.settings.template_source_chat_id = 0

    def on_runtime_log_received(self, level: str, message: str) -> None:
        self.log_page.append_log(level, message)

    def on_runtime_hint(self, message: str) -> None:
        self.log_page.append_log("INFO", message)
        self.statusBar().showMessage(message, 5000)

    def on_account_status_changed(self, account_name: str, status: str, detail: str) -> None:
        self.status_map[account_name] = (status, detail)
        self.refresh_all_views()

    def on_scheduler_status_changed(self, status: str) -> None:
        self.scheduler_status = status
        self.refresh_all_views()
        self.statusBar().showMessage(f"调度器状态：{status}", 3000)

    def on_templates_changed(self) -> None:
        self.templates = list(self.runtime_service.templates)
        self.task_page.set_context(self.accounts, self.groups, self.templates)
        self.task_page.set_tasks(self.tasks)
        self.template_page.set_templates(self.templates)
        self.statusBar().showMessage("模板列表已自动刷新", 3000)

    def on_templates_sync_timer(self) -> None:
        try:
            self.runtime_service.sync_templates_from_disk()
        except Exception:
            pass

    def on_code_input_required(
        self,
        account_name: str,
        phone: str,
        future: concurrent.futures.Future,
    ) -> None:
        dialog = VerifyInputDialog(
            title="输入验证码",
            label_text=f"账号：{account_name}\n手机号：{phone}\n\n请输入 Telegram 验证码：",
            password_mode=False,
            parent=self,
        )

        if dialog.exec():
            if not future.done():
                future.set_result(dialog.get_value())
        else:
            if not future.done():
                future.set_result("")

    def on_password_input_required(
        self,
        account_name: str,
        future: concurrent.futures.Future,
    ) -> None:
        dialog = VerifyInputDialog(
            title="输入二步验证密码",
            label_text=f"账号：{account_name}\n\n请输入二步验证密码：",
            password_mode=True,
            parent=self,
        )

        if dialog.exec():
            if not future.done():
                future.set_result(dialog.get_value())
        else:
            if not future.done():
                future.set_result("")

    def on_save_all_clicked(self) -> None:
        try:
            self._sync_settings_from_dashboard()
            self.runtime_service.save_settings(self.settings)
            self.runtime_service.save_accounts(self.accounts)
            self.runtime_service.save_groups(self.groups)
            self.runtime_service.save_tasks(self.tasks)
            self.runtime_service.save_templates(self.templates)
            self._show_info("全部配置已保存")
        except Exception as exc:
            self._show_error(f"保存失败：{exc}")

    def on_reload_clicked(self) -> None:
        try:
            self.runtime_service.reload_config_cache()
            self.accounts = list(self.runtime_service.accounts)
            self.groups = list(self.runtime_service.groups)
            self.tasks = list(self.runtime_service.tasks)
            self.templates = list(self.runtime_service.templates)
            self.settings = self.runtime_service.settings
            self.status_map = self.runtime_service.get_status_map()
            self.scheduler_status = self.runtime_service.get_scheduler_status()
            self.refresh_all_views()
            self._show_info("配置已重新加载")
        except Exception as exc:
            self._show_error(f"重新加载失败：{exc}")

    def on_start_all_clicked(self) -> None:
        try:
            self._sync_settings_from_dashboard()
            self.runtime_service.save_settings(self.settings)
            self.runtime_service.start_all()
        except Exception as exc:
            self._show_error(f"启动失败：{exc}")

    def on_stop_all_clicked(self) -> None:
        try:
            self.runtime_service.stop_all()
        except Exception as exc:
            self._show_error(f"停止失败：{exc}")

    def on_start_scheduler_clicked(self) -> None:
        try:
            self._sync_settings_from_dashboard()
            self.runtime_service.save_settings(self.settings)
            self.runtime_service.save_groups(self.groups)
            self.runtime_service.save_tasks(self.tasks)
            self.runtime_service.start_scheduler()
        except Exception as exc:
            self._show_error(f"启动调度器失败：{exc}")

    def on_stop_scheduler_clicked(self) -> None:
        try:
            self.runtime_service.stop_scheduler()
        except Exception as exc:
            self._show_error(f"停止调度器失败：{exc}")

    def on_save_account_clicked(self) -> None:
        try:
            account = self.account_page.get_form_account()

            if not account.account_name:
                raise ValueError("账号名称不能为空")
            if not account.api_hash:
                raise ValueError("API Hash 不能为空")
            if not account.phone:
                raise ValueError("手机号不能为空")
            if not account.session_name:
                raise ValueError("Session 名称不能为空")

            existing_index = next(
                (
                    idx
                    for idx, item in enumerate(self.accounts)
                    if item.account_name == account.account_name
                ),
                None,
            )

            if existing_index is None:
                self.accounts.append(account)
            else:
                self.accounts[existing_index] = account

            self.runtime_service.save_accounts(self.accounts)
            self.refresh_all_views()
            self._show_info("账号已保存")
        except Exception as exc:
            self._show_error(f"保存账号失败：{exc}")

    def on_delete_account_clicked(self) -> None:
        account_name = self.account_page.get_selected_account_name()
        if not account_name:
            self._show_error("请先选择一个账号")
            return

        self.accounts = [
            item for item in self.accounts if item.account_name != account_name
        ]
        self.runtime_service.save_accounts(self.accounts)
        self.status_map.pop(account_name, None)
        self.account_page.clear_form()
        self.refresh_all_views()
        self._show_info("账号已删除")

    def on_login_account_clicked(self) -> None:
        account_name = self.account_page.get_selected_account_name()
        if not account_name:
            self._show_error("请先选择一个账号")
            return

        account = next(
            (item for item in self.accounts if item.account_name == account_name),
            None,
        )
        if account is None:
            self._show_error("账号不存在")
            return

        confirm = LoginConfirmDialog(account.account_name, account.phone, self)
        if confirm.exec():
            self.runtime_service.login_account(account_name)

    def on_start_account_clicked(self) -> None:
        account_name = self.account_page.get_selected_account_name()
        if not account_name:
            self._show_error("请先选择一个账号")
            return

        self.runtime_service.start_account(account_name)

    def on_stop_account_clicked(self) -> None:
        account_name = self.account_page.get_selected_account_name()
        if not account_name:
            self._show_error("请先选择一个账号")
            return

        self.runtime_service.stop_account(account_name)

    def on_save_group_clicked(self) -> None:
        try:
            group = self.group_page.get_form_group()

            if not group.group_name:
                raise ValueError("群组名称不能为空")

            existing_index = next(
                (
                    idx
                    for idx, item in enumerate(self.groups)
                    if item.group_id == group.group_id
                ),
                None,
            )

            if existing_index is None:
                self.groups.append(group)
            else:
                self.groups[existing_index] = group

            self.runtime_service.save_groups(self.groups)
            self.refresh_all_views()
            self._show_info("群组已保存")
        except Exception as exc:
            self._show_error(f"保存群组失败：{exc}")

    def on_delete_group_clicked(self) -> None:
        row = self.group_page.get_selected_row()
        if row < 0 or row >= len(self.groups):
            self._show_error("请先选择一个群组")
            return

        group_id = self.groups[row].group_id
        self.groups.pop(row)

        for task in self.tasks:
            if task.group_id == group_id:
                task.group_id = ""

        self.runtime_service.save_groups(self.groups)
        self.runtime_service.save_tasks(self.tasks)
        self.group_page.clear_form()
        self.refresh_all_views()
        self._show_info("群组已删除，相关任务的目标群已清空")

    def on_save_task_clicked(self) -> None:
        try:
            task = self.task_page.get_form_task()

            if not task.task_name:
                raise ValueError("任务名称不能为空")
            if not task.account_name:
                raise ValueError("请选择发送账号")
            if not task.group_id:
                raise ValueError("请选择目标群组")

            if task.message_mode == "template":
                if not task.template_id:
                    raise ValueError("模板消息必须选择模板")
            else:
                if not task.text:
                    raise ValueError("文本消息必须填写内容")

            existing_index = next(
                (
                    idx
                    for idx, item in enumerate(self.tasks)
                    if item.task_id == task.task_id
                ),
                None,
            )

            if existing_index is None:
                self.tasks.append(task)
            else:
                self.tasks[existing_index] = task

            self.runtime_service.save_tasks(self.tasks)
            self.refresh_all_views()
            self._show_info("任务已保存")
        except Exception as exc:
            self._show_error(f"保存任务失败：{exc}")

    def on_delete_task_clicked(self) -> None:
        row = self.task_page.get_selected_row()
        if row < 0 or row >= len(self.tasks):
            self._show_error("请先选择一个任务")
            return

        self.tasks.pop(row)
        self.runtime_service.save_tasks(self.tasks)
        self.task_page.clear_form()
        self.refresh_all_views()
        self._show_info("任务已删除")

    def on_task_up_clicked(self) -> None:
        row = self.task_page.get_selected_row()
        if row <= 0:
            return

        self.tasks[row - 1], self.tasks[row] = self.tasks[row], self.tasks[row - 1]
        self.runtime_service.save_tasks(self.tasks)
        self.refresh_all_views()
        self.task_page.table.selectRow(row - 1)

    def on_task_down_clicked(self) -> None:
        row = self.task_page.get_selected_row()
        if row < 0 or row >= len(self.tasks) - 1:
            return

        self.tasks[row + 1], self.tasks[row] = self.tasks[row], self.tasks[row + 1]
        self.runtime_service.save_tasks(self.tasks)
        self.refresh_all_views()
        self.task_page.table.selectRow(row + 1)

    def on_send_task_once_clicked(self) -> None:
        task_id = self.task_page.get_selected_task_id()
        if not task_id:
            self._show_error("请先选择一个任务")
            return

        try:
            self.runtime_service.save_tasks(self.tasks)
            self.runtime_service.send_task_once(task_id)
            self.statusBar().showMessage("已提交立即发送任务", 3000)
        except Exception as exc:
            self._show_error(f"立即发送失败：{exc}")

    def on_save_template_clicked(self) -> None:
        try:
            template = self.template_page.get_form_template()

            if not template.template_name:
                raise ValueError("模板名称不能为空")
            if not template.source_account_name:
                raise ValueError("来源账号不能为空")
            if not template.source_chat_id:
                raise ValueError("来源 Chat ID 不能为空")
            if not template.source_message_ids:
                raise ValueError("来源消息 ID 列表不能为空")

            existing_index = next(
                (
                    idx
                    for idx, item in enumerate(self.templates)
                    if item.template_id == template.template_id
                ),
                None,
            )

            if existing_index is None:
                self.templates.append(template)
            else:
                self.templates[existing_index] = template

            self.runtime_service.save_templates(self.templates)
            self.refresh_all_views()
            self._show_info("模板已保存")
        except Exception as exc:
            self._show_error(f"保存模板失败：{exc}")

    def on_delete_template_clicked(self) -> None:
        row = self.template_page.get_selected_row()
        if row < 0 or row >= len(self.templates):
            self._show_error("请先选择一个模板")
            return

        template_id = self.templates[row].template_id
        self.templates.pop(row)

        for task in self.tasks:
            if task.template_id == template_id:
                task.template_id = ""

        self.runtime_service.save_templates(self.templates)
        self.runtime_service.save_tasks(self.tasks)
        self.template_page.clear_form()
        self.refresh_all_views()
        self._show_info("模板已删除，相关任务的模板选择已清空")

    def closeEvent(self, event) -> None:
        try:
            self.templates_sync_timer.stop()
            self.runtime_service.shutdown()
        finally:
            super().closeEvent(event)
from __future__ import annotations

import concurrent.futures
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
)
from app.gui.dialogs.login_dialog import LoginConfirmDialog
from app.gui.dialogs.verify_dialog import VerifyInputDialog
from app.gui.forms.account_form import AccountForm
from app.gui.forms.group_form import GroupForm
from app.gui.forms.task_form import TaskForm
from app.gui.forms.template_form import TemplateForm
from app.gui.pages.account_page import AccountPage
from app.gui.pages.config_page import ConfigPage
from app.gui.pages.dashboard_page import DashboardPage
from app.gui.pages.group_page import GroupPage
from app.gui.pages.log_page import LogPage
from app.gui.pages.noise_page import NoisePage
from app.gui.pages.task_page import TaskPage
from app.gui.pages.template_page import TemplatePage
from app.gui.style import build_app_qss
from app.gui.widgets.dock_panel import create_config_dock
from app.services.runtime_service import RuntimeService


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)
    return str(Path(__file__).resolve().parents[2] / relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Telegram 用户号群发任务面板")

        icon_path = Path(resource_path("app.ico"))
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.resize(1280, 860)
        self.setMinimumSize(980, 680)

        self.runtime_service = RuntimeService()
        self.accounts = list(self.runtime_service.accounts)
        self.groups = list(self.runtime_service.groups)
        self.tasks = list(self.runtime_service.tasks)
        self.templates = list(self.runtime_service.templates)
        self.settings = self.runtime_service.settings
        self.status_map = self.runtime_service.get_status_map()
        self.scheduler_status = self.runtime_service.get_scheduler_status()
        self._style_signature = self._build_style_signature()

        self._apply_app_style()

        self.dashboard_page = DashboardPage()
        self.config_page = ConfigPage(self.runtime_service)
        self.account_page = AccountPage()
        self.group_page = GroupPage()
        self.task_page = TaskPage()
        self.template_page = TemplatePage()
        self.noise_page = NoisePage(self.runtime_service)
        self.log_page = LogPage(str(self.runtime_service.get_logs_dir()))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.addTab(self.dashboard_page, "运行总控")
        self.tabs.addTab(self.config_page, "配置管理")
        self.tabs.addTab(self.account_page, "账号管理")
        self.tabs.addTab(self.group_page, "群组管理")
        self.tabs.addTab(self.task_page, "任务管理")
        self.tabs.addTab(self.template_page, "模板管理")
        self.tabs.addTab(self.noise_page, "噪音配置")
        self.tabs.addTab(self.log_page, "日志查看")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self._create_docks()

        self.templates_sync_timer = QTimer(self)
        self.templates_sync_timer.setInterval(1500)

        self._connect_signals()
        self.refresh_all_views()

        self.templates_sync_timer.timeout.connect(self.on_templates_sync_timer)
        self.templates_sync_timer.start()

        self.statusBar().showMessage("准备就绪", 3000)

    def _create_docks(self) -> None:
        self.account_form = AccountForm()
        self.group_form = GroupForm()
        self.task_form = TaskForm()
        self.template_form = TemplateForm()

        self.account_dock = create_config_dock(
            parent=self,
            object_name="accountConfigDock",
            title="账号配置",
            content=self.account_form,
            default_width=int(getattr(self.settings, "account_panel_width", 520)),
            default_height=int(getattr(self.settings, "account_panel_height", 620)),
            font_size=int(getattr(self.settings, "account_panel_font_size", 13)),
        )
        self.group_dock = create_config_dock(
            parent=self,
            object_name="groupConfigDock",
            title="群组配置",
            content=self.group_form,
            default_width=int(getattr(self.settings, "group_panel_width", 520)),
            default_height=int(getattr(self.settings, "group_panel_height", 620)),
            font_size=int(getattr(self.settings, "group_panel_font_size", 13)),
        )
        self.task_dock = create_config_dock(
            parent=self,
            object_name="taskConfigDock",
            title="任务配置",
            content=self.task_form,
            default_width=int(getattr(self.settings, "task_panel_width", 680)),
            default_height=int(getattr(self.settings, "task_panel_height", 760)),
            font_size=int(getattr(self.settings, "task_panel_font_size", 13)),
        )
        self.template_dock = create_config_dock(
            parent=self,
            object_name="templateConfigDock",
            title="模板配置",
            content=self.template_form,
            default_width=int(getattr(self.settings, "template_panel_width", 520)),
            default_height=int(getattr(self.settings, "template_panel_height", 520)),
            font_size=int(getattr(self.settings, "template_panel_font_size", 13)),
        )

        self.account_dock.hide()
        self.group_dock.hide()
        self.task_dock.hide()
        self.template_dock.hide()

    def _connect_signals(self) -> None:
        self.dashboard_page.start_all_button.clicked.connect(self.on_start_all_clicked)
        self.dashboard_page.stop_all_button.clicked.connect(self.on_stop_all_clicked)
        self.dashboard_page.start_scheduler_button.clicked.connect(self.on_start_scheduler_clicked)
        self.dashboard_page.stop_scheduler_button.clicked.connect(self.on_stop_scheduler_clicked)

        self.account_page.add_button.clicked.connect(self.on_open_account_add)
        self.account_page.config_button.clicked.connect(self.on_open_account_config)
        self.account_page.delete_button.clicked.connect(self.on_delete_account_clicked)
        self.account_page.up_button.clicked.connect(self.on_account_up_clicked)
        self.account_page.down_button.clicked.connect(self.on_account_down_clicked)
        self.account_page.login_button.clicked.connect(self.on_login_account_clicked)
        self.account_page.start_button.clicked.connect(self.on_start_account_clicked)
        self.account_page.stop_button.clicked.connect(self.on_stop_account_clicked)

        self.group_page.add_button.clicked.connect(self.on_open_group_add)
        self.group_page.config_button.clicked.connect(self.on_open_group_config)
        self.group_page.delete_button.clicked.connect(self.on_delete_group_clicked)
        self.group_page.up_button.clicked.connect(self.on_group_up_clicked)
        self.group_page.down_button.clicked.connect(self.on_group_down_clicked)

        self.task_page.add_button.clicked.connect(self.on_open_task_add)
        self.task_page.config_button.clicked.connect(self.on_open_task_config)
        self.task_page.delete_button.clicked.connect(self.on_delete_task_clicked)
        self.task_page.up_button.clicked.connect(self.on_task_up_clicked)
        self.task_page.down_button.clicked.connect(self.on_task_down_clicked)

        self.template_page.config_button.clicked.connect(self.on_open_template_config)
        self.template_page.delete_button.clicked.connect(self.on_delete_template_clicked)
        self.template_page.up_button.clicked.connect(self.on_template_up_clicked)
        self.template_page.down_button.clicked.connect(self.on_template_down_clicked)
        self.template_page.refresh_button.clicked.connect(self.on_reload_clicked)

        self.account_form.add_requested.connect(self.on_open_account_add)
        self.account_form.save_requested.connect(self.on_save_account_clicked)
        self.group_form.add_requested.connect(self.on_open_group_add)
        self.group_form.save_requested.connect(self.on_save_group_clicked)
        self.task_form.add_requested.connect(self.on_open_task_add)
        self.task_form.save_requested.connect(self.on_save_task_clicked)
        self.template_form.save_requested.connect(self.on_save_template_clicked)

        self.runtime_service.log_received.connect(self.on_runtime_log_received)
        self.runtime_service.account_status_changed.connect(self.on_account_status_changed)
        self.runtime_service.runtime_hint.connect(self.on_runtime_hint)
        self.runtime_service.templates_changed.connect(self.on_templates_changed)

        if hasattr(self.runtime_service, "noise_pool_changed"):
            self.runtime_service.noise_pool_changed.connect(self.on_noise_pool_changed)

        self.runtime_service.scheduler_status_changed.connect(self.on_scheduler_status_changed)

        self.runtime_service.input_provider.code_input_required.connect(
            self.on_code_input_required
        )
        self.runtime_service.input_provider.password_input_required.connect(
            self.on_password_input_required
        )

    def _build_style_signature(self) -> tuple[int, ...]:
        return (
            int(getattr(self.settings, "global_font_size", 13) or 13),
            int(getattr(self.settings, "table_font_size", 13) or 13),
            int(getattr(self.settings, "button_font_size", 13) or 13),
            int(getattr(self.settings, "input_font_size", 13) or 13),
            int(getattr(self.settings, "floating_panel_font_size", 13) or 13),
            int(getattr(self.settings, "account_panel_font_size", 13) or 13),
            int(getattr(self.settings, "group_panel_font_size", 13) or 13),
            int(getattr(self.settings, "task_panel_font_size", 13) or 13),
            int(getattr(self.settings, "template_panel_font_size", 13) or 13),
        )

    def _apply_app_style(self) -> None:
        self.setStyleSheet(build_app_qss(self.settings))

    def _refresh_style_if_needed(self) -> None:
        current_signature = self._build_style_signature()
        if current_signature == self._style_signature:
            return

        self._style_signature = current_signature
        self._apply_app_style()

        self.account_dock.set_panel_font_size(int(getattr(self.settings, "account_panel_font_size", 13)))
        self.group_dock.set_panel_font_size(int(getattr(self.settings, "group_panel_font_size", 13)))
        self.task_dock.set_panel_font_size(int(getattr(self.settings, "task_panel_font_size", 13)))
        self.template_dock.set_panel_font_size(int(getattr(self.settings, "template_panel_font_size", 13)))

    def _sync_state_from_runtime(self) -> None:
        self.accounts = list(self.runtime_service.accounts)
        self.groups = list(self.runtime_service.groups)
        self.tasks = list(self.runtime_service.tasks)
        self.templates = list(self.runtime_service.templates)
        self.settings = self.runtime_service.settings
        self.status_map = self.runtime_service.get_status_map()
        self.scheduler_status = self.runtime_service.get_scheduler_status()
        self._refresh_style_if_needed()

        if hasattr(self, "log_page"):
            if hasattr(self.log_page, "set_logs_dir"):
                self.log_page.set_logs_dir(self.runtime_service.get_logs_dir())
            else:
                self.log_page.logs_dir = str(self.runtime_service.get_logs_dir())

    def refresh_all_views(self) -> None:
        self.account_page.set_defaults(
            bool(getattr(self.settings, "default_account_enabled", True)),
            bool(getattr(self.settings, "default_session_name_follow_account", True)),
        )
        self.group_page.set_defaults(
            bool(getattr(self.settings, "default_group_enabled", True)),
            bool(getattr(self.settings, "default_group_username_normalize", True)),
        )

        self.account_form.set_defaults(
            bool(getattr(self.settings, "default_account_enabled", True)),
            bool(getattr(self.settings, "default_session_name_follow_account", True)),
        )
        self.group_form.set_defaults(
            bool(getattr(self.settings, "default_group_enabled", True)),
            bool(getattr(self.settings, "default_group_username_normalize", True)),
        )
        self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings)

        self.dashboard_page.update_summary(
            self.accounts,
            self.groups,
            self.tasks,
            self.settings,
            self.scheduler_status,
        )
        self.dashboard_page.update_status_table(self.accounts, self.status_map)

        self.account_page.set_accounts(self.accounts, self.status_map)
        self.group_page.set_groups(self.groups)
        self.task_page.set_context(self.accounts, self.groups, self.templates, self.settings)
        self.task_page.set_tasks(self.tasks)
        self.template_page.set_templates(self.templates)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "错误", text)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "提示", text)

    def _ensure_can_modify_sending_data(self) -> None:
        if self.runtime_service.is_scheduler_running():
            raise RuntimeError("请先停止群发功能")

    def _open_dock(self, dock) -> None:
        dock.show()
        dock.raise_()
        dock.activateWindow()

    def on_open_account_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            self.account_page.clear_selection()
            self.account_form.clear_form()
            self._open_dock(self.account_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_account_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.account_page.get_selected_row()
            if row < 0 or row >= len(self.accounts):
                self._show_error("请先选择一个账号")
                return
            self.account_form.load_account(self.accounts[row])
            self._open_dock(self.account_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_group_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            self.group_page.clear_selection()
            self.group_form.clear_form()
            self._open_dock(self.group_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_group_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.group_page.get_selected_row()
            if row < 0 or row >= len(self.groups):
                self._show_error("请先选择一个群组")
                return
            self.group_form.load_group(self.groups[row])
            self._open_dock(self.group_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_task_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            self.task_page.clear_selection()
            self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings)
            self.task_form.clear_form()
            self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_task_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            if row < 0 or row >= len(self.tasks):
                self._show_error("请先选择一个任务")
                return
            self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings)
            self.task_form.load_task(self.tasks[row])
            self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_template_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.template_page.get_selected_row()
            if row < 0 or row >= len(self.templates):
                self._show_error("请先选择一个模板")
                return
            self.template_form.load_template(self.templates[row])
            self._open_dock(self.template_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def _replace_account_name_in_tasks(self, old_account_name: str, new_account_name: str) -> bool:
        old_value = str(old_account_name or "").strip()
        new_value = str(new_account_name or "").strip()
        if not old_value or not new_value or old_value == new_value:
            return False

        changed = False
        for task in self.tasks:
            account_names = self._task_account_names(task)
            replaced = [new_value if item == old_value else item for item in account_names]
            deduped: list[str] = []
            for item in replaced:
                if item and item not in deduped:
                    deduped.append(item)

            if deduped != account_names:
                task.account_names = deduped
                changed = True

            if str(getattr(task, "account_name", "") or "").strip() == old_value:
                task.account_name = new_value
                changed = True

        return changed

    def _remove_account_from_tasks(self, account_name: str) -> bool:
        target = str(account_name or "").strip()
        changed = False

        for task in self.tasks:
            account_names = self._task_account_names(task)
            filtered = [item for item in account_names if item != target]
            if filtered != account_names:
                task.account_names = filtered
                changed = True

            if str(getattr(task, "account_name", "") or "").strip() == target:
                task.account_name = filtered[0] if filtered else ""
                changed = True

            task.current_account_index = 0 if not filtered else min(
                int(getattr(task, "current_account_index", 0) or 0),
                len(filtered) - 1,
            )

        return changed

    def _remove_group_from_tasks(self, group_id: str) -> bool:
        target = str(group_id or "").strip()
        changed = False

        for task in self.tasks:
            group_ids = self._task_group_ids(task)
            filtered = [item for item in group_ids if item != target]
            if filtered != group_ids:
                task.group_ids = filtered
                changed = True

            if str(getattr(task, "group_id", "") or "").strip() == target:
                task.group_id = filtered[0] if filtered else ""
                changed = True

            task.current_group_index = 0 if not filtered else min(
                int(getattr(task, "current_group_index", 0) or 0),
                len(filtered) - 1,
            )

        return changed

    def _remove_template_from_tasks(self, template_id: str) -> bool:
        target = str(template_id or "").strip()
        changed = False

        for task in self.tasks:
            template_ids = self._task_template_ids(task)
            filtered = [item for item in template_ids if item != target]
            if filtered != template_ids:
                task.template_ids = filtered
                changed = True

            if str(getattr(task, "template_id", "") or "").strip() == target:
                task.template_id = filtered[0] if filtered else ""
                changed = True

        return changed

    @staticmethod
    def _task_account_names(task) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "account_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "account_name", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    @staticmethod
    def _task_group_ids(task) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "group_ids", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "group_id", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    @staticmethod
    def _task_template_ids(task) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "template_ids", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(task, "template_id", "") or "").strip()
        if legacy and legacy not in result:
            result.insert(0, legacy)
        return result

    def _validate_task_accounts(self, task) -> None:
        account_names = self._task_account_names(task)
        if not account_names:
            raise ValueError("请选择至少一个发送账号")

        existing = {account.account_name for account in self.accounts}
        missing = [item for item in account_names if item not in existing]
        if missing:
            raise ValueError("发送账号不存在：" + "、".join(missing))

        task.account_names = account_names
        task.account_name = task.account_name if task.account_name in account_names else account_names[0]
        task.current_account_index = int(getattr(task, "current_account_index", 0) or 0) % len(account_names)

    def _validate_task_groups(self, task) -> None:
        group_ids = self._task_group_ids(task)
        if not group_ids:
            raise ValueError("请选择至少一个目标群组")

        existing = {group.group_id for group in self.groups}
        missing = [item for item in group_ids if item not in existing]
        if missing:
            raise ValueError("目标群组不存在：" + "、".join(missing))

        task.group_ids = group_ids
        task.group_id = task.group_id if task.group_id in group_ids else group_ids[0]
        task.current_group_index = int(getattr(task, "current_group_index", 0) or 0) % len(group_ids)

    def _validate_task_message(self, task) -> None:
        message_mode = str(getattr(task, "message_mode", "") or "").strip()

        if message_mode == MESSAGE_MODE_TEMPLATE:
            template_ids = self._task_template_ids(task)
            if not template_ids:
                raise ValueError("模板消息必须至少选择一个模板")

            existing = {template.template_id for template in self.templates}
            missing = [item for item in template_ids if item not in existing]
            if missing:
                raise ValueError("模板不存在：" + "、".join(missing))

            task.template_ids = template_ids
            task.template_id = task.template_id if task.template_id in template_ids else template_ids[0]
            return

        if message_mode == MESSAGE_MODE_TEXT:
            if not str(getattr(task, "text", "") or "").strip():
                raise ValueError("文本消息必须填写内容")
            return

        raise ValueError(f"不支持的消息类型：{message_mode or '空'}")

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
        self._sync_state_from_runtime()
        self.refresh_all_views()
        self.statusBar().showMessage("模板列表已自动刷新", 3000)

    def on_noise_pool_changed(self) -> None:
        self.statusBar().showMessage("噪音池已更新", 3000)

    def on_templates_sync_timer(self) -> None:
        try:
            changed = self.runtime_service.sync_templates_from_disk()
            if changed:
                self._sync_state_from_runtime()
                self.refresh_all_views()

            if hasattr(self.runtime_service, "sync_noise_pool_from_disk"):
                self.runtime_service.sync_noise_pool_from_disk()

            self._sync_state_from_runtime()
            self.refresh_all_views()

        except Exception as exc:
            self.on_runtime_log_received("WARNING", f"自动同步配置失败：{exc}")

    def on_code_input_required(self, account_name: str, phone: str, future: concurrent.futures.Future) -> None:
        dialog = VerifyInputDialog(
            title="输入验证码",
            label_text=f"账号：{account_name}\n手机号：{phone}\n\n请输入 Telegram 验证码：",
            password_mode=False,
            parent=self,
        )

        if dialog.exec():
            if not future.done():
                future.set_result(dialog.get_value())
        elif not future.done():
            future.set_result("")

    def on_password_input_required(self, account_name: str, future: concurrent.futures.Future) -> None:
        dialog = VerifyInputDialog(
            title="输入二步验证密码",
            label_text=f"账号：{account_name}\n\n请输入二步验证密码：",
            password_mode=True,
            parent=self,
        )

        if dialog.exec():
            if not future.done():
                future.set_result(dialog.get_value())
        elif not future.done():
            future.set_result("")

    def on_reload_clicked(self) -> None:
        try:
            self.runtime_service.reload_config_cache()
            self._sync_state_from_runtime()

            if hasattr(self.config_page, "reload_from_runtime"):
                self.config_page.reload_from_runtime()

            if hasattr(self.noise_page, "reload_from_runtime"):
                self.noise_page.reload_from_runtime()

            self.refresh_all_views()
            self._show_info("配置已重新加载")
        except Exception as exc:
            self._show_error(f"重新加载失败：{exc}")

    def on_start_all_clicked(self) -> None:
        try:
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
            self.runtime_service.start_scheduler()
        except Exception as exc:
            self._show_error(f"启动群发失败：{exc}")

    def on_stop_scheduler_clicked(self) -> None:
        try:
            self.runtime_service.stop_scheduler()
        except Exception as exc:
            self._show_error(f"停止群发失败：{exc}")

    def on_save_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            account = self.account_form.get_form_account()

            if not account.account_name:
                raise ValueError("账号名称不能为空")
            if not account.api_hash:
                raise ValueError("API Hash 不能为空")
            if not account.phone:
                raise ValueError("手机号不能为空")
            if not account.session_name:
                account.session_name = account.account_name

            selected_index = self.account_page.get_selected_row()
            old_account_name = ""

            if 0 <= selected_index < len(self.accounts):
                old_account_name = self.accounts[selected_index].account_name
                existing_index = selected_index
            else:
                existing_index = next(
                    (idx for idx, item in enumerate(self.accounts) if item.account_name == account.account_name),
                    None,
                )

            for idx, item in enumerate(self.accounts):
                if idx != existing_index and item.account_name == account.account_name:
                    raise ValueError("账号名称已存在，不能重复")

            if existing_index is None:
                self.accounts.append(account)
            else:
                self.accounts[existing_index] = account

            tasks_changed = self._replace_account_name_in_tasks(old_account_name, account.account_name)

            self.runtime_service.save_accounts(self.accounts)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.account_page.select_account_name(account.account_name)
            self.account_form.load_account(account)
            self._show_info("账号已保存")
        except Exception as exc:
            self._show_error(f"保存账号失败：{exc}")

    def on_delete_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.account_page.get_selected_row()
            if row < 0 or row >= len(self.accounts):
                self._show_error("请先选择一个账号")
                return

            account_name = self.accounts[row].account_name
            self.accounts.pop(row)
            tasks_changed = self._remove_account_from_tasks(account_name)

            self.runtime_service.save_accounts(self.accounts)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self.status_map.pop(account_name, None)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.account_page.select_row(min(row, len(self.accounts) - 1))
            self._show_info("账号已删除，相关任务的账号池已同步更新")
        except Exception as exc:
            self._show_error(f"删除账号失败：{exc}")

    def on_account_up_clicked(self) -> None:
        self._move_item(self.accounts, self.account_page, -1, self.runtime_service.save_accounts, "移动账号失败")

    def on_account_down_clicked(self) -> None:
        self._move_item(self.accounts, self.account_page, 1, self.runtime_service.save_accounts, "移动账号失败")

    def on_login_account_clicked(self) -> None:
        account_name = self.account_page.get_selected_account_name()
        if not account_name:
            self._show_error("请先选择一个账号")
            return

        account = next((item for item in self.accounts if item.account_name == account_name), None)
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
            self._ensure_can_modify_sending_data()
            group = self.group_form.get_form_group()

            if not group.group_name:
                raise ValueError("群组名称不能为空")
            if not group.chat_id:
                raise ValueError("Chat ID 不能为空")

            existing_index = next((idx for idx, item in enumerate(self.groups) if item.group_id == group.group_id), None)
            if existing_index is None:
                self.groups.append(group)
            else:
                self.groups[existing_index] = group

            self.runtime_service.save_groups(self.groups)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.group_page.select_group_id(group.group_id)
            self.group_form.load_group(group)
            self._show_info("群组已保存")
        except Exception as exc:
            self._show_error(f"保存群组失败：{exc}")

    def on_delete_group_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.group_page.get_selected_row()
            if row < 0 or row >= len(self.groups):
                self._show_error("请先选择一个群组")
                return

            group_id = self.groups[row].group_id
            self.groups.pop(row)
            tasks_changed = self._remove_group_from_tasks(group_id)

            self.runtime_service.save_groups(self.groups)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.group_page.select_row(min(row, len(self.groups) - 1))
            self._show_info("群组已删除，相关任务的目标群组池已同步更新")
        except Exception as exc:
            self._show_error(f"删除群组失败：{exc}")

    def on_group_up_clicked(self) -> None:
        self._move_item(self.groups, self.group_page, -1, self.runtime_service.save_groups, "移动群组失败")

    def on_group_down_clicked(self) -> None:
        self._move_item(self.groups, self.group_page, 1, self.runtime_service.save_groups, "移动群组失败")

    def on_save_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            task = self.task_form.get_form_task()

            if not task.task_name:
                raise ValueError("任务名称不能为空")

            self._validate_task_accounts(task)
            self._validate_task_groups(task)
            self._validate_task_message(task)

            existing_index = next((idx for idx, item in enumerate(self.tasks) if item.task_id == task.task_id), None)
            if existing_index is None:
                self.tasks.append(task)
            else:
                self.tasks[existing_index] = task

            self.runtime_service.save_tasks(self.tasks)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.task_page.select_task_id(task.task_id)
            self.task_form.load_task(task)
            self._show_info("任务已保存")
        except Exception as exc:
            self._show_error(f"保存任务失败：{exc}")

    def on_delete_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            if row < 0 or row >= len(self.tasks):
                self._show_error("请先选择一个任务")
                return

            self.tasks.pop(row)
            self.runtime_service.save_tasks(self.tasks)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.task_page.select_row(min(row, len(self.tasks) - 1))
            self._show_info("任务已删除")
        except Exception as exc:
            self._show_error(f"删除任务失败：{exc}")

    def on_task_up_clicked(self) -> None:
        self._move_item(self.tasks, self.task_page, -1, self.runtime_service.save_tasks, "移动任务失败")

    def on_task_down_clicked(self) -> None:
        self._move_item(self.tasks, self.task_page, 1, self.runtime_service.save_tasks, "移动任务失败")

    def on_save_template_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            template = self.template_form.get_form_template()

            if not template.template_name:
                raise ValueError("模板名称不能为空")

            existing_index = next((idx for idx, item in enumerate(self.templates) if item.template_id == template.template_id), None)
            if existing_index is None:
                raise ValueError("模板不存在，模板只能由素材监听自动创建")

            self.templates[existing_index] = template
            self.runtime_service.save_templates(self.templates)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.template_page.select_template_id(template.template_id)
            self.template_form.load_template(template)
            self._show_info("模板已保存")
        except Exception as exc:
            self._show_error(f"保存模板失败：{exc}")

    def on_delete_template_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.template_page.get_selected_row()
            if row < 0 or row >= len(self.templates):
                self._show_error("请先选择一个模板")
                return

            template_id = self.templates[row].template_id
            self.templates.pop(row)
            tasks_changed = self._remove_template_from_tasks(template_id)

            self.runtime_service.save_templates(self.templates)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.template_page.select_row(min(row, len(self.templates) - 1))
            self._show_info("模板已删除，相关任务的模板池已同步更新")
        except Exception as exc:
            self._show_error(f"删除模板失败：{exc}")

    def on_template_up_clicked(self) -> None:
        self._move_item(self.templates, self.template_page, -1, self.runtime_service.save_templates, "移动模板失败")

    def on_template_down_clicked(self) -> None:
        self._move_item(self.templates, self.template_page, 1, self.runtime_service.save_templates, "移动模板失败")

    def _move_item(self, items: list, page, direction: int, save_func, error_title: str) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = page.get_selected_row()
            target_row = row + direction

            if row < 0 or target_row < 0 or target_row >= len(items):
                return

            items[row], items[target_row] = items[target_row], items[row]
            save_func(items)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            page.select_row(target_row)
        except Exception as exc:
            self._show_error(f"{error_title}：{exc}")

    def closeEvent(self, event) -> None:
        try:
            self.templates_sync_timer.stop()
            self.runtime_service.shutdown()
        finally:
            super().closeEvent(event)

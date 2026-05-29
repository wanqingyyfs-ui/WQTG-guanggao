from __future__ import annotations

import concurrent.futures
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from app.core.models import MESSAGE_MODE_TEMPLATE, MESSAGE_MODE_TEXT
from app.gui.dialogs.login_dialog import LoginConfirmDialog
from app.gui.dialogs.verify_dialog import VerifyInputDialog
from app.gui.forms.account_form import AccountForm
from app.gui.forms.group_form import GroupForm
from app.gui.forms.task_form import TaskForm
from app.gui.forms.template_form import TemplateForm
from app.gui.pages.account_page import AccountPage
from app.gui.pages.config_page import ConfigPage
from app.gui.pages.dashboard_page import DashboardPage
from app.gui.pages.group_membership_page import GroupMembershipPage
from app.gui.pages.group_page import GroupPage
try:
    from app.gui.pages.noise_page import NoisePage
except ImportError:
    from app.gui.pages.noise_page import NoisePoolPage as NoisePage
from app.gui.pages.task_page import TaskPage
from app.gui.pages.template_page import TemplatePage
from app.gui.style import build_app_qss
from app.gui.widgets.dock_panel import create_config_dock
from app.services.runtime_service_grouped import RuntimeService


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
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        self._style_signature = self._build_style_signature()
        self._runtime_log_buffer: list[tuple[str, str, str]] = []

        self._apply_app_style()

        self.dashboard_page = DashboardPage()
        self.config_page = ConfigPage(self.runtime_service)
        self.account_page = AccountPage()
        self.group_page = GroupPage()
        self.group_membership_page = GroupMembershipPage()
        self.task_page = TaskPage()
        self.template_page = TemplatePage()
        self.noise_page = NoisePage(self.runtime_service)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.addTab(self.dashboard_page, "运行总控")
        self.tabs.addTab(self.config_page, "配置管理")
        self.tabs.addTab(self.account_page, "账号管理")
        self.tabs.addTab(self.group_page, "群组管理")
        self.tabs.addTab(self.group_membership_page, "分组管理")
        self.tabs.addTab(self.task_page, "任务管理")
        self.tabs.addTab(self.template_page, "模板管理")
        self.tabs.addTab(self.noise_page, "噪音配置")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self._create_docks()

        self.templates_sync_timer = QTimer(self)
        self.templates_sync_timer.setInterval(1500)
        self.templates_sync_timer.timeout.connect(self.on_templates_sync_timer)

        self._runtime_log_flush_timer = QTimer(self)
        self._runtime_log_flush_timer.setInterval(250)
        self._runtime_log_flush_timer.timeout.connect(self._flush_runtime_log_buffer)

        self._status_refresh_timer = QTimer(self)
        self._status_refresh_timer.setInterval(400)
        self._status_refresh_timer.timeout.connect(self._flush_account_status_refresh)

        self._connect_signals()
        self.refresh_all_views()
        self.templates_sync_timer.start()
        self.statusBar().showMessage("准备就绪", 3000)

    def _create_docks(self) -> None:
        self.account_form = AccountForm()
        self.group_form = GroupForm()
        self.task_form = TaskForm()
        self.template_form = TemplateForm()
        self.account_dock = create_config_dock(self, "accountConfigDock", "账号配置", self.account_form, int(getattr(self.settings, "account_panel_width", 520)), int(getattr(self.settings, "account_panel_height", 620)), int(getattr(self.settings, "account_panel_font_size", 13)))
        self.group_dock = create_config_dock(self, "groupConfigDock", "群组配置", self.group_form, int(getattr(self.settings, "group_panel_width", 520)), int(getattr(self.settings, "group_panel_height", 620)), int(getattr(self.settings, "group_panel_font_size", 13)))
        self.task_dock = create_config_dock(self, "taskConfigDock", "任务配置", self.task_form, int(getattr(self.settings, "task_panel_width", 680)), int(getattr(self.settings, "task_panel_height", 760)), int(getattr(self.settings, "task_panel_font_size", 13)))
        self.template_dock = create_config_dock(self, "templateConfigDock", "模板配置", self.template_form, int(getattr(self.settings, "template_panel_width", 520)), int(getattr(self.settings, "template_panel_height", 520)), int(getattr(self.settings, "template_panel_font_size", 13)))
        self.account_dock.hide(); self.group_dock.hide(); self.task_dock.hide(); self.template_dock.hide()

    def _connect_signals(self) -> None:
        self.dashboard_page.start_all_requested.connect(self.on_start_all_clicked)
        self.dashboard_page.stop_all_requested.connect(self.on_stop_all_clicked)
        self.dashboard_page.start_scheduler_requested.connect(self.on_start_scheduler_clicked)
        self.dashboard_page.stop_scheduler_requested.connect(self.on_stop_scheduler_clicked)

        self.account_page.config_button.clicked.connect(self.on_open_account_config)
        self.account_page.delete_button.clicked.connect(self.on_delete_account_clicked)
        self.account_page.up_button.clicked.connect(self.on_account_up_clicked)
        self.account_page.down_button.clicked.connect(self.on_account_down_clicked)
        self.account_page.login_button.clicked.connect(self.on_login_account_clicked)
        self.account_page.start_button.clicked.connect(self.on_start_account_clicked)
        self.account_page.stop_button.clicked.connect(self.on_stop_account_clicked)

        self.group_page.config_button.clicked.connect(self.on_open_group_config)
        self.group_page.delete_button.clicked.connect(self.on_delete_group_clicked)
        self.group_page.up_button.clicked.connect(self.on_group_up_clicked)
        self.group_page.down_button.clicked.connect(self.on_group_down_clicked)

        self.group_membership_page.save_requested.connect(self.on_save_group_memberships_requested)
        self.group_membership_page.discard_requested.connect(self.on_discard_group_memberships_requested)

        self.task_page.config_button.clicked.connect(self.on_open_task_config)
        self.task_page.delete_button.clicked.connect(self.on_delete_task_clicked)
        self.task_page.up_button.clicked.connect(self.on_task_up_clicked)
        self.task_page.down_button.clicked.connect(self.on_task_down_clicked)
        self.task_page.start_task_button.clicked.connect(self.on_start_selected_task_clicked)
        self.task_page.stop_task_button.clicked.connect(self.on_stop_selected_task_clicked)

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
        self.runtime_service.scheduler_status_changed.connect(self.on_scheduler_status_changed)
        if hasattr(self.runtime_service, "noise_pool_changed"):
            self.runtime_service.noise_pool_changed.connect(self.on_noise_pool_changed)
        self.runtime_service.input_provider.code_input_required.connect(self.on_code_input_required)
        self.runtime_service.input_provider.password_input_required.connect(self.on_password_input_required)

    def _build_style_signature(self) -> tuple[int, ...]:
        return tuple(int(getattr(self.settings, name, 13) or 13) for name in [
            "global_font_size", "table_font_size", "button_font_size", "input_font_size", "floating_panel_font_size",
            "account_panel_font_size", "group_panel_font_size", "task_panel_font_size", "template_panel_font_size",
        ])

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

    def refresh_all_views(self) -> None:
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        account_group_definitions = self._merge_account_group_definitions()
        group_group_definitions = self._merge_group_group_definitions()

        self.account_page.set_defaults(bool(getattr(self.settings, "default_account_enabled", True)), bool(getattr(self.settings, "default_session_name_follow_account", True)))
        self.group_page.set_defaults(bool(getattr(self.settings, "default_group_enabled", True)), bool(getattr(self.settings, "default_group_username_normalize", True)))
        self.account_form.set_defaults(bool(getattr(self.settings, "default_account_enabled", True)), bool(getattr(self.settings, "default_session_name_follow_account", True)))
        self.group_form.set_defaults(bool(getattr(self.settings, "default_group_enabled", True)), bool(getattr(self.settings, "default_group_username_normalize", True)))

        self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings, self.tasks, account_group_definitions=account_group_definitions, group_group_definitions=group_group_definitions)
        self.dashboard_page.update_summary(self.accounts, self.groups, self.tasks, self.settings, self.scheduler_status)
        self.dashboard_page.update_status_table(self.accounts, self.status_map)
        self.account_page.set_accounts(self.accounts, self.status_map)
        self.group_page.set_groups(self.groups)
        self.task_page.set_context(self.accounts, self.groups, self.templates, self.settings)
        self.task_page.set_tasks(self.tasks)
        self.template_page.set_templates(self.templates)
        if not self.group_membership_page.is_dirty():
            self.group_membership_page.set_context(self.accounts, self.groups, {"account_groups": account_group_definitions, "group_groups": group_group_definitions}, self.account_group_proxies)

    def _force_refresh_group_membership_page(self) -> None:
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        self.group_membership_page.set_context(self.accounts, self.groups, {"account_groups": self._merge_account_group_definitions(), "group_groups": self._merge_group_group_definitions()}, self.account_group_proxies)

    def _load_group_membership_sets(self) -> dict[str, list[str]]:
        try:
            return self.runtime_service.config_service.load_group_sets()
        except Exception:
            return {"account_groups": [], "group_groups": []}

    def _save_group_membership_sets(self, group_sets: dict) -> None:
        self.runtime_service.config_service.save_group_sets(group_sets)
        self.group_membership_sets = self._load_group_membership_sets()

    def _load_account_group_proxies(self) -> dict:
        try:
            return self.runtime_service.config_service.load_account_group_proxies()
        except Exception:
            return {}

    def _save_account_group_proxies(self, account_group_proxies: dict) -> None:
        self.runtime_service.config_service.save_account_group_proxies(account_group_proxies)
        self.account_group_proxies = self._load_account_group_proxies()

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "错误", text)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "提示", text)

    def _ensure_can_modify_sending_data(self) -> None:
        if self.runtime_service.is_scheduler_running():
            raise RuntimeError("请先停止群发功能")

    def _open_dock(self, dock) -> None:
        if hasattr(dock, "open_panel") and callable(dock.open_panel):
            dock.open_panel(); return
        dock.show(); dock.raise_(); dock.activateWindow()

    def on_open_account_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); self.account_page.clear_selection(); self.account_form.clear_form(); self._open_dock(self.account_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_account_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.account_page.get_selected_row()
            self.account_form.load_account(self.accounts[row]) if 0 <= row < len(self.accounts) else self.account_form.clear_form()
            self._open_dock(self.account_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_group_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); self.group_page.clear_selection(); self.group_form.clear_form(); self._open_dock(self.group_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_group_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.group_page.get_selected_row()
            self.group_form.load_group(self.groups[row]) if 0 <= row < len(self.groups) else self.group_form.clear_form()
            self._open_dock(self.group_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_task_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); self.task_page.clear_selection()
            self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings, self.tasks, "", self._merge_account_group_definitions(), self._merge_group_group_definitions())
            self.task_form.clear_form(); self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_task_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.task_page.get_selected_row(); current_task_id = ""
            if 0 <= row < len(self.tasks): current_task_id = str(getattr(self.tasks[row], "task_id", "") or "")
            self.task_form.set_context(self.accounts, self.groups, self.templates, self.settings, self.tasks, current_task_id, self._merge_account_group_definitions(), self._merge_group_group_definitions())
            self.task_form.load_task(self.tasks[row]) if 0 <= row < len(self.tasks) else self.task_form.clear_form()
            self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_template_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.template_page.get_selected_row()
            self.template_form.load_template(self.templates[row]) if 0 <= row < len(self.templates) else self.template_form.clear_form()
            self._open_dock(self.template_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_save_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); account = self.account_form.get_form_account()
            if not account.account_name: raise ValueError("账号名称不能为空")
            if not account.api_hash: raise ValueError("API Hash 不能为空")
            if not account.phone: raise ValueError("手机号不能为空")
            if not account.session_name: account.session_name = account.account_name
            selected_index = self.account_page.get_selected_row(); existing_index = selected_index if 0 <= selected_index < len(self.accounts) else next((idx for idx, item in enumerate(self.accounts) if item.account_name == account.account_name), None)
            for idx, item in enumerate(self.accounts):
                if idx != existing_index and item.account_name == account.account_name: raise ValueError("账号名称已存在，不能重复")
            if existing_index is None: self.accounts.append(account)
            else: self.accounts[existing_index] = account
            self.runtime_service.save_accounts(self.accounts); self._sync_state_from_runtime(); self.refresh_all_views(); self.account_page.select_account_name(account.account_name); self.account_form.load_account(account); self._show_info("账号已保存")
        except Exception as exc:
            self._show_error(f"保存账号失败：{exc}")

    def on_delete_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.account_page.get_selected_row()
            if row < 0 or row >= len(self.accounts): self._show_error("请先选择一个账号"); return
            account_name = self.accounts[row].account_name; self.accounts.pop(row); self.runtime_service.save_accounts(self.accounts); self.status_map.pop(account_name, None)
            self._sync_state_from_runtime(); self.refresh_all_views(); self.account_page.select_row(min(row, len(self.accounts) - 1)); self._show_info("账号已删除")
        except Exception as exc:
            self._show_error(f"删除账号失败：{exc}")

    def on_account_up_clicked(self) -> None: self._move_item(self.accounts, self.account_page, -1, self.runtime_service.save_accounts, "移动账号失败")
    def on_account_down_clicked(self) -> None: self._move_item(self.accounts, self.account_page, 1, self.runtime_service.save_accounts, "移动账号失败")

    def on_login_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); account_name = self.account_page.get_selected_account_name()
            if not account_name: self._show_error("请先选择一个账号"); return
            account = next((item for item in self.accounts if item.account_name == account_name), None)
            if account is None: self._show_error("账号不存在"); return
            if LoginConfirmDialog(account.account_name, account.phone, self).exec(): self.runtime_service.login_account(account_name)
        except Exception as exc:
            self._show_error(str(exc))

    def on_start_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); account_name = self.account_page.get_selected_account_name()
            if not account_name: self._show_error("请先选择一个账号"); return
            self.runtime_service.start_account(account_name)
        except Exception as exc:
            self._show_error(str(exc))

    def on_stop_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); account_name = self.account_page.get_selected_account_name()
            if not account_name: self._show_error("请先选择一个账号"); return
            self.runtime_service.stop_account(account_name)
        except Exception as exc:
            self._show_error(str(exc))

    def on_save_group_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); group = self.group_form.get_form_group()
            if not group.group_name: raise ValueError("群组名称不能为空")
            if not group.chat_id: raise ValueError("Chat ID 不能为空")
            existing_index = next((idx for idx, item in enumerate(self.groups) if item.group_id == group.group_id), None)
            if existing_index is None: self.groups.append(group)
            else: self.groups[existing_index] = group
            self.runtime_service.save_groups(self.groups); self._sync_state_from_runtime(); self.refresh_all_views(); self.group_page.select_group_id(group.group_id); self.group_form.load_group(group); self._show_info("群组已保存")
        except Exception as exc:
            self._show_error(f"保存群组失败：{exc}")

    def on_delete_group_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.group_page.get_selected_row()
            if row < 0 or row >= len(self.groups): self._show_error("请先选择一个群组"); return
            self.groups.pop(row); self.runtime_service.save_groups(self.groups); self._sync_state_from_runtime(); self.refresh_all_views(); self.group_page.select_row(min(row, len(self.groups) - 1)); self._show_info("群组已删除")
        except Exception as exc:
            self._show_error(f"删除群组失败：{exc}")

    def on_group_up_clicked(self) -> None: self._move_item(self.groups, self.group_page, -1, self.runtime_service.save_groups, "移动群组失败")
    def on_group_down_clicked(self) -> None: self._move_item(self.groups, self.group_page, 1, self.runtime_service.save_groups, "移动群组失败")

    def on_save_group_memberships_requested(self, accounts, groups, group_sets, account_group_proxies=None) -> None:
        try:
            self._ensure_can_modify_sending_data(); self._save_group_membership_sets(group_sets if isinstance(group_sets, dict) else {}); self._save_account_group_proxies(account_group_proxies if isinstance(account_group_proxies, dict) else {})
            self.runtime_service.save_accounts(list(accounts or [])); self.runtime_service.save_groups(list(groups or [])); self._sync_state_from_runtime(); self.group_membership_page.mark_clean(); self.refresh_all_views(); self._force_refresh_group_membership_page(); self._show_info("分组配置已保存")
        except Exception as exc:
            self._show_error(f"保存分组配置失败：{exc}")

    def on_discard_group_memberships_requested(self) -> None:
        try:
            self.runtime_service.reload_config_cache(); self._sync_state_from_runtime(); self.group_membership_page.mark_clean(); self.refresh_all_views(); self._force_refresh_group_membership_page(); self.statusBar().showMessage("已放弃未保存的分组更改", 3000)
        except Exception as exc:
            self._show_error(f"放弃未保存更改失败：{exc}")

    def on_save_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); task = self.task_form.get_form_task(); self._validate_grouped_task(task)
            existing_index = next((idx for idx, item in enumerate(self.tasks) if item.task_id == task.task_id), None)
            if existing_index is None: self.tasks.append(task)
            else: self.tasks[existing_index] = task
            self.runtime_service.save_tasks(self.tasks); self._sync_state_from_runtime(); self.refresh_all_views(); self.task_page.select_task_id(task.task_id); self.task_form.load_task(task); self._show_info("任务已保存")
        except Exception as exc:
            self._show_error(f"保存任务失败：{exc}")

    def on_delete_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.task_page.get_selected_row()
            if row < 0 or row >= len(self.tasks): self._show_error("请先选择一个任务"); return
            self.tasks.pop(row); self.runtime_service.save_tasks(self.tasks); self._sync_state_from_runtime(); self.refresh_all_views(); self.task_page.select_row(min(row, len(self.tasks) - 1)); self._show_info("任务已删除")
        except Exception as exc:
            self._show_error(f"删除任务失败：{exc}")

    def on_task_up_clicked(self) -> None: self._move_item(self.tasks, self.task_page, -1, self.runtime_service.save_tasks, "移动任务失败")
    def on_task_down_clicked(self) -> None: self._move_item(self.tasks, self.task_page, 1, self.runtime_service.save_tasks, "移动任务失败")

    def on_start_selected_task_clicked(self) -> None:
        try:
            task_id = self.task_page.get_selected_task_id()
            if not task_id: self._show_error("请先选择一个任务"); return
            task = next((item for item in self.tasks if str(getattr(item, "task_id", "") or "") == task_id), None)
            if task is None: self._show_error("任务不存在"); return
            if not bool(getattr(task, "enabled", True)): self._show_error("未启用任务不能启动，请先启用任务"); return
            self.runtime_service.start_task_scheduler(task_id); self.statusBar().showMessage(f"已请求启动任务：{getattr(task, 'task_name', task_id)}", 3000)
        except Exception as exc:
            self._show_error(f"启动任务失败：{exc}")

    def on_stop_selected_task_clicked(self) -> None:
        try:
            task_id = self.task_page.get_selected_task_id()
            if not task_id: self._show_error("请先选择一个任务"); return
            self.runtime_service.stop_task_scheduler(task_id); self.statusBar().showMessage("已请求停止任务", 3000)
        except Exception as exc:
            self._show_error(f"停止任务失败：{exc}")

    def on_save_template_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); template = self.template_form.get_form_template()
            if not template.template_name: raise ValueError("模板名称不能为空")
            existing_index = next((idx for idx, item in enumerate(self.templates) if item.template_id == template.template_id), None)
            if existing_index is None: raise ValueError("模板不存在，模板只能由素材监听自动创建")
            self.templates[existing_index] = template; self.runtime_service.save_templates(self.templates); self._sync_state_from_runtime(); self.refresh_all_views(); self.template_page.select_template_id(template.template_id); self.template_form.load_template(template); self._show_info("模板已保存")
        except Exception as exc:
            self._show_error(f"保存模板失败：{exc}")

    def on_delete_template_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data(); row = self.template_page.get_selected_row()
            if row < 0 or row >= len(self.templates): self._show_error("请先选择一个模板"); return
            template_id = self.templates[row].template_id; self.templates.pop(row); tasks_changed = self._remove_template_from_tasks(template_id)
            self.runtime_service.save_templates(self.templates)
            if tasks_changed: self.runtime_service.save_tasks(self.tasks)
            self._sync_state_from_runtime(); self.refresh_all_views(); self.template_page.select_row(min(row, len(self.templates) - 1)); self._show_info("模板已删除，相关任务的模板池已同步更新")
        except Exception as exc:
            self._show_error(f"删除模板失败：{exc}")

    def on_template_up_clicked(self) -> None: self._move_template_and_sync_tasks(-1)
    def on_template_down_clicked(self) -> None: self._move_template_and_sync_tasks(1)

    def _validate_grouped_task(self, task) -> None:
        if not str(getattr(task, "task_name", "") or "").strip(): raise ValueError("任务名称不能为空")
        account_group_names = self._task_account_group_names(task); group_group_names = self._task_group_group_names(task)
        if not account_group_names: raise ValueError("账号组池不能为空，请先在分组管理里新增账号组并选择账号")
        if not group_group_names: raise ValueError("群聊组池不能为空，请先在分组管理里新增群聊组并选择群")
        if len(account_group_names) != len(group_group_names): raise ValueError(f"账号组数量和群聊组数量必须一致。当前账号组 {len(account_group_names)} 个，群聊组 {len(group_group_names)} 个。")
        conflict = self._find_account_group_conflict(task)
        if conflict: raise ValueError(conflict)
        missing_account_groups = [name for name in account_group_names if not self._enabled_accounts_in_group(name)]
        if missing_account_groups: raise ValueError("以下账号组没有启用账号：" + "、".join(missing_account_groups))
        missing_group_groups = [name for name in group_group_names if not self._enabled_groups_in_group(name)]
        if missing_group_groups: raise ValueError("以下群聊组没有启用群组：" + "、".join(missing_group_groups))
        if int(getattr(task, "account_delay_max_ms", 0) or 0) < int(getattr(task, "account_delay_min_ms", 0) or 0): raise ValueError("账号延迟最大值不能小于账号延迟最小值")
        if int(getattr(task, "group_delay_max_ms", 0) or 0) < int(getattr(task, "group_delay_min_ms", 0) or 0): raise ValueError("群组延迟最大值不能小于群组延迟最小值")
        if bool(getattr(task, "daily_window_enabled", False)) and str(task.daily_start_time) == str(task.daily_end_time): raise ValueError("每日开始时间不能等于每日结束时间")
        if str(getattr(task, "message_mode", "") or "") == MESSAGE_MODE_TEMPLATE:
            template_ids = self._task_template_ids(task)
            if not template_ids: raise ValueError("模板消息必须至少选择一个模板")
            existing = {template.template_id for template in self.templates}; missing = [item for item in template_ids if item not in existing]
            if missing: raise ValueError("模板不存在：" + "、".join(missing))
        elif str(getattr(task, "message_mode", "") or "") == MESSAGE_MODE_TEXT:
            if not str(getattr(task, "text", "") or "").strip(): raise ValueError("文本消息必须填写内容")
        else: raise ValueError("不支持的消息类型")

    def _find_account_group_conflict(self, task) -> str:
        current_task_id = str(getattr(task, "task_id", "") or "").strip(); selected = set(self._task_account_group_names(task))
        for other in self.tasks:
            if not bool(getattr(other, "enabled", True)): continue
            other_id = str(getattr(other, "task_id", "") or "").strip()
            if other_id and other_id == current_task_id: continue
            for group_name in self._task_account_group_names(other):
                if group_name in selected: return f"账号组【{group_name}】已被启用任务【{getattr(other, 'task_name', other_id)}】占用，不能重复选择"
        return ""

    def _enabled_accounts_in_group(self, account_group: str):
        target = str(account_group or "").strip(); return [account for account in self.accounts if bool(getattr(account, "enabled", True)) and str(getattr(account, "account_group", "") or "").strip() == target]

    def _enabled_groups_in_group(self, group_group: str):
        target = str(group_group or "").strip(); return [group for group in self.groups if bool(getattr(group, "enabled", True)) and target in self._group_group_names(group)]

    def _merge_account_group_definitions(self) -> list[str]:
        result = self._normalize_text_values(self.group_membership_sets.get("account_groups"))
        for account in self.accounts:
            value = str(getattr(account, "account_group", "") or "").strip()
            if value and value not in result: result.append(value)
        return result

    def _merge_group_group_definitions(self) -> list[str]:
        result = self._normalize_text_values(self.group_membership_sets.get("group_groups"))
        for group in self.groups:
            for value in self._group_group_names(group):
                if value and value not in result: result.append(value)
        return result

    @staticmethod
    def _normalize_text_values(values) -> list[str]:
        result: list[str] = []
        raw_items = [values] if isinstance(values, str) else list(values or [])
        for item in raw_items:
            value = str(item or "").strip()
            if value and value not in result: result.append(value)
        return result

    @staticmethod
    def _task_account_group_names(task) -> list[str]:
        return MainWindow._normalize_text_values(getattr(task, "account_group_names", []) or [])

    @staticmethod
    def _task_group_group_names(task) -> list[str]:
        return MainWindow._normalize_text_values(getattr(task, "group_group_names", []) or [])

    @staticmethod
    def _group_group_names(group) -> list[str]:
        result = MainWindow._normalize_text_values(getattr(group, "group_group_names", []) or [])
        legacy = str(getattr(group, "group_group", "") or "").strip()
        if legacy and legacy not in result: result.insert(0, legacy)
        return result

    @staticmethod
    def _task_template_ids(task) -> list[str]:
        result = MainWindow._normalize_text_values(getattr(task, "template_ids", []) or [])
        legacy = str(getattr(task, "template_id", "") or "").strip()
        if legacy and legacy not in result: result.insert(0, legacy)
        return result

    def _remove_template_from_tasks(self, template_id: str) -> bool:
        target = str(template_id or "").strip(); changed = False
        for task in self.tasks:
            template_ids = self._task_template_ids(task); filtered = [item for item in template_ids if item != target]
            if filtered != template_ids: task.template_ids = filtered; changed = True
            if str(getattr(task, "template_id", "") or "").strip() == target: task.template_id = filtered[0] if filtered else ""; changed = True
        return changed

    def _move_template_and_sync_tasks(self, direction: int) -> None:
        try:
            self._ensure_can_modify_sending_data(); target_row = self._swap_selected_item(self.templates, self.template_page, direction)
            if target_row < 0: return
            self.runtime_service.save_templates(self.templates); self._sync_state_from_runtime(); self.refresh_all_views(); self.template_page.select_row(target_row)
        except Exception as exc: self._show_error(f"移动模板失败：{exc}")

    def _move_item(self, items: list, page, direction: int, save_func, error_title: str) -> None:
        try:
            self._ensure_can_modify_sending_data(); target_row = self._swap_selected_item(items, page, direction)
            if target_row < 0: return
            save_func(items); self._sync_state_from_runtime(); self.refresh_all_views(); page.select_row(target_row)
        except Exception as exc: self._show_error(f"{error_title}：{exc}")

    @staticmethod
    def _swap_selected_item(items: list, page, direction: int) -> int:
        row = page.get_selected_row(); target_row = row + direction
        if row < 0 or target_row < 0 or target_row >= len(items): return -1
        items[row], items[target_row] = items[target_row], items[row]; return target_row

    def on_runtime_log_received(self, level: str, message: str) -> None:
        now_text = datetime.now().strftime("%H:%M:%S")
        self._runtime_log_buffer.append((now_text, str(level or "INFO").upper(), str(message or "")))
        if len(self._runtime_log_buffer) > 2000: self._runtime_log_buffer = self._runtime_log_buffer[-2000:]
        if not self._runtime_log_flush_timer.isActive(): self._runtime_log_flush_timer.start()

    def _flush_runtime_log_buffer(self) -> None:
        if not self._runtime_log_buffer: self._runtime_log_flush_timer.stop(); return
        batch = self._runtime_log_buffer[:300]; del self._runtime_log_buffer[:300]
        self.dashboard_page.append_log_lines([f"{time_text} [{level}] {message}" for time_text, level, message in batch])
        if not self._runtime_log_buffer: self._runtime_log_flush_timer.stop()

    def on_runtime_hint(self, message: str) -> None:
        self.on_runtime_log_received("INFO", message); self.statusBar().showMessage(message, 5000)

    def on_account_status_changed(self, account_name: str, status: str, detail: str) -> None:
        self.status_map[account_name] = (status, detail)
        if not self._status_refresh_timer.isActive(): self._status_refresh_timer.start()

    def _flush_account_status_refresh(self) -> None:
        self._status_refresh_timer.stop(); self.dashboard_page.update_summary(self.accounts, self.groups, self.tasks, self.settings, self.scheduler_status); self.dashboard_page.update_status_table(self.accounts, self.status_map); self.account_page.set_accounts(self.accounts, self.status_map)

    def on_scheduler_status_changed(self, status: str) -> None:
        self.scheduler_status = status; self.dashboard_page.update_summary(self.accounts, self.groups, self.tasks, self.settings, self.scheduler_status); self.statusBar().showMessage(f"调度器状态：{status}", 3000)

    def on_templates_changed(self) -> None:
        self._sync_state_from_runtime(); self.refresh_all_views(); self.statusBar().showMessage("模板列表已自动刷新", 3000)

    def on_noise_pool_changed(self) -> None:
        self.statusBar().showMessage("噪音池已更新", 3000)

    def on_templates_sync_timer(self) -> None:
        try:
            changed = self.runtime_service.sync_templates_from_disk(); noise_changed = bool(self.runtime_service.sync_noise_pool_from_disk()) if hasattr(self.runtime_service, "sync_noise_pool_from_disk") else False
            if changed or noise_changed: self._sync_state_from_runtime(); self.refresh_all_views()
        except Exception as exc: self.on_runtime_log_received("WARNING", f"自动同步配置失败：{exc}")

    def on_reload_clicked(self) -> None:
        try:
            self.runtime_service.reload_config_cache(); self._sync_state_from_runtime()
            if hasattr(self.config_page, "reload_from_runtime"): self.config_page.reload_from_runtime()
            if hasattr(self.noise_page, "reload_from_runtime"): self.noise_page.reload_from_runtime()
            self.refresh_all_views(); self._show_info("配置已重新加载")
        except Exception as exc: self._show_error(f"重新加载失败：{exc}")

    def on_start_all_clicked(self) -> None:
        try: self.runtime_service.start_all()
        except Exception as exc: self._show_error(f"启动失败：{exc}")

    def on_stop_all_clicked(self) -> None:
        try: self.runtime_service.stop_all()
        except Exception as exc: self._show_error(f"停止失败：{exc}")

    def on_start_scheduler_clicked(self) -> None:
        try: self.runtime_service.start_scheduler()
        except Exception as exc: self._show_error(f"启动群发失败：{exc}")

    def on_stop_scheduler_clicked(self) -> None:
        try: self.runtime_service.stop_scheduler()
        except Exception as exc: self._show_error(f"停止群发失败：{exc}")

    def on_code_input_required(self, account_name: str, phone: str, future: concurrent.futures.Future) -> None:
        dialog = VerifyInputDialog("输入验证码", f"账号：{account_name}\n手机号：{phone}\n\n请输入 Telegram 验证码：", False, self)
        future.set_result(dialog.get_value() if dialog.exec() and not future.done() else "") if not future.done() else None

    def on_password_input_required(self, account_name: str, future: concurrent.futures.Future) -> None:
        dialog = VerifyInputDialog("输入二步验证密码", f"账号：{account_name}\n\n请输入二步验证密码：", True, self)
        future.set_result(dialog.get_value() if dialog.exec() and not future.done() else "") if not future.done() else None

    def closeEvent(self, event) -> None:
        try:
            self.templates_sync_timer.stop(); self._runtime_log_flush_timer.stop(); self._status_refresh_timer.stop(); self.runtime_service.shutdown()
        finally:
            super().closeEvent(event)

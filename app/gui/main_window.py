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
from app.gui.pages.account_page import AccountPage
from app.gui.pages.config_page import ConfigPage
from app.gui.pages.dashboard_page import DashboardPage
from app.gui.pages.group_page import GroupPage
from app.gui.pages.log_page import LogPage
from app.gui.pages.noise_page import NoisePage
from app.gui.pages.task_page import TaskPage
from app.gui.pages.template_page import TemplatePage
from app.gui.style import build_app_qss
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

        self._hide_legacy_send_once_button()

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

        self.templates_sync_timer = QTimer(self)
        self.templates_sync_timer.setInterval(1500)

        self._connect_signals()
        self.refresh_all_views()

        self.templates_sync_timer.timeout.connect(self.on_templates_sync_timer)
        self.templates_sync_timer.start()

        self.statusBar().showMessage("准备就绪", 3000)

    def _connect_signals(self) -> None:
        if hasattr(self.dashboard_page, "save_button"):
            self.dashboard_page.save_button.clicked.connect(self.on_save_all_clicked)

        if hasattr(self.dashboard_page, "reload_button"):
            self.dashboard_page.reload_button.clicked.connect(self.on_reload_clicked)

        if hasattr(self.dashboard_page, "start_all_button"):
            self.dashboard_page.start_all_button.clicked.connect(
                self.on_start_all_clicked
            )

        if hasattr(self.dashboard_page, "stop_all_button"):
            self.dashboard_page.stop_all_button.clicked.connect(
                self.on_stop_all_clicked
            )

        if hasattr(self.dashboard_page, "start_scheduler_button"):
            self.dashboard_page.start_scheduler_button.clicked.connect(
                self.on_start_scheduler_clicked
            )

        if hasattr(self.dashboard_page, "stop_scheduler_button"):
            self.dashboard_page.stop_scheduler_button.clicked.connect(
                self.on_stop_scheduler_clicked
            )

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

        self.template_page.add_button.clicked.connect(self.template_page.clear_form)
        self.template_page.save_button.clicked.connect(self.on_save_template_clicked)
        self.template_page.delete_button.clicked.connect(
            self.on_delete_template_clicked
        )

        if hasattr(self.template_page, "refresh_button"):
            self.template_page.refresh_button.clicked.connect(self.on_reload_clicked)

        self.runtime_service.log_received.connect(self.on_runtime_log_received)
        self.runtime_service.account_status_changed.connect(
            self.on_account_status_changed
        )
        self.runtime_service.runtime_hint.connect(self.on_runtime_hint)
        self.runtime_service.templates_changed.connect(self.on_templates_changed)

        if hasattr(self.runtime_service, "noise_pool_changed"):
            self.runtime_service.noise_pool_changed.connect(self.on_noise_pool_changed)

        self.runtime_service.scheduler_status_changed.connect(
            self.on_scheduler_status_changed
        )

        self.runtime_service.input_provider.code_input_required.connect(
            self.on_code_input_required
        )
        self.runtime_service.input_provider.password_input_required.connect(
            self.on_password_input_required
        )

    def _hide_legacy_send_once_button(self) -> None:
        if not hasattr(self.task_page, "send_once_button"):
            return

        self.task_page.send_once_button.setVisible(False)
        self.task_page.send_once_button.setEnabled(False)
        self.task_page.send_once_button.setToolTip(
            "最终版已移除立即发送一次功能"
        )

    def _build_style_signature(self) -> tuple[int, int, int, int]:
        return (
            int(getattr(self.settings, "global_font_size", 13) or 13),
            int(getattr(self.settings, "table_font_size", 13) or 13),
            int(getattr(self.settings, "button_font_size", 13) or 13),
            int(getattr(self.settings, "input_font_size", 13) or 13),
        )

    def _apply_app_style(self) -> None:
        self.setStyleSheet(build_app_qss(self.settings))

    def _refresh_style_if_needed(self) -> None:
        current_signature = self._build_style_signature()

        if current_signature == self._style_signature:
            return

        self._style_signature = current_signature
        self._apply_app_style()

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
        self.task_page.set_context(self.accounts, self.groups, self.templates)
        self.task_page.set_tasks(self.tasks)
        self.template_page.set_templates(self.templates)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "错误", text)

    def _show_info(self, text: str) -> None:
        QMessageBox.information(self, "提示", text)

    def _ensure_can_modify_sending_data(self) -> None:
        if hasattr(self.runtime_service, "ensure_can_modify_sending_data"):
            self.runtime_service.ensure_can_modify_sending_data()
            return

        if self.scheduler_status == "running":
            raise RuntimeError("群发运行中，不能修改会影响发送的数据，请先停止群发调度器")

    def _sync_settings_from_dashboard(self) -> None:
        if hasattr(self.dashboard_page, "scheduler_tick_spin"):
            self.settings.scheduler_tick_seconds = float(
                self.dashboard_page.scheduler_tick_spin.value()
            )

        if hasattr(self.dashboard_page, "max_concurrent_tasks_spin"):
            self.settings.max_concurrent_tasks = int(
                self.dashboard_page.max_concurrent_tasks_spin.value()
            )

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

    def _get_selected_account_index(self) -> int:
        selected_rows = self.account_page.table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def _replace_account_name_in_tasks(
        self,
        old_account_name: str,
        new_account_name: str,
    ) -> bool:
        old_value = str(old_account_name or "").strip()
        new_value = str(new_account_name or "").strip()

        if not old_value or not new_value or old_value == new_value:
            return False

        changed = False

        for task in self.tasks:
            account_names = self._task_account_names(task)

            replaced_names: list[str] = []
            for account_name in account_names:
                value = new_value if account_name == old_value else account_name
                if value and value not in replaced_names:
                    replaced_names.append(value)

            if replaced_names != account_names:
                task.account_names = replaced_names
                changed = True

            if str(getattr(task, "account_name", "") or "").strip() == old_value:
                task.account_name = new_value
                changed = True

        return changed

    def _remove_account_from_tasks(self, account_name: str) -> bool:
        target_account_name = str(account_name or "").strip()
        if not target_account_name:
            return False

        changed = False

        for task in self.tasks:
            account_names = self._task_account_names(task)
            filtered_account_names = [
                value for value in account_names if value != target_account_name
            ]

            if filtered_account_names != account_names:
                task.account_names = filtered_account_names
                changed = True

            if str(getattr(task, "account_name", "") or "").strip() == target_account_name:
                task.account_name = (
                    filtered_account_names[0] if filtered_account_names else ""
                )
                changed = True

            if filtered_account_names:
                current_index = self._safe_non_negative_int(
                    getattr(task, "current_account_index", 0),
                    0,
                )

                if current_index >= len(filtered_account_names):
                    task.current_account_index = 0
                    changed = True
            else:
                if getattr(task, "current_account_index", 0) != 0:
                    task.current_account_index = 0
                    changed = True

        return changed

    def _remove_group_from_tasks(self, group_id: str) -> bool:
        target_group_id = str(group_id or "").strip()
        if not target_group_id:
            return False

        changed = False

        for task in self.tasks:
            group_ids = self._task_group_ids(task)
            filtered_group_ids = [
                value for value in group_ids if value != target_group_id
            ]

            if filtered_group_ids != group_ids:
                task.group_ids = filtered_group_ids
                changed = True

            if str(getattr(task, "group_id", "") or "").strip() == target_group_id:
                task.group_id = filtered_group_ids[0] if filtered_group_ids else ""
                changed = True

            if filtered_group_ids:
                current_index = self._safe_non_negative_int(
                    getattr(task, "current_group_index", 0),
                    0,
                )

                if current_index >= len(filtered_group_ids):
                    task.current_group_index = 0
                    changed = True
            else:
                if getattr(task, "current_group_index", 0) != 0:
                    task.current_group_index = 0
                    changed = True

        return changed

    def _remove_template_from_tasks(self, template_id: str) -> bool:
        target_template_id = str(template_id or "").strip()
        if not target_template_id:
            return False

        changed = False

        for task in self.tasks:
            template_ids = self._task_template_ids(task)
            filtered_template_ids = [
                value for value in template_ids if value != target_template_id
            ]

            if filtered_template_ids != template_ids:
                task.template_ids = filtered_template_ids
                changed = True

            if str(getattr(task, "template_id", "") or "").strip() == target_template_id:
                task.template_id = (
                    filtered_template_ids[0] if filtered_template_ids else ""
                )
                changed = True

        return changed

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _safe_non_negative_int(cls, value: Any, default: int = 0) -> int:
        number = cls._safe_int(value, default)

        if number < 0:
            return 0

        return number

    @staticmethod
    def _task_account_names(task) -> list[str]:
        account_names: list[str] = []

        for raw_account_name in getattr(task, "account_names", []) or []:
            value = str(raw_account_name or "").strip()
            if value and value not in account_names:
                account_names.append(value)

        legacy_account_name = str(getattr(task, "account_name", "") or "").strip()
        if legacy_account_name and legacy_account_name not in account_names:
            account_names.insert(0, legacy_account_name)

        return account_names

    @staticmethod
    def _task_group_ids(task) -> list[str]:
        group_ids: list[str] = []

        for raw_group_id in getattr(task, "group_ids", []) or []:
            value = str(raw_group_id or "").strip()
            if value and value not in group_ids:
                group_ids.append(value)

        legacy_group_id = str(getattr(task, "group_id", "") or "").strip()
        if legacy_group_id and legacy_group_id not in group_ids:
            group_ids.insert(0, legacy_group_id)

        return group_ids

    @staticmethod
    def _task_template_ids(task) -> list[str]:
        template_ids: list[str] = []

        for raw_template_id in getattr(task, "template_ids", []) or []:
            value = str(raw_template_id or "").strip()
            if value and value not in template_ids:
                template_ids.append(value)

        legacy_template_id = str(getattr(task, "template_id", "") or "").strip()
        if legacy_template_id and legacy_template_id not in template_ids:
            template_ids.insert(0, legacy_template_id)

        return template_ids

    def _validate_task_accounts(self, task) -> None:
        account_names = self._task_account_names(task)
        if not account_names:
            raise ValueError("请选择至少一个发送账号")

        existing_account_names = {account.account_name for account in self.accounts}
        missing_account_names = [
            account_name
            for account_name in account_names
            if account_name not in existing_account_names
        ]

        if missing_account_names:
            raise ValueError(
                "发送账号不存在："
                + "、".join(missing_account_names)
            )

        task.account_names = account_names

        if not str(getattr(task, "account_name", "") or "").strip():
            task.account_name = account_names[0]

        if task.account_name not in account_names:
            task.account_name = account_names[0]

        current_index = self._safe_non_negative_int(
            getattr(task, "current_account_index", 0),
            0,
        )
        task.current_account_index = current_index % len(account_names)

    def _validate_task_groups(self, task) -> None:
        group_ids = self._task_group_ids(task)
        if not group_ids:
            raise ValueError("请选择至少一个目标群组")

        existing_group_ids = {group.group_id for group in self.groups}
        missing_group_ids = [
            group_id
            for group_id in group_ids
            if group_id not in existing_group_ids
        ]

        if missing_group_ids:
            raise ValueError(
                "目标群组不存在："
                + "、".join(missing_group_ids)
            )

        task.group_ids = group_ids

        if not str(getattr(task, "group_id", "") or "").strip():
            task.group_id = group_ids[0]

        if task.group_id not in group_ids:
            task.group_id = group_ids[0]

        current_index = self._safe_non_negative_int(
            getattr(task, "current_group_index", 0),
            0,
        )
        task.current_group_index = current_index % len(group_ids)

    def _validate_task_message(self, task) -> None:
        message_mode = str(getattr(task, "message_mode", "") or "").strip()

        if message_mode == MESSAGE_MODE_TEMPLATE:
            template_ids = self._task_template_ids(task)
            if not template_ids:
                raise ValueError("模板消息必须至少选择一个模板")

            existing_template_ids = {template.template_id for template in self.templates}
            missing_template_ids = [
                template_id
                for template_id in template_ids
                if template_id not in existing_template_ids
            ]

            if missing_template_ids:
                raise ValueError(
                    "模板不存在："
                    + "、".join(missing_template_ids)
                )

            task.template_ids = template_ids

            if not str(getattr(task, "template_id", "") or "").strip():
                task.template_id = template_ids[0]

            if task.template_id not in template_ids:
                task.template_id = template_ids[0]

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

    def on_account_status_changed(
        self,
        account_name: str,
        status: str,
        detail: str,
    ) -> None:
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

        except Exception as exc:
            self.on_runtime_log_received(
                "WARNING",
                f"自动同步配置失败：{exc}",
            )

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
            self._ensure_can_modify_sending_data()
            self._sync_settings_from_dashboard()
            self.runtime_service.save_settings(self.settings)
            self.runtime_service.save_accounts(self.accounts)
            self.runtime_service.save_groups(self.groups)
            self.runtime_service.save_tasks(self.tasks)
            self.runtime_service.save_templates(self.templates)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self._show_info("全部配置已保存")
        except Exception as exc:
            self._show_error(f"保存失败：{exc}")

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
            self._sync_settings_from_dashboard()

            if not self.runtime_service.is_scheduler_running():
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
            self._ensure_can_modify_sending_data()
            account = self.account_page.get_form_account()

            if not account.account_name:
                raise ValueError("账号名称不能为空")
            if account.api_id <= 0:
                raise ValueError("API ID 必须是大于 0 的数字")
            if not account.api_hash:
                raise ValueError("API Hash 不能为空")
            if not account.phone:
                raise ValueError("手机号不能为空")

            if not account.session_name and getattr(
                self.settings,
                "default_session_name_follow_account",
                True,
            ):
                account.session_name = account.account_name

            if not account.session_name:
                raise ValueError("Session 名称不能为空")

            selected_index = self._get_selected_account_index()
            old_account_name = ""

            if 0 <= selected_index < len(self.accounts):
                old_account_name = self.accounts[selected_index].account_name
                existing_index = selected_index
            else:
                existing_index = next(
                    (
                        idx
                        for idx, item in enumerate(self.accounts)
                        if item.account_name == account.account_name
                    ),
                    None,
                )

            for idx, item in enumerate(self.accounts):
                if idx != existing_index and item.account_name == account.account_name:
                    raise ValueError("账号名称已存在，不能重复")

            if existing_index is None:
                self.accounts.append(account)
            else:
                self.accounts[existing_index] = account

            tasks_changed = self._replace_account_name_in_tasks(
                old_account_name,
                account.account_name,
            )

            self.runtime_service.save_accounts(self.accounts)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self.refresh_all_views()
            self._show_info("账号已保存")
        except Exception as exc:
            self._show_error(f"保存账号失败：{exc}")

    def on_delete_account_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            selected_index = self._get_selected_account_index()

            if selected_index < 0 or selected_index >= len(self.accounts):
                self._show_error("请先选择一个账号")
                return

            account_name = self.accounts[selected_index].account_name
            self.accounts.pop(selected_index)

            tasks_changed = self._remove_account_from_tasks(account_name)

            self.runtime_service.save_accounts(self.accounts)
            if tasks_changed:
                self.runtime_service.save_tasks(self.tasks)

            self.status_map.pop(account_name, None)
            self.account_page.clear_form()
            self.refresh_all_views()
            self._show_info("账号已删除，相关任务的账号池已同步更新")
        except Exception as exc:
            self._show_error(f"删除账号失败：{exc}")

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
            self._ensure_can_modify_sending_data()
            group = self.group_page.get_form_group()

            if not group.group_name:
                raise ValueError("群组名称不能为空")
            if not group.chat_id:
                raise ValueError("Chat ID 不能为空")

            if getattr(self.settings, "default_group_username_normalize", True):
                group.username = str(group.username or "").strip().lstrip("@")

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

            self.group_page.clear_form()
            self.refresh_all_views()
            self._show_info("群组已删除，相关任务的目标群组池已同步更新")
        except Exception as exc:
            self._show_error(f"删除群组失败：{exc}")

    def on_save_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            task = self.task_page.get_form_task()

            if not task.task_name:
                raise ValueError("任务名称不能为空")

            self._validate_task_accounts(task)
            self._validate_task_groups(task)
            self._validate_task_message(task)

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
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            if row < 0 or row >= len(self.tasks):
                self._show_error("请先选择一个任务")
                return

            self.tasks.pop(row)
            self.runtime_service.save_tasks(self.tasks)
            self.task_page.clear_form()
            self.refresh_all_views()
            self._show_info("任务已删除")
        except Exception as exc:
            self._show_error(f"删除任务失败：{exc}")

    def on_task_up_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            if row <= 0:
                return

            self.tasks[row - 1], self.tasks[row] = self.tasks[row], self.tasks[row - 1]
            self.runtime_service.save_tasks(self.tasks)
            self.refresh_all_views()
            self.task_page.table.selectRow(row - 1)
        except Exception as exc:
            self._show_error(f"移动任务失败：{exc}")

    def on_task_down_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            if row < 0 or row >= len(self.tasks) - 1:
                return

            self.tasks[row + 1], self.tasks[row] = self.tasks[row], self.tasks[row + 1]
            self.runtime_service.save_tasks(self.tasks)
            self.refresh_all_views()
            self.task_page.table.selectRow(row + 1)
        except Exception as exc:
            self._show_error(f"移动任务失败：{exc}")

    def on_save_template_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
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

            self.template_page.clear_form()
            self.refresh_all_views()
            self._show_info("模板已删除，相关任务的模板池已同步更新")
        except Exception as exc:
            self._show_error(f"删除模板失败：{exc}")

    def closeEvent(self, event) -> None:
        try:
            self.templates_sync_timer.stop()
            self.runtime_service.shutdown()
        finally:
            super().closeEvent(event)
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from app.core.models import MESSAGE_MODE_TEMPLATE, MESSAGE_MODE_TEXT
from app.gui.pages.group_membership_page import GroupMembershipPage
from app.services.runtime_service_grouped import RuntimeService
import app.gui.main_window as base_main_window

base_main_window.RuntimeService = RuntimeService


class MainWindow(base_main_window.MainWindow):
    def __init__(self):
        super().__init__()
        self._runtime_log_buffer: list[tuple[str, str, str]] = []
        self._runtime_log_flush_timer = QTimer(self)
        self._runtime_log_flush_timer.setInterval(250)
        self._runtime_log_flush_timer.timeout.connect(self._flush_runtime_log_buffer)
        self._status_refresh_timer = QTimer(self)
        self._status_refresh_timer.setInterval(400)
        self._status_refresh_timer.timeout.connect(self._flush_account_status_refresh)
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        self.group_membership_page = GroupMembershipPage()
        self.tabs.insertTab(4, self.group_membership_page, "分组管理")
        self.group_membership_page.save_requested.connect(self.on_save_group_memberships_requested)
        self.group_membership_page.discard_requested.connect(self.on_discard_group_memberships_requested)

        if hasattr(self.task_page, "start_task_button"):
            self.task_page.start_task_button.clicked.connect(self.on_start_selected_task_clicked)
        if hasattr(self.task_page, "stop_task_button"):
            self.task_page.stop_task_button.clicked.connect(self.on_stop_selected_task_clicked)

        self.refresh_all_views()

    def _load_group_membership_sets(self) -> dict[str, list[str]]:
        service = getattr(self.runtime_service, "config_service", None)
        if service is not None and hasattr(service, "load_group_sets"):
            try:
                return service.load_group_sets()
            except Exception:
                pass
        return {"account_groups": [], "group_groups": []}

    def _save_group_membership_sets(self, group_sets: dict) -> None:
        service = getattr(self.runtime_service, "config_service", None)
        if service is not None and hasattr(service, "save_group_sets"):
            service.save_group_sets(group_sets)
        self.group_membership_sets = self._load_group_membership_sets()

    def _load_account_group_proxies(self) -> dict:
        service = getattr(self.runtime_service, "config_service", None)
        if service is not None and hasattr(service, "load_account_group_proxies"):
            try:
                return service.load_account_group_proxies()
            except Exception:
                pass
        return {}

    def _save_account_group_proxies(self, account_group_proxies: dict) -> None:
        service = getattr(self.runtime_service, "config_service", None)
        if service is not None and hasattr(service, "save_account_group_proxies"):
            service.save_account_group_proxies(account_group_proxies)
        self.account_group_proxies = self._load_account_group_proxies()

    def refresh_all_views(self) -> None:
        super().refresh_all_views()
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        account_group_definitions = self._merge_account_group_definitions()
        group_group_definitions = self._merge_group_group_definitions()

        if hasattr(self.task_form, "set_context"):
            self.task_form.set_context(
                self.accounts,
                self.groups,
                self.templates,
                self.settings,
                self.tasks,
                account_group_definitions=account_group_definitions,
                group_group_definitions=group_group_definitions,
            )

        if hasattr(self, "group_membership_page"):
            if not self.group_membership_page.is_dirty():
                self.group_membership_page.set_context(
                    self.accounts,
                    self.groups,
                    {
                        "account_groups": account_group_definitions,
                        "group_groups": group_group_definitions,
                    },
                    self.account_group_proxies,
                )

    def _force_refresh_group_membership_page(self) -> None:
        if not hasattr(self, "group_membership_page"):
            return
        self.group_membership_sets = self._load_group_membership_sets()
        self.account_group_proxies = self._load_account_group_proxies()
        self.group_membership_page.set_context(
            self.accounts,
            self.groups,
            {
                "account_groups": self._merge_account_group_definitions(),
                "group_groups": self._merge_group_group_definitions(),
            },
            self.account_group_proxies,
        )

    def _merge_account_group_definitions(self) -> list[str]:
        result = self._normalize_text_values(self.group_membership_sets.get("account_groups"))
        for account in self.accounts:
            value = str(getattr(account, "account_group", "") or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    def _merge_group_group_definitions(self) -> list[str]:
        result = self._normalize_text_values(self.group_membership_sets.get("group_groups"))
        for group in self.groups:
            for value in self._group_group_names(group):
                if value and value not in result:
                    result.append(value)
        return result

    def on_open_task_add(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            self.task_page.clear_selection()
            self.task_form.set_context(
                self.accounts,
                self.groups,
                self.templates,
                self.settings,
                self.tasks,
                "",
                self._merge_account_group_definitions(),
                self._merge_group_group_definitions(),
            )
            self.task_form.clear_form()
            self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_open_task_config(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            row = self.task_page.get_selected_row()
            current_task_id = ""
            if 0 <= row < len(self.tasks):
                current_task_id = str(getattr(self.tasks[row], "task_id", "") or "")
            self.task_form.set_context(
                self.accounts,
                self.groups,
                self.templates,
                self.settings,
                self.tasks,
                current_task_id,
                self._merge_account_group_definitions(),
                self._merge_group_group_definitions(),
            )
            if 0 <= row < len(self.tasks):
                self.task_form.load_task(self.tasks[row])
            else:
                self.task_form.clear_form()
            self._open_dock(self.task_dock)
        except Exception as exc:
            self._show_error(str(exc))

    def on_save_task_clicked(self) -> None:
        try:
            self._ensure_can_modify_sending_data()
            task = self.task_form.get_form_task()
            self._validate_grouped_task(task)
            existing_index = next((idx for idx, item in enumerate(self.tasks) if item.task_id == task.task_id), None)
            if existing_index is None:
                self.tasks.append(task)
            else:
                self.tasks[existing_index] = task
            self.runtime_service.save_tasks(self.tasks)
            self._sync_state_from_runtime()
            self.refresh_all_views()
            self.task_page.select_task_id(task.task_id)
            self.task_form.set_context(
                self.accounts,
                self.groups,
                self.templates,
                self.settings,
                self.tasks,
                task.task_id,
                self._merge_account_group_definitions(),
                self._merge_group_group_definitions(),
            )
            self.task_form.load_task(task)
            self._show_info("任务已保存")
        except Exception as exc:
            self._show_error(f"保存任务失败：{exc}")

    def on_save_group_memberships_requested(self, accounts, groups, group_sets, account_group_proxies=None) -> None:
        try:
            self._ensure_can_modify_sending_data()
            self._save_group_membership_sets(group_sets if isinstance(group_sets, dict) else {})
            self._save_account_group_proxies(account_group_proxies if isinstance(account_group_proxies, dict) else {})
            self.runtime_service.save_accounts(list(accounts or []))
            self.runtime_service.save_groups(list(groups or []))
            self._sync_state_from_runtime()
            if hasattr(self, "group_membership_page"):
                self.group_membership_page.mark_clean()
            self.refresh_all_views()
            self._force_refresh_group_membership_page()
            self._show_info("分组配置已保存")
        except Exception as exc:
            self._show_error(f"保存分组配置失败：{exc}")

    def on_discard_group_memberships_requested(self) -> None:
        try:
            self.runtime_service.reload_config_cache()
            self._sync_state_from_runtime()
            if hasattr(self, "group_membership_page"):
                self.group_membership_page.mark_clean()
            self.refresh_all_views()
            self._force_refresh_group_membership_page()
            self.statusBar().showMessage("已放弃未保存的分组更改", 3000)
        except Exception as exc:
            self._show_error(f"放弃未保存更改失败：{exc}")

    def _validate_grouped_task(self, task) -> None:
        if not str(getattr(task, "task_name", "") or "").strip():
            raise ValueError("任务名称不能为空")
        account_group_names = self._task_account_group_names(task)
        group_group_names = self._task_group_group_names(task)
        if not account_group_names:
            raise ValueError("账号组池不能为空，请先在分组管理里新增账号组并选择账号")
        if not group_group_names:
            raise ValueError("群聊组池不能为空，请先在分组管理里新增群聊组并选择群")
        if len(account_group_names) != len(group_group_names):
            raise ValueError(f"账号组数量和群聊组数量必须一致。当前账号组 {len(account_group_names)} 个，群聊组 {len(group_group_names)} 个。")
        conflict = self._find_account_group_conflict(task)
        if conflict:
            raise ValueError(conflict)
        missing_account_groups = [name for name in account_group_names if not self._enabled_accounts_in_group(name)]
        if missing_account_groups:
            raise ValueError("以下账号组没有启用账号：" + "、".join(missing_account_groups))
        missing_group_groups = [name for name in group_group_names if not self._enabled_groups_in_group(name)]
        if missing_group_groups:
            raise ValueError("以下群聊组没有启用群组：" + "、".join(missing_group_groups))
        if int(getattr(task, "account_delay_max_ms", 0) or 0) < int(getattr(task, "account_delay_min_ms", 0) or 0):
            raise ValueError("账号延迟最大值不能小于账号延迟最小值")
        if int(getattr(task, "group_delay_max_ms", 0) or 0) < int(getattr(task, "group_delay_min_ms", 0) or 0):
            raise ValueError("群组延迟最大值不能小于群组延迟最小值")
        if bool(getattr(task, "daily_window_enabled", False)) and str(task.daily_start_time) == str(task.daily_end_time):
            raise ValueError("每日开始时间不能等于每日结束时间")
        if str(getattr(task, "message_mode", "") or "") == MESSAGE_MODE_TEMPLATE:
            template_ids = self._task_template_ids(task)
            if not template_ids:
                raise ValueError("模板消息必须至少选择一个模板")
            existing = {template.template_id for template in self.templates}
            missing = [item for item in template_ids if item not in existing]
            if missing:
                raise ValueError("模板不存在：" + "、".join(missing))
        elif str(getattr(task, "message_mode", "") or "") == MESSAGE_MODE_TEXT:
            if not str(getattr(task, "text", "") or "").strip():
                raise ValueError("文本消息必须填写内容")
        else:
            raise ValueError("不支持的消息类型")

    def _find_account_group_conflict(self, task) -> str:
        current_task_id = str(getattr(task, "task_id", "") or "").strip()
        selected = set(self._task_account_group_names(task))
        for other in self.tasks:
            if not bool(getattr(other, "enabled", True)):
                continue
            other_id = str(getattr(other, "task_id", "") or "").strip()
            if other_id and other_id == current_task_id:
                continue
            for group_name in self._task_account_group_names(other):
                if group_name in selected:
                    return f"账号组【{group_name}】已被启用任务【{getattr(other, 'task_name', other_id)}】占用，不能重复选择"
        return ""

    def _enabled_accounts_in_group(self, account_group: str):
        target = str(account_group or "").strip()
        return [
            account
            for account in self.accounts
            if bool(getattr(account, "enabled", True))
            and str(getattr(account, "account_group", "") or "").strip() == target
        ]

    def _enabled_groups_in_group(self, group_group: str):
        target = str(group_group or "").strip()
        return [
            group
            for group in self.groups
            if bool(getattr(group, "enabled", True))
            and target in self._group_group_names(group)
        ]

    @staticmethod
    def _normalize_text_values(values) -> list[str]:
        result: list[str] = []
        if values is None:
            return result
        if isinstance(values, str):
            raw_items = [values]
        else:
            raw_items = list(values or [])
        for item in raw_items:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _task_account_group_names(task) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "account_group_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _task_group_group_names(task) -> list[str]:
        result: list[str] = []
        for item in getattr(task, "group_group_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _group_group_names(group) -> list[str]:
        result: list[str] = []
        for item in getattr(group, "group_group_names", []) or []:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
        legacy = str(getattr(group, "group_group", "") or "").strip()
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

    def on_start_selected_task_clicked(self) -> None:
        try:
            task_id = self.task_page.get_selected_task_id()
            if not task_id:
                self._show_error("请先选择一个任务")
                return
            task = next((item for item in self.tasks if str(getattr(item, "task_id", "") or "") == task_id), None)
            if task is None:
                self._show_error("任务不存在")
                return
            if not bool(getattr(task, "enabled", True)):
                self._show_error("未启用任务不能启动，请先启用任务")
                return
            self.runtime_service.start_task_scheduler(task_id)
            self.statusBar().showMessage(f"已请求启动任务：{getattr(task, 'task_name', task_id)}", 3000)
        except Exception as exc:
            self._show_error(f"启动任务失败：{exc}")

    def on_stop_selected_task_clicked(self) -> None:
        try:
            task_id = self.task_page.get_selected_task_id()
            if not task_id:
                self._show_error("请先选择一个任务")
                return
            self.runtime_service.stop_task_scheduler(task_id)
            self.statusBar().showMessage("已请求停止任务", 3000)
        except Exception as exc:
            self._show_error(f"停止任务失败：{exc}")



    def on_account_status_changed(self, account_name: str, status: str, detail: str) -> None:
        self.status_map[account_name] = (status, detail)
        if not hasattr(self, "_status_refresh_timer"):
            return super().on_account_status_changed(account_name, status, detail)
        if not self._status_refresh_timer.isActive():
            self._status_refresh_timer.start()

    def _flush_account_status_refresh(self) -> None:
        self._status_refresh_timer.stop()
        try:
            if hasattr(self, "dashboard_page"):
                self.dashboard_page.update_summary(
                    self.accounts,
                    self.groups,
                    self.tasks,
                    self.settings,
                    self.scheduler_status,
                )
                self.dashboard_page.update_status_table(self.accounts, self.status_map)
            if hasattr(self, "account_page"):
                self.account_page.set_accounts(self.accounts, self.status_map)
        except Exception as exc:
            self.on_runtime_log_received("WARNING", f"刷新账号状态失败：{exc}")

    def on_runtime_log_received(self, level: str, message: str) -> None:
        if not hasattr(self, "_runtime_log_buffer"):
            return super().on_runtime_log_received(level, message)

        now_text = datetime.now().strftime("%H:%M:%S")
        self._runtime_log_buffer.append((now_text, str(level or "INFO").upper(), str(message or "")))
        if len(self._runtime_log_buffer) > 2000:
            self._runtime_log_buffer = self._runtime_log_buffer[-2000:]

        if not self._runtime_log_flush_timer.isActive():
            self._runtime_log_flush_timer.start()

    def _flush_runtime_log_buffer(self) -> None:
        if not getattr(self, "_runtime_log_buffer", None):
            self._runtime_log_flush_timer.stop()
            return

        batch = self._runtime_log_buffer[:300]
        del self._runtime_log_buffer[:300]

        if hasattr(self, "log_page") and hasattr(self.log_page, "log_text"):
            text = "\n".join(f"{time_text} [{level}] {message}" for time_text, level, message in batch)
            self.log_page.log_text.appendPlainText(text)
            scrollbar = self.log_page.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        elif hasattr(self, "log_page"):
            for time_text, level, message in batch:
                self.log_page.append_log(level, message)

        if not self._runtime_log_buffer:
            self._runtime_log_flush_timer.stop()

    def on_templates_sync_timer(self) -> None:
        try:
            changed = self.runtime_service.sync_templates_from_disk()
            noise_changed = False
            if hasattr(self.runtime_service, "sync_noise_pool_from_disk"):
                noise_changed = bool(self.runtime_service.sync_noise_pool_from_disk())

            if changed or noise_changed:
                self._sync_state_from_runtime()
                self.refresh_all_views()

        except Exception as exc:
            self.on_runtime_log_received("WARNING", f"自动同步配置失败：{exc}")

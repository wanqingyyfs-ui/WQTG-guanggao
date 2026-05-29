from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import AccountConfig, GroupConfig
from app.core.proxy_utils import mask_proxy_config, normalize_proxy_config
from app.gui.widgets.check_combo_box import CheckComboBox
from app.gui.widgets.no_wheel import NoWheelComboBox


class GroupMembershipPage(QWidget):
    """账号组 / 群聊组独立维护页。

    重要设计：
    - 页面编辑期间使用独立的成员关系缓存，不直接依赖列表控件当前勾选状态作为唯一数据源。
    - 账号组是单归属：一个账号只允许存在于一个账号组。
    - 群聊组是多归属：一个群可以存在于多个群聊组。
    - set_context() 只在外部刷新且页面无未保存更改时调用，避免把正在编辑的勾选状态冲掉。
    """

    save_requested = Signal(object, object, object, object)
    discard_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accounts: list[AccountConfig] = []
        self.groups: list[GroupConfig] = []
        self.account_group_names: list[str] = []
        self.group_group_names: list[str] = []

        self._account_group_members: dict[str, list[str]] = {}
        self._group_group_members: dict[str, list[str]] = {}
        self.account_group_proxies: dict[str, dict[str, Any]] = {}

        self._active_account_group = ""
        self._active_group_group = ""
        self._loading = False
        self._dirty = False

        self.title_label = QLabel("分组管理")
        self.title_label.setObjectName("PageTitleLabel")

        self.account_group_combo = NoWheelComboBox()
        self.account_group_new_edit = QLineEdit()
        self.account_group_new_edit.setPlaceholderText("输入账号组名称")
        self.account_group_add_button = QPushButton("新增账号组")
        self.account_members_combo = CheckComboBox()
        self.account_members_combo.lineEdit().setPlaceholderText("请选择属于当前账号组的账号")
        self.account_hint_label = QLabel(
            "每个账号只能属于一个账号组；勾选到当前账号组后，会自动从其他账号组移除。"
        )
        self.account_hint_label.setWordWrap(True)

        self.proxy_enabled_check = QCheckBox("启用当前账号组静态代理")
        self.proxy_raw_edit = QLineEdit()
        self.proxy_raw_edit.setPlaceholderText("例如：103.23.130.28:1337:用户名:密码")
        self.proxy_remark_edit = QLineEdit()
        self.proxy_remark_edit.setPlaceholderText("代理备注，可选")
        self.proxy_preview_label = QLabel("当前账号组代理：直连")
        self.proxy_preview_label.setWordWrap(True)
        self.proxy_hint_label = QLabel("代理格式默认按 socks5 解析；修改后需要停止并重新启动对应账号才会生效。")
        self.proxy_hint_label.setWordWrap(True)

        self.group_group_combo = NoWheelComboBox()
        self.group_group_new_edit = QLineEdit()
        self.group_group_new_edit.setPlaceholderText("输入群聊组名称")
        self.group_group_add_button = QPushButton("新增群聊组")
        self.group_members_combo = CheckComboBox()
        self.group_members_combo.lineEdit().setPlaceholderText("请选择属于当前群聊组的群")
        self.group_hint_label = QLabel("每个群可以属于多个群聊组；保存时会保留多组关系。")
        self.group_hint_label.setWordWrap(True)

        self.status_label = QLabel("已保存")
        self.status_label.setWordWrap(True)
        self.save_button = QPushButton("保存分组配置")
        self.reload_button = QPushButton("放弃未保存更改")

        self._build_ui()
        self._connect_signals()
        self._update_dirty_ui()

    def _build_ui(self) -> None:
        left_card = self._build_account_card()
        right_card = self._build_group_card()

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)
        content_layout.addWidget(left_card, 1)
        content_layout.addWidget(right_card, 1)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.status_label, 1)
        button_layout.addStretch(1)
        button_layout.addWidget(self.reload_button)
        button_layout.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addLayout(content_layout, 1)
        layout.addLayout(button_layout)

    def _build_account_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("DashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("账号组")
        title.setObjectName("DashboardStatusLabel")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.addWidget(QLabel("当前账号组："), 0, 0)
        grid.addWidget(self.account_group_combo, 0, 1, 1, 2)
        grid.addWidget(QLabel("新增账号组："), 1, 0)
        grid.addWidget(self.account_group_new_edit, 1, 1)
        grid.addWidget(self.account_group_add_button, 1, 2)
        grid.addWidget(QLabel("组内账号："), 2, 0)
        grid.addWidget(self.account_members_combo, 2, 1, 1, 2)
        grid.addWidget(self.proxy_enabled_check, 3, 1, 1, 2)
        grid.addWidget(QLabel("静态代理："), 4, 0)
        grid.addWidget(self.proxy_raw_edit, 4, 1, 1, 2)
        grid.addWidget(QLabel("代理备注："), 5, 0)
        grid.addWidget(self.proxy_remark_edit, 5, 1, 1, 2)

        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addWidget(self.account_hint_label)
        layout.addWidget(self.proxy_preview_label)
        layout.addWidget(self.proxy_hint_label)
        layout.addStretch(1)
        return card

    def _build_group_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("DashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("群聊组")
        title.setObjectName("DashboardStatusLabel")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.addWidget(QLabel("当前群聊组："), 0, 0)
        grid.addWidget(self.group_group_combo, 0, 1, 1, 2)
        grid.addWidget(QLabel("新增群聊组："), 1, 0)
        grid.addWidget(self.group_group_new_edit, 1, 1)
        grid.addWidget(self.group_group_add_button, 1, 2)
        grid.addWidget(QLabel("组内群聊："), 2, 0)
        grid.addWidget(self.group_members_combo, 2, 1, 1, 2)

        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addWidget(self.group_hint_label)
        layout.addStretch(1)
        return card

    def _connect_signals(self) -> None:
        self.account_group_add_button.clicked.connect(self.on_add_account_group_clicked)
        self.group_group_add_button.clicked.connect(self.on_add_group_group_clicked)
        self.account_group_combo.currentIndexChanged.connect(self._on_account_group_changed)
        self.group_group_combo.currentIndexChanged.connect(self._on_group_group_changed)
        self.account_members_combo.checked_items_changed.connect(self._on_account_members_changed)
        self.group_members_combo.checked_items_changed.connect(self._on_group_members_changed)
        self.proxy_enabled_check.toggled.connect(self._on_proxy_fields_changed)
        self.proxy_raw_edit.textChanged.connect(self._on_proxy_fields_changed)
        self.proxy_remark_edit.textChanged.connect(self._on_proxy_fields_changed)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.reload_button.clicked.connect(self.discard_requested.emit)

    def is_dirty(self) -> bool:
        return bool(self._dirty)

    def mark_clean(self) -> None:
        self._dirty = False
        self._update_dirty_ui()

    def _mark_dirty(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._update_dirty_ui()

    def _update_dirty_ui(self) -> None:
        if self._dirty:
            self.status_label.setText("有未保存的分组更改")
            self.reload_button.setEnabled(True)
        else:
            self.status_label.setText("已保存")
            self.reload_button.setEnabled(False)
        self.save_button.setEnabled(True)

    def set_context(
        self,
        accounts: list[AccountConfig],
        groups: list[GroupConfig],
        group_sets: dict[str, Any] | None = None,
        account_group_proxies: dict[str, Any] | None = None,
    ) -> None:
        self._loading = True
        try:
            self.accounts = copy.deepcopy(list(accounts or []))
            self.groups = copy.deepcopy(list(groups or []))
            group_sets = group_sets if isinstance(group_sets, dict) else {}

            account_group_names = self._normalize_values(group_sets.get("account_groups"))
            for account in self.accounts:
                value = str(getattr(account, "account_group", "") or "").strip()
                if value and value not in account_group_names:
                    account_group_names.append(value)

            group_group_names = self._normalize_values(group_sets.get("group_groups"))
            for group in self.groups:
                for value in self._group_group_names(group):
                    if value and value not in group_group_names:
                        group_group_names.append(value)

            self.account_group_names = account_group_names
            self.group_group_names = group_group_names
            self._account_group_members = self._build_account_group_members()
            self._group_group_members = self._build_group_group_members()
            self.account_group_proxies = self._normalize_proxy_map(account_group_proxies)
            for group_name in self.account_group_names:
                self.account_group_proxies.setdefault(group_name, self._empty_proxy_config())

            previous_account_group = self._active_account_group
            previous_group_group = self._active_group_group

            self._populate_account_group_combo(preferred=previous_account_group)
            self._populate_group_group_combo(preferred=previous_group_group)
            self._populate_account_members_combo()
            self._populate_group_members_combo()

            self._active_account_group = str(self.account_group_combo.currentData() or "").strip()
            self._active_group_group = str(self.group_group_combo.currentData() or "").strip()
            self._refresh_account_members_selection()
            self._refresh_proxy_fields()
            self._refresh_group_members_selection()
            self._dirty = False
        finally:
            self._loading = False
            self._update_dirty_ui()

    def _build_account_group_members(self) -> dict[str, list[str]]:
        members: dict[str, list[str]] = {name: [] for name in self.account_group_names}
        for account in self.accounts:
            account_name = str(getattr(account, "account_name", "") or "").strip()
            group_name = str(getattr(account, "account_group", "") or "").strip()
            if not account_name or not group_name:
                continue
            if group_name not in members:
                members[group_name] = []
                self.account_group_names.append(group_name)
            if account_name not in members[group_name]:
                members[group_name].append(account_name)
        return members

    def _build_group_group_members(self) -> dict[str, list[str]]:
        members: dict[str, list[str]] = {name: [] for name in self.group_group_names}
        for group in self.groups:
            group_id = str(getattr(group, "group_id", "") or "").strip()
            if not group_id:
                continue
            for group_name in self._group_group_names(group):
                if group_name not in members:
                    members[group_name] = []
                    self.group_group_names.append(group_name)
                if group_id not in members[group_name]:
                    members[group_name].append(group_id)
        return members

    def _on_account_group_changed(self) -> None:
        if self._loading:
            return
        self._store_account_members_from_combo(self._active_account_group)
        self._store_proxy_from_fields(self._active_account_group)
        self._active_account_group = str(self.account_group_combo.currentData() or "").strip()
        self._refresh_account_members_selection()
        self._refresh_proxy_fields()

    def _on_group_group_changed(self) -> None:
        if self._loading:
            return
        self._store_group_members_from_combo(self._active_group_group)
        self._active_group_group = str(self.group_group_combo.currentData() or "").strip()
        self._refresh_group_members_selection()

    def _on_account_members_changed(self) -> None:
        if self._loading:
            return
        self._store_account_members_from_combo(self._active_account_group)
        self._mark_dirty()

    def _on_group_members_changed(self) -> None:
        if self._loading:
            return
        self._store_group_members_from_combo(self._active_group_group)
        self._mark_dirty()

    def on_add_account_group_clicked(self) -> None:
        name = self.account_group_new_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请先填写账号组名称")
            return
        if name in self.account_group_names:
            QMessageBox.warning(self, "提示", f"账号组【{name}】已存在")
            self._select_combo_value(self.account_group_combo, name)
            return

        self._store_account_members_from_combo(self._active_account_group)
        self.account_group_names.append(name)
        self._account_group_members.setdefault(name, [])
        self.account_group_proxies.setdefault(name, self._empty_proxy_config())
        self.account_group_new_edit.clear()
        self._populate_account_group_combo(preferred=name)
        self._active_account_group = str(self.account_group_combo.currentData() or "").strip()
        self._refresh_account_members_selection()
        self._mark_dirty()

    def on_add_group_group_clicked(self) -> None:
        name = self.group_group_new_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请先填写群聊组名称")
            return
        if name in self.group_group_names:
            QMessageBox.warning(self, "提示", f"群聊组【{name}】已存在")
            self._select_combo_value(self.group_group_combo, name)
            return

        self._store_group_members_from_combo(self._active_group_group)
        self.group_group_names.append(name)
        self._group_group_members.setdefault(name, [])
        self.group_group_new_edit.clear()
        self._populate_group_group_combo(preferred=name)
        self._active_group_group = str(self.group_group_combo.currentData() or "").strip()
        self._refresh_group_members_selection()
        self._mark_dirty()

    def on_save_clicked(self) -> None:
        self._store_account_members_from_combo(self._active_account_group)
        self._store_proxy_from_fields(self._active_account_group)
        self._store_group_members_from_combo(self._active_group_group)

        accounts = self._build_accounts_for_save()
        groups = self._build_groups_for_save()
        group_sets = {
            "account_groups": list(self.account_group_names),
            "group_groups": list(self.group_group_names),
        }
        self.save_requested.emit(accounts, groups, group_sets, self._build_proxies_for_save())


    def _on_proxy_fields_changed(self) -> None:
        if self._loading:
            return
        self._store_proxy_from_fields(self._active_account_group)
        self._update_proxy_preview()
        self._mark_dirty()

    @staticmethod
    def _empty_proxy_config() -> dict[str, Any]:
        return {
            "enabled": False,
            "proxy_type": "socks5",
            "host": "",
            "port": 0,
            "username": "",
            "password": "",
            "raw_proxy": "",
            "remark": "",
        }

    def _normalize_proxy_map(self, value: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        raw_map = value if isinstance(value, dict) else {}
        result: dict[str, dict[str, Any]] = {}
        for group_name, raw_config in raw_map.items():
            safe_group_name = str(group_name or "").strip()
            if not safe_group_name:
                continue
            try:
                result[safe_group_name] = normalize_proxy_config(raw_config, strict=False)
            except Exception:
                result[safe_group_name] = self._empty_proxy_config()
        return result

    def _store_proxy_from_fields(self, selected_group: str) -> None:
        selected_group = str(selected_group or "").strip()
        if not selected_group:
            return
        raw_proxy = self.proxy_raw_edit.text().strip()
        raw_config = {
            "enabled": self.proxy_enabled_check.isChecked(),
            "proxy_type": "socks5",
            "raw_proxy": raw_proxy,
            "remark": self.proxy_remark_edit.text(),
        }
        try:
            config = normalize_proxy_config(raw_config, strict=False)
        except Exception:
            config = dict(raw_config)
            config.update({"host": "", "port": 0, "username": "", "password": ""})
        self.account_group_proxies[selected_group] = config

    def _refresh_proxy_fields(self) -> None:
        selected_group = str(self.account_group_combo.currentData() or "").strip()
        config = normalize_proxy_config(self.account_group_proxies.get(selected_group, self._empty_proxy_config()), strict=False)
        self.proxy_enabled_check.blockSignals(True)
        self.proxy_raw_edit.blockSignals(True)
        self.proxy_remark_edit.blockSignals(True)
        try:
            self.proxy_enabled_check.setChecked(bool(config.get("enabled", False)))
            raw_proxy = str(config.get("raw_proxy", "") or "").strip()
            if not raw_proxy and config.get("host") and config.get("port"):
                pieces = [str(config.get("host", "")), str(config.get("port", ""))]
                if str(config.get("username", "") or "").strip() or str(config.get("password", "") or ""):
                    pieces.append(str(config.get("username", "") or ""))
                    pieces.append(str(config.get("password", "") or ""))
                raw_proxy = ":".join(pieces)
            self.proxy_raw_edit.setText(raw_proxy)
            self.proxy_remark_edit.setText(str(config.get("remark", "") or ""))
        finally:
            self.proxy_enabled_check.blockSignals(False)
            self.proxy_raw_edit.blockSignals(False)
            self.proxy_remark_edit.blockSignals(False)
        self._update_proxy_preview()

    def _update_proxy_preview(self) -> None:
        selected_group = str(self.account_group_combo.currentData() or "").strip()
        config = self.account_group_proxies.get(selected_group, self._empty_proxy_config())
        if self.proxy_enabled_check.isChecked():
            config = normalize_proxy_config(
                {
                    "enabled": True,
                    "proxy_type": "socks5",
                    "raw_proxy": self.proxy_raw_edit.text().strip(),
                    "remark": self.proxy_remark_edit.text(),
                },
                strict=False,
            )
        self.proxy_preview_label.setText(f"当前账号组代理：{mask_proxy_config(config)}")

    def _build_proxies_for_save(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for group_name in self.account_group_names:
            raw_config = self.account_group_proxies.get(group_name, self._empty_proxy_config())
            try:
                config = normalize_proxy_config(raw_config, strict=True)
            except Exception as exc:
                errors.append(f"账号组【{group_name}】：{exc}")
                continue
            if config.get("enabled") or str(config.get("raw_proxy", "") or "").strip() or str(config.get("remark", "") or "").strip():
                result[group_name] = config
        if errors:
            raise ValueError("代理配置有误：" + "；".join(errors))
        return result

    def _populate_account_group_combo(self, preferred: str = "") -> None:
        current = str(preferred or self.account_group_combo.currentData() or "").strip()
        self.account_group_combo.blockSignals(True)
        try:
            self.account_group_combo.clear()
            for name in self.account_group_names:
                self.account_group_combo.addItem(name, name)
            self._select_combo_value(self.account_group_combo, current)
        finally:
            self.account_group_combo.blockSignals(False)

    def _populate_group_group_combo(self, preferred: str = "") -> None:
        current = str(preferred or self.group_group_combo.currentData() or "").strip()
        self.group_group_combo.blockSignals(True)
        try:
            self.group_group_combo.clear()
            for name in self.group_group_names:
                self.group_group_combo.addItem(name, name)
            self._select_combo_value(self.group_group_combo, current)
        finally:
            self.group_group_combo.blockSignals(False)

    def _populate_account_members_combo(self) -> None:
        self.account_members_combo.blockSignals(True)
        try:
            self.account_members_combo.clear_items()
            for account in self.accounts:
                account_name = str(getattr(account, "account_name", "") or "").strip()
                if not account_name:
                    continue
                suffix = "" if bool(getattr(account, "enabled", True)) else "（未启用）"
                phone = str(getattr(account, "phone", "") or "").strip()
                owner_group = self._account_owner_group(account_name)
                owner_suffix = ""
                current_group = str(self.account_group_combo.currentData() or "").strip()
                if owner_group and owner_group != current_group:
                    owner_suffix = f" / 当前属于：{owner_group}"
                label = f"{account_name}{suffix}{owner_suffix}"
                if phone:
                    label = f"{label} / {phone}"
                self.account_members_combo.add_check_item(label, account_name)
        finally:
            self.account_members_combo.blockSignals(False)

    def _populate_group_members_combo(self) -> None:
        self.group_members_combo.blockSignals(True)
        try:
            self.group_members_combo.clear_items()
            for group in self.groups:
                group_id = str(getattr(group, "group_id", "") or "").strip()
                if not group_id:
                    continue
                suffix = "" if bool(getattr(group, "enabled", True)) else "（未启用）"
                label = f"{getattr(group, 'group_name', '') or group_id}{suffix} ({getattr(group, 'chat_id', '')})"
                self.group_members_combo.add_check_item(label, group_id)
        finally:
            self.group_members_combo.blockSignals(False)

    def _refresh_account_members_selection(self) -> None:
        selected_group = str(self.account_group_combo.currentData() or "").strip()
        selected_accounts = list(self._account_group_members.get(selected_group, []))
        self.account_members_combo.blockSignals(True)
        try:
            self.account_members_combo.set_checked_data(selected_accounts)
        finally:
            self.account_members_combo.blockSignals(False)
        self._populate_account_members_combo_labels_preserving_selection(selected_accounts)

    def _populate_account_members_combo_labels_preserving_selection(self, selected_accounts: list[str]) -> None:
        # 账号被移动到当前组后，需要刷新“当前属于”提示；这里保持当前勾选不变。
        self.account_members_combo.blockSignals(True)
        try:
            self.account_members_combo.clear_items()
            current_group = str(self.account_group_combo.currentData() or "").strip()
            selected_set = set(selected_accounts)
            for account in self.accounts:
                account_name = str(getattr(account, "account_name", "") or "").strip()
                if not account_name:
                    continue
                suffix = "" if bool(getattr(account, "enabled", True)) else "（未启用）"
                phone = str(getattr(account, "phone", "") or "").strip()
                owner_group = self._account_owner_group(account_name)
                owner_suffix = ""
                if owner_group and owner_group != current_group:
                    owner_suffix = f" / 当前属于：{owner_group}"
                label = f"{account_name}{suffix}{owner_suffix}"
                if phone:
                    label = f"{label} / {phone}"
                self.account_members_combo.add_check_item(
                    label,
                    account_name,
                    checked=account_name in selected_set,
                )
        finally:
            self.account_members_combo.blockSignals(False)

    def _refresh_group_members_selection(self) -> None:
        selected_group = str(self.group_group_combo.currentData() or "").strip()
        selected_groups = list(self._group_group_members.get(selected_group, []))
        self.group_members_combo.blockSignals(True)
        try:
            self.group_members_combo.set_checked_data(selected_groups)
        finally:
            self.group_members_combo.blockSignals(False)

    def _store_account_members_from_combo(self, selected_group: str) -> None:
        selected_group = str(selected_group or "").strip()
        if not selected_group:
            return
        selected_account_names = self._normalize_values(self.account_members_combo.checked_data())
        available_account_names = set(self._account_name_order())
        selected_account_names = [name for name in selected_account_names if name in available_account_names]

        selected_set = set(selected_account_names)
        for group_name in list(self._account_group_members.keys()):
            if group_name == selected_group:
                continue
            self._account_group_members[group_name] = [
                account_name
                for account_name in self._account_group_members.get(group_name, [])
                if account_name not in selected_set
            ]
        self._account_group_members[selected_group] = selected_account_names

    def _store_group_members_from_combo(self, selected_group: str) -> None:
        selected_group = str(selected_group or "").strip()
        if not selected_group:
            return
        selected_group_ids = self._normalize_values(self.group_members_combo.checked_data())
        available_group_ids = set(self._group_id_order())
        self._group_group_members[selected_group] = [
            group_id for group_id in selected_group_ids if group_id in available_group_ids
        ]

    def _build_accounts_for_save(self) -> list[AccountConfig]:
        account_to_group: dict[str, str] = {}
        for group_name in self.account_group_names:
            for account_name in self._account_group_members.get(group_name, []):
                if account_name and account_name not in account_to_group:
                    account_to_group[account_name] = group_name

        result = copy.deepcopy(self.accounts)
        for account in result:
            account_name = str(getattr(account, "account_name", "") or "").strip()
            account.account_group = account_to_group.get(account_name, "")
        return result

    def _build_groups_for_save(self) -> list[GroupConfig]:
        group_id_to_memberships: dict[str, list[str]] = {group_id: [] for group_id in self._group_id_order()}
        for group_name in self.group_group_names:
            for group_id in self._group_group_members.get(group_name, []):
                if not group_id:
                    continue
                memberships = group_id_to_memberships.setdefault(group_id, [])
                if group_name not in memberships:
                    memberships.append(group_name)

        result = copy.deepcopy(self.groups)
        for group in result:
            group_id = str(getattr(group, "group_id", "") or "").strip()
            memberships = group_id_to_memberships.get(group_id, [])
            group.group_group_names = list(memberships)
            group.group_group = memberships[0] if memberships else ""
        return result

    def _account_owner_group(self, account_name: str) -> str:
        target = str(account_name or "").strip()
        if not target:
            return ""
        for group_name in self.account_group_names:
            if target in self._account_group_members.get(group_name, []):
                return group_name
        return ""

    def _account_name_order(self) -> list[str]:
        result: list[str] = []
        for account in self.accounts:
            account_name = str(getattr(account, "account_name", "") or "").strip()
            if account_name and account_name not in result:
                result.append(account_name)
        return result

    def _group_id_order(self) -> list[str]:
        result: list[str] = []
        for group in self.groups:
            group_id = str(getattr(group, "group_id", "") or "").strip()
            if group_id and group_id not in result:
                result.append(group_id)
        return result

    @staticmethod
    def _normalize_values(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            raw_items = [values]
        elif isinstance(values, (list, tuple, set)):
            raw_items = list(values)
        else:
            return []
        result: list[str] = []
        for item in raw_items:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _group_group_names(group: GroupConfig) -> list[str]:
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
    def _select_combo_value(combo: NoWheelComboBox, value: str) -> None:
        target = str(value or "").strip()
        index = combo.findData(target)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

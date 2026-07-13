from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from app.services.tgapipldc_behavior_service import TgapipldcBehaviorService

ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class ProfileBehaviorManagerDialog(QDialog):
    """Manage behavior order and each behavior's ordered step list."""

    def __init__(self, service: TgapipldcBehaviorService,
                 base_config_provider: Callable[[], dict] | None = None,
                 run_callback: Callable[[str, dict], None] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.base_config_provider = base_config_provider or (lambda: {})
        self.run_callback = run_callback
        self.behaviors = self.service.load_behaviors()
        self.behavior_index = -1
        self.step_index = -1
        self.editing = "behavior"
        self.setWindowTitle("资料维护行为与步骤管理")
        self.resize(1050, 680)

        self.behavior_list = QListWidget()
        self.step_list = QListWidget()
        self.json_edit = QPlainTextEdit()
        self.json_edit.setPlaceholderText("选择行为或步骤后，在这里编辑其 JSON，再点击“应用编辑”。")
        self.add_behavior = QPushButton("新增行为")
        self.delete_behavior = QPushButton("删除行为")
        self.behavior_up = QPushButton("上移行为")
        self.behavior_down = QPushButton("下移行为")
        self.add_step = QPushButton("新增步骤")
        self.delete_step = QPushButton("删除步骤")
        self.step_up = QPushButton("上移步骤")
        self.step_down = QPushButton("下移步骤")
        self.apply_edit = QPushButton("应用编辑")
        self.save = QPushButton("保存配置")
        self.run = QPushButton("保存并运行选中行为")
        self.close = QPushButton("关闭")
        self._build()
        self._connect()
        self._refresh_behaviors(0)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        hint = QLabel(
            "每个行为由可排序步骤组成。修改头像默认是：上传头像 → 裁剪确认 → 资料保存 → 等待稳定。"
            "内置行为不能删除，但可以在 JSON 中启停；自定义行为和所有步骤均可增删、排序和配置重试。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        split.addWidget(self._column("行为", self.behavior_list,
                                     (self.add_behavior, self.delete_behavior, self.behavior_up, self.behavior_down)))
        split.addWidget(self._column("步骤", self.step_list,
                                     (self.add_step, self.delete_step, self.step_up, self.step_down)))
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.addWidget(QLabel("选中对象配置（JSON）"))
        editor_layout.addWidget(self.json_edit, 1)
        editor_layout.addWidget(self.apply_edit)
        split.addWidget(editor)
        split.setSizes([270, 300, 480])
        buttons = QHBoxLayout()
        buttons.addWidget(self.save)
        buttons.addWidget(self.run)
        buttons.addStretch(1)
        buttons.addWidget(self.close)
        root.addLayout(buttons)
        self.save.setObjectName("PrimaryButton")
        self.run.setObjectName("PrimaryButton")

    @staticmethod
    def _column(title: str, listing: QListWidget, buttons) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(title))
        layout.addWidget(listing, 1)
        row = QHBoxLayout()
        for button in buttons:
            row.addWidget(button)
        layout.addLayout(row)
        return widget

    def _connect(self) -> None:
        self.behavior_list.currentRowChanged.connect(self._select_behavior)
        self.step_list.currentRowChanged.connect(self._select_step)
        self.add_behavior.clicked.connect(self._add_behavior)
        self.delete_behavior.clicked.connect(self._delete_behavior)
        self.behavior_up.clicked.connect(lambda: self._move_behavior(-1))
        self.behavior_down.clicked.connect(lambda: self._move_behavior(1))
        self.add_step.clicked.connect(self._add_step)
        self.delete_step.clicked.connect(self._delete_step)
        self.step_up.clicked.connect(lambda: self._move_step(-1))
        self.step_down.clicked.connect(lambda: self._move_step(1))
        self.apply_edit.clicked.connect(self._apply_json)
        self.save.clicked.connect(self._save)
        self.run.clicked.connect(self._save_and_run)
        self.close.clicked.connect(self.reject)

    def _behavior(self):
        return self.behaviors[self.behavior_index] if 0 <= self.behavior_index < len(self.behaviors) else None

    def _step(self):
        behavior = self._behavior()
        steps = behavior.get("steps") if behavior else []
        return steps[self.step_index] if 0 <= self.step_index < len(steps) else None

    def _refresh_behaviors(self, index: int = 0) -> None:
        self.behavior_list.blockSignals(True)
        self.behavior_list.clear()
        for behavior in self.behaviors:
            mark = "✓" if behavior.get("enabled", True) else "×"
            builtin = " [内置]" if behavior.get("builtin") else ""
            self.behavior_list.addItem(f"{mark} {behavior.get('name')} ({behavior.get('id')}){builtin}")
        self.behavior_list.blockSignals(False)
        if self.behaviors:
            self.behavior_list.setCurrentRow(max(0, min(index, len(self.behaviors) - 1)))
            self._select_behavior(self.behavior_list.currentRow())
        else:
            self.behavior_index = -1
            self.step_list.clear()
            self.json_edit.clear()

    def _refresh_steps(self, index: int = 0) -> None:
        behavior = self._behavior()
        steps = behavior.get("steps") if behavior else []
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for item in steps:
            mark = "✓" if item.get("enabled", True) else "×"
            self.step_list.addItem(f"{mark} {item.get('name')} ({item.get('type')})")
        self.step_list.blockSignals(False)
        if steps:
            self.step_list.setCurrentRow(max(0, min(index, len(steps) - 1)))
        else:
            self.step_index = -1

    def _select_behavior(self, index: int) -> None:
        self.behavior_index = index
        self.step_index = -1
        self.editing = "behavior"
        behavior = self._behavior()
        self.json_edit.setPlainText(json.dumps(behavior or {}, ensure_ascii=False, indent=2))
        self._refresh_steps(0)
        self.delete_behavior.setEnabled(bool(behavior and not behavior.get("builtin")))

    def _select_step(self, index: int) -> None:
        self.step_index = index
        item = self._step()
        if item is not None:
            self.editing = "step"
            self.json_edit.setPlainText(json.dumps(item, ensure_ascii=False, indent=2))

    def _add_behavior(self) -> None:
        behavior_id, ok = QInputDialog.getText(self, "新增行为", "行为 ID")
        behavior_id = behavior_id.strip().lower()
        if not ok:
            return
        if not ID_RE.fullmatch(behavior_id) or any(x.get("id") == behavior_id for x in self.behaviors):
            QMessageBox.warning(self, "无法新增", "ID 格式不正确或已经存在。")
            return
        name, ok = QInputDialog.getText(self, "新增行为", "行为名称", text=behavior_id)
        if ok:
            self.behaviors.append({"id": behavior_id, "name": name.strip() or behavior_id,
                                   "enabled": True, "builtin": False,
                                   "failure_mode": "strict", "steps": []})
            self._refresh_behaviors(len(self.behaviors) - 1)

    def _delete_behavior(self) -> None:
        behavior = self._behavior()
        if not behavior or behavior.get("builtin"):
            return
        if QMessageBox.question(self, "删除行为", f"确定删除“{behavior.get('name')}”吗？") == QMessageBox.StandardButton.Yes:
            old = self.behavior_index
            self.behaviors.pop(old)
            self._refresh_behaviors(max(0, old - 1))

    def _move_behavior(self, delta: int) -> None:
        old, new = self.behavior_index, self.behavior_index + delta
        if old < 0 or new < 0 or new >= len(self.behaviors):
            return
        self.behaviors[old], self.behaviors[new] = self.behaviors[new], self.behaviors[old]
        self._refresh_behaviors(new)

    def _add_step(self) -> None:
        behavior = self._behavior()
        if behavior is None:
            return
        keys = list(self.service.step_types)
        labels = [f"{self.service.step_types[key]}（{key}）" for key in keys]
        selected, ok = QInputDialog.getItem(self, "新增步骤", "步骤类型", labels, 0, False)
        if not ok:
            return
        kind = keys[labels.index(selected)]
        existing = {x.get("id") for x in behavior.get("steps") or []}
        step_id, number = kind.replace(".", "_"), 2
        base = step_id
        while step_id in existing:
            step_id, number = f"{base}_{number}", number + 1
        params = {"milliseconds": 1000} if kind == "wait" else ({"behavior_id": "photo"} if kind == "behavior.run" else {})
        behavior.setdefault("steps", []).append({"id": step_id, "name": self.service.step_types[kind],
                                                  "type": kind, "enabled": True, "required": True,
                                                  "retries": 1, "wait_after_ms": 0, "params": params})
        self._refresh_steps(len(behavior["steps"]) - 1)

    def _delete_step(self) -> None:
        behavior = self._behavior()
        if behavior is None or self.step_index < 0:
            return
        old = self.step_index
        behavior["steps"].pop(old)
        self._refresh_steps(max(0, old - 1))

    def _move_step(self, delta: int) -> None:
        behavior = self._behavior()
        if behavior is None:
            return
        steps, old, new = behavior.get("steps") or [], self.step_index, self.step_index + delta
        if old < 0 or new < 0 or new >= len(steps):
            return
        steps[old], steps[new] = steps[new], steps[old]
        self._refresh_steps(new)

    def _apply_json(self) -> None:
        try:
            value = json.loads(self.json_edit.toPlainText() or "{}")
            if not isinstance(value, dict):
                raise ValueError("必须是 JSON 对象")
            if self.editing == "step":
                current = self._step()
                if current is None:
                    return
                current.clear()
                current.update(value)
                self._refresh_steps(self.step_index)
            else:
                current = self._behavior()
                if current is None:
                    return
                was_builtin = bool(current.get("builtin"))
                if was_builtin and value.get("id") != current.get("id"):
                    raise ValueError("内置行为不能修改 ID")
                current.clear()
                current.update(value)
                if was_builtin:
                    current["builtin"] = True
                self._refresh_behaviors(self.behavior_index)
        except Exception as exc:
            QMessageBox.critical(self, "应用失败", str(exc))

    def _validated(self) -> None:
        ids = set()
        for behavior in self.behaviors:
            behavior_id = str(behavior.get("id") or "")
            if not ID_RE.fullmatch(behavior_id) or behavior_id in ids:
                raise ValueError(f"行为 ID 不合法或重复：{behavior_id}")
            ids.add(behavior_id)
            step_ids = set()
            for item in behavior.get("steps") or []:
                step_id = str(item.get("id") or "")
                if not ID_RE.fullmatch(step_id) or step_id in step_ids:
                    raise ValueError(f"{behavior_id} 的步骤 ID 不合法或重复：{step_id}")
                step_ids.add(step_id)
                if item.get("type") not in self.service.step_types:
                    raise ValueError(f"不支持的步骤类型：{item.get('type')}")
        for behavior in self.behaviors:
            for item in behavior.get("steps") or []:
                if item.get("type") == "behavior.run":
                    target = str((item.get("params") or {}).get("behavior_id") or "")
                    if target not in ids:
                        raise ValueError(f"步骤引用了不存在的行为：{target}")

    def _save(self):
        try:
            self._apply_json()
            self._validated()
            saved = self.service.save_behaviors(self.behaviors, self.base_config_provider())
            self.behaviors = deepcopy(saved.get("profile_behaviors") or [])
            self._refresh_behaviors(max(0, self.behavior_index))
            QMessageBox.information(self, "保存成功", "行为与步骤配置已保存。")
            return saved
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return None

    def _save_and_run(self) -> None:
        behavior = self._behavior()
        saved = self._save()
        if behavior and saved is not None and self.run_callback:
            self.run_callback(str(behavior.get("id") or ""), saved)
            self.accept()


def install_profile_behavior_manager(profile_page, workspace_service,
                                     run_callback: Callable[[str, dict], None] | None,
                                     parent=None):
    if hasattr(profile_page, "behavior_manager_button"):
        return profile_page.behavior_manager_service
    service = TgapipldcBehaviorService(workspace_service)
    button = QPushButton("行为与步骤管理")
    button.setObjectName("PrimaryButton")
    button.setMinimumHeight(34)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    def open_dialog() -> None:
        dialog = ProfileBehaviorManagerDialog(service, profile_page.get_profile_maintenance_config,
                                               run_callback, parent or profile_page)
        dialog.exec()
        profile_page.set_profile_maintenance_config(service.load_config())

    button.clicked.connect(open_dialog)
    layout = profile_page.layout()
    if layout is not None:
        layout.insertWidget(min(1, layout.count()), button)
    profile_page.behavior_manager_button = button
    profile_page.behavior_manager_service = service
    return service

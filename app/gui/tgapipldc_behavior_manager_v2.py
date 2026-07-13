from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMessageBox, QPushButton

from app.gui.tgapipldc_behavior_manager import ProfileBehaviorManagerDialog
from app.services.tgapipldc_behavior_service import TgapipldcBehaviorService


class ProfileBehaviorManagerDialogV2(ProfileBehaviorManagerDialog):
    """Behavior manager whose custom click steps are first-class locator targets."""

    def __init__(
        self,
        service: TgapipldcBehaviorService,
        base_config_provider: Callable[[], dict] | None = None,
        run_callback: Callable[[str, dict], None] | None = None,
        locator_callback: Callable[[str], None] | None = None,
        parent=None,
    ) -> None:
        self.locator_callback = locator_callback
        super().__init__(service, base_config_provider, run_callback, parent)

        self.add_step.setText("新增自定义点击步骤")
        try:
            self.add_step.clicked.disconnect()
        except Exception:
            pass
        self.add_step.clicked.connect(self._add_custom_click_step)

        self.add_system_step_button = QPushButton("新增内置功能步骤")
        self.locate_step_button = QPushButton("去定位当前步骤")
        self.locate_step_button.setObjectName("PrimaryButton")
        for button in (self.add_system_step_button, self.locate_step_button):
            button.setMinimumHeight(32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.add_system_step_button.clicked.connect(self._add_system_step)
        self.locate_step_button.clicked.connect(self._locate_current_step)

        row = QHBoxLayout()
        row.addWidget(self.add_system_step_button)
        row.addWidget(self.locate_step_button)
        row.addStretch(1)
        root = self.layout()
        if root is not None:
            root.insertLayout(max(0, root.count() - 1), row)
        self._refresh_steps(max(0, self.step_index))

    def _refresh_steps(self, index: int = 0) -> None:
        super()._refresh_steps(index)
        behavior = self._behavior()
        steps = behavior.get("steps") if behavior else []
        for row, item in enumerate(steps):
            target_id = self.service.locator_target_for_step(
                str(behavior.get("id") or ""), item
            )
            widget_item = self.step_list.item(row)
            if widget_item is not None and target_id:
                widget_item.setText(widget_item.text() + f"  →  {target_id}")
        self._refresh_locator_button()

    def _select_step(self, index: int) -> None:
        super()._select_step(index)
        self._refresh_locator_button()

    def _refresh_locator_button(self) -> None:
        behavior = self._behavior()
        item = self._step()
        target_id = self.service.locator_target_for_step(
            str((behavior or {}).get("id") or ""), item or {}
        )
        if hasattr(self, "locate_step_button"):
            self.locate_step_button.setEnabled(bool(target_id and self.locator_callback))
            self.locate_step_button.setToolTip(
                f"打开自动化定位设置：{target_id}"
                if target_id
                else "当前步骤不需要页面点击定位"
            )

    def _add_custom_click_step(self) -> None:
        behavior = self._behavior()
        if behavior is None:
            return
        step_id, ok = QInputDialog.getText(
            self,
            "新增自定义点击步骤",
            "步骤 ID（例如 click_confirm）",
        )
        if not ok:
            return
        step_id = str(step_id or "").strip().lower()
        existing = {str(item.get("id") or "") for item in behavior.get("steps") or []}
        if step_id in existing:
            QMessageBox.warning(self, "无法新增", f"步骤 ID 已存在：{step_id}")
            return
        name, ok = QInputDialog.getText(
            self,
            "新增自定义点击步骤",
            "步骤名称（例如 点击确认按钮）",
            text=step_id,
        )
        if not ok:
            return
        try:
            item = self.service.make_custom_click_step(
                str(behavior.get("id") or ""), step_id, str(name or "")
            )
        except Exception as exc:
            QMessageBox.critical(self, "新增失败", str(exc))
            return
        behavior.setdefault("steps", []).append(item)
        self._refresh_steps(len(behavior["steps"]) - 1)

    def _add_system_step(self) -> None:
        super()._add_step()

    def _locate_current_step(self) -> None:
        behavior = self._behavior()
        item = self._step()
        target_id = self.service.locator_target_for_step(
            str((behavior or {}).get("id") or ""), item or {}
        )
        if not target_id:
            QMessageBox.information(self, "无需定位", "当前步骤不是页面点击步骤。")
            return
        saved = self._save()
        if saved is None:
            return
        if self.locator_callback is None:
            QMessageBox.warning(self, "无法打开", "自动化定位页面尚未连接。")
            return
        self.locator_callback(target_id)
        self.accept()


def install_profile_behavior_manager_v2(
    profile_page,
    workspace_service,
    run_callback: Callable[[str, dict], None] | None,
    locator_callback: Callable[[str], None] | None,
    parent=None,
):
    if hasattr(profile_page, "behavior_manager_button"):
        return profile_page.behavior_manager_service
    service = TgapipldcBehaviorService(workspace_service)
    button = QPushButton("行为与步骤管理")
    button.setObjectName("PrimaryButton")
    button.setMinimumHeight(34)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    def open_dialog() -> None:
        dialog = ProfileBehaviorManagerDialogV2(
            service,
            profile_page.get_profile_maintenance_config,
            run_callback,
            locator_callback,
            parent or profile_page,
        )
        dialog.exec()
        profile_page.set_profile_maintenance_config(service.load_config())

    button.clicked.connect(open_dialog)
    layout = profile_page.layout()
    if layout is not None:
        layout.insertWidget(min(1, layout.count()), button)
    profile_page.behavior_manager_button = button
    profile_page.behavior_manager_service = service
    return service

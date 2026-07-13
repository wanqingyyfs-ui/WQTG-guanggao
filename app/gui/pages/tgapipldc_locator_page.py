from __future__ import annotations

import json
from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


MODE_STRATEGIES = "strategies"
MODE_ABSOLUTE = "absolute_position"


class TgapipldcLocatorPage(QWidget):
    save_target_requested = Signal(str, str)
    reset_target_requested = Signal(str)
    reload_requested = Signal()
    calibrate_requested = Signal(str, str, str)
    open_config_directory_requested = Signal()
    stop_process_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets: dict[str, dict] = {}
        self._profiles: list[dict] = []

        self.title_label = QLabel("自动化定位设置")
        self.title_label.setObjectName("PageTitleLabel")
        self.status_label = QLabel("状态：准备就绪")
        self.status_label.setObjectName("DashboardStatusLabel")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(360)
        self.description_label = QLabel("请选择定位目标")
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("TgapipldcSmallLabel")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(360)
        self.url_edit = QLineEdit("https://web.telegram.org/k/")

        self.locator_mode_combo = QComboBox()
        self.locator_mode_combo.addItem("Strategies（元素特征）", MODE_STRATEGIES)
        self.locator_mode_combo.addItem("绝对位置（像素坐标）", MODE_ABSOLUTE)
        self.locator_mode_combo.setMinimumWidth(220)

        self.absolute_x_spinbox = QDoubleSpinBox()
        self.absolute_x_spinbox.setRange(0.0, 10000.0)
        self.absolute_x_spinbox.setDecimals(1)
        self.absolute_x_spinbox.setSingleStep(1.0)
        self.absolute_y_spinbox = QDoubleSpinBox()
        self.absolute_y_spinbox.setRange(0.0, 10000.0)
        self.absolute_y_spinbox.setDecimals(1)
        self.absolute_y_spinbox.setSingleStep(1.0)
        self.viewport_width_spinbox = QSpinBox()
        self.viewport_width_spinbox.setRange(1, 10000)
        self.viewport_width_spinbox.setValue(1200)
        self.viewport_height_spinbox = QSpinBox()
        self.viewport_height_spinbox.setRange(1, 10000)
        self.viewport_height_spinbox.setValue(900)
        self.absolute_captured_label = QLabel("绝对位置：尚未校准")
        self.absolute_captured_label.setObjectName("TgapipldcSmallLabel")

        self.target_json_edit = QPlainTextEdit()
        self.target_json_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.target_json_edit.setPlaceholderText("当前目标的完整 JSON 配置")

        self.reload_button = QPushButton("重新加载")
        self.save_button = QPushButton("保存目标")
        self.reset_button = QPushButton("恢复默认")
        self.calibrate_button = QPushButton("打开校准浏览器")
        self.open_directory_button = QPushButton("打开配置目录")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)

        self.log_text_edit = QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_text_edit.setPlaceholderText("定位配置与校准日志会显示在这里。")

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("TgapipldcHeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.status_label, 0)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        root.addWidget(splitter, 1)

        config_frame = QFrame()
        config_frame.setObjectName("TgapipldcSectionFrame")
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(14, 12, 14, 14)
        config_layout.setSpacing(10)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("定位目标"), 0)
        target_row.addWidget(self.target_combo, 1)
        target_row.addWidget(self.reload_button, 0)
        target_row.addWidget(self.reset_button, 0)
        config_layout.addLayout(target_row)
        config_layout.addWidget(self.description_label)

        calibration_grid = QGridLayout()
        calibration_grid.addWidget(QLabel("测试 Profile"), 0, 0)
        calibration_grid.addWidget(self.profile_combo, 0, 1, 1, 5)
        calibration_grid.addWidget(QLabel("打开地址"), 1, 0)
        calibration_grid.addWidget(self.url_edit, 1, 1, 1, 5)
        calibration_grid.addWidget(QLabel("运行定位模式"), 2, 0)
        calibration_grid.addWidget(self.locator_mode_combo, 2, 1, 1, 2)
        calibration_grid.addWidget(self.absolute_captured_label, 2, 3, 1, 3)
        calibration_grid.addWidget(QLabel("绝对 X"), 3, 0)
        calibration_grid.addWidget(self.absolute_x_spinbox, 3, 1)
        calibration_grid.addWidget(QLabel("绝对 Y"), 3, 2)
        calibration_grid.addWidget(self.absolute_y_spinbox, 3, 3)
        calibration_grid.addWidget(QLabel("校准视口"), 3, 4)
        viewport_row = QHBoxLayout()
        viewport_row.setContentsMargins(0, 0, 0, 0)
        viewport_row.addWidget(self.viewport_width_spinbox)
        viewport_row.addWidget(QLabel("×"))
        viewport_row.addWidget(self.viewport_height_spinbox)
        calibration_grid.addLayout(viewport_row, 3, 5)
        config_layout.addLayout(calibration_grid)

        hint = QLabel(
            "定位模式互斥：Strategies 只使用 role/CSS/text/XPath；绝对位置只按校准时记录的像素坐标点击，"
            "不会先寻找页面中的同类按钮。两套数据会同时保留，可随时切换。打开校准浏览器后，"
            "顶部也能选择要保存的模式。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        config_layout.addWidget(hint)

        config_layout.addWidget(self.target_json_edit, 1)

        action_row = QHBoxLayout()
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.calibrate_button)
        action_row.addWidget(self.open_directory_button)
        action_row.addWidget(self.stop_button)
        action_row.addStretch(1)
        config_layout.addLayout(action_row)

        log_frame = QFrame()
        log_frame.setObjectName("TgapipldcSectionFrame")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(14, 12, 14, 14)
        log_layout.addWidget(QLabel("运行日志"))
        log_layout.addWidget(self.log_text_edit, 1)

        splitter.addWidget(config_frame)
        splitter.addWidget(log_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 240])

        for button in (
            self.reload_button,
            self.save_button,
            self.reset_button,
            self.calibrate_button,
            self.open_directory_button,
            self.stop_button,
        ):
            button.setMinimumHeight(32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setObjectName("PrimaryButton")
        self.calibrate_button.setObjectName("PrimaryButton")

    def _connect_signals(self) -> None:
        self.target_combo.currentIndexChanged.connect(self._load_selected_target)
        self.reload_button.clicked.connect(self.reload_requested.emit)
        self.save_button.clicked.connect(self._emit_save)
        self.reset_button.clicked.connect(self._emit_reset)
        self.calibrate_button.clicked.connect(self._emit_calibrate)
        self.open_directory_button.clicked.connect(
            self.open_config_directory_requested.emit
        )
        self.stop_button.clicked.connect(self.stop_process_requested.emit)
        self.locator_mode_combo.currentIndexChanged.connect(self._apply_mode_to_json)
        self.absolute_x_spinbox.valueChanged.connect(
            self._apply_absolute_fields_to_json
        )
        self.absolute_y_spinbox.valueChanged.connect(
            self._apply_absolute_fields_to_json
        )
        self.viewport_width_spinbox.valueChanged.connect(
            self._apply_absolute_fields_to_json
        )
        self.viewport_height_spinbox.valueChanged.connect(
            self._apply_absolute_fields_to_json
        )

    def set_targets(self, targets: dict[str, dict]) -> None:
        selected_id = self.current_target_id()
        self._targets = deepcopy(dict(targets or {}))
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        for target_id, config in sorted(
            self._targets.items(),
            key=lambda item: (str(item[1].get("category") or ""), item[0]),
        ):
            category = str(config.get("category") or "其他")
            description = str(config.get("description") or target_id)
            self.target_combo.addItem(f"[{category}] {description}", target_id)
        if selected_id:
            index = self.target_combo.findData(selected_id)
            if index >= 0:
                self.target_combo.setCurrentIndex(index)
        self.target_combo.blockSignals(False)
        self._load_selected_target()

    def set_profiles(self, profiles) -> None:
        selected = self.current_profile_dir()
        self._profiles = []
        self.profile_combo.clear()
        for item in profiles or []:
            if hasattr(item, "profile_dir"):
                payload = {
                    "profile_dir": str(item.profile_dir),
                    "display_name": str(item.display_name),
                    "raw_proxy": str(getattr(item, "raw_proxy", "") or ""),
                }
            else:
                payload = dict(item or {})
            profile_dir = str(payload.get("profile_dir") or "")
            if not profile_dir:
                continue
            self._profiles.append(payload)
            self.profile_combo.addItem(
                str(payload.get("display_name") or profile_dir), profile_dir
            )
        if selected:
            index = self.profile_combo.findData(selected)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)

    def current_target_id(self) -> str:
        return str(self.target_combo.currentData() or "")

    def current_profile_dir(self) -> str:
        return str(self.profile_combo.currentData() or "")

    def current_target_json(self) -> str:
        return self.target_json_edit.toPlainText()

    def current_locator_mode(self) -> str:
        return str(self.locator_mode_combo.currentData() or MODE_STRATEGIES)

    def set_status(self, text: str) -> None:
        self.status_label.setText(
            f"状态：{str(text or '').strip() or '准备就绪'}"
        )

    def set_process_running(self, running: bool) -> None:
        is_running = bool(running)
        for widget in (
            self.target_combo,
            self.profile_combo,
            self.url_edit,
            self.locator_mode_combo,
            self.absolute_x_spinbox,
            self.absolute_y_spinbox,
            self.viewport_width_spinbox,
            self.viewport_height_spinbox,
            self.target_json_edit,
            self.reload_button,
            self.save_button,
            self.reset_button,
            self.calibrate_button,
            self.open_directory_button,
        ):
            widget.setEnabled(not is_running)
        self.stop_button.setEnabled(is_running)
        self.set_status("运行中" if is_running else "准备就绪")

    def append_log(self, message: str) -> None:
        text = str(message or "").rstrip()
        if not text:
            return
        self.log_text_edit.appendPlainText(text)
        scrollbar = self.log_text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _load_selected_target(self) -> None:
        target_id = self.current_target_id()
        target = deepcopy(self._targets.get(target_id) or {})
        self.description_label.setText(
            f"配置键：{target_id}\n{str(target.get('description') or '')}"
            if target_id
            else "请选择定位目标"
        )
        self.target_json_edit.blockSignals(True)
        self.target_json_edit.setPlainText(
            json.dumps(target, ensure_ascii=False, indent=2)
        )
        self.target_json_edit.blockSignals(False)
        self._sync_mode_fields_from_target(target)

    def _sync_mode_fields_from_target(self, target: dict) -> None:
        mode = str(target.get("locator_mode") or MODE_STRATEGIES)
        mode_index = self.locator_mode_combo.findData(mode)
        absolute = (
            target.get("absolute_position")
            if isinstance(target.get("absolute_position"), dict)
            else {}
        )
        widgets = (
            self.locator_mode_combo,
            self.absolute_x_spinbox,
            self.absolute_y_spinbox,
            self.viewport_width_spinbox,
            self.viewport_height_spinbox,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.locator_mode_combo.setCurrentIndex(max(0, mode_index))
        self.absolute_x_spinbox.setValue(float(absolute.get("x") or 0.0))
        self.absolute_y_spinbox.setValue(float(absolute.get("y") or 0.0))
        self.viewport_width_spinbox.setValue(
            max(1, int(absolute.get("viewport_width") or 1200))
        )
        self.viewport_height_spinbox.setValue(
            max(1, int(absolute.get("viewport_height") or 900))
        )
        for widget in widgets:
            widget.blockSignals(False)
        captured = bool(absolute.get("captured", False))
        self.absolute_captured_label.setText(
            "绝对位置：已校准" if captured else "绝对位置：尚未校准"
        )

    def _target_from_editor(self) -> dict | None:
        try:
            target = json.loads(self.target_json_edit.toPlainText() or "{}")
        except Exception:
            return None
        return target if isinstance(target, dict) else None

    def _replace_editor_target(self, target: dict) -> None:
        cursor = self.target_json_edit.textCursor()
        self.target_json_edit.blockSignals(True)
        self.target_json_edit.setPlainText(
            json.dumps(target, ensure_ascii=False, indent=2)
        )
        self.target_json_edit.setTextCursor(cursor)
        self.target_json_edit.blockSignals(False)

    def _apply_mode_to_json(self) -> None:
        target = self._target_from_editor()
        if target is None:
            return
        target["locator_mode"] = self.current_locator_mode()
        self._replace_editor_target(target)

    def _apply_absolute_fields_to_json(self) -> None:
        target = self._target_from_editor()
        if target is None:
            return
        target["absolute_position"] = {
            "x": float(self.absolute_x_spinbox.value()),
            "y": float(self.absolute_y_spinbox.value()),
            "viewport_width": int(self.viewport_width_spinbox.value()),
            "viewport_height": int(self.viewport_height_spinbox.value()),
            "captured": True,
        }
        self.absolute_captured_label.setText("绝对位置：已校准（手动设置）")
        self._replace_editor_target(target)

    def _emit_save(self) -> None:
        target_id = self.current_target_id()
        if target_id:
            self.save_target_requested.emit(target_id, self.current_target_json())

    def _emit_reset(self) -> None:
        target_id = self.current_target_id()
        if target_id:
            self.reset_target_requested.emit(target_id)

    def _emit_calibrate(self) -> None:
        target_id = self.current_target_id()
        profile_dir = self.current_profile_dir()
        if target_id and profile_dir:
            self._apply_mode_to_json()
            self.save_target_requested.emit(target_id, self.current_target_json())
            self.calibrate_requested.emit(
                target_id,
                profile_dir,
                self.url_edit.text().strip(),
            )

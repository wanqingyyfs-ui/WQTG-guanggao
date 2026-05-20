from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
    ACCOUNT_ROTATE_MODE_SINGLE,
    GROUP_ROTATE_MODE_ROUND_ROBIN,
    GROUP_ROTATE_MODE_SINGLE,
    MESSAGE_MODE_TEMPLATE,
    MESSAGE_MODE_TEXT,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    Settings,
)
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    style_form_layout,
    style_group_box,
)
from app.gui.widgets.no_wheel import (
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
    NoWheelTimeEdit,
)

MAX_SECONDS = 365 * 24 * 60 * 60


class ConfigPage(QWidget):
    """
    配置管理页。

    最终规则：
    - 本页自动保存、自动从 runtime 重新加载，不提供手动保存/重新加载按钮。
    - 群发运行中，发送相关配置禁用；UI 外观配置仍允许修改。
    - 延迟和间隔在 UI 中按“秒”填写，支持 3 位小数，内部保存为毫秒。
    """

    def __init__(self, runtime_service, parent=None):
        super().__init__(parent)

        self.runtime = runtime_service
        self._loading = False
        self._last_error_text = ""
        self._send_related_widgets: list[QWidget] = []
        self._ui_related_widgets: list[QWidget] = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._auto_save)

        self._build_ui()
        self.reload_from_runtime()

        if hasattr(self.runtime, "scheduler_status_changed"):
            self.runtime.scheduler_status_changed.connect(
                self._on_scheduler_status_changed
            )

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel("配置管理")
        title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        content_layout.addWidget(self._build_runtime_group())
        content_layout.addWidget(self._build_probability_group())
        content_layout.addWidget(self._build_default_data_group())
        content_layout.addWidget(self._build_default_task_group())
        content_layout.addWidget(self._build_ui_group())
        content_layout.addStretch(1)

        apply_large_inputs(content_widget)

        root_layout.addWidget(title_label)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(make_scroll_area(content_widget), 1)

    def _build_runtime_group(self) -> QGroupBox:
        group = QGroupBox("基础运行与素材监听配置")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.app_name_edit = QLineEdit()
        self.log_level_combo = NoWheelComboBox()
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.log_level_combo.addItem(level, level)

        self.max_concurrent_tasks_spin = NoWheelSpinBox()
        self.max_concurrent_tasks_spin.setRange(0, 9999)
        self.max_concurrent_tasks_spin.setSpecialValueText("0 = 不限制")
        self.max_concurrent_tasks_spin.setToolTip(
            "0 表示不限制并发；大于 0 表示最多同时执行多少个任务"
        )

        self.template_source_account_name_edit = QLineEdit()
        self.template_source_account_name_edit.setPlaceholderText("用于监听素材群的账号名称")

        self.template_source_chat_id_edit = QLineEdit()
        self.template_source_chat_id_edit.setPlaceholderText("素材群 Chat ID，只能填写数字")

        self.config_auto_save_debounce_spin = NoWheelSpinBox()
        self.config_auto_save_debounce_spin.setRange(100, 10000)
        self.config_auto_save_debounce_spin.setSingleStep(50)
        self.config_auto_save_debounce_spin.setSuffix(" 毫秒")

        form.addRow("应用名称：", self.app_name_edit)
        form.addRow("日志等级：", self.log_level_combo)
        form.addRow("最大并发任务：", self.max_concurrent_tasks_spin)
        form.addRow("素材监听账号：", self.template_source_account_name_edit)
        form.addRow("素材群 Chat ID：", self.template_source_chat_id_edit)
        form.addRow("自动保存防抖：", self.config_auto_save_debounce_spin)

        self._send_related_widgets.extend(
            [
                self.app_name_edit,
                self.log_level_combo,
                self.max_concurrent_tasks_spin,
                self.template_source_account_name_edit,
                self.template_source_chat_id_edit,
            ]
        )
        self._ui_related_widgets.append(self.config_auto_save_debounce_spin)

        return group

    def _build_probability_group(self) -> QGroupBox:
        group = QGroupBox("发送前概率判定")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.ad_probability_spin = NoWheelSpinBox()
        self.ad_probability_spin.setRange(0, 100)
        self.ad_probability_spin.setSuffix(" %")

        self.noise_probability_spin = NoWheelSpinBox()
        self.noise_probability_spin.setRange(0, 100)
        self.noise_probability_spin.setSuffix(" %")

        self.skip_probability_spin = NoWheelSpinBox()
        self.skip_probability_spin.setRange(0, 100)
        self.skip_probability_spin.setSuffix(" %")

        self.probability_status_label = QLabel("")
        self.probability_status_label.setWordWrap(True)

        form.addRow("发送广告概率：", self.ad_probability_spin)
        form.addRow("发送噪音概率：", self.noise_probability_spin)
        form.addRow("跳过概率：", self.skip_probability_spin)
        form.addRow("概率校验：", self.probability_status_label)

        self._send_related_widgets.extend(
            [
                self.ad_probability_spin,
                self.noise_probability_spin,
                self.skip_probability_spin,
            ]
        )

        return group

    def _build_default_data_group(self) -> QGroupBox:
        group = QGroupBox("新增数据默认值")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.default_account_enabled_check = QCheckBox("新增账号默认启用")
        self.default_group_enabled_check = QCheckBox("新增群组默认启用")
        self.default_template_enabled_check = QCheckBox("新增模板默认启用")
        self.default_session_name_follow_account_check = QCheckBox(
            "新增账号时，Session 名默认跟随账号名称"
        )
        self.default_group_username_normalize_check = QCheckBox(
            "新增群组时，自动规范化 username"
        )

        form.addRow("账号：", self.default_account_enabled_check)
        form.addRow("群组：", self.default_group_enabled_check)
        form.addRow("模板：", self.default_template_enabled_check)
        form.addRow("Session：", self.default_session_name_follow_account_check)
        form.addRow("群组 username：", self.default_group_username_normalize_check)

        self._send_related_widgets.extend(
            [
                self.default_account_enabled_check,
                self.default_group_enabled_check,
                self.default_template_enabled_check,
                self.default_session_name_follow_account_check,
                self.default_group_username_normalize_check,
            ]
        )

        return group

    def _build_default_task_group(self) -> QGroupBox:
        group = QGroupBox("新增任务默认值")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.default_task_account_rotate_combo = NoWheelComboBox()
        self.default_task_account_rotate_combo.addItem(
            "单账号", ACCOUNT_ROTATE_MODE_SINGLE
        )
        self.default_task_account_rotate_combo.addItem(
            "多账号轮询", ACCOUNT_ROTATE_MODE_ROUND_ROBIN
        )

        self.default_task_account_delay_min_seconds_spin = self._new_seconds_spin()
        self.default_task_account_delay_max_seconds_spin = self._new_seconds_spin()

        self.default_task_group_rotate_combo = NoWheelComboBox()
        self.default_task_group_rotate_combo.addItem("单群组", GROUP_ROTATE_MODE_SINGLE)
        self.default_task_group_rotate_combo.addItem(
            "多群组轮询", GROUP_ROTATE_MODE_ROUND_ROBIN
        )

        self.default_task_group_delay_min_seconds_spin = self._new_seconds_spin()
        self.default_task_group_delay_max_seconds_spin = self._new_seconds_spin()

        self.default_task_message_mode_combo = NoWheelComboBox()
        self.default_task_message_mode_combo.addItem("模板消息", MESSAGE_MODE_TEMPLATE)
        self.default_task_message_mode_combo.addItem("纯文本消息", MESSAGE_MODE_TEXT)

        self.default_task_schedule_mode_combo = NoWheelComboBox()
        self.default_task_schedule_mode_combo.addItem("间隔执行", SCHEDULE_MODE_INTERVAL)
        self.default_task_schedule_mode_combo.addItem("每日定时", SCHEDULE_MODE_DAILY)

        self.default_task_interval_seconds_spin = self._new_seconds_spin()
        self.default_task_interval_seconds_spin.setRange(0, MAX_SECONDS)
        self.default_task_interval_seconds_spin.setToolTip(
            "0 表示任务完成后立即进入下一轮到期状态"
        )

        self.default_task_daily_time_edit = NoWheelTimeEdit()
        self.default_task_daily_time_edit.setDisplayFormat("HH:mm")

        form.addRow("账号轮换模式：", self.default_task_account_rotate_combo)
        form.addRow("账号延迟最小值：", self.default_task_account_delay_min_seconds_spin)
        form.addRow("账号延迟最大值：", self.default_task_account_delay_max_seconds_spin)
        form.addRow("群组轮换模式：", self.default_task_group_rotate_combo)
        form.addRow("群组延迟最小值：", self.default_task_group_delay_min_seconds_spin)
        form.addRow("群组延迟最大值：", self.default_task_group_delay_max_seconds_spin)
        form.addRow("消息模式：", self.default_task_message_mode_combo)
        form.addRow("调度模式：", self.default_task_schedule_mode_combo)
        form.addRow("间隔时间：", self.default_task_interval_seconds_spin)
        form.addRow("每日时间：", self.default_task_daily_time_edit)

        self._send_related_widgets.extend(
            [
                self.default_task_account_rotate_combo,
                self.default_task_account_delay_min_seconds_spin,
                self.default_task_account_delay_max_seconds_spin,
                self.default_task_group_rotate_combo,
                self.default_task_group_delay_min_seconds_spin,
                self.default_task_group_delay_max_seconds_spin,
                self.default_task_message_mode_combo,
                self.default_task_schedule_mode_combo,
                self.default_task_interval_seconds_spin,
                self.default_task_daily_time_edit,
            ]
        )

        return group

    def _build_ui_group(self) -> QGroupBox:
        group = QGroupBox("界面显示配置")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.global_font_size_spin = self._new_font_spin()
        self.table_font_size_spin = self._new_font_spin()
        self.button_font_size_spin = self._new_font_spin()
        self.input_font_size_spin = self._new_font_spin()
        self.floating_panel_font_size_spin = self._new_font_spin()

        self.account_panel_font_size_spin = self._new_font_spin()
        self.account_panel_width_spin = self._new_size_spin()
        self.account_panel_height_spin = self._new_size_spin()

        self.group_panel_font_size_spin = self._new_font_spin()
        self.group_panel_width_spin = self._new_size_spin()
        self.group_panel_height_spin = self._new_size_spin()

        self.task_panel_font_size_spin = self._new_font_spin()
        self.task_panel_width_spin = self._new_size_spin()
        self.task_panel_height_spin = self._new_size_spin()

        self.template_panel_font_size_spin = self._new_font_spin()
        self.template_panel_width_spin = self._new_size_spin()
        self.template_panel_height_spin = self._new_size_spin()

        form.addRow("全局字号：", self.global_font_size_spin)
        form.addRow("表格字号：", self.table_font_size_spin)
        form.addRow("按钮字号：", self.button_font_size_spin)
        form.addRow("输入框字号：", self.input_font_size_spin)
        form.addRow("浮动面板默认字号：", self.floating_panel_font_size_spin)
        form.addRow("账号面板字号：", self.account_panel_font_size_spin)
        form.addRow("账号面板宽度：", self.account_panel_width_spin)
        form.addRow("账号面板高度：", self.account_panel_height_spin)
        form.addRow("群组面板字号：", self.group_panel_font_size_spin)
        form.addRow("群组面板宽度：", self.group_panel_width_spin)
        form.addRow("群组面板高度：", self.group_panel_height_spin)
        form.addRow("任务面板字号：", self.task_panel_font_size_spin)
        form.addRow("任务面板宽度：", self.task_panel_width_spin)
        form.addRow("任务面板高度：", self.task_panel_height_spin)
        form.addRow("模板面板字号：", self.template_panel_font_size_spin)
        form.addRow("模板面板宽度：", self.template_panel_width_spin)
        form.addRow("模板面板高度：", self.template_panel_height_spin)

        self._ui_related_widgets.extend(
            [
                self.global_font_size_spin,
                self.table_font_size_spin,
                self.button_font_size_spin,
                self.input_font_size_spin,
                self.floating_panel_font_size_spin,
                self.account_panel_font_size_spin,
                self.account_panel_width_spin,
                self.account_panel_height_spin,
                self.group_panel_font_size_spin,
                self.group_panel_width_spin,
                self.group_panel_height_spin,
                self.task_panel_font_size_spin,
                self.task_panel_width_spin,
                self.task_panel_height_spin,
                self.template_panel_font_size_spin,
                self.template_panel_width_spin,
                self.template_panel_height_spin,
            ]
        )

        return group

    @staticmethod
    def _new_seconds_spin() -> NoWheelDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(0, 24 * 60 * 60)
        spin.setDecimals(3)
        spin.setSingleStep(0.100)
        spin.setSuffix(" 秒")
        return spin

    @staticmethod
    def _new_font_spin() -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setRange(8, 36)
        spin.setSuffix(" px")
        return spin

    @staticmethod
    def _new_size_spin() -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setRange(200, 3000)
        spin.setSingleStep(10)
        spin.setSuffix(" px")
        return spin

    def reload_from_runtime(self) -> None:
        self._loading = True
        try:
            self._load_settings(getattr(self.runtime, "settings", Settings()))
            self._set_status("已自动加载当前配置")
            self._last_error_text = ""
        except Exception as exc:
            self._set_error(f"加载配置失败：{exc}")
            QMessageBox.critical(self, "加载配置失败", str(exc))
        finally:
            self._loading = False
            self._connect_auto_save_signals()
            self._update_probability_status()
            self._update_running_state()

    def _load_settings(self, settings: Settings) -> None:
        self.app_name_edit.setText(str(settings.app_name or ""))
        self._set_combo_value(self.log_level_combo, str(settings.log_level or "INFO"))
        self.max_concurrent_tasks_spin.setValue(int(settings.max_concurrent_tasks or 0))
        self.template_source_account_name_edit.setText(
            str(settings.template_source_account_name or "")
        )
        self.template_source_chat_id_edit.setText(
            str(settings.template_source_chat_id or 0)
            if int(settings.template_source_chat_id or 0)
            else ""
        )
        self.config_auto_save_debounce_spin.setValue(
            int(settings.config_auto_save_debounce_ms or 400)
        )

        self.ad_probability_spin.setValue(int(settings.ad_probability or 0))
        self.noise_probability_spin.setValue(int(settings.noise_probability or 0))
        self.skip_probability_spin.setValue(int(settings.skip_probability or 0))

        self.default_account_enabled_check.setChecked(
            bool(settings.default_account_enabled)
        )
        self.default_group_enabled_check.setChecked(bool(settings.default_group_enabled))
        self.default_template_enabled_check.setChecked(
            bool(settings.default_template_enabled)
        )
        self.default_session_name_follow_account_check.setChecked(
            bool(settings.default_session_name_follow_account)
        )
        self.default_group_username_normalize_check.setChecked(
            bool(settings.default_group_username_normalize)
        )

        self._set_combo_value(
            self.default_task_account_rotate_combo,
            str(settings.default_task_account_rotate_mode),
        )
        self.default_task_account_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(settings.default_task_account_delay_min_ms)
        )
        self.default_task_account_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(settings.default_task_account_delay_max_ms)
        )
        self._set_combo_value(
            self.default_task_group_rotate_combo,
            str(settings.default_task_group_rotate_mode),
        )
        self.default_task_group_delay_min_seconds_spin.setValue(
            self._ms_to_seconds(settings.default_task_group_delay_min_ms)
        )
        self.default_task_group_delay_max_seconds_spin.setValue(
            self._ms_to_seconds(settings.default_task_group_delay_max_ms)
        )
        self._set_combo_value(
            self.default_task_message_mode_combo,
            str(settings.default_task_message_mode),
        )
        self._set_combo_value(
            self.default_task_schedule_mode_combo,
            str(settings.default_task_schedule_mode),
        )
        self.default_task_interval_seconds_spin.setValue(
            self._ms_to_seconds(settings.default_task_interval_ms)
        )
        self.default_task_daily_time_edit.setTime(
            self._time_from_text(settings.default_task_daily_time)
        )

        self.global_font_size_spin.setValue(int(settings.global_font_size))
        self.table_font_size_spin.setValue(int(settings.table_font_size))
        self.button_font_size_spin.setValue(int(settings.button_font_size))
        self.input_font_size_spin.setValue(int(settings.input_font_size))
        self.floating_panel_font_size_spin.setValue(int(settings.floating_panel_font_size))

        self.account_panel_font_size_spin.setValue(int(settings.account_panel_font_size))
        self.account_panel_width_spin.setValue(int(settings.account_panel_width))
        self.account_panel_height_spin.setValue(int(settings.account_panel_height))

        self.group_panel_font_size_spin.setValue(int(settings.group_panel_font_size))
        self.group_panel_width_spin.setValue(int(settings.group_panel_width))
        self.group_panel_height_spin.setValue(int(settings.group_panel_height))

        self.task_panel_font_size_spin.setValue(int(settings.task_panel_font_size))
        self.task_panel_width_spin.setValue(int(settings.task_panel_width))
        self.task_panel_height_spin.setValue(int(settings.task_panel_height))

        self.template_panel_font_size_spin.setValue(int(settings.template_panel_font_size))
        self.template_panel_width_spin.setValue(int(settings.template_panel_width))
        self.template_panel_height_spin.setValue(int(settings.template_panel_height))

    def _connect_auto_save_signals(self) -> None:
        for widget in self._send_related_widgets + self._ui_related_widgets:
            if getattr(widget, "_config_page_signal_connected", False):
                continue

            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._schedule_auto_save)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._schedule_auto_save)
            elif isinstance(widget, NoWheelComboBox):
                widget.currentIndexChanged.connect(self._schedule_auto_save)
            elif isinstance(widget, (NoWheelSpinBox, NoWheelDoubleSpinBox)):
                widget.valueChanged.connect(self._schedule_auto_save)
            elif isinstance(widget, NoWheelTimeEdit):
                widget.timeChanged.connect(self._schedule_auto_save)

            widget._config_page_signal_connected = True

    def _schedule_auto_save(self) -> None:
        if self._loading:
            return

        self._update_probability_status()
        debounce_ms = int(self.config_auto_save_debounce_spin.value())
        self._save_timer.start(max(100, debounce_ms))

    def _auto_save(self) -> None:
        if not self._loading:
            self.save_now(show_message=False)

    def save_now(self, show_message: bool = False) -> bool:
        self._save_timer.stop()

        try:
            settings = self._build_settings_from_controls()

            if not settings.probability_is_valid:
                self._set_error(
                    f"概率总和必须等于 100，当前为 {settings.probability_total}"
                )
                return False

            self.runtime.save_settings(settings)
            self._load_settings(settings)
            self._update_probability_status()
            self._set_status("配置已自动保存")
            self._last_error_text = ""

            if self._template_source_changed(settings):
                self._set_status("配置已自动保存；素材监听配置变更后，账号可能需要重启后完全生效")

            if show_message:
                QMessageBox.information(self, "保存成功", "配置已保存")

            return True

        except Exception as exc:
            self._set_error(f"保存失败：{exc}")
            if show_message:
                QMessageBox.warning(self, "保存失败", str(exc))
            return False

    def _build_settings_from_controls(self) -> Settings:
        account_delay_min_ms = self._seconds_to_ms(
            self.default_task_account_delay_min_seconds_spin.value()
        )
        account_delay_max_ms = self._seconds_to_ms(
            self.default_task_account_delay_max_seconds_spin.value()
        )
        group_delay_min_ms = self._seconds_to_ms(
            self.default_task_group_delay_min_seconds_spin.value()
        )
        group_delay_max_ms = self._seconds_to_ms(
            self.default_task_group_delay_max_seconds_spin.value()
        )

        if account_delay_max_ms < account_delay_min_ms:
            account_delay_max_ms = account_delay_min_ms

        if group_delay_max_ms < group_delay_min_ms:
            group_delay_max_ms = group_delay_min_ms

        template_source_chat_id = 0
        chat_id_text = self.template_source_chat_id_edit.text().strip()
        if chat_id_text:
            try:
                template_source_chat_id = int(chat_id_text)
            except ValueError as exc:
                raise ValueError("素材群 Chat ID 必须是数字") from exc

        runtime_settings = getattr(self.runtime, "settings", Settings())

        return Settings(
            app_name=self.app_name_edit.text().strip()
            or "telegram_user_group_sender_gui",
            log_level=self.log_level_combo.currentData() or "INFO",
            log_file=str(getattr(runtime_settings, "log_file", "logs/app.log")),
            sessions_dir=str(getattr(runtime_settings, "sessions_dir", "")),
            scheduler_tick_seconds=float(
                getattr(runtime_settings, "scheduler_tick_seconds", 1.0)
            ),
            max_concurrent_tasks=int(self.max_concurrent_tasks_spin.value()),
            default_send_interval_seconds=float(
                getattr(runtime_settings, "default_send_interval_seconds", 1.0)
            ),
            template_source_account_name=(
                self.template_source_account_name_edit.text().strip()
            ),
            template_source_chat_id=template_source_chat_id,
            ad_probability=int(self.ad_probability_spin.value()),
            noise_probability=int(self.noise_probability_spin.value()),
            skip_probability=int(self.skip_probability_spin.value()),
            default_account_enabled=self.default_account_enabled_check.isChecked(),
            default_group_enabled=self.default_group_enabled_check.isChecked(),
            default_template_enabled=self.default_template_enabled_check.isChecked(),
            default_session_name_follow_account=(
                self.default_session_name_follow_account_check.isChecked()
            ),
            default_group_username_normalize=(
                self.default_group_username_normalize_check.isChecked()
            ),
            default_task_account_rotate_mode=(
                self.default_task_account_rotate_combo.currentData()
                or ACCOUNT_ROTATE_MODE_SINGLE
            ),
            default_task_account_delay_min_ms=account_delay_min_ms,
            default_task_account_delay_max_ms=account_delay_max_ms,
            default_task_group_rotate_mode=(
                self.default_task_group_rotate_combo.currentData()
                or GROUP_ROTATE_MODE_SINGLE
            ),
            default_task_group_delay_min_ms=group_delay_min_ms,
            default_task_group_delay_max_ms=group_delay_max_ms,
            default_task_message_mode=(
                self.default_task_message_mode_combo.currentData()
                or MESSAGE_MODE_TEMPLATE
            ),
            default_task_schedule_mode=(
                self.default_task_schedule_mode_combo.currentData()
                or SCHEDULE_MODE_INTERVAL
            ),
            default_task_interval_ms=self._seconds_to_ms(
                self.default_task_interval_seconds_spin.value()
            ),
            default_task_daily_time=self.default_task_daily_time_edit.time().toString(
                "HH:mm"
            ),
            global_font_size=int(self.global_font_size_spin.value()),
            table_font_size=int(self.table_font_size_spin.value()),
            button_font_size=int(self.button_font_size_spin.value()),
            input_font_size=int(self.input_font_size_spin.value()),
            floating_panel_font_size=int(self.floating_panel_font_size_spin.value()),
            account_panel_font_size=int(self.account_panel_font_size_spin.value()),
            account_panel_width=int(self.account_panel_width_spin.value()),
            account_panel_height=int(self.account_panel_height_spin.value()),
            group_panel_font_size=int(self.group_panel_font_size_spin.value()),
            group_panel_width=int(self.group_panel_width_spin.value()),
            group_panel_height=int(self.group_panel_height_spin.value()),
            task_panel_font_size=int(self.task_panel_font_size_spin.value()),
            task_panel_width=int(self.task_panel_width_spin.value()),
            task_panel_height=int(self.task_panel_height_spin.value()),
            template_panel_font_size=int(self.template_panel_font_size_spin.value()),
            template_panel_width=int(self.template_panel_width_spin.value()),
            template_panel_height=int(self.template_panel_height_spin.value()),
            config_auto_save_debounce_ms=int(
                self.config_auto_save_debounce_spin.value()
            ),
        )

    def _template_source_changed(self, new_settings: Settings) -> bool:
        old_settings = getattr(self.runtime, "settings", None)
        if old_settings is None:
            return False

        return (
            str(getattr(old_settings, "template_source_account_name", "") or "")
            != str(new_settings.template_source_account_name or "")
            or int(getattr(old_settings, "template_source_chat_id", 0) or 0)
            != int(new_settings.template_source_chat_id or 0)
        )

    def _update_probability_status(self) -> None:
        total = (
            self.ad_probability_spin.value()
            + self.noise_probability_spin.value()
            + self.skip_probability_spin.value()
        )

        if total == 100:
            self.probability_status_label.setText("正常：概率总和 = 100")
            self.probability_status_label.setStyleSheet("color: #1f7a1f;")
            return

        self.probability_status_label.setText(
            f"错误：概率总和必须等于 100，当前为 {total}"
        )
        self.probability_status_label.setStyleSheet("color: #b00020;")

    def _on_scheduler_status_changed(self, _status: str) -> None:
        self._update_running_state()

    def _update_running_state(self) -> None:
        running = False
        if hasattr(self.runtime, "is_scheduler_running"):
            try:
                running = bool(self.runtime.is_scheduler_running())
            except Exception:
                running = False

        for widget in self._send_related_widgets:
            widget.setEnabled(not running)

        for widget in self._ui_related_widgets:
            widget.setEnabled(True)

        if running:
            self._set_status("群发运行中：发送相关配置已锁定，界面外观仍可调整")
        elif self._last_error_text:
            self._set_error(self._last_error_text)
        else:
            self._set_status("配置会自动保存")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #1f5f99;")

    def _set_error(self, text: str) -> None:
        self._last_error_text = text
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #b00020;")

    @staticmethod
    def _set_combo_value(combo: NoWheelComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @staticmethod
    def _time_from_text(value: str) -> QTime:
        parsed = QTime.fromString(str(value or "09:00").strip(), "HH:mm")
        return parsed if parsed.isValid() else QTime(9, 0)

    @staticmethod
    def _seconds_to_ms(value: Any) -> int:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            seconds = 0.0

        if seconds < 0:
            seconds = 0.0

        return int(round(seconds * 1000))

    @staticmethod
    def _ms_to_seconds(value: Any) -> float:
        try:
            ms = int(value)
        except (TypeError, ValueError):
            ms = 0

        if ms < 0:
            ms = 0

        return round(ms / 1000.0, 3)

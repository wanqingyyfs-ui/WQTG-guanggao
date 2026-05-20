from __future__ import annotations

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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


class ConfigPage(QWidget):
    def __init__(self, runtime_service, parent=None):
        super().__init__(parent)

        self.runtime = runtime_service
        self._loading = False
        self._last_error_text = ""

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

        title_layout = QHBoxLayout()
        title_layout.setSpacing(12)

        title_label = QLabel("配置管理")
        title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.reload_button = QPushButton("重新加载")
        self.reload_button.clicked.connect(self.reload_from_runtime)

        self.save_button = QPushButton("立即保存")
        self.save_button.clicked.connect(self.save_now)

        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        title_layout.addWidget(self.status_label)
        title_layout.addWidget(self.reload_button)
        title_layout.addWidget(self.save_button)

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

        root_layout.addLayout(title_layout)
        root_layout.addWidget(make_scroll_area(content_widget), 1)

    def _build_runtime_group(self) -> QGroupBox:
        group = QGroupBox("基础运行配置")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.app_name_edit = QLineEdit()
        self.log_level_combo = NoWheelComboBox()
        self.log_level_combo.addItem("DEBUG", "DEBUG")
        self.log_level_combo.addItem("INFO", "INFO")
        self.log_level_combo.addItem("WARNING", "WARNING")
        self.log_level_combo.addItem("ERROR", "ERROR")

        self.scheduler_tick_spin = NoWheelDoubleSpinBox()
        self.scheduler_tick_spin.setRange(0.05, 60.0)
        self.scheduler_tick_spin.setSingleStep(0.05)
        self.scheduler_tick_spin.setDecimals(2)
        self.scheduler_tick_spin.setSuffix(" 秒")

        self.max_concurrent_tasks_spin = NoWheelSpinBox()
        self.max_concurrent_tasks_spin.setRange(0, 9999)
        self.max_concurrent_tasks_spin.setSpecialValueText("0 = 不限制")
        self.max_concurrent_tasks_spin.setToolTip(
            "0 表示不限制并发；大于 0 表示最多同时执行多少个任务"
        )

        self.config_auto_save_debounce_spin = NoWheelSpinBox()
        self.config_auto_save_debounce_spin.setRange(100, 10000)
        self.config_auto_save_debounce_spin.setSingleStep(50)
        self.config_auto_save_debounce_spin.setSuffix(" 毫秒")

        form.addRow("应用名称：", self.app_name_edit)
        form.addRow("日志等级：", self.log_level_combo)
        form.addRow("调度扫描间隔：", self.scheduler_tick_spin)
        form.addRow("最大并发任务：", self.max_concurrent_tasks_spin)
        form.addRow("配置自动保存防抖：", self.config_auto_save_debounce_spin)

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

        return group

    def _build_default_task_group(self) -> QGroupBox:
        group = QGroupBox("新增任务默认值")
        style_group_box(group)

        form = QFormLayout(group)
        style_form_layout(form)

        self.default_task_account_rotate_combo = NoWheelComboBox()
        self.default_task_account_rotate_combo.addItem(
            "单账号",
            ACCOUNT_ROTATE_MODE_SINGLE,
        )
        self.default_task_account_rotate_combo.addItem(
            "多账号轮询",
            ACCOUNT_ROTATE_MODE_ROUND_ROBIN,
        )

        self.default_task_account_delay_min_ms_spin = NoWheelSpinBox()
        self.default_task_account_delay_min_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.default_task_account_delay_min_ms_spin.setSingleStep(100)
        self.default_task_account_delay_min_ms_spin.setSuffix(" 毫秒")

        self.default_task_account_delay_max_ms_spin = NoWheelSpinBox()
        self.default_task_account_delay_max_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.default_task_account_delay_max_ms_spin.setSingleStep(100)
        self.default_task_account_delay_max_ms_spin.setSuffix(" 毫秒")

        self.default_task_group_rotate_combo = NoWheelComboBox()
        self.default_task_group_rotate_combo.addItem(
            "单群组",
            GROUP_ROTATE_MODE_SINGLE,
        )
        self.default_task_group_rotate_combo.addItem(
            "多群组轮询",
            GROUP_ROTATE_MODE_ROUND_ROBIN,
        )

        self.default_task_group_delay_min_ms_spin = NoWheelSpinBox()
        self.default_task_group_delay_min_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.default_task_group_delay_min_ms_spin.setSingleStep(100)
        self.default_task_group_delay_min_ms_spin.setSuffix(" 毫秒")

        self.default_task_group_delay_max_ms_spin = NoWheelSpinBox()
        self.default_task_group_delay_max_ms_spin.setRange(0, 24 * 60 * 60 * 1000)
        self.default_task_group_delay_max_ms_spin.setSingleStep(100)
        self.default_task_group_delay_max_ms_spin.setSuffix(" 毫秒")

        self.default_task_message_mode_combo = NoWheelComboBox()
        self.default_task_message_mode_combo.addItem("模板消息", MESSAGE_MODE_TEMPLATE)
        self.default_task_message_mode_combo.addItem("纯文本消息", MESSAGE_MODE_TEXT)

        self.default_task_schedule_mode_combo = NoWheelComboBox()
        self.default_task_schedule_mode_combo.addItem("间隔执行", SCHEDULE_MODE_INTERVAL)
        self.default_task_schedule_mode_combo.addItem("每日定时", SCHEDULE_MODE_DAILY)

        self.default_task_interval_ms_spin = NoWheelSpinBox()
        self.default_task_interval_ms_spin.setRange(0, 365 * 24 * 60 * 60 * 1000)
        self.default_task_interval_ms_spin.setSingleStep(1000)
        self.default_task_interval_ms_spin.setSuffix(" 毫秒")

        self.default_task_daily_time_edit = NoWheelTimeEdit()
        self.default_task_daily_time_edit.setDisplayFormat("HH:mm")

        form.addRow("账号轮换模式：", self.default_task_account_rotate_combo)
        form.addRow("账号延迟最小值：", self.default_task_account_delay_min_ms_spin)
        form.addRow("账号延迟最大值：", self.default_task_account_delay_max_ms_spin)
        form.addRow("群组轮换模式：", self.default_task_group_rotate_combo)
        form.addRow("群组延迟最小值：", self.default_task_group_delay_min_ms_spin)
        form.addRow("群组延迟最大值：", self.default_task_group_delay_max_ms_spin)
        form.addRow("消息模式：", self.default_task_message_mode_combo)
        form.addRow("调度模式：", self.default_task_schedule_mode_combo)
        form.addRow("间隔时间：", self.default_task_interval_ms_spin)
        form.addRow("每日时间：", self.default_task_daily_time_edit)

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

        return group

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
            settings = getattr(self.runtime, "settings", Settings())
            self._load_settings(settings)
            self._set_status("已加载当前配置")
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
        self.scheduler_tick_spin.setValue(float(settings.scheduler_tick_seconds or 1.0))
        self.max_concurrent_tasks_spin.setValue(int(settings.max_concurrent_tasks or 0))
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
        self.default_task_account_delay_min_ms_spin.setValue(
            int(settings.default_task_account_delay_min_ms)
        )
        self.default_task_account_delay_max_ms_spin.setValue(
            int(settings.default_task_account_delay_max_ms)
        )
        self._set_combo_value(
            self.default_task_group_rotate_combo,
            str(settings.default_task_group_rotate_mode),
        )
        self.default_task_group_delay_min_ms_spin.setValue(
            int(settings.default_task_group_delay_min_ms)
        )
        self.default_task_group_delay_max_ms_spin.setValue(
            int(settings.default_task_group_delay_max_ms)
        )
        self._set_combo_value(
            self.default_task_message_mode_combo,
            str(settings.default_task_message_mode),
        )
        self._set_combo_value(
            self.default_task_schedule_mode_combo,
            str(settings.default_task_schedule_mode),
        )
        self.default_task_interval_ms_spin.setValue(int(settings.default_task_interval_ms))
        self.default_task_daily_time_edit.setTime(
            self._time_from_text(settings.default_task_daily_time)
        )

        self.global_font_size_spin.setValue(int(settings.global_font_size))
        self.table_font_size_spin.setValue(int(settings.table_font_size))
        self.button_font_size_spin.setValue(int(settings.button_font_size))
        self.input_font_size_spin.setValue(int(settings.input_font_size))
        self.floating_panel_font_size_spin.setValue(
            int(settings.floating_panel_font_size)
        )

        self.account_panel_font_size_spin.setValue(int(settings.account_panel_font_size))
        self.account_panel_width_spin.setValue(int(settings.account_panel_width))
        self.account_panel_height_spin.setValue(int(settings.account_panel_height))

        self.group_panel_font_size_spin.setValue(int(settings.group_panel_font_size))
        self.group_panel_width_spin.setValue(int(settings.group_panel_width))
        self.group_panel_height_spin.setValue(int(settings.group_panel_height))

        self.task_panel_font_size_spin.setValue(int(settings.task_panel_font_size))
        self.task_panel_width_spin.setValue(int(settings.task_panel_width))
        self.task_panel_height_spin.setValue(int(settings.task_panel_height))

        self.template_panel_font_size_spin.setValue(
            int(settings.template_panel_font_size)
        )
        self.template_panel_width_spin.setValue(int(settings.template_panel_width))
        self.template_panel_height_spin.setValue(int(settings.template_panel_height))

    def _connect_auto_save_signals(self) -> None:
        widgets = [
            self.app_name_edit,
            self.log_level_combo,
            self.scheduler_tick_spin,
            self.max_concurrent_tasks_spin,
            self.config_auto_save_debounce_spin,
            self.ad_probability_spin,
            self.noise_probability_spin,
            self.skip_probability_spin,
            self.default_account_enabled_check,
            self.default_group_enabled_check,
            self.default_template_enabled_check,
            self.default_session_name_follow_account_check,
            self.default_group_username_normalize_check,
            self.default_task_account_rotate_combo,
            self.default_task_account_delay_min_ms_spin,
            self.default_task_account_delay_max_ms_spin,
            self.default_task_group_rotate_combo,
            self.default_task_group_delay_min_ms_spin,
            self.default_task_group_delay_max_ms_spin,
            self.default_task_message_mode_combo,
            self.default_task_schedule_mode_combo,
            self.default_task_interval_ms_spin,
            self.default_task_daily_time_edit,
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

        for widget in widgets:
            self._connect_widget_change_signal(widget)

    def _connect_widget_change_signal(self, widget) -> None:
        if getattr(widget, "_config_page_signal_connected", False):
            return

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

        debounce_ms = self.config_auto_save_debounce_spin.value()
        self._save_timer.start(max(100, int(debounce_ms)))

    def _auto_save(self) -> None:
        if self._loading:
            return

        self.save_now(show_message=False)

    def save_now(self, show_message: bool = True) -> bool:
        self._save_timer.stop()

        try:
            settings = self._build_settings_from_controls()

            if not settings.probability_is_valid:
                self._set_error(
                    "概率总和必须等于 100，当前为 "
                    f"{settings.probability_total}"
                )
                return False

            self.runtime.save_settings(settings)
            self._load_settings(settings)
            self._update_probability_status()
            self._set_status("配置已保存")
            self._last_error_text = ""

            if show_message:
                QMessageBox.information(self, "保存成功", "配置已保存")

            return True

        except Exception as exc:
            self._set_error(f"保存失败：{exc}")

            if show_message:
                QMessageBox.warning(self, "保存失败", str(exc))

            return False

    def _build_settings_from_controls(self) -> Settings:
        account_delay_min_ms = self.default_task_account_delay_min_ms_spin.value()
        account_delay_max_ms = self.default_task_account_delay_max_ms_spin.value()
        group_delay_min_ms = self.default_task_group_delay_min_ms_spin.value()
        group_delay_max_ms = self.default_task_group_delay_max_ms_spin.value()

        if account_delay_max_ms < account_delay_min_ms:
            account_delay_max_ms = account_delay_min_ms

        if group_delay_max_ms < group_delay_min_ms:
            group_delay_max_ms = group_delay_min_ms

        return Settings(
            app_name=self.app_name_edit.text().strip()
            or "telegram_user_group_sender_gui",
            log_level=self.log_level_combo.currentData() or "INFO",
            log_file=str(getattr(self.runtime.settings, "log_file", "logs/app.log")),
            sessions_dir=str(getattr(self.runtime.settings, "sessions_dir", "")),
            scheduler_tick_seconds=float(self.scheduler_tick_spin.value()),
            max_concurrent_tasks=int(self.max_concurrent_tasks_spin.value()),
            default_send_interval_seconds=float(
                getattr(self.runtime.settings, "default_send_interval_seconds", 1.0)
            ),
            template_source_account_name=str(
                getattr(self.runtime.settings, "template_source_account_name", "")
            ),
            template_source_chat_id=int(
                getattr(self.runtime.settings, "template_source_chat_id", 0)
            ),
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
            default_task_interval_ms=int(self.default_task_interval_ms_spin.value()),
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

        if running:
            self.status_label.setText("群发运行中：配置禁止保存")
            self.status_label.setStyleSheet("color: #b00020;")
            self.save_button.setEnabled(False)
        else:
            if self._last_error_text:
                self._set_error(self._last_error_text)
            else:
                self._set_status("可编辑")
            self.save_button.setEnabled(True)

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

        if index < 0:
            index = 0

        combo.setCurrentIndex(index)

    @staticmethod
    def _time_from_text(value: str) -> QTime:
        text = str(value or "09:00").strip()
        parsed = QTime.fromString(text, "HH:mm")

        if parsed.isValid():
            return parsed

        return QTime(9, 0)
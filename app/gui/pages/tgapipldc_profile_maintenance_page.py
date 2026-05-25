from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class TgapipldcProfileMaintenancePage(QWidget):
    """Telegram 账号资料维护页面。

    本页面只负责展示、采集配置和发出信号；实际业务由 RuntimeService / RunnerService
    调用 app/vendor/tgapipldc/src/update_telegram_profile.py 完成。
    """

    upload_profile_photos_requested = Signal(object)
    open_profile_photo_library_requested = Signal()
    clear_profile_maintenance_results_requested = Signal()
    profile_maintenance_requested = Signal(str, dict)
    stop_process_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title_label = QLabel("账号资料维护")
        self.title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("状态：准备就绪")
        self.status_label.setObjectName("DashboardStatusLabel")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.description_label = QLabel(
            "读取 account_proxy_map.csv 中已绑定的账号，按账号自己的 profile 和代理逐个打开 Telegram Web，"
            "支持单项维护或一次性维护全部资料。"
        )
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("TgapipldcSmallLabel")

        self.photo_library_path_edit = QLineEdit("assets/profile_photos")
        self.photo_library_path_edit.setReadOnly(True)
        self.photo_library_path_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.upload_profile_photos_button = QPushButton("上传图片")
        self.open_profile_photo_library_button = QPushButton("打开图片库")

        self.update_photo_checkbox = QCheckBox("启用修改头像")
        self.update_photo_checkbox.setChecked(True)
        self.photo_mode_combo = QComboBox()
        self.photo_mode_combo.addItem("随机", "random")
        self.photo_mode_combo.addItem("顺序", "sequential")
        self.photo_mode_combo.addItem("不重复随机", "unique_random")

        self.update_name_checkbox = QCheckBox("启用修改昵称")
        self.update_name_checkbox.setChecked(True)
        self.name_pool_edit = QPlainTextEdit()
        self.name_pool_edit.setPlaceholderText(
            "一行一个名字，例如：\n张三\n李四\n王五\n\n也支持 First Name,Last Name：\n张,三\n李,四"
        )
        self.name_pool_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.update_username_checkbox = QCheckBox("启用修改用户名")
        self.update_username_checkbox.setChecked(True)
        self.username_keyword_edit = QLineEdit()
        self.username_keyword_edit.setPlaceholderText("例如 keyword")
        self.username_start_index_spinbox = QSpinBox()
        self.username_start_index_spinbox.setRange(1, 999999999)
        self.username_start_index_spinbox.setValue(1)
        self.username_preview_label = QLabel("预览：keyword1、keyword2、keyword3")
        self.username_preview_label.setObjectName("TgapipldcSmallLabel")

        self.update_bio_checkbox = QCheckBox("启用修改统一签名")
        self.update_bio_checkbox.setChecked(True)
        self.bio_text_edit = QPlainTextEdit()
        self.bio_text_edit.setPlaceholderText("所有账号统一写入 Telegram Bio / About。为空则跳过签名修改。")
        self.bio_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        self.add_chat_folder_checkbox = QCheckBox("启用添加分组文件夹")
        self.add_chat_folder_checkbox.setChecked(True)
        self.chat_folder_link_edit = QLineEdit()
        self.chat_folder_link_edit.setPlaceholderText("https://t.me/addlist/xxxx")

        self.account_delay_spinbox = QSpinBox()
        self.account_delay_spinbox.setRange(0, 600000)
        self.account_delay_spinbox.setSingleStep(500)
        self.account_delay_spinbox.setValue(3000)
        self.stop_on_error_checkbox = QCheckBox("遇到账号错误后停止全部流程")
        self.stop_on_error_checkbox.setChecked(False)

        self.profile_status_button = QPushButton("检测资料状态")
        self.profile_photo_button = QPushButton("修改头像")
        self.profile_name_button = QPushButton("修改昵称")
        self.profile_username_button = QPushButton("修改用户名")
        self.profile_bio_button = QPushButton("修改签名")
        self.profile_folder_button = QPushButton("添加分组文件夹")
        self.profile_all_button = QPushButton("修改全部选项")
        self.clear_profile_results_button = QPushButton("清空维护结果")
        self.stop_process_button = QPushButton("停止")

        self.log_text_edit = QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setPlaceholderText("账号资料维护运行日志会显示在这里。")
        self.log_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._build_ui()
        self._connect_signals()
        self._refresh_username_preview()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        header_bar = QFrame()
        header_bar.setObjectName("TgapipldcHeaderBar")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.status_label, 0)
        root_layout.addWidget(header_bar, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setObjectName("ProfileMaintenanceScrollArea")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(12)

        scroll_layout.addWidget(self._build_intro_section())
        scroll_layout.addWidget(self._build_photo_section())
        scroll_layout.addWidget(self._build_name_section())
        scroll_layout.addWidget(self._build_username_section())
        scroll_layout.addWidget(self._build_bio_section())
        scroll_layout.addWidget(self._build_folder_section())
        scroll_layout.addWidget(self._build_run_section())
        scroll_layout.addWidget(self._build_log_section(), 1)

        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area, 1)

        self._style_widgets()

    def _build_intro_section(self) -> QFrame:
        section = self._create_section("说明")
        layout = section.layout()
        layout.addWidget(self.description_label)
        hint = QLabel(
            "建议先点击“检测资料状态”，确认代理、profile 和登录状态正常后，再执行修改头像、昵称、用户名、签名或分组文件夹。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_photo_section(self) -> QFrame:
        section = self._create_section("头像设置")
        layout = section.layout()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("图片库"), 0)
        row.addWidget(self.photo_library_path_edit, 1)
        row.addWidget(self.upload_profile_photos_button, 0)
        row.addWidget(self.open_profile_photo_library_button, 0)
        layout.addLayout(row)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(self.update_photo_checkbox, 0, 0)
        grid.addWidget(QLabel("头像选择方式"), 0, 1)
        grid.addWidget(self.photo_mode_combo, 0, 2)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)

        hint = QLabel("支持 jpg、jpeg、png、webp。上传后会复制到本地图片库，并自动改名，避免中文路径和特殊字符问题。")
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_name_section(self) -> QFrame:
        section = self._create_section("昵称设置")
        layout = section.layout()
        layout.addWidget(self.update_name_checkbox)
        self.name_pool_edit.setMinimumHeight(150)
        self.name_pool_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.name_pool_edit)
        hint = QLabel("没有逗号时写入 First Name 并清空 Last Name；有逗号时逗号前为 First Name，逗号后为 Last Name。")
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_username_section(self) -> QFrame:
        section = self._create_section("用户名设置")
        layout = section.layout()
        layout.addWidget(self.update_username_checkbox)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("关键词"), 0)
        row.addWidget(self.username_keyword_edit, 1)
        row.addWidget(QLabel("起始序号"), 0)
        row.addWidget(self.username_start_index_spinbox, 0)
        layout.addLayout(row)
        layout.addWidget(self.username_preview_label)

        hint = QLabel("用户名按“关键词 + 序号”生成；如果被占用或不符合 Telegram 规则，会记录失败并继续下一个账号。")
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_bio_section(self) -> QFrame:
        section = self._create_section("签名设置")
        layout = section.layout()
        layout.addWidget(self.update_bio_checkbox)
        self.bio_text_edit.setMinimumHeight(120)
        self.bio_text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.bio_text_edit)
        hint = QLabel("签名为空时跳过签名修改；不做签名池随机。")
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_folder_section(self) -> QFrame:
        section = self._create_section("分组文件夹")
        layout = section.layout()
        layout.addWidget(self.add_chat_folder_checkbox)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("分组文件夹链接"), 0)
        row.addWidget(self.chat_folder_link_edit, 1)
        layout.addLayout(row)

        hint = QLabel("链接通常是 https://t.me/addlist/xxxx。脚本会发送到 Saved Messages / 收藏夹，再点击链接并添加文件夹。")
        hint.setWordWrap(True)
        hint.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint)
        return section

    def _build_run_section(self) -> QFrame:
        section = self._create_section("运行")
        layout = section.layout()

        settings_row = QHBoxLayout()
        settings_row.setContentsMargins(0, 0, 0, 0)
        settings_row.setSpacing(8)
        settings_row.addWidget(QLabel("账号间隔毫秒"), 0)
        settings_row.addWidget(self.account_delay_spinbox, 0)
        settings_row.addWidget(self.stop_on_error_checkbox, 0)
        settings_row.addStretch(1)
        layout.addLayout(settings_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        for button in (
            self.profile_status_button,
            self.profile_photo_button,
            self.profile_name_button,
            self.profile_username_button,
            self.profile_bio_button,
            self.profile_folder_button,
            self.profile_all_button,
            self.clear_profile_results_button,
            self.stop_process_button,
        ):
            action_row.addWidget(button, 0)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return section

    def _build_log_section(self) -> QFrame:
        section = self._create_section("运行日志")
        layout = section.layout()
        self.log_text_edit.setMinimumHeight(240)
        self.log_text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_text_edit.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.log_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.log_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.log_text_edit, 1)
        return section

    @staticmethod
    def _create_section(title: str) -> QFrame:
        section = QFrame()
        section.setObjectName("TgapipldcSectionFrame")
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("TgapipldcSectionTitleLabel")
        layout.addWidget(title_label)
        return section

    def _style_widgets(self) -> None:
        self.setMinimumHeight(520)

        locked_header_style = (
            "QLineEdit {"
            "background: #f3f6fb;"
            "border: 1px solid #d7deea;"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "color: #334155;"
            "}"
        )
        self.photo_library_path_edit.setStyleSheet(locked_header_style)

        for editor in (
            self.name_pool_edit,
            self.bio_text_edit,
            self.log_text_edit,
        ):
            editor.setViewportMargins(0, 0, 0, 0)
            editor.document().setDocumentMargin(6)

        buttons = [
            self.upload_profile_photos_button,
            self.open_profile_photo_library_button,
            self.profile_status_button,
            self.profile_photo_button,
            self.profile_name_button,
            self.profile_username_button,
            self.profile_bio_button,
            self.profile_folder_button,
            self.profile_all_button,
            self.clear_profile_results_button,
            self.stop_process_button,
        ]
        for button in buttons:
            button.setMinimumHeight(32)
            button.setMaximumHeight(36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.profile_status_button.setMinimumWidth(108)
        self.profile_photo_button.setMinimumWidth(88)
        self.profile_name_button.setMinimumWidth(88)
        self.profile_username_button.setMinimumWidth(98)
        self.profile_bio_button.setMinimumWidth(88)
        self.profile_folder_button.setMinimumWidth(120)
        self.profile_all_button.setMinimumWidth(116)
        self.clear_profile_results_button.setMinimumWidth(116)
        self.stop_process_button.setMinimumWidth(72)
        self.upload_profile_photos_button.setMinimumWidth(88)
        self.open_profile_photo_library_button.setMinimumWidth(104)

        self.profile_all_button.setObjectName("PrimaryButton")
        self.clear_profile_results_button.setObjectName("DangerButton")
        self.stop_process_button.setObjectName("DangerButton")
        self.stop_process_button.setEnabled(False)

        self.photo_mode_combo.setMinimumWidth(140)
        self.username_start_index_spinbox.setMinimumWidth(120)
        self.account_delay_spinbox.setMinimumWidth(120)

    def _connect_signals(self) -> None:
        self.upload_profile_photos_button.clicked.connect(self._choose_profile_photos)
        self.open_profile_photo_library_button.clicked.connect(
            self.open_profile_photo_library_requested.emit
        )
        self.clear_profile_results_button.clicked.connect(
            self.clear_profile_maintenance_results_requested.emit
        )
        self.stop_process_button.clicked.connect(self.stop_process_requested.emit)

        self.profile_status_button.clicked.connect(lambda: self._emit_profile_maintenance("status"))
        self.profile_photo_button.clicked.connect(lambda: self._emit_profile_maintenance("photo"))
        self.profile_name_button.clicked.connect(lambda: self._emit_profile_maintenance("name"))
        self.profile_username_button.clicked.connect(lambda: self._emit_profile_maintenance("username"))
        self.profile_bio_button.clicked.connect(lambda: self._emit_profile_maintenance("bio"))
        self.profile_folder_button.clicked.connect(lambda: self._emit_profile_maintenance("folder"))
        self.profile_all_button.clicked.connect(lambda: self._emit_profile_maintenance("all"))

        self.username_keyword_edit.textChanged.connect(self._refresh_username_preview)
        self.username_start_index_spinbox.valueChanged.connect(self._refresh_username_preview)

    def set_profile_maintenance_config(self, config: dict) -> None:
        config = dict(config or {})
        self.update_photo_checkbox.setChecked(bool(config.get("update_photo", True)))
        self._set_combo_data(self.photo_mode_combo, str(config.get("photo_mode") or "random"))
        self.photo_library_path_edit.setText(str(config.get("photo_library_dir") or "assets/profile_photos"))

        self.update_name_checkbox.setChecked(bool(config.get("update_name", True)))
        name_pool = config.get("name_pool") or []
        if isinstance(name_pool, str):
            name_text = name_pool
        else:
            name_text = "\n".join(str(item or "") for item in name_pool)
        self.name_pool_edit.setPlainText(name_text)

        self.update_username_checkbox.setChecked(bool(config.get("update_username", True)))
        self.username_keyword_edit.setText(str(config.get("username_keyword") or ""))
        try:
            self.username_start_index_spinbox.setValue(max(1, int(config.get("username_start_index") or 1)))
        except Exception:
            self.username_start_index_spinbox.setValue(1)

        self.update_bio_checkbox.setChecked(bool(config.get("update_bio", True)))
        self.bio_text_edit.setPlainText(str(config.get("bio_text") or ""))

        self.add_chat_folder_checkbox.setChecked(bool(config.get("add_chat_folder", True)))
        self.chat_folder_link_edit.setText(str(config.get("chat_folder_link") or ""))

        try:
            self.account_delay_spinbox.setValue(max(0, int(config.get("account_delay_ms") or 3000)))
        except Exception:
            self.account_delay_spinbox.setValue(3000)
        self.stop_on_error_checkbox.setChecked(bool(config.get("stop_on_error", False)))
        self._refresh_username_preview()

    def get_profile_maintenance_config(self) -> dict:
        name_pool = [
            line.strip()
            for line in self.name_pool_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if line.strip()
        ]
        return {
            "update_photo": self.update_photo_checkbox.isChecked(),
            "photo_mode": self.photo_mode_combo.currentData() or "random",
            "photo_library_dir": self.photo_library_path_edit.text().strip() or "assets/profile_photos",
            "update_name": self.update_name_checkbox.isChecked(),
            "name_pool": name_pool,
            "update_username": self.update_username_checkbox.isChecked(),
            "username_keyword": self.username_keyword_edit.text().strip(),
            "username_start_index": int(self.username_start_index_spinbox.value()),
            "update_bio": self.update_bio_checkbox.isChecked(),
            "bio_text": self.bio_text_edit.toPlainText(),
            "add_chat_folder": self.add_chat_folder_checkbox.isChecked(),
            "chat_folder_link": self.chat_folder_link_edit.text().strip(),
            "account_delay_ms": int(self.account_delay_spinbox.value()),
            "stop_on_error": self.stop_on_error_checkbox.isChecked(),
        }

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{str(text or '').strip() or '准备就绪'}")

    def append_log(self, message: str) -> None:
        safe_message = str(message or "").rstrip()
        if not safe_message:
            return
        self.log_text_edit.appendPlainText(safe_message)
        scrollbar = self.log_text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self) -> None:
        self.log_text_edit.clear()

    def set_process_running(self, running: bool) -> None:
        is_running = bool(running)
        for button in (
            self.upload_profile_photos_button,
            self.open_profile_photo_library_button,
            self.profile_status_button,
            self.profile_photo_button,
            self.profile_name_button,
            self.profile_username_button,
            self.profile_bio_button,
            self.profile_folder_button,
            self.profile_all_button,
            self.clear_profile_results_button,
        ):
            button.setEnabled(not is_running)
        self.stop_process_button.setEnabled(is_running)
        self.set_status("运行中" if is_running else "准备就绪")

    def _choose_profile_photos(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择头像图片",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.webp)",
        )
        if file_paths:
            self.upload_profile_photos_requested.emit(file_paths)

    def _emit_profile_maintenance(self, action: str) -> None:
        self.profile_maintenance_requested.emit(action, self.get_profile_maintenance_config())

    def _refresh_username_preview(self) -> None:
        keyword = self.username_keyword_edit.text().strip() or "keyword"
        start_index = int(self.username_start_index_spinbox.value())
        examples = [f"{keyword}{start_index + offset}" for offset in range(3)]
        self.username_preview_label.setText("预览：" + "、".join(examples))

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if str(combo.itemData(index)) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

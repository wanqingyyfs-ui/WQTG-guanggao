from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


ACCOUNTS_HEADER_TEXT = "phone,country,profile_dir,status,yanzheng"
PROXIES_HEADER_TEXT = "raw_proxy"


class TgapipldcPage(QWidget):
    """
    tgapipldc API 批量工作台页面。

    当前动态代理规则：
    - accounts.csv 正文仍按 phone,country,profile_dir,status,yanzheng 填写；
    - 动态轮换代理只保存一条 raw_proxy；
    - “生成运行表”会把同一条动态代理写入所有账号的 account_proxy_map.csv；
    - 旧的检测代理、构建代理池流程在界面中隐藏，避免继续按一账号一代理操作。
    """

    overwrite_accounts_requested = Signal(str)
    overwrite_proxies_requested = Signal(str)

    reload_csv_requested = Signal()

    test_proxies_requested = Signal()
    build_proxy_pool_requested = Signal()
    assign_proxies_requested = Signal()
    export_api_requested = Signal()
    stop_process_requested = Signal()

    import_api_requested = Signal()
    login_wqtg_accounts_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title_label = QLabel("API 批量工作台")
        self.title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("状态：准备就绪")
        self.status_label.setObjectName("DashboardStatusLabel")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.accounts_header_edit = QLineEdit(ACCOUNTS_HEADER_TEXT)
        self.accounts_header_edit.setReadOnly(True)
        self.accounts_header_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.accounts_header_edit.setToolTip("accounts.csv 第一行表头，已锁定不可编辑。")

        self.proxies_header_edit = QLineEdit(PROXIES_HEADER_TEXT)
        self.proxies_header_edit.setReadOnly(True)
        self.proxies_header_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.proxies_header_edit.setToolTip("动态轮换代理表头，已锁定不可编辑。")

        self.accounts_text_edit = QPlainTextEdit()
        self.accounts_text_edit.setPlaceholderText(
            "14255871436,US,profiles/14255871436,pending,https://accac.cc/xxx/GetHTML"
        )
        self.accounts_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.proxies_text_edit = QPlainTextEdit()
        self.proxies_text_edit.setPlaceholderText(
            "只填写一条动态轮换代理，例如：\nQg8Ajet4-res-th:GlVF6XC@proxy.as.ip2up.com:10235"
        )
        self.proxies_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.log_text_edit = QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setPlaceholderText("tgapipldc 工作台日志会显示在这里。")
        self.log_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.reload_csv_button = QPushButton("刷新 CSV")
        self.overwrite_accounts_button = QPushButton("覆盖 accounts")
        self.overwrite_proxies_button = QPushButton("保存动态代理")

        self.test_proxies_button = QPushButton("检测代理")
        self.build_proxy_pool_button = QPushButton("构建池")
        self.assign_proxies_button = QPushButton("生成运行表")
        self.export_api_button = QPushButton("获取 API")
        self.stop_process_button = QPushButton("停止")

        self.import_api_button = QPushButton("导入 API")
        self.login_wqtg_accounts_button = QPushButton("登录 WQTG")

        self._build_ui()
        self._connect_signals()

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

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(10)
        self.main_splitter.setObjectName("TgapipldcMainSplitter")
        root_layout.addWidget(self.main_splitter, 1)

        self.upper_splitter = QSplitter(Qt.Orientation.Vertical)
        self.upper_splitter.setChildrenCollapsible(False)
        self.upper_splitter.setHandleWidth(10)
        self.upper_splitter.setObjectName("TgapipldcUpperSplitter")

        self.csv_group = self._build_csv_group()
        self.action_group = self._build_action_group()
        self.log_group = self._build_log_group()

        self.upper_splitter.addWidget(self.csv_group)
        self.upper_splitter.addWidget(self.action_group)
        self.upper_splitter.setStretchFactor(0, 5)
        self.upper_splitter.setStretchFactor(1, 1)
        self.upper_splitter.setCollapsible(0, False)
        self.upper_splitter.setCollapsible(1, False)
        self.upper_splitter.setSizes([350, 104])

        self.main_splitter.addWidget(self.upper_splitter)
        self.main_splitter.addWidget(self.log_group)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([470, 230])

        self._style_widgets()

    def _build_csv_group(self) -> QFrame:
        group = QFrame()
        group.setObjectName("TgapipldcSectionFrame")
        group.setMinimumHeight(260)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title_label = QLabel("账号与动态轮换代理")
        title_label.setObjectName("TgapipldcSectionTitleLabel")

        title_row.addWidget(title_label, 1)
        title_row.addWidget(self.reload_csv_button, 0)
        title_row.addWidget(self.overwrite_accounts_button, 0)
        title_row.addWidget(self.overwrite_proxies_button, 0)

        layout.addLayout(title_row)

        hint_label = QLabel(
            "动态代理只配置一条。生成运行表后，每个账号仍使用自己的 profile_dir，但所有浏览器都从这条动态代理启动。"
        )
        hint_label.setWordWrap(True)
        hint_label.setObjectName("TgapipldcSmallLabel")
        layout.addWidget(hint_label)

        csv_splitter = QSplitter(Qt.Orientation.Horizontal)
        csv_splitter.setChildrenCollapsible(False)
        csv_splitter.setHandleWidth(8)
        csv_splitter.setObjectName("TgapipldcCsvSplitter")
        csv_splitter.addWidget(
            self._build_csv_card(
                title="accounts.csv",
                header_widget=self.accounts_header_edit,
                editor_widget=self.accounts_text_edit,
            )
        )
        csv_splitter.addWidget(
            self._build_csv_card(
                title="动态轮换代理",
                header_widget=self.proxies_header_edit,
                editor_widget=self.proxies_text_edit,
            )
        )
        csv_splitter.setStretchFactor(0, 1)
        csv_splitter.setStretchFactor(1, 1)
        csv_splitter.setSizes([480, 480])

        layout.addWidget(csv_splitter, 1)

        return group

    def _build_csv_card(
        self,
        title: str,
        header_widget: QLineEdit,
        editor_widget: QPlainTextEdit,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("TgapipldcCsvCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName("TgapipldcCsvTitleLabel")

        header_label = QLabel("锁定表头")
        header_label.setObjectName("TgapipldcSmallLabel")

        data_label = QLabel("数据行")
        data_label.setObjectName("TgapipldcSmallLabel")

        header_widget.setMinimumHeight(30)
        header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        editor_widget.setMinimumHeight(130)
        editor_widget.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        editor_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        editor_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        editor_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout.addWidget(title_label)
        layout.addSpacing(4)
        layout.addWidget(header_label)
        layout.addWidget(header_widget)
        layout.addSpacing(6)
        layout.addWidget(data_label)
        layout.addWidget(editor_widget, 1)

        return card

    def _build_action_group(self) -> QFrame:
        group = QFrame()
        group.setObjectName("TgapipldcSectionFrame")
        group.setMinimumHeight(86)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_label = QLabel("动态代理流程")
        title_label.setObjectName("TgapipldcSectionTitleLabel")
        layout.addWidget(title_label, 0)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        buttons = [
            self.test_proxies_button,
            self.build_proxy_pool_button,
            self.assign_proxies_button,
            self.export_api_button,
            self.stop_process_button,
            self.import_api_button,
            self.login_wqtg_accounts_button,
        ]

        for button in buttons:
            button_row.addWidget(button, 0)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        return group

    def _build_log_group(self) -> QFrame:
        group = QFrame()
        group.setObjectName("TgapipldcSectionFrame")
        group.setMinimumHeight(150)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        title_label = QLabel("运行日志")
        title_label.setObjectName("TgapipldcSectionTitleLabel")
        layout.addWidget(title_label, 0)

        self.log_text_edit.setMinimumHeight(120)
        self.log_text_edit.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.log_text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.log_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout.addWidget(self.log_text_edit, 1)

        return group

    def _style_widgets(self) -> None:
        self.setMinimumHeight(520)

        splitter_style = (
            "QSplitter::handle {"
            "background: #dbe3ef;"
            "border-radius: 4px;"
            "margin: 2px 18px;"
            "}"
            "QSplitter::handle:hover {"
            "background: #b9c7db;"
            "}"
        )

        self.main_splitter.setStyleSheet(splitter_style)
        self.upper_splitter.setStyleSheet(splitter_style)

        for splitter in self.findChildren(QSplitter):
            splitter.setStyleSheet(splitter_style)

        for editor in (
            self.accounts_text_edit,
            self.proxies_text_edit,
            self.log_text_edit,
        ):
            editor.setViewportMargins(0, 0, 0, 0)
            editor.document().setDocumentMargin(6)

        locked_header_style = (
            "QLineEdit {"
            "background: #f3f6fb;"
            "border: 1px solid #d7deea;"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "color: #334155;"
            "}"
        )
        self.accounts_header_edit.setStyleSheet(locked_header_style)
        self.proxies_header_edit.setStyleSheet(locked_header_style)

        csv_buttons = [
            self.reload_csv_button,
            self.overwrite_accounts_button,
            self.overwrite_proxies_button,
        ]
        for button in csv_buttons:
            button.setMinimumHeight(32)
            button.setMaximumHeight(34)
            button.setMinimumWidth(96)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.overwrite_accounts_button.setMinimumWidth(118)
        self.overwrite_proxies_button.setMinimumWidth(118)

        flow_button_sizes = {
            self.test_proxies_button: 82,
            self.build_proxy_pool_button: 76,
            self.assign_proxies_button: 96,
            self.export_api_button: 82,
            self.stop_process_button: 64,
            self.import_api_button: 82,
            self.login_wqtg_accounts_button: 96,
        }

        for button, width in flow_button_sizes.items():
            button.setMinimumHeight(30)
            button.setMaximumHeight(34)
            button.setMinimumWidth(width)
            button.setMaximumWidth(width + 12)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.test_proxies_button.setVisible(False)
        self.build_proxy_pool_button.setVisible(False)

        self.stop_process_button.setObjectName("DangerButton")
        self.stop_process_button.setEnabled(False)

    def _connect_signals(self) -> None:
        self.reload_csv_button.clicked.connect(self.reload_csv_requested.emit)

        self.overwrite_accounts_button.clicked.connect(
            lambda: self.overwrite_accounts_requested.emit(self.get_accounts_text())
        )
        self.overwrite_proxies_button.clicked.connect(
            lambda: self.overwrite_proxies_requested.emit(self.get_proxies_text())
        )

        self.test_proxies_button.clicked.connect(self.test_proxies_requested.emit)
        self.build_proxy_pool_button.clicked.connect(self.build_proxy_pool_requested.emit)
        self.assign_proxies_button.clicked.connect(self.assign_proxies_requested.emit)
        self.export_api_button.clicked.connect(self.export_api_requested.emit)
        self.stop_process_button.clicked.connect(self.stop_process_requested.emit)

        self.import_api_button.clicked.connect(self.import_api_requested.emit)
        self.login_wqtg_accounts_button.clicked.connect(
            self.login_wqtg_accounts_requested.emit
        )

    def get_accounts_text(self) -> str:
        return self._strip_locked_header(
            self.accounts_text_edit.toPlainText(),
            ACCOUNTS_HEADER_TEXT,
        )

    def set_accounts_text(self, text: str) -> None:
        self.accounts_text_edit.setPlainText(
            self._strip_locked_header(text, ACCOUNTS_HEADER_TEXT)
        )

    def get_proxies_text(self) -> str:
        return self._strip_locked_header(
            self.proxies_text_edit.toPlainText(),
            PROXIES_HEADER_TEXT,
        )

    def set_proxies_text(self, text: str) -> None:
        self.proxies_text_edit.setPlainText(
            self._strip_locked_header(text, PROXIES_HEADER_TEXT)
        )

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

        self.test_proxies_button.setEnabled(not is_running)
        self.build_proxy_pool_button.setEnabled(not is_running)
        self.assign_proxies_button.setEnabled(not is_running)
        self.export_api_button.setEnabled(not is_running)
        self.import_api_button.setEnabled(not is_running)
        self.login_wqtg_accounts_button.setEnabled(not is_running)

        self.stop_process_button.setEnabled(is_running)

        if is_running:
            self.set_status("运行中")
        else:
            self.set_status("准备就绪")

    @staticmethod
    def _strip_locked_header(text: str, header_text: str) -> str:
        raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = raw_text.split("\n")

        while lines and not lines[0].strip():
            lines.pop(0)

        if lines and lines[0].strip().lower() == header_text.strip().lower():
            lines.pop(0)

        return "\n".join(lines).strip()

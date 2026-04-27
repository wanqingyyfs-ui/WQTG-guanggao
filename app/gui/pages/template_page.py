from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    TemplateConfig,
    TEMPLATE_SEND_MODE_FORWARD,
    TEMPLATE_SEND_MODE_CLONE,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_ALBUM,
)


class TemplatePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.templates: list[TemplateConfig] = []

        # 顶部列表
        self.table = QTableWidget(0, 7)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        self.table.setMaximumHeight(16777215)
        self.table.setHorizontalHeaderLabels(
            ["模板名", "来源账号", "类型", "发送模式", "启用", "媒体数", "来源消息"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        # 左侧编辑区控件
        self.template_id_edit = QLineEdit()
        self.template_id_edit.setReadOnly(True)

        self.template_name_edit = QLineEdit()
        self.source_account_name_edit = QLineEdit()
        self.source_chat_id_edit = QLineEdit()
        self.source_chat_title_edit = QLineEdit()
        self.source_message_ids_edit = QLineEdit()
        self.created_at_edit = QLineEdit()
        self.created_at_edit.setReadOnly(True)

        self.message_type_combo = QComboBox()
        self.message_type_combo.addItem("text", TEMPLATE_MESSAGE_TYPE_TEXT)
        self.message_type_combo.addItem("photo", TEMPLATE_MESSAGE_TYPE_PHOTO)
        self.message_type_combo.addItem("album", TEMPLATE_MESSAGE_TYPE_ALBUM)

        self.send_mode_combo = QComboBox()
        self.send_mode_combo.addItem("forward", TEMPLATE_SEND_MODE_FORWARD)
        self.send_mode_combo.addItem("clone", TEMPLATE_SEND_MODE_CLONE)

        self.preview_text_edit = QTextEdit()
        self.raw_text_edit = QTextEdit()
        self.preview_text_edit.setMinimumHeight(130)
        self.raw_text_edit.setMinimumHeight(130)

        self.enabled_checkbox = QCheckBox("启用此模板")
        self.has_custom_emoji_checkbox = QCheckBox("包含 Telegram 自定义 emoji")
        self.has_custom_emoji_checkbox.setEnabled(False)
        self.has_media_checkbox = QCheckBox("包含媒体")
        self.has_media_checkbox.setEnabled(False)

        self.media_count_label = QLabel("0")
        self.preview_images_label = QLabel("当前版本暂未展示图片缩略图")
        self.preview_images_label.setWordWrap(True)

        # 统一给左侧输入框更大的最小宽度，避免被压瘪
        edit_min_width = 320
        for w in [
            self.template_id_edit,
            self.template_name_edit,
            self.source_account_name_edit,
            self.source_chat_id_edit,
            self.source_chat_title_edit,
            self.source_message_ids_edit,
            self.created_at_edit,
            self.message_type_combo,
            self.send_mode_combo,
        ]:
            w.setMinimumWidth(edit_min_width)
            w.setMinimumHeight(36)

        # 左侧模板编辑
        form_group = QGroupBox("模板编辑")
        form_group.setObjectName("templateFormGroup")
        form_group.setMinimumWidth(520)
        form_group.setMinimumHeight(760)

        form_layout = QFormLayout(form_group)
        form_layout.setHorizontalSpacing(18)
        form_layout.setVerticalSpacing(14)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.addRow("模板 ID：", self.template_id_edit)
        form_layout.addRow("模板名称：", self.template_name_edit)
        form_layout.addRow("来源账号：", self.source_account_name_edit)
        form_layout.addRow("来源 Chat ID：", self.source_chat_id_edit)
        form_layout.addRow("来源聊天标题：", self.source_chat_title_edit)
        form_layout.addRow("来源消息ID（,分隔）：", self.source_message_ids_edit)
        form_layout.addRow("消息类型：", self.message_type_combo)
        form_layout.addRow("发送模式：", self.send_mode_combo)
        form_layout.addRow("创建时间：", self.created_at_edit)
        form_layout.addRow("", self.enabled_checkbox)
        form_layout.addRow("", self.has_custom_emoji_checkbox)
        form_layout.addRow("", self.has_media_checkbox)

        # 左侧滚动容器：空间不够时滚动，不压缩
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        form_scroll.setWidget(form_group)
        form_scroll.setMinimumWidth(560)
        form_scroll.setMinimumHeight(430)

        # 右侧预览
        preview_group = QGroupBox("模板预览")
        preview_group.setObjectName("templatePreviewGroup")
        groupbox_title_style = """
        QGroupBox#templateFormGroup,
        QGroupBox#templatePreviewGroup {
            margin-top: 25px;
            padding-top: 22px;
        }

        QGroupBox#templateFormGroup::title,
        QGroupBox#templatePreviewGroup::title {
            subcontrol-origin: margin;
            left: 16px;
            padding: 2px 10px 2px 10px;
        }
        """

        form_group.setStyleSheet(groupbox_title_style)
        preview_group.setStyleSheet(groupbox_title_style)
        preview_layout = QGridLayout(preview_group)
        preview_layout.setHorizontalSpacing(18)
        preview_layout.setVerticalSpacing(14)
        preview_layout.addWidget(QLabel("预览摘要："), 0, 0)
        preview_layout.addWidget(self.preview_text_edit, 1, 0)
        preview_layout.addWidget(QLabel("完整原文："), 0, 1)
        preview_layout.addWidget(self.raw_text_edit, 1, 1)
        preview_layout.addWidget(QLabel("媒体数量："), 2, 0)
        preview_layout.addWidget(self.media_count_label, 2, 1)
        preview_layout.addWidget(QLabel("图片预览："), 3, 0)
        preview_layout.addWidget(self.preview_images_label, 3, 1)

        self.preview_text_edit.setReadOnly(False)
        self.raw_text_edit.setReadOnly(False)

        # 顶部区域
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_layout.addWidget(QLabel("模板列表"))

        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setMinimumHeight(180)
        table_scroll.setWidget(self.table)

        top_layout.addWidget(table_scroll)

        # 底部左右区域
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(18)
        bottom_layout.addWidget(form_scroll, 0)
        bottom_layout.addWidget(preview_group, 1)

        # 按钮
        self.add_button = QPushButton("新增模板")
        self.save_button = QPushButton("保存模板")
        self.delete_button = QPushButton("删除模板")
        self.refresh_button = QPushButton("刷新列表")

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.refresh_button)

        # 上下分割：只控制上下比例，不让你下面左侧再被莫名压扁
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("""
        QSplitter::handle {
            background-color: #e5e7eb;
            border-top: 1px solid #cbd5e1;
            border-bottom: 1px solid #cbd5e1;
        }
        QSplitter::handle:hover {
            background-color: #cbd5e1;
        }
        """)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([350, 430])

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(splitter)
        layout.addLayout(button_layout)

        self.table.itemSelectionChanged.connect(self.load_selected_template)

    def set_templates(self, templates: list[TemplateConfig]) -> None:
        self.templates = templates
        self.refresh_table()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.templates))
        for row, template in enumerate(self.templates):
            source_ids_text = ",".join(str(x) for x in template.source_message_ids)
            self.table.setItem(row, 0, QTableWidgetItem(template.template_name))
            self.table.setItem(row, 1, QTableWidgetItem(template.source_account_name))
            self.table.setItem(row, 2, QTableWidgetItem(template.message_type))
            self.table.setItem(row, 3, QTableWidgetItem(template.send_mode))
            self.table.setItem(row, 4, QTableWidgetItem("是" if template.enabled else "否"))
            self.table.setItem(row, 5, QTableWidgetItem(str(template.media_count)))
            self.table.setItem(row, 6, QTableWidgetItem(source_ids_text))

    def load_selected_template(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.templates):
            return

        template = self.templates[row]
        self.template_id_edit.setText(template.template_id)
        self.template_name_edit.setText(template.template_name)
        self.source_account_name_edit.setText(template.source_account_name)
        self.source_chat_id_edit.setText(str(template.source_chat_id))
        self.source_chat_title_edit.setText(template.source_chat_title)
        self.source_message_ids_edit.setText(",".join(str(x) for x in template.source_message_ids))
        self.created_at_edit.setText(template.created_at)

        message_type_index = self.message_type_combo.findData(template.message_type)
        if message_type_index >= 0:
            self.message_type_combo.setCurrentIndex(message_type_index)

        send_mode_index = self.send_mode_combo.findData(template.send_mode)
        if send_mode_index >= 0:
            self.send_mode_combo.setCurrentIndex(send_mode_index)

        self.preview_text_edit.setPlainText(template.preview_text)
        self.raw_text_edit.setPlainText(template.raw_text)
        self.enabled_checkbox.setChecked(template.enabled)
        self.has_custom_emoji_checkbox.setChecked(template.has_custom_emoji)
        self.has_media_checkbox.setChecked(template.has_media)
        self.media_count_label.setText(str(template.media_count))

        if template.preview_images:
            self.preview_images_label.setText("\n".join(template.preview_images))
        else:
            self.preview_images_label.setText("当前版本暂未生成本地缩略图缓存")

    def clear_form(self) -> None:
        self.template_id_edit.clear()
        self.template_name_edit.clear()
        self.source_account_name_edit.clear()
        self.source_chat_id_edit.clear()
        self.source_chat_title_edit.clear()
        self.source_message_ids_edit.clear()
        self.created_at_edit.clear()
        self.message_type_combo.setCurrentIndex(0)
        self.send_mode_combo.setCurrentIndex(0)
        self.preview_text_edit.clear()
        self.raw_text_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.has_custom_emoji_checkbox.setChecked(False)
        self.has_media_checkbox.setChecked(False)
        self.media_count_label.setText("0")
        self.preview_images_label.setText("当前版本暂未展示图片缩略图")

    def get_selected_row(self) -> int:
        return self.table.currentRow()

    def get_form_template(self) -> TemplateConfig:
        template_id = self.template_id_edit.text().strip()
        if not template_id:
            import uuid
            template_id = uuid.uuid4().hex

        source_message_ids = []
        raw_ids = self.source_message_ids_edit.text().strip()
        if raw_ids:
            for item in raw_ids.split(","):
                value = item.strip()
                if value:
                    source_message_ids.append(int(value))

        preview_text = self.preview_text_edit.toPlainText().strip()
        raw_text = self.raw_text_edit.toPlainText().strip()

        return TemplateConfig(
            template_id=template_id,
            template_name=self.template_name_edit.text().strip(),
            source_account_name=self.source_account_name_edit.text().strip(),
            source_chat_id=int(self.source_chat_id_edit.text().strip() or "0"),
            source_chat_title=self.source_chat_title_edit.text().strip(),
            source_message_ids=source_message_ids,
            message_type=self.message_type_combo.currentData(),
            send_mode=self.send_mode_combo.currentData(),
            preview_text=preview_text,
            raw_text=raw_text,
            has_custom_emoji=self.has_custom_emoji_checkbox.isChecked(),
            has_media=self.has_media_checkbox.isChecked(),
            media_count=max(len(source_message_ids), 0),
            preview_images=[],
            enabled=self.enabled_checkbox.isChecked(),
            created_at=self.created_at_edit.text().strip(),
        )
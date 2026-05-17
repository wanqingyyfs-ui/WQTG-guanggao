from __future__ import annotations

import uuid

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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    TEMPLATE_MESSAGE_TYPE_ALBUM,
    TEMPLATE_MESSAGE_TYPE_PHOTO,
    TEMPLATE_MESSAGE_TYPE_TEXT,
    TEMPLATE_SEND_MODE_CLONE,
    TEMPLATE_SEND_MODE_FORWARD,
    TemplateConfig,
)
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    make_scroll_area,
    make_vertical_splitter,
    style_form_layout,
    style_group_box,
    style_table,
    style_text_editor,
)


class TemplatePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.templates: list[TemplateConfig] = []

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["模板名", "来源账号", "类型", "发送模式", "启用", "媒体数", "来源消息"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        style_table(self.table)

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
        style_text_editor(self.preview_text_edit, 190)
        style_text_editor(self.raw_text_edit, 190)

        self.enabled_checkbox = QCheckBox("启用此模板")
        self.has_custom_emoji_checkbox = QCheckBox("包含 Telegram 自定义 emoji")
        self.has_custom_emoji_checkbox.setEnabled(False)
        self.has_media_checkbox = QCheckBox("包含媒体")
        self.has_media_checkbox.setEnabled(False)

        self.media_count_label = QLabel("0")
        self.preview_images_label = QLabel("当前版本暂未展示图片缩略图")
        self.preview_images_label.setWordWrap(True)

        form_group = QGroupBox("模板配置")
        style_group_box(form_group)

        form_layout = QFormLayout(form_group)
        style_form_layout(form_layout)
        form_layout.addRow("模板 ID", self.template_id_edit)
        form_layout.addRow("模板名称", self.template_name_edit)
        form_layout.addRow("来源账号", self.source_account_name_edit)
        form_layout.addRow("来源 Chat ID", self.source_chat_id_edit)
        form_layout.addRow("来源聊天标题", self.source_chat_title_edit)
        form_layout.addRow("来源消息ID（,分隔）", self.source_message_ids_edit)
        form_layout.addRow("消息类型", self.message_type_combo)
        form_layout.addRow("发送模式", self.send_mode_combo)
        form_layout.addRow("创建时间", self.created_at_edit)
        form_layout.addRow("启用状态", self.enabled_checkbox)
        form_layout.addRow("自定义 emoji", self.has_custom_emoji_checkbox)
        form_layout.addRow("媒体状态", self.has_media_checkbox)

        apply_large_inputs(form_group)

        preview_group = QGroupBox("模板预览")
        style_group_box(preview_group)

        preview_layout = QGridLayout(preview_group)
        preview_layout.setContentsMargins(24, 26, 24, 24)
        preview_layout.setHorizontalSpacing(18)
        preview_layout.setVerticalSpacing(16)
        preview_layout.addWidget(QLabel("预览摘要"), 0, 0)
        preview_layout.addWidget(QLabel("完整原文"), 0, 1)
        preview_layout.addWidget(self.preview_text_edit, 1, 0)
        preview_layout.addWidget(self.raw_text_edit, 1, 1)
        preview_layout.addWidget(QLabel("媒体数量"), 2, 0)
        preview_layout.addWidget(self.media_count_label, 2, 1)
        preview_layout.addWidget(QLabel("图片预览"), 3, 0)
        preview_layout.addWidget(self.preview_images_label, 3, 1)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)
        bottom_splitter.setHandleWidth(10)
        bottom_splitter.addWidget(make_scroll_area(form_group, minimum_height=330))
        bottom_splitter.addWidget(make_scroll_area(preview_group, minimum_height=330))
        bottom_splitter.setStretchFactor(0, 4)
        bottom_splitter.setStretchFactor(1, 5)
        bottom_splitter.setSizes([520, 640])

        bottom_splitter.setStyleSheet("""
        QSplitter::handle {
            background-color: #d7dde7;
            border-left: 1px solid #b8c2d1;
            border-right: 1px solid #b8c2d1;
            margin: 80px 2px 80px 2px;
            border-radius: 3px;
        }

        QSplitter::handle:hover {
            background-color: #9fb0c7;
        }

        QSplitter::handle:pressed {
            background-color: #7387a3;
        }
        """)

        self.add_button = QPushButton("新增模板")
        self.save_button = QPushButton("保存模板")
        self.delete_button = QPushButton("删除模板")
        self.refresh_button = QPushButton("刷新列表")

        button_bar = QWidget()
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(14)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.refresh_button)

        table_group = QGroupBox("模板列表")
        style_group_box(table_group)

        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(18, 20, 18, 18)
        table_layout.addWidget(self.table)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_layout.addWidget(QLabel("模板管理"))
        top_layout.addWidget(make_scroll_area(table_group, minimum_height=240), 1)

        bottom_content = QWidget()
        bottom_layout = QVBoxLayout(bottom_content)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(bottom_splitter, 1)
        bottom_layout.addWidget(button_bar)

        bottom_scroll = make_scroll_area(bottom_content, minimum_height=360)

        splitter = make_vertical_splitter(
            top_widget=top_widget,
            bottom_widget=bottom_scroll,
            sizes=[330, 560],
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(self.load_selected_template)

    def set_templates(self, templates: list[TemplateConfig]) -> None:
        self.templates = list(templates)
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
        self.source_message_ids_edit.setText(
            ",".join(str(x) for x in template.source_message_ids)
        )
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
        self.table.clearSelection()

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
            template_id = uuid.uuid4().hex

        source_message_ids: list[int] = []
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
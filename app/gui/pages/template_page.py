from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "模板名",
                "来源账号",
                "来源 Chat ID",
                "类型",
                "发送模式",
                "启用",
                "媒体数",
                "来源消息",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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
        self.media_count_label.setMinimumHeight(36)
        self.media_count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

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
        form_layout.addRow("来源消息 ID（英文逗号分隔）", self.source_message_ids_edit)
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
        self.message_type_combo.currentIndexChanged.connect(
            self.on_message_type_changed
        )
        self.source_message_ids_edit.textChanged.connect(
            self.update_media_state_preview
        )

        self.clear_form()

    def set_templates(self, templates: list[TemplateConfig]) -> None:
        self.templates = list(templates)
        self.refresh_table()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.templates))

        for row, template in enumerate(self.templates):
            source_ids_text = ",".join(
                str(message_id)
                for message_id in self._normalize_message_ids(
                    template.source_message_ids
                )
            )

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(str(template.template_name or "")),
            )
            self.table.setItem(
                row,
                1,
                QTableWidgetItem(str(template.source_account_name or "")),
            )
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(str(template.source_chat_id or "")),
            )
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(str(template.message_type or "")),
            )
            self.table.setItem(
                row,
                4,
                QTableWidgetItem(str(template.send_mode or "")),
            )
            self.table.setItem(
                row,
                5,
                QTableWidgetItem("是" if template.enabled else "否"),
            )
            self.table.setItem(
                row,
                6,
                QTableWidgetItem(str(self._template_media_count(template))),
            )
            self.table.setItem(row, 7, QTableWidgetItem(source_ids_text))

    def load_selected_template(self) -> None:
        row = self.table.currentRow()

        if row < 0 or row >= len(self.templates):
            return

        template = self.templates[row]
        source_message_ids = self._normalize_message_ids(template.source_message_ids)

        self.template_id_edit.setText(str(template.template_id or ""))
        self.template_name_edit.setText(str(template.template_name or ""))
        self.source_account_name_edit.setText(str(template.source_account_name or ""))
        self.source_chat_id_edit.setText(str(template.source_chat_id or ""))
        self.source_chat_title_edit.setText(str(template.source_chat_title or ""))
        self.source_message_ids_edit.setText(
            ",".join(str(message_id) for message_id in source_message_ids)
        )
        self.created_at_edit.setText(str(template.created_at or ""))

        self._restore_combo_value(
            self.message_type_combo,
            self._safe_message_type(template.message_type),
        )
        self._restore_combo_value(
            self.send_mode_combo,
            TEMPLATE_SEND_MODE_FORWARD,
        )

        self.preview_text_edit.setPlainText(str(template.preview_text or ""))
        self.raw_text_edit.setPlainText(str(template.raw_text or ""))
        self.enabled_checkbox.setChecked(bool(template.enabled))
        self.has_custom_emoji_checkbox.setChecked(bool(template.has_custom_emoji))
        self.has_media_checkbox.setChecked(bool(template.has_media))
        self.media_count_label.setText(str(self._template_media_count(template)))

        if template.preview_images:
            self.preview_images_label.setText(
                "\n".join(str(item) for item in template.preview_images)
            )
        else:
            self.preview_images_label.setText("当前版本暂未生成本地缩略图缓存")

        self.update_media_state_preview()

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

        self.update_media_state_preview()

    def get_selected_row(self) -> int:
        return self.table.currentRow()

    def get_form_template(self) -> TemplateConfig:
        selected_template = self._selected_template()

        template_id = self.template_id_edit.text().strip()
        if not template_id:
            template_id = uuid.uuid4().hex

        template_name = self.template_name_edit.text().strip()
        source_account_name = self.source_account_name_edit.text().strip()
        source_chat_id = self._parse_chat_id(self.source_chat_id_edit.text())
        source_message_ids = self._parse_message_ids(
            self.source_message_ids_edit.text()
        )

        message_type = self._safe_message_type(self.message_type_combo.currentData())
        send_mode = TEMPLATE_SEND_MODE_FORWARD

        raw_text = self.raw_text_edit.toPlainText().strip()
        preview_text = self.preview_text_edit.toPlainText().strip()

        if not preview_text and raw_text:
            preview_text = raw_text[:80]

        if not raw_text and preview_text:
            raw_text = preview_text

        has_media = message_type in {
            TEMPLATE_MESSAGE_TYPE_PHOTO,
            TEMPLATE_MESSAGE_TYPE_ALBUM,
        }

        media_count = self._media_count_from_type_and_ids(
            message_type=message_type,
            source_message_ids=source_message_ids,
        )

        preview_images = []
        if selected_template is not None:
            preview_images = [
                str(item)
                for item in selected_template.preview_images
                if str(item).strip()
            ]

        created_at = self.created_at_edit.text().strip()
        if not created_at:
            created_at = datetime.now().isoformat(timespec="seconds")

        return TemplateConfig(
            template_id=template_id,
            template_name=template_name,
            source_account_name=source_account_name,
            source_chat_id=source_chat_id,
            source_chat_title=self.source_chat_title_edit.text().strip(),
            source_message_ids=source_message_ids,
            message_type=message_type,
            send_mode=send_mode,
            preview_text=preview_text,
            raw_text=raw_text,
            has_custom_emoji=(
                selected_template.has_custom_emoji
                if selected_template is not None
                else False
            ),
            has_media=has_media,
            media_count=media_count,
            preview_images=preview_images,
            enabled=self.enabled_checkbox.isChecked(),
            created_at=created_at,
        )

    def on_message_type_changed(self) -> None:
        self.update_media_state_preview()

    def update_media_state_preview(self) -> None:
        message_type = self._safe_message_type(self.message_type_combo.currentData())

        try:
            source_message_ids = self._parse_message_ids(
                self.source_message_ids_edit.text(),
                allow_empty=True,
            )
        except ValueError:
            source_message_ids = []

        has_media = message_type in {
            TEMPLATE_MESSAGE_TYPE_PHOTO,
            TEMPLATE_MESSAGE_TYPE_ALBUM,
        }
        media_count = self._media_count_from_type_and_ids(
            message_type=message_type,
            source_message_ids=source_message_ids,
        )

        self.has_media_checkbox.setChecked(has_media)
        self.media_count_label.setText(str(media_count))

    def _selected_template(self) -> TemplateConfig | None:
        row = self.get_selected_row()

        if 0 <= row < len(self.templates):
            return self.templates[row]

        return None

    @staticmethod
    def _restore_combo_value(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _safe_message_type(value: Any) -> str:
        message_type = str(value or TEMPLATE_MESSAGE_TYPE_TEXT).strip()

        if message_type not in {
            TEMPLATE_MESSAGE_TYPE_TEXT,
            TEMPLATE_MESSAGE_TYPE_PHOTO,
            TEMPLATE_MESSAGE_TYPE_ALBUM,
        }:
            return TEMPLATE_MESSAGE_TYPE_TEXT

        return message_type

    @staticmethod
    def _parse_chat_id(value: Any) -> int:
        raw_text = str(value or "").strip()

        if not raw_text:
            return 0

        try:
            return int(raw_text)
        except ValueError as exc:
            raise ValueError("来源 Chat ID 必须是数字") from exc

    @classmethod
    def _parse_message_ids(
        cls,
        value: Any,
        allow_empty: bool = False,
    ) -> list[int]:
        raw_text = str(value or "").replace("，", ",").strip()

        if not raw_text:
            if allow_empty:
                return []
            raise ValueError("来源消息 ID 列表不能为空")

        result: list[int] = []

        for raw_item in raw_text.split(","):
            item = raw_item.strip()

            if not item:
                continue

            try:
                message_id = int(item)
            except ValueError as exc:
                raise ValueError(f"来源消息 ID 必须是数字: {item}") from exc

            if message_id <= 0:
                raise ValueError(f"来源消息 ID 必须大于 0: {message_id}")

            if message_id not in result:
                result.append(message_id)

        if not result and not allow_empty:
            raise ValueError("来源消息 ID 列表不能为空")

        return result

    @classmethod
    def _normalize_message_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []

        if isinstance(value, int):
            raw_items = [value]
        elif isinstance(value, str):
            raw_items = value.replace("，", ",").split(",")
        elif isinstance(value, list | tuple | set):
            raw_items = list(value)
        else:
            return []

        result: list[int] = []

        for item in raw_items:
            try:
                message_id = int(str(item).strip())
            except (TypeError, ValueError):
                continue

            if message_id > 0 and message_id not in result:
                result.append(message_id)

        return result

    @staticmethod
    def _media_count_from_type_and_ids(
        message_type: str,
        source_message_ids: list[int],
    ) -> int:
        if message_type == TEMPLATE_MESSAGE_TYPE_TEXT:
            return 0

        if message_type == TEMPLATE_MESSAGE_TYPE_PHOTO:
            return 1 if source_message_ids else 0

        if message_type == TEMPLATE_MESSAGE_TYPE_ALBUM:
            return len(source_message_ids)

        return 0

    def _template_media_count(self, template: TemplateConfig) -> int:
        message_type = self._safe_message_type(template.message_type)
        source_message_ids = self._normalize_message_ids(template.source_message_ids)

        calculated_count = self._media_count_from_type_and_ids(
            message_type=message_type,
            source_message_ids=source_message_ids,
        )

        if calculated_count:
            return calculated_count

        try:
            return max(0, int(template.media_count))
        except (TypeError, ValueError):
            return 0
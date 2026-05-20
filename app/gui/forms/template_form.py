from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import TemplateConfig
from app.gui.pages.layout_utils import (
    apply_large_inputs,
    style_form_layout,
    style_text_editor,
)


class TemplateForm(QWidget):
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_template: TemplateConfig | None = None

        self.template_name_edit = QLineEdit()
        self.template_name_edit.setPlaceholderText("模板名称")

        self.enabled_checkbox = QCheckBox("启用此模板")

        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("备注")
        style_text_editor(self.remark_edit, 160)

        self.info_edit = QPlainTextEdit()
        self.info_edit.setReadOnly(True)
        style_text_editor(self.info_edit, 180)

        self.save_button = QPushButton("保存")

        self._build_ui()
        self.save_button.clicked.connect(self.save_requested.emit)
        self.clear_form()

    def _build_ui(self) -> None:
        form = QFormLayout()
        style_form_layout(form)
        form.addRow("模板名称：", self.template_name_edit)
        form.addRow("启用状态：", self.enabled_checkbox)
        form.addRow("备注：", self.remark_edit)
        form.addRow("只读信息：", self.info_edit)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addLayout(button_layout)
        layout.addStretch(1)

        apply_large_inputs(self)

    def load_template(self, template: TemplateConfig) -> None:
        self._current_template = template
        self.template_name_edit.setText(str(template.template_name or ""))
        self.enabled_checkbox.setChecked(bool(template.enabled))
        self.remark_edit.setPlainText(str(getattr(template, "remark", "") or ""))
        self.info_edit.setPlainText(self._build_info_text(template))

    def clear_form(self) -> None:
        self._current_template = None
        self.template_name_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.remark_edit.clear()
        self.info_edit.setPlainText("请先从模板列表选择一个模板。")

    def get_form_template(self) -> TemplateConfig:
        if self._current_template is None:
            raise ValueError("请先选择一个模板")

        old = self._current_template

        return TemplateConfig(
            template_id=old.template_id,
            template_name=self.template_name_edit.text().strip(),
            source_account_name=old.source_account_name,
            source_chat_id=old.source_chat_id,
            source_chat_title=old.source_chat_title,
            source_message_ids=list(old.source_message_ids),
            message_type=old.message_type,
            send_mode=old.send_mode,
            preview_text=old.preview_text,
            raw_text=old.raw_text,
            has_custom_emoji=old.has_custom_emoji,
            has_media=old.has_media,
            media_count=old.media_count,
            preview_images=list(old.preview_images),
            enabled=self.enabled_checkbox.isChecked(),
            created_at=old.created_at,
            remark=self.remark_edit.toPlainText().strip(),
        )

    @staticmethod
    def _build_info_text(template: TemplateConfig) -> str:
        source_ids = ",".join(str(item) for item in template.source_message_ids)
        return (
            f"模板 ID：{template.template_id}\n"
            f"来源账号：{template.source_account_name}\n"
            f"来源 Chat ID：{template.source_chat_id}\n"
            f"来源标题：{template.source_chat_title}\n"
            f"来源消息 ID：{source_ids}\n"
            f"消息类型：{template.message_type}\n"
            f"发送模式：{template.send_mode}\n"
            f"媒体数量：{template.media_count}\n"
            f"创建时间：{template.created_at}\n\n"
            "以上字段由素材监听生成，当前表单只允许修改模板名称、启用状态和备注。"
        )

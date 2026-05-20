from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import TemplateConfig
from app.gui.pages.layout_utils import (
    apply_large_inputs,
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
        style_text_editor(self.remark_edit, 120)

        self.save_button = QPushButton("保存")
        self.save_button.setEnabled(False)

        self._build_ui()
        self.save_button.clicked.connect(self.save_requested.emit)
        self.clear_form()

    def _build_ui(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_labeled_widget(grid, 0, 0, "模板名称：", self.template_name_edit)
        grid.addWidget(self.enabled_checkbox, 0, 2, 1, 2)

        remark_label = QLabel("备注：")
        remark_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(remark_label, 1, 0)
        grid.addWidget(self.remark_edit, 1, 1, 1, 3)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(grid)
        layout.addLayout(button_layout)
        layout.addStretch(1)

        apply_large_inputs(self)

    @staticmethod
    def _add_labeled_widget(
        grid: QGridLayout,
        row: int,
        label_column: int,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, label_column)
        grid.addWidget(widget, row, label_column + 1)

    def load_template(self, template: TemplateConfig) -> None:
        self._current_template = template
        self.template_name_edit.setText(str(template.template_name or ""))
        self.enabled_checkbox.setChecked(bool(template.enabled))
        self.remark_edit.setPlainText(str(getattr(template, "remark", "") or ""))
        self.save_button.setEnabled(True)

    def clear_form(self) -> None:
        self._current_template = None
        self.template_name_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.remark_edit.clear()
        self.save_button.setEnabled(False)

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

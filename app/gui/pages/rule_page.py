from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
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
    QSizePolicy,
)

from app.core.models import (
    RuleConfig,
    RULE_TYPE_KEYWORD,
    RULE_TYPE_FIRST_CONTACT,
    REPLY_MODE_TEXT,
    REPLY_MODE_TEMPLATE,
)
from app.core.utils import split_keywords_text, keywords_to_text


class RulePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: list[RuleConfig] = []
        self.template_items: list[tuple[str, str]] = []

        # =========================
        # 顶部规则列表
        # =========================
        self.table = QTableWidget(0, 5)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(180)
        self.table.setMaximumHeight(16777215)
        self.table.setHorizontalHeaderLabels(["规则名", "类型", "回复模式", "启用", "说明"])
        self.table.horizontalHeader().setStretchLastSection(True)

        # =========================
        # 编辑区控件
        # =========================
        self.rule_name_edit = QLineEdit()

        self.rule_type_combo = QComboBox()
        self.rule_type_combo.addItem("关键词规则", RULE_TYPE_KEYWORD)
        self.rule_type_combo.addItem("首次接待规则", RULE_TYPE_FIRST_CONTACT)

        self.trigger_name_combo = QComboBox()
        self.trigger_name_combo.addItem("welcome", "welcome")
        self.trigger_name_combo.addItem("business_hours", "business_hours")

        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["contains", "exact", "regex"])

        self.reply_mode_combo = QComboBox()
        self.reply_mode_combo.addItem("文本回复", REPLY_MODE_TEXT)
        self.reply_mode_combo.addItem("模板回复", REPLY_MODE_TEMPLATE)

        self.template_combo = QComboBox()
        self.template_combo.addItem("未选择模板", "")

        self.keywords_edit = QLineEdit()

        self.reply_text_edit = QTextEdit()
        self.reply_text_edit.setMinimumHeight(150)
        self.reply_text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.enabled_checkbox = QCheckBox("启用此规则")

        self.add_button = QPushButton("新增规则")
        self.insert_button = QPushButton("添加规则")
        self.save_button = QPushButton("保存规则")
        self.delete_button = QPushButton("删除规则")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")

        self.is_new_mode = False

        self._setup_editor_widget_sizes()

        # =========================
        # 下方表单内容区（可滚动）
        # =========================
        form_content = QWidget()
        form_content.setMinimumHeight(760)
        form_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )

        form_grid = QGridLayout(form_content)
        form_grid.setContentsMargins(28, 24, 28, 24)
        form_grid.setHorizontalSpacing(22)
        form_grid.setVerticalSpacing(16)

        # label 样式统一
        self._add_form_row(form_grid, 0, "规则名称：", self.rule_name_edit)
        self._add_form_row(form_grid, 1, "规则类型：", self.rule_type_combo)
        self._add_form_row(form_grid, 2, "首次接待类型：", self.trigger_name_combo)
        self._add_form_row(form_grid, 3, "匹配方式：", self.match_type_combo)
        self._add_form_row(form_grid, 4, "回复模式：", self.reply_mode_combo)
        self._add_form_row(form_grid, 5, "绑定模板：", self.template_combo)
        self._add_form_row(form_grid, 6, "关键词（英文逗号分隔）：", self.keywords_edit)

        reply_label = QLabel("回复内容：")
        reply_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form_grid.addWidget(reply_label, 7, 0)
        form_grid.addWidget(self.reply_text_edit, 7, 1)

        # 复选框单独一行，绝不和 QTextEdit 重叠
        checkbox_row = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_row)
        checkbox_layout.setContentsMargins(0, 6, 0, 0)
        checkbox_layout.setSpacing(0)
        checkbox_layout.addWidget(self.enabled_checkbox)
        checkbox_layout.addStretch()

        empty_label = QLabel("")
        form_grid.addWidget(empty_label, 8, 0)
        form_grid.addWidget(checkbox_row, 8, 1)

        form_grid.setColumnStretch(0, 0)
        form_grid.setColumnStretch(1, 1)

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.form_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.form_scroll.setMinimumHeight(420)
        self.form_scroll.setWidget(form_content)

        # =========================
        # 按钮区（固定底部，不参与滚动）
        # =========================
        button_bar = QWidget()
        button_bar.setMinimumHeight(72)
        button_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(12, 10, 12, 10)
        button_layout.setSpacing(12)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.insert_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)

        # =========================
        # 上半区
        # =========================
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)


        title_label = QLabel("规则列表（从上到下就是匹配与发送顺序）")
        top_layout.addWidget(title_label)

        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setMinimumHeight(150)
        table_scroll.setWidget(self.table)

        top_layout.addWidget(table_scroll)

        # =========================
        # 下半区
        # =========================
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)
        bottom_layout.addWidget(self.form_scroll, 1)
        bottom_layout.addWidget(button_bar, 0)

        # =========================
        # 分割区
        # =========================
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
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([260, 560])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(splitter)

        # 信号
        self.table.itemSelectionChanged.connect(self.load_selected_rule)
        self.rule_type_combo.currentIndexChanged.connect(self.update_visibility)
        self.reply_mode_combo.currentIndexChanged.connect(self.update_visibility)

        self.update_visibility()

    def _setup_editor_widget_sizes(self) -> None:
        editor_widgets = [
            self.rule_name_edit,
            self.rule_type_combo,
            self.trigger_name_combo,
            self.match_type_combo,
            self.reply_mode_combo,
            self.template_combo,
            self.keywords_edit,
        ]

        for widget in editor_widgets:
            widget.setMinimumWidth(420)
            widget.setMinimumHeight(42)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _add_form_row(self, grid: QGridLayout, row: int, label_text: str, field_widget: QWidget) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label, row, 0)
        grid.addWidget(field_widget, row, 1)

    def set_templates(self, templates) -> None:
        current_template_id = self.template_combo.currentData()
        self.template_combo.clear()
        self.template_combo.addItem("未选择模板", "")
        self.template_items = []

        for template in templates:
            label = template.template_name or template.template_id
            self.template_combo.addItem(label, template.template_id)
            self.template_items.append((template.template_id, label))

        index = self.template_combo.findData(current_template_id)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)

    def set_rules(self, rules: list[RuleConfig]) -> None:
        self.rules = rules
        self.refresh_table()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.rules))
        for row, rule in enumerate(self.rules):
            if rule.rule_type == RULE_TYPE_FIRST_CONTACT:
                desc = rule.trigger_name or "first_contact"
                type_name = "首次接待"
            else:
                desc = ",".join(rule.keywords)
                type_name = "关键词"

            reply_mode_name = "模板" if rule.reply_mode == REPLY_MODE_TEMPLATE else "文本"

            self.table.setItem(row, 0, QTableWidgetItem(rule.rule_name))
            self.table.setItem(row, 1, QTableWidgetItem(type_name))
            self.table.setItem(row, 2, QTableWidgetItem(reply_mode_name))
            self.table.setItem(row, 3, QTableWidgetItem("是" if rule.enabled else "否"))
            self.table.setItem(row, 4, QTableWidgetItem(desc))

    def update_visibility(self) -> None:
        rule_type = self.rule_type_combo.currentData()
        reply_mode = self.reply_mode_combo.currentData()

        is_keyword = rule_type == RULE_TYPE_KEYWORD
        is_template = reply_mode == REPLY_MODE_TEMPLATE

        self.trigger_name_combo.setEnabled(not is_keyword)
        self.match_type_combo.setEnabled(is_keyword)
        self.keywords_edit.setEnabled(is_keyword)

        self.template_combo.setEnabled(is_template)
        self.reply_text_edit.setEnabled(not is_template)

    def load_selected_rule(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rules):
            return

        self.is_new_mode = False
        rule = self.rules[row]
        self.rule_name_edit.setText(rule.rule_name)

        rule_type_index = self.rule_type_combo.findData(rule.rule_type)
        if rule_type_index >= 0:
            self.rule_type_combo.setCurrentIndex(rule_type_index)

        trigger_index = self.trigger_name_combo.findData(rule.trigger_name)
        if trigger_index >= 0:
            self.trigger_name_combo.setCurrentIndex(trigger_index)

        match_index = self.match_type_combo.findText(rule.match_type)
        if match_index >= 0:
            self.match_type_combo.setCurrentIndex(match_index)

        reply_mode_index = self.reply_mode_combo.findData(rule.reply_mode)
        if reply_mode_index >= 0:
            self.reply_mode_combo.setCurrentIndex(reply_mode_index)

        template_index = self.template_combo.findData(rule.template_id)
        if template_index >= 0:
            self.template_combo.setCurrentIndex(template_index)
        else:
            self.template_combo.setCurrentIndex(0)

        self.keywords_edit.setText(keywords_to_text(rule.keywords))
        self.reply_text_edit.setPlainText(rule.reply_text)
        self.enabled_checkbox.setChecked(rule.enabled)

        self.update_visibility()
        self.is_new_mode = False

    def clear_form(self) -> None:
        self.rule_name_edit.clear()
        self.rule_type_combo.setCurrentIndex(0)
        self.trigger_name_combo.setCurrentIndex(0)
        self.match_type_combo.setCurrentIndex(0)
        self.reply_mode_combo.setCurrentIndex(0)
        self.template_combo.setCurrentIndex(0)
        self.keywords_edit.clear()
        self.reply_text_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.update_visibility()

    def begin_add_mode(self) -> None:
        self.table.clearSelection()
        self.clear_form()
        self.is_new_mode = True

    def get_form_rule(self) -> RuleConfig:
        rule_type = self.rule_type_combo.currentData()
        reply_mode = self.reply_mode_combo.currentData()

        return RuleConfig(
            rule_name=self.rule_name_edit.text().strip(),
            rule_type=rule_type,
            trigger_name=self.trigger_name_combo.currentData() if rule_type == RULE_TYPE_FIRST_CONTACT else "",
            keywords=split_keywords_text(self.keywords_edit.text()) if rule_type == RULE_TYPE_KEYWORD else [],
            reply_text=self.reply_text_edit.toPlainText().strip(),
            match_type=self.match_type_combo.currentText().strip(),
            enabled=self.enabled_checkbox.isChecked(),
            reply_mode=reply_mode,
            template_id=self.template_combo.currentData() if reply_mode == REPLY_MODE_TEMPLATE else "",
        )

    def get_selected_row(self) -> int:
        return self.table.currentRow()
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.gui.pages.layout_utils import (
    HORIZONTAL_SPLITTER_QSS,
    apply_large_inputs,
    style_list_widget,
    style_text_editor,
)


class NoisePage(QWidget):
    """
    噪音池页面。

    最终规则：
    - 不自动保存。
    - 增删改排序后标记为“未保存”。
    - 只有点击“保存”才写入 noise_pool.json。
    - 允许重复内容；保存时只去掉空白内容。
    """

    def __init__(self, runtime_service, parent=None):
        super().__init__(parent)

        self.runtime = runtime_service
        self.noise_pool: list[str] = []
        self._loading = False
        self._dirty = False
        self._last_error_text = ""

        self._build_ui()
        self.reload_from_runtime()

        if hasattr(self.runtime, "scheduler_status_changed"):
            self.runtime.scheduler_status_changed.connect(
                self._on_scheduler_status_changed
            )

        if hasattr(self.runtime, "noise_pool_changed"):
            self.runtime.noise_pool_changed.connect(self._on_runtime_noise_pool_changed)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(12)

        title_label = QLabel("噪音配置")
        title_label.setObjectName("PageTitleLabel")

        self.status_label = QLabel("")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.save_button = QPushButton("保存噪音池")
        self.save_button.clicked.connect(self.save_now)

        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        title_layout.addWidget(self.status_label)
        title_layout.addWidget(self.save_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.setStyleSheet(HORIZONTAL_SPLITTER_QSS)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([460, 720])

        root_layout.addLayout(title_layout)
        root_layout.addWidget(splitter, 1)

        apply_large_inputs(self)

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        hint_label = QLabel(
            "命中噪音概率时，会从这里随机选择一条文本发送。重复添加同一内容可以提高它的随机权重。"
        )
        hint_label.setWordWrap(True)

        self.count_label = QLabel("共 0 条")

        self.noise_list = QListWidget()
        style_list_widget(self.noise_list, min_height=420)
        self.noise_list.currentRowChanged.connect(self._on_current_row_changed)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.add_button = QPushButton("新增")
        self.delete_button = QPushButton("删除")
        self.move_up_button = QPushButton("上移")
        self.move_down_button = QPushButton("下移")

        self.add_button.clicked.connect(self.add_item)
        self.delete_button.clicked.connect(self.delete_current_item)
        self.move_up_button.clicked.connect(self.move_current_item_up)
        self.move_down_button.clicked.connect(self.move_current_item_down)

        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.move_up_button)
        button_layout.addWidget(self.move_down_button)

        layout.addWidget(hint_label)
        layout.addWidget(self.count_label)
        layout.addWidget(self.noise_list, 1)
        layout.addLayout(button_layout)

        return widget

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(10)

        editor_title = QLabel("当前噪音内容")
        editor_title.setObjectName("SectionTitleLabel")

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在这里输入噪音文本，可以包含多行。")
        style_text_editor(self.editor, min_height=420)
        self.editor.textChanged.connect(self._on_editor_text_changed)

        helper_label = QLabel("保存时会自动丢弃空白项，但不会去重。")
        helper_label.setWordWrap(True)

        layout.addWidget(editor_title)
        layout.addWidget(self.editor, 1)
        layout.addWidget(helper_label)

        return widget

    def reload_from_runtime(self) -> None:
        self._loading = True
        try:
            service = getattr(self.runtime, "noise_pool_service", None)
            if service is None:
                self.noise_pool = list(getattr(self.runtime, "noise_pool", []) or [])
            else:
                self.noise_pool = service.get_all()

            self._dirty = False
            self._refresh_list()
            self._set_status("已加载，未修改")
            self._last_error_text = ""
        except Exception as exc:
            self._set_error(f"加载失败：{exc}")
            QMessageBox.critical(self, "加载噪音池失败", str(exc))
        finally:
            self._loading = False
            self._update_running_state()

    def _on_runtime_noise_pool_changed(self) -> None:
        if not self._dirty:
            self.reload_from_runtime()

    def _refresh_list(self, current_row: int | None = None) -> None:
        self.noise_list.clear()

        for index, text in enumerate(self.noise_pool):
            item = QListWidgetItem(f"{index + 1}. {self._preview_text(text)}")
            item.setData(Qt.ItemDataRole.UserRole, text)
            self.noise_list.addItem(item)

        self.count_label.setText(f"共 {len(self.noise_pool)} 条")

        if not self.noise_pool:
            self.editor.clear()
            self.editor.setEnabled(False)
            self._update_buttons()
            return

        self.editor.setEnabled(True)

        if current_row is None:
            current_row = min(max(0, self.noise_list.currentRow()), len(self.noise_pool) - 1)

        current_row = min(max(0, current_row), len(self.noise_pool) - 1)
        self.noise_list.setCurrentRow(current_row)
        self._update_buttons()

    @staticmethod
    def _preview_text(text: str) -> str:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return "空内容"
        return normalized[:60] + "..." if len(normalized) > 60 else normalized

    def _on_current_row_changed(self, row: int) -> None:
        self._loading = True
        try:
            if row < 0 or row >= len(self.noise_pool):
                self.editor.clear()
                self.editor.setEnabled(False)
                return

            self.editor.setEnabled(True)
            self.editor.setPlainText(self.noise_pool[row])
        finally:
            self._loading = False
            self._update_buttons()

    def _on_editor_text_changed(self) -> None:
        if self._loading:
            return

        row = self.noise_list.currentRow()
        if row < 0 or row >= len(self.noise_pool):
            return

        self.noise_pool[row] = self.editor.toPlainText()
        self._mark_dirty()
        self._refresh_list(current_row=row)

    def add_item(self) -> None:
        if not self._can_edit_with_message():
            return

        self.noise_pool.append("")
        self._mark_dirty()
        self._refresh_list(current_row=len(self.noise_pool) - 1)
        self.editor.setFocus()

    def delete_current_item(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()
        if row < 0 or row >= len(self.noise_pool):
            QMessageBox.information(self, "提示", "请先选择要删除的噪音内容")
            return

        self.noise_pool.pop(row)
        self._mark_dirty()
        self._refresh_list(current_row=min(row, len(self.noise_pool) - 1))

    def move_current_item_up(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()
        if row <= 0 or row >= len(self.noise_pool):
            return

        self.noise_pool[row - 1], self.noise_pool[row] = self.noise_pool[row], self.noise_pool[row - 1]
        self._mark_dirty()
        self._refresh_list(current_row=row - 1)

    def move_current_item_down(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()
        if row < 0 or row >= len(self.noise_pool) - 1:
            return

        self.noise_pool[row + 1], self.noise_pool[row] = self.noise_pool[row], self.noise_pool[row + 1]
        self._mark_dirty()
        self._refresh_list(current_row=row + 1)

    def save_now(self, show_message: bool = True) -> bool:
        if not self._can_edit_with_message():
            return False

        try:
            cleaned_pool = self._clean_noise_pool(self.noise_pool)
            self.runtime.save_noise_pool(cleaned_pool)
            self.noise_pool = list(cleaned_pool)
            self._dirty = False
            self._refresh_list()
            self._set_status("噪音池已保存")
            self._last_error_text = ""

            if show_message:
                QMessageBox.information(self, "保存成功", "噪音池已保存")

            return True
        except Exception as exc:
            self._set_error(f"保存失败：{exc}")
            if show_message:
                QMessageBox.warning(self, "保存失败", str(exc))
            return False

    def _mark_dirty(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._set_status("有未保存修改")

    @staticmethod
    def _clean_noise_pool(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text:
                result.append(text)
        return result

    def _can_edit_with_message(self) -> bool:
        if not self._is_scheduler_running():
            return True

        QMessageBox.warning(self, "群发运行中", "请先停止群发功能")
        self._update_running_state()
        return False

    def _is_scheduler_running(self) -> bool:
        if hasattr(self.runtime, "is_scheduler_running"):
            try:
                return bool(self.runtime.is_scheduler_running())
            except Exception:
                return False
        return False

    def _on_scheduler_status_changed(self, _status: str) -> None:
        self._update_running_state()

    def _update_running_state(self) -> None:
        running = self._is_scheduler_running()

        self.add_button.setEnabled(not running)
        self.save_button.setEnabled(not running)
        self.editor.setReadOnly(running)
        self._update_buttons()

        if running:
            self.status_label.setText("群发运行中：请先停止群发功能")
            self.status_label.setStyleSheet("color: #b00020;")
        elif self._dirty:
            self._set_status("有未保存修改")
        elif self._last_error_text:
            self._set_error(self._last_error_text)
        else:
            self._set_status("已加载，未修改")

    def _update_buttons(self) -> None:
        row = self.noise_list.currentRow()
        has_selection = 0 <= row < len(self.noise_pool)
        running = self._is_scheduler_running()

        self.delete_button.setEnabled(has_selection and not running)
        self.move_up_button.setEnabled(has_selection and row > 0 and not running)
        self.move_down_button.setEnabled(
            has_selection and row < len(self.noise_pool) - 1 and not running
        )

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #1f5f99;")

    def _set_error(self, text: str) -> None:
        self._last_error_text = text
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #b00020;")

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
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
    def __init__(self, runtime_service, parent=None):
        super().__init__(parent)

        self.runtime = runtime_service
        self.noise_pool: list[str] = []
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

        if hasattr(self.runtime, "noise_pool_changed"):
            self.runtime.noise_pool_changed.connect(self.reload_from_runtime)

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

        self.reload_button = QPushButton("重新加载")
        self.reload_button.clicked.connect(self.reload_from_runtime)

        self.save_button = QPushButton("立即保存")
        self.save_button.clicked.connect(self.save_now)

        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        title_layout.addWidget(self.status_label)
        title_layout.addWidget(self.reload_button)
        title_layout.addWidget(self.save_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.setStyleSheet(HORIZONTAL_SPLITTER_QSS)
        splitter.setChildrenCollapsible(False)

        left_widget = self._build_left_panel()
        right_widget = self._build_right_panel()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
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
            "噪音池说明：发送前如果命中噪音概率，会从这里随机选择一条文本发送。"
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

        helper_label = QLabel(
            "提示：允许重复内容。重复添加某条噪音，可以提高它被随机选中的概率。"
        )
        helper_label.setWordWrap(True)

        layout.addWidget(editor_title)
        layout.addWidget(self.editor, 1)
        layout.addWidget(helper_label)

        return widget

    def reload_from_runtime(self) -> None:
        self._loading = True

        try:
            if hasattr(self.runtime, "sync_noise_pool_from_disk"):
                self.runtime.sync_noise_pool_from_disk()

            service = getattr(self.runtime, "noise_pool_service", None)

            if service is None:
                self.noise_pool = list(getattr(self.runtime, "noise_pool", []) or [])
            else:
                self.noise_pool = service.get_all()

            self._refresh_list()
            self._set_status("已加载噪音池")
            self._last_error_text = ""

        except Exception as exc:
            self._set_error(f"加载失败：{exc}")
            QMessageBox.critical(self, "加载噪音池失败", str(exc))

        finally:
            self._loading = False
            self._update_running_state()

    def _refresh_list(self, current_row: int | None = None) -> None:
        self.noise_list.clear()

        for index, text in enumerate(self.noise_pool):
            preview = self._preview_text(text)
            item = QListWidgetItem(f"{index + 1}. {preview}")
            item.setData(Qt.ItemDataRole.UserRole, text)
            self.noise_list.addItem(item)

        self.count_label.setText(f"共 {len(self.noise_pool)} 条")

        if not self.noise_pool:
            self.editor.clear()
            self.editor.setEnabled(False)
            return

        self.editor.setEnabled(True)

        if current_row is None:
            current_row = min(
                max(0, self.noise_list.currentRow()),
                len(self.noise_pool) - 1,
            )

        if current_row < 0:
            current_row = 0

        if current_row >= len(self.noise_pool):
            current_row = len(self.noise_pool) - 1

        self.noise_list.setCurrentRow(current_row)

    @staticmethod
    def _preview_text(text: str) -> str:
        normalized = " ".join(str(text or "").split())

        if not normalized:
            return "空内容"

        if len(normalized) > 60:
            return normalized[:60] + "..."

        return normalized

    def _on_current_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.noise_pool):
            self._loading = True
            self.editor.clear()
            self.editor.setEnabled(False)
            self._loading = False
            return

        self._loading = True
        self.editor.setEnabled(True)
        self.editor.setPlainText(self.noise_pool[row])
        self._loading = False

        self._update_buttons()

    def _on_editor_text_changed(self) -> None:
        if self._loading:
            return

        row = self.noise_list.currentRow()

        if row < 0 or row >= len(self.noise_pool):
            return

        self.noise_pool[row] = self.editor.toPlainText()
        self._refresh_list(current_row=row)
        self._schedule_auto_save()

    def add_item(self) -> None:
        if not self._can_edit_with_message():
            return

        self.noise_pool.append("")
        self._refresh_list(current_row=len(self.noise_pool) - 1)
        self.editor.setFocus()
        self._schedule_auto_save()

    def delete_current_item(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()

        if row < 0 or row >= len(self.noise_pool):
            QMessageBox.information(self, "提示", "请先选择要删除的噪音内容")
            return

        self.noise_pool.pop(row)
        next_row = min(row, len(self.noise_pool) - 1)
        self._refresh_list(current_row=next_row)
        self._schedule_auto_save()

    def move_current_item_up(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()

        if row <= 0 or row >= len(self.noise_pool):
            return

        self.noise_pool[row - 1], self.noise_pool[row] = (
            self.noise_pool[row],
            self.noise_pool[row - 1],
        )
        self._refresh_list(current_row=row - 1)
        self._schedule_auto_save()

    def move_current_item_down(self) -> None:
        if not self._can_edit_with_message():
            return

        row = self.noise_list.currentRow()

        if row < 0 or row >= len(self.noise_pool) - 1:
            return

        self.noise_pool[row + 1], self.noise_pool[row] = (
            self.noise_pool[row],
            self.noise_pool[row + 1],
        )
        self._refresh_list(current_row=row + 1)
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
        if self._loading:
            return

        debounce_ms = 400
        settings = getattr(self.runtime, "settings", None)

        if settings is not None:
            debounce_ms = int(getattr(settings, "config_auto_save_debounce_ms", 400))

        self._save_timer.start(max(100, debounce_ms))

    def _auto_save(self) -> None:
        if self._loading:
            return

        self.save_now(show_message=False)

    def save_now(self, show_message: bool = True) -> bool:
        self._save_timer.stop()

        try:
            cleaned_pool = self._clean_noise_pool(self.noise_pool)
            self.runtime.save_noise_pool(cleaned_pool)
            self.noise_pool = list(cleaned_pool)
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

        QMessageBox.warning(
            self,
            "群发运行中",
            "群发运行中，不能修改噪音池，请先停止群发调度器。",
        )
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
        self.delete_button.setEnabled(not running)
        self.move_up_button.setEnabled(not running)
        self.move_down_button.setEnabled(not running)
        self.save_button.setEnabled(not running)
        self.editor.setReadOnly(running)

        self._update_buttons()

        if running:
            self.status_label.setText("群发运行中：噪音池禁止修改")
            self.status_label.setStyleSheet("color: #b00020;")
            return

        if self._last_error_text:
            self._set_error(self._last_error_text)
        else:
            self._set_status("可编辑")

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
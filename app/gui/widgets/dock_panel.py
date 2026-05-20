from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class DockPanelSize:
    min_width: int
    min_height: int
    default_width: int
    default_height: int
    content_max_width: int


DEFAULT_PANEL_SIZE = DockPanelSize(
    min_width=720,
    min_height=560,
    default_width=720,
    default_height=600,
    content_max_width=680,
)

TASK_PANEL_SIZE = DockPanelSize(
    min_width=1080,
    min_height=780,
    default_width=1080,
    default_height=820,
    content_max_width=1020,
)

DOCK_CONTENT_MARGINS = (34, 34, 34, 30)
DOCK_CONTENT_SPACING = 18


class ConfigDockWidget(QDockWidget):
    """
    通用配置浮动面板。

    设计目标：
    - 使用 Qt 官方推荐的 QDockWidget。
    - 默认点击配置后自动以浮动窗口弹出，不需要用户手动拖出。
    - 支持关闭、移动、重新停靠、调整大小。
    - 任务配置面板使用更大的默认比例，避免控件被挤压。
    - 内容区使用 QScrollArea，但优先给足宽度，避免不必要的横向滚动。
    """

    closed = Signal(str)

    def __init__(
        self,
        object_name: str,
        title: str,
        content: QWidget | None = None,
        parent: QWidget | None = None,
        default_width: int = 720,
        default_height: int = 600,
        font_size: int = 13,
        floating: bool = True,
        allowed_areas: Qt.DockWidgetArea = (
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        ),
    ):
        super().__init__(title, parent)

        self._object_name = str(object_name or "").strip() or "configDockWidget"
        self._panel_size = self._resolve_panel_size(
            object_name=self._object_name,
            default_width=default_width,
            default_height=default_height,
        )
        self._font_size = self._safe_font_size(font_size, 13)
        self._content: QWidget | None = None

        self.setObjectName(self._object_name)
        self.setAllowedAreas(allowed_areas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setMinimumSize(self._panel_size.min_width, self._panel_size.min_height)
        self.resize(self._panel_size.default_width, self._panel_size.default_height)
        self.setFloating(bool(floating))
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._apply_font_style()

        if content is not None:
            self.set_content(content)

    @classmethod
    def _resolve_panel_size(
        cls,
        object_name: str,
        default_width: int,
        default_height: int,
    ) -> DockPanelSize:
        base = TASK_PANEL_SIZE if "task" in str(object_name or "").lower() else DEFAULT_PANEL_SIZE

        safe_default_width = cls._safe_positive_int(default_width, base.default_width)
        safe_default_height = cls._safe_positive_int(default_height, base.default_height)

        return DockPanelSize(
            min_width=base.min_width,
            min_height=base.min_height,
            default_width=max(safe_default_width, base.default_width, base.min_width),
            default_height=max(safe_default_height, base.default_height, base.min_height),
            content_max_width=base.content_max_width,
        )

    @staticmethod
    def _safe_positive_int(value: Any, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = int(default)

        if number <= 0:
            return int(default)

        return number

    @classmethod
    def _safe_font_size(cls, value: Any, default: int = 13) -> int:
        size = cls._safe_positive_int(value, default)

        if size < 8:
            return 8

        if size > 36:
            return 36

        return size

    def _apply_font_style(self) -> None:
        self.setStyleSheet(
            f"""
            QDockWidget {{
                font-size: {self._font_size}px;
            }}

            QDockWidget::title {{
                padding: 9px 12px;
                font-weight: 600;
            }}
            """
        )

    def set_content(self, content: QWidget, scrollable: bool = True) -> None:
        self._content = content

        if scrollable:
            self.setWidget(make_dock_scroll_area(content, self._panel_size.content_max_width))
        else:
            self.setWidget(content)

    def content_widget(self) -> QWidget | None:
        return self._content

    def set_panel_font_size(self, font_size: int) -> None:
        self._font_size = self._safe_font_size(font_size, self._font_size)
        self._apply_font_style()

    def open_panel(self) -> None:
        self.setFloating(True)
        self.setMinimumSize(self._panel_size.min_width, self._panel_size.min_height)
        self.resize(self._panel_size.default_width, self._panel_size.default_height)
        self.show()
        self._center_over_parent()
        self.raise_()
        self.activateWindow()

    def _center_over_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        try:
            parent_center = parent.frameGeometry().center()
            own_geometry = self.frameGeometry()
            own_geometry.moveCenter(parent_center)
            self.move(own_geometry.topLeft())
        except Exception:
            return

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit(self.objectName())
        super().closeEvent(event)


def make_dock_scroll_area(content: QWidget, content_max_width: int) -> QScrollArea:
    scroll_area = QScrollArea()
    scroll_area.setObjectName("ConfigDockScrollArea")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setWidget(make_dock_content_widget(content, content_max_width))
    scroll_area.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    return scroll_area


def make_dock_content_widget(
    content: QWidget | None = None,
    content_max_width: int = DEFAULT_PANEL_SIZE.content_max_width,
    margins: tuple[int, int, int, int] = DOCK_CONTENT_MARGINS,
    spacing: int = DOCK_CONTENT_SPACING,
) -> QWidget:
    wrapper = QWidget()
    wrapper.setObjectName("ConfigDockContentWrapper")
    wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    if content is not None:
        content.setMaximumWidth(max(400, int(content_max_width)))
        content.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )
        layout.addWidget(content, 1, Qt.AlignmentFlag.AlignHCenter)

    layout.addStretch(1)
    return wrapper


def create_config_dock(
    parent,
    object_name: str,
    title: str,
    content: QWidget,
    default_width: int = 720,
    default_height: int = 600,
    font_size: int = 13,
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea,
    floating: bool = True,
) -> ConfigDockWidget:
    dock = ConfigDockWidget(
        object_name=object_name,
        title=title,
        content=content,
        parent=parent,
        default_width=default_width,
        default_height=default_height,
        font_size=font_size,
        floating=floating,
    )

    if parent is not None and hasattr(parent, "addDockWidget"):
        parent.addDockWidget(area, dock)

    return dock

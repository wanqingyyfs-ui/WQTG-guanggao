from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


DOCK_MIN_WIDTH = 620
DOCK_MIN_HEIGHT = 520
DOCK_CONTENT_MAX_WIDTH = 920
DOCK_CONTENT_MARGINS = (34, 34, 34, 30)
DOCK_CONTENT_SPACING = 18


class ConfigDockWidget(QDockWidget):
    """
    通用配置浮动面板。

    设计目标：
    - 使用 Qt 官方推荐的 QDockWidget 方式，不再用固定比例的页面内表单。
    - 支持停靠、浮动、关闭、调整大小。
    - 关闭后不销毁内容，后续点击“配置”按钮可以再次打开。
    - 内容区默认使用 QScrollArea，避免表单较长时撑破窗口。
    - 面板保留统一外边距、合理最小尺寸，并让表单内容在面板中更居中。
    """

    closed = Signal(str)

    def __init__(
        self,
        object_name: str,
        title: str,
        content: QWidget | None = None,
        parent: QWidget | None = None,
        default_width: int = 620,
        default_height: int = 640,
        font_size: int = 13,
        floating: bool = False,
        allowed_areas: Qt.DockWidgetArea = (
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        ),
    ):
        super().__init__(title, parent)

        self._object_name = str(object_name or "").strip() or "configDockWidget"
        self._default_width = max(
            self._safe_positive_int(default_width, 620),
            DOCK_MIN_WIDTH,
        )
        self._default_height = max(
            self._safe_positive_int(default_height, 640),
            DOCK_MIN_HEIGHT,
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
        self.setMinimumSize(DOCK_MIN_WIDTH, DOCK_MIN_HEIGHT)
        self.resize(self._default_width, self._default_height)
        self.setFloating(bool(floating))
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._apply_font_style()

        if content is not None:
            self.set_content(content)

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
            self.setWidget(make_dock_scroll_area(content))
        else:
            self.setWidget(content)

    def content_widget(self) -> QWidget | None:
        return self._content

    def set_panel_font_size(self, font_size: int) -> None:
        self._font_size = self._safe_font_size(font_size, self._font_size)
        self._apply_font_style()

    def open_panel(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit(self.objectName())
        super().closeEvent(event)


def make_dock_scroll_area(content: QWidget) -> QScrollArea:
    scroll_area = QScrollArea()
    scroll_area.setObjectName("ConfigDockScrollArea")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setWidget(make_dock_content_widget(content))
    scroll_area.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    return scroll_area


def make_dock_content_widget(
    content: QWidget | None = None,
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
        content.setMaximumWidth(DOCK_CONTENT_MAX_WIDTH)
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
    default_width: int = 620,
    default_height: int = 640,
    font_size: int = 13,
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea,
    floating: bool = False,
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

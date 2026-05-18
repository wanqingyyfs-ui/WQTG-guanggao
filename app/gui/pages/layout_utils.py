from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QWidget,
)


CONTROL_MIN_HEIGHT = 54
TEXT_EDIT_MIN_HEIGHT = 150
LIST_MIN_HEIGHT = 120
TABLE_MIN_HEIGHT = 120


SPLITTER_QSS = """
QSplitter::handle {
    background-color: #7f91aa;
    border-top: 1px solid #5f718a;
    border-bottom: 1px solid #5f718a;
    border-radius: 3px;
}

QSplitter::handle:hover {
    background-color: #4f6480;
}

QSplitter::handle:pressed {
    background-color: #2f4058;
}
"""


HORIZONTAL_SPLITTER_QSS = """
QSplitter::handle {
    background-color: #d7dde7;
    border-left: 1px solid #b8c2d1;
    border-right: 1px solid #b8c2d1;
    border-radius: 3px;
}

QSplitter::handle:hover {
    background-color: #9fb0c7;
}

QSplitter::handle:pressed {
    background-color: #7387a3;
}
"""


GROUP_BOX_QSS = """
QGroupBox {
    margin-top: 26px;
    padding-top: 22px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 2px 10px 2px 10px;
}
"""


def style_standard_control(widget: QWidget) -> None:
    widget.setMinimumHeight(CONTROL_MIN_HEIGHT)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )


def style_text_editor(
    widget: QWidget,
    min_height: int = TEXT_EDIT_MIN_HEIGHT,
) -> None:
    widget.setMinimumHeight(max(0, int(min_height)))
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )


def style_list_widget(
    widget: QListWidget,
    min_height: int = LIST_MIN_HEIGHT,
) -> None:
    widget.setMinimumHeight(max(0, int(min_height)))
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )


def style_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setMinimumHeight(TABLE_MIN_HEIGHT)
    table.setMaximumHeight(16777215)
    table.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )


def style_form_layout(form_layout: QFormLayout) -> None:
    form_layout.setContentsMargins(28, 26, 28, 26)
    form_layout.setHorizontalSpacing(24)
    form_layout.setVerticalSpacing(18)
    form_layout.setLabelAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
    form_layout.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
    )


def style_group_box(group_box: QGroupBox) -> None:
    group_box.setStyleSheet(GROUP_BOX_QSS)
    group_box.setMinimumHeight(0)
    group_box.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )


def apply_large_inputs(root: QWidget) -> None:
    for widget in root.findChildren(QWidget):
        if isinstance(widget, (QLineEdit, QComboBox, QAbstractSpinBox)):
            style_standard_control(widget)
        elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
            style_text_editor(widget)
        elif isinstance(widget, QListWidget):
            style_list_widget(widget)


def make_scroll_area(
    widget: QWidget,
    minimum_height: int = 0,
    horizontal: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    vertical: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAsNeeded,
) -> QScrollArea:
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(horizontal)
    scroll_area.setVerticalScrollBarPolicy(vertical)
    scroll_area.setMinimumHeight(max(0, int(minimum_height)))
    scroll_area.setWidget(widget)
    scroll_area.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    return scroll_area


def make_vertical_splitter(
    top_widget: QWidget,
    bottom_widget: QWidget,
    sizes: list[int] | None = None,
    children_collapsible: bool = True,
) -> QSplitter:
    top_widget.setMinimumHeight(0)
    bottom_widget.setMinimumHeight(0)

    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(top_widget)
    splitter.addWidget(bottom_widget)
    splitter.setChildrenCollapsible(children_collapsible)
    splitter.setCollapsible(0, children_collapsible)
    splitter.setCollapsible(1, children_collapsible)
    splitter.setHandleWidth(12)
    splitter.setStyleSheet(SPLITTER_QSS)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)

    if sizes:
        splitter.setSizes([max(0, int(item)) for item in sizes])
    else:
        splitter.setSizes([360, 520])

    return splitter


def make_horizontal_splitter(
    left_widget: QWidget,
    right_widget: QWidget,
    sizes: list[int] | None = None,
    children_collapsible: bool = False,
) -> QSplitter:
    left_widget.setMinimumWidth(0)
    right_widget.setMinimumWidth(0)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(left_widget)
    splitter.addWidget(right_widget)
    splitter.setChildrenCollapsible(children_collapsible)
    splitter.setCollapsible(0, children_collapsible)
    splitter.setCollapsible(1, children_collapsible)
    splitter.setHandleWidth(10)
    splitter.setStyleSheet(HORIZONTAL_SPLITTER_QSS)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)

    if sizes:
        splitter.setSizes([max(0, int(item)) for item in sizes])
    else:
        splitter.setSizes([520, 640])

    return splitter
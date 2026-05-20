from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_font_size(value: Any, default: int = 13) -> int:
    size = _safe_int(value, default)

    if size < 8:
        return 8

    if size > 36:
        return 36

    return size


def build_app_qss(settings: Any | None = None) -> str:
    global_font_size = _safe_font_size(
        getattr(settings, "global_font_size", 13),
        13,
    )
    table_font_size = _safe_font_size(
        getattr(settings, "table_font_size", global_font_size),
        global_font_size,
    )
    button_font_size = _safe_font_size(
        getattr(settings, "button_font_size", global_font_size),
        global_font_size,
    )
    input_font_size = _safe_font_size(
        getattr(settings, "input_font_size", global_font_size),
        global_font_size,
    )
    floating_panel_font_size = _safe_font_size(
        getattr(settings, "floating_panel_font_size", global_font_size),
        global_font_size,
    )

    return f"""
QWidget {{
    background-color: #f6f8fb;
    color: #1f2937;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: {global_font_size}px;
}}

QMainWindow {{
    background-color: #f6f8fb;
}}

QTabWidget::pane {{
    border: 1px solid #d9dee7;
    border-radius: 14px;
    background: #ffffff;
    margin-top: 14px;
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background: #eef2f7;
    color: #4b5563;
    border: 1px solid #d9dee7;
    padding: 12px 22px;
    min-width: 104px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 8px;
    margin-top: 4px;
    font-size: {global_font_size}px;
}}

QTabBar::tab:selected {{
    background: #ffffff;
    color: #111827;
    font-weight: 600;
    margin-top: 0px;
}}

QTabBar::tab:hover {{
    background: #e8edf5;
}}

QGroupBox {{
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    margin-top: 14px;
    padding: 18px 16px 16px 16px;
    font-weight: 600;
    font-size: {global_font_size}px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #111827;
    background: #ffffff;
}}

QPushButton {{
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 9px 16px;
    min-height: 18px;
    font-weight: 600;
    font-size: {button_font_size}px;
}}

QPushButton:hover {{
    background-color: #1d4ed8;
}}

QPushButton:pressed {{
    background-color: #1e40af;
}}

QPushButton:disabled {{
    background-color: #cbd5e1;
    color: #f8fafc;
}}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QTimeEdit,
QDateEdit,
QDateTimeEdit,
QListWidget {{
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: #bfdbfe;
    selection-color: #111827;
    font-size: {input_font_size}px;
}}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QTimeEdit:focus,
QDateEdit:focus,
QDateTimeEdit:focus,
QListWidget:focus {{
    border: 1px solid #60a5fa;
}}

QLineEdit:read-only,
QPlainTextEdit:read-only,
QTextEdit:read-only {{
    background: #f8fafc;
    color: #64748b;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    width: 0px;
    height: 0px;
}}

QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid #d1d5db;
    selection-background-color: #dbeafe;
    selection-color: #111827;
    outline: 0;
    font-size: {input_font_size}px;
}}

QListWidget::item {{
    min-height: 30px;
    padding: 4px 8px;
    border-radius: 6px;
}}

QListWidget::item:selected {{
    background: #dbeafe;
    color: #111827;
}}

QListWidget::item:hover {{
    background: #eef2ff;
}}

QCheckBox {{
    spacing: 8px;
    font-size: {global_font_size}px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
}}

QCheckBox::indicator:unchecked {{
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    background: #ffffff;
}}

QCheckBox::indicator:checked {{
    border: 1px solid #2563eb;
    border-radius: 5px;
    background: #2563eb;
}}

QTableWidget {{
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    gridline-color: #eef2f7;
    selection-background-color: #dbeafe;
    selection-color: #111827;
    alternate-background-color: #fafcff;
    font-size: {table_font_size}px;
}}

QTableWidget::item {{
    padding: 6px;
    font-size: {table_font_size}px;
}}

QTableWidget::item:selected {{
    background: #dbeafe;
    color: #111827;
}}

QHeaderView::section {{
    background: #f8fafc;
    color: #374151;
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 600;
    font-size: {table_font_size}px;
}}

QTableCornerButton::section {{
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid #e5e7eb;
}}

QLabel {{
    color: #374151;
    font-size: {global_font_size}px;
}}

QLabel#PageTitleLabel {{
    color: #111827;
    font-size: {global_font_size + 6}px;
    font-weight: 700;
}}

QLabel#SectionTitleLabel {{
    color: #111827;
    font-size: {global_font_size + 2}px;
    font-weight: 700;
}}

QLabel#DashboardStatusLabel {{
    color: #475569;
    background: transparent;
    font-size: {global_font_size + 1}px;
}}

QLabel#DashboardHintLabel {{
    color: #64748b;
    background: transparent;
    font-size: {global_font_size}px;
}}

QFrame#DashboardCard {{
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 18px;
}}

QStatusBar {{
    background: #ffffff;
    border-top: 1px solid #e5e7eb;
    color: #475569;
    font-size: {global_font_size}px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px;
}}

QScrollBar::handle:vertical {{
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: #94a3b8;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 4px;
}}

QScrollBar::handle:horizontal {{
    background: #cbd5e1;
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #94a3b8;
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QSplitter::handle {{
    background-color: #d7dde7;
}}

QDockWidget {{
    background: #ffffff;
    border: 1px solid #d9dee7;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    font-size: {floating_panel_font_size}px;
}}

QDockWidget::title {{
    background: #eef2f7;
    color: #111827;
    padding: 9px 10px;
    font-weight: 600;
    text-align: left;
    font-size: {floating_panel_font_size}px;
}}

QDockWidget QWidget {{
    font-size: {floating_panel_font_size}px;
}}

QDockWidget QPushButton {{
    font-size: {button_font_size}px;
}}

QDockWidget QLineEdit,
QDockWidget QTextEdit,
QDockWidget QPlainTextEdit,
QDockWidget QComboBox,
QDockWidget QSpinBox,
QDockWidget QDoubleSpinBox,
QDockWidget QTimeEdit,
QDockWidget QDateEdit,
QDockWidget QDateTimeEdit,
QDockWidget QListWidget {{
    font-size: {input_font_size}px;
}}

QScrollArea#ConfigDockScrollArea {{
    background: #ffffff;
    border: none;
}}

QMessageBox {{
    background-color: #ffffff;
}}

QMessageBox QLabel {{
    color: #111827;
    background: transparent;
    font-size: {global_font_size}px;
}}

QMessageBox QPushButton {{
    min-width: 82px;
    font-size: {button_font_size}px;
}}
"""


APP_QSS = build_app_qss()

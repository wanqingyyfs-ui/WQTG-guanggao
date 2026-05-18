from __future__ import annotations


APP_QSS = """
QWidget {
    background-color: #f6f8fb;
    color: #1f2937;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #f6f8fb;
}

QTabWidget::pane {
    border: 1px solid #d9dee7;
    border-radius: 14px;
    background: #ffffff;
    margin-top: 14px;
}

QTabBar {
    background: transparent;
}

QTabBar::tab {
    background: #eef2f7;
    color: #4b5563;
    border: 1px solid #d9dee7;
    padding: 12px 22px;
    min-width: 104px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 8px;
    margin-top: 4px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #111827;
    font-weight: 600;
    margin-top: 0px;
}

QTabBar::tab:hover {
    background: #e8edf5;
}

QGroupBox {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    margin-top: 14px;
    padding: 18px 16px 16px 16px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #111827;
    background: #ffffff;
}

QPushButton {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 9px 16px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1d4ed8;
}

QPushButton:pressed {
    background-color: #1e40af;
}

QPushButton:disabled {
    background-color: #cbd5e1;
    color: #f8fafc;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QListWidget {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: #bfdbfe;
    selection-color: #111827;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QListWidget:focus {
    border: 1px solid #60a5fa;
}

QLineEdit:read-only {
    background: #f8fafc;
    color: #64748b;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    width: 0px;
    height: 0px;
}

QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d1d5db;
    selection-background-color: #dbeafe;
    selection-color: #111827;
    outline: 0;
}

QListWidget::item {
    min-height: 30px;
    padding: 4px 8px;
    border-radius: 6px;
}

QListWidget::item:selected {
    background: #dbeafe;
    color: #111827;
}

QListWidget::item:hover {
    background: #eef2ff;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QCheckBox::indicator:unchecked {
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    background: #ffffff;
}

QCheckBox::indicator:checked {
    border: 1px solid #2563eb;
    border-radius: 5px;
    background: #2563eb;
}

QTableWidget {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    gridline-color: #eef2f7;
    selection-background-color: #dbeafe;
    selection-color: #111827;
    alternate-background-color: #fafcff;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background: #dbeafe;
    color: #111827;
}

QHeaderView::section {
    background: #f8fafc;
    color: #374151;
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 600;
}

QTableCornerButton::section {
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid #e5e7eb;
}

QLabel {
    color: #374151;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e5e7eb;
    color: #475569;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 4px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

QMessageBox {
    background-color: #ffffff;
}

QMessageBox QLabel {
    color: #111827;
    background: transparent;
}

QMessageBox QPushButton {
    min-width: 82px;
}
"""
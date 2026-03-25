"""Global Qt stylesheet for the desktop UI."""

from __future__ import annotations

from pathlib import Path

from src.ui.theme import TOKENS, alpha_hex


def build_stylesheet() -> str:
    checkmark_path = (Path(__file__).resolve().parent / "assets" / "checkmark.svg").as_posix()
    return f"""
QWidget {{
    color: {TOKENS.text_main};
    background: transparent;
    selection-background-color: {TOKENS.accent};
    selection-color: #f8fbfc;
}}

QMainWindow, QWidget#appRoot {{
    background-color: {TOKENS.bg_canvas};
}}

QMenuBar, QMenu, QStatusBar {{
    background-color: {TOKENS.bg_panel_alt};
    color: {TOKENS.text_main};
}}

QMenuBar {{
    border-bottom: 1px solid {TOKENS.line_soft};
}}

QMenu {{
    border: 1px solid {TOKENS.line_soft};
}}

QWidget#topBar {{
    background-color: {TOKENS.bg_panel_alt};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_lg}px;
}}

QFrame#panelCard, QFrame#sessionCard {{
    background-color: {TOKENS.bg_panel};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_lg}px;
}}

QFrame#sessionCard[active="true"] {{
    border: 2px solid {TOKENS.accent};
    background-color: {TOKENS.bg_panel_strong};
}}

QFrame#toolbarCard, QWidget#toolbarCard {{
    background-color: {TOKENS.bg_panel_alt};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_md}px;
}}

QLabel#titleLabel {{
    font-size: 18px;
    font-weight: 700;
    color: {TOKENS.text_main};
}}

QLabel#subtitleLabel, QLabel#mutedLabel {{
    color: {TOKENS.text_soft};
    font-size: 12px;
}}

QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TOKENS.text_main};
}}

QLabel#summaryLabel {{
    color: {TOKENS.text_soft};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.96)};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_sm}px;
    padding: 8px 12px;
    min-height: 18px;
    color: {TOKENS.text_main};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {TOKENS.accent};
}}

QComboBox#sessionSiteSelector {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.98)};
    border: 1px solid {alpha_hex(TOKENS.accent, 0.34)};
    border-radius: {TOKENS.radius_md}px;
    padding: 7px 34px 7px 12px;
    min-height: 20px;
    font-weight: 600;
}}

QComboBox#sessionSiteSelector:hover {{
    background-color: {TOKENS.bg_panel_alt};
    border-color: {alpha_hex(TOKENS.accent, 0.52)};
}}

QComboBox#sessionSiteSelector:focus {{
    border: 1px solid {TOKENS.accent};
    background-color: {alpha_hex(TOKENS.accent, 0.08)};
}}

QComboBox#sessionSiteSelector::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {alpha_hex(TOKENS.accent, 0.18)};
    background-color: {alpha_hex(TOKENS.accent, 0.08)};
    border-top-right-radius: {TOKENS.radius_md}px;
    border-bottom-right-radius: {TOKENS.radius_md}px;
}}

QComboBox#sessionSiteSelector QAbstractItemView {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.98)};
    border: 1px solid {TOKENS.line_soft};
    selection-background-color: {alpha_hex(TOKENS.accent, 0.2)};
    selection-color: {TOKENS.text_main};
    outline: none;
}}

QPushButton {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.9)};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_sm}px;
    padding: 8px 14px;
    min-height: 18px;
    color: {TOKENS.text_main};
}}

QPushButton:hover {{
    background-color: {TOKENS.bg_panel_alt};
    border-color: {TOKENS.line_strong};
}}

QPushButton:pressed {{
    background-color: {TOKENS.accent_soft};
}}

QPushButton[feedbackPressed="true"] {{
    background-color: {alpha_hex(TOKENS.accent, 0.18)};
    border: 2px solid {TOKENS.accent};
}}

QPushButton[variant="primary"] {{
    background-color: {TOKENS.accent};
    border-color: {TOKENS.accent_strong};
    color: #f8fbfc;
}}

QPushButton[variant="danger"] {{
    background-color: {TOKENS.danger_soft};
    border-color: {alpha_hex(TOKENS.danger, 0.35)};
    color: {TOKENS.danger};
}}

QPushButton[variant="ghost"] {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.55)};
}}

QPushButton[chrome="icon"] {{
    padding: 0;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    border-radius: {TOKENS.radius_sm}px;
    border: none;
    background-color: transparent;
}}

QPushButton[chrome="icon"]:hover {{
    background-color: {TOKENS.bg_panel_alt};
    border: 1px solid {TOKENS.line_soft};
}}

QPushButton[chrome="icon"]:pressed {{
    background-color: {TOKENS.accent_soft};
}}

QPushButton#siteActionButton {{
    min-width: 0;
    min-height: 42px;
    max-height: 42px;
    padding: 0;
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_sm}px;
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.94)};
}}

QPushButton#siteActionButton:hover {{
    background-color: {TOKENS.bg_panel_alt};
    border-color: {TOKENS.line_strong};
}}

QPushButton#siteActionButton:pressed {{
    background-color: {TOKENS.accent_soft};
}}

QPushButton#siteActionButton[feedbackPressed="true"] {{
    background-color: {alpha_hex(TOKENS.accent, 0.16)};
    border: 2px solid {TOKENS.accent};
}}

QListWidget, QTreeView, QTreeWidget, QTableWidget, QTextEdit#logOutput {{
    background-color: {alpha_hex(TOKENS.bg_panel_strong, 0.96)};
    alternate-background-color: {TOKENS.bg_panel_alt};
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_md}px;
    gridline-color: {TOKENS.line_soft};
    outline: none;
}}

QListWidget::item, QTreeView::item, QTreeWidget::item, QTableWidget::item {{
    padding: 6px;
}}

QListWidget::item:selected, QTreeView::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {TOKENS.accent};
    color: #f8fbfc;
    outline: none;
}}

QListWidget#siteList::item {{
    margin: 2px 4px;
    padding: 8px 10px;
    border: 1px solid transparent;
    border-radius: {TOKENS.radius_sm}px;
}}

QListWidget#siteList::item:selected,
QListWidget#siteList::item:selected:active,
QListWidget#siteList::item:selected:!active {{
    background-color: {alpha_hex(TOKENS.accent, 0.22)};
    color: {TOKENS.text_main};
    border: 1px solid {TOKENS.accent};
    font-weight: 700;
}}

QListWidget::item:hover, QTreeView::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: {TOKENS.accent_soft};
}}

QListWidget::item:selected:hover,
QListWidget::item:selected:active:hover,
QListWidget::item:selected:!active:hover,
QTreeView::item:selected:hover,
QTreeView::item:selected:active:hover,
QTreeView::item:selected:!active:hover,
QTreeWidget::item:selected:hover,
QTreeWidget::item:selected:active:hover,
QTreeWidget::item:selected:!active:hover,
QTableWidget::item:selected:hover,
QTableWidget::item:selected:active:hover,
QTableWidget::item:selected:!active:hover {{
    background-color: {TOKENS.accent};
    color: #f8fbfc;
}}

QHeaderView::section {{
    background-color: {TOKENS.bg_panel_alt};
    border: none;
    border-right: 1px solid {TOKENS.line_strong};
    border-bottom: 1px solid {TOKENS.line_soft};
    padding: 6px 8px;
    font-weight: 700;
    color: {TOKENS.text_soft};
}}

QHeaderView::section:last {{
    border-right: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px;
}}

QScrollBar::handle:vertical {{
    background: {alpha_hex(TOKENS.text_muted, 0.45)};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    border: none;
}}

QSplitter::handle {{
    background-color: {alpha_hex(TOKENS.text_muted, 0.18)};
    border-radius: 4px;
}}

QCheckBox {{
    spacing: 8px;
    color: {TOKENS.text_main};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {TOKENS.line_strong};
    background-color: {TOKENS.bg_panel_alt};
}}

QCheckBox::indicator:unchecked {{
    background-color: {TOKENS.bg_panel_alt};
    border: 1px solid {TOKENS.line_strong};
}}

QCheckBox::indicator:checked {{
    background-color: {TOKENS.accent};
    border: 1px solid {TOKENS.accent_strong};
    image: url({checkmark_path});
}}

QCheckBox::indicator:hover {{
    border: 1px solid {TOKENS.accent};
}}

QCheckBox#taskRowCheckbox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {TOKENS.line_strong};
    background-color: {TOKENS.bg_panel_strong};
}}

QCheckBox#taskRowCheckbox::indicator:checked {{
    background-color: {TOKENS.accent};
    border: 1px solid {TOKENS.accent_strong};
    image: url({checkmark_path});
}}

QCheckBox#taskRowCheckbox::indicator:hover {{
    border: 1px solid {TOKENS.accent};
}}

QDialog {{
    background-color: {TOKENS.bg_surface};
}}

QGroupBox {{
    border: 1px solid {TOKENS.line_soft};
    border-radius: {TOKENS.radius_md}px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: 700;
    background-color: {TOKENS.bg_panel};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TOKENS.text_soft};
}}
"""

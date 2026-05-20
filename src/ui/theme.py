"""Shared visual theme tokens for the Qt desktop UI."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeTokens:
    bg_canvas: str = "#edf2f5"
    bg_surface: str = "#f7f9f8"
    bg_panel: str = "#ffffff"
    bg_panel_alt: str = "#eff6f8"
    bg_panel_strong: str = "#ffffff"
    bg_highlight: str = "#dff0ef"
    line_soft: str = "#d3dde2"
    line_strong: str = "#aebdc5"
    text_main: str = "#1d2b34"
    text_soft: str = "#53646e"
    text_muted: str = "#71808a"
    accent: str = "#176b8f"
    accent_strong: str = "#0f4d68"
    accent_soft: str = "#d8edf3"
    warning: str = "#9a651e"
    warning_soft: str = "#f1e2cc"
    danger: str = "#a43e4c"
    danger_soft: str = "#f2dce1"
    success: str = "#1f7a54"
    success_soft: str = "#dceee6"
    radius_sm: int = 8
    radius_md: int = 12
    radius_lg: int = 16
    spacing_xs: int = 6
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 14


TOKENS = ThemeTokens()


def alpha_hex(color: str, alpha: float) -> str:
    """Return a CSS rgba() string from a hex color and alpha ratio."""
    qcolor = QColor(color)
    return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {alpha:.3f})"


def app_font(point_size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(["IBM Plex Sans", "Noto Sans SC", "Segoe UI", "Arial"])
    font.setPointSize(point_size)
    return font


def mono_font(point_size: int = 9) -> QFont:
    font = QFont()
    font.setFamilies(["IBM Plex Mono", "Cascadia Mono", "Consolas", "Courier New"])
    font.setPointSize(point_size)
    return font


def apply_theme(app: QApplication) -> None:
    """Apply the shared application font and stylesheet."""
    from src.ui.theme_qss import build_stylesheet

    app.setFont(app_font())
    app.setStyleSheet(build_stylesheet())

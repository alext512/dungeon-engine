"""Shared tab-bar overflow behavior for the editor UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabBar, QTabWidget


def configure_tab_bar_overflow(tab_bar: QTabBar) -> None:
    """Prefer scrolling over trimming or squeezing tab labels."""
    tab_bar.setUsesScrollButtons(True)
    tab_bar.setElideMode(Qt.TextElideMode.ElideNone)
    tab_bar.setExpanding(False)


def configure_tab_widget_overflow(tab_widget: QTabWidget) -> None:
    """Apply the shared overflow policy to a tab widget and its tab bar."""
    tab_widget.setUsesScrollButtons(True)
    tab_widget.setElideMode(Qt.TextElideMode.ElideNone)
    configure_tab_bar_overflow(tab_widget.tabBar())

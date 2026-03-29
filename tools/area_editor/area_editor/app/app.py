"""QApplication factory and configuration."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create and configure the editor QApplication."""
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Area Editor")
    app.setOrganizationName("PuzzleDungeon")
    return app

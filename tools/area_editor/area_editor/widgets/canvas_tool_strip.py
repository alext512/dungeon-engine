"""Small central strip for canvas editing tools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
)


class CanvasToolStrip(QFrame):
    """Compact action strip shown above the central document tabs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CanvasToolStrip")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            """
            QFrame#CanvasToolStrip {
                background: #f5f5f5;
                border: 0;
                border-bottom: 1px solid #d8d8d8;
            }
            QLabel#CanvasToolStripLabel {
                color: #555;
                font-weight: 600;
                padding-left: 2px;
                padding-right: 4px;
            }
            QToolButton {
                padding: 3px 10px;
            }
            QToolButton:checked {
                font-weight: 600;
            }
            """
        )

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 3, 6, 3)
        self._layout.setSpacing(4)

        label = QLabel("Canvas Tools")
        label.setObjectName("CanvasToolStripLabel")
        self._layout.addWidget(label)
        self._layout.addSpacing(4)
        self._layout.addStretch(1)

    def set_actions(self, actions: list[QAction]) -> None:
        """Populate the strip from existing shared QAction objects."""
        while self._layout.count() > 3:
            item = self._layout.takeAt(2)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        insert_at = 2
        for action in actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setAutoRaise(False)
            self._layout.insertWidget(insert_at, button)
            insert_at += 1

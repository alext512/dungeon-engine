"""Small central strip for canvas editing tools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
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

        self._title_label = QLabel("Canvas Tools")
        self._title_label.setObjectName("CanvasToolStripLabel")
        self._layout.addWidget(self._title_label)
        self._layout.addSpacing(8)
        self._layout.addStretch(1)
        self._section_labels: list[str] = []
        self._button_texts: list[str] = []

    def set_actions(self, actions: list[QAction]) -> None:
        """Populate the strip from existing shared QAction objects."""
        self.set_sections([("Tools", actions)])

    def set_sections(self, sections: list[tuple[str, list[QAction]]]) -> None:
        """Populate the strip with labeled action groups."""
        while self._layout.count() > 3:
            item = self._layout.takeAt(2)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._section_labels = []
        self._button_texts = []

        insert_at = 2
        for section_index, (title, actions) in enumerate(sections):
            label = QLabel(f"{title}:")
            label.setObjectName("CanvasToolStripLabel")
            self._layout.insertWidget(insert_at, label)
            insert_at += 1
            self._section_labels.append(title)
            for action in actions:
                button = QToolButton()
                button.setDefaultAction(action)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setAutoRaise(False)
                button.setSizePolicy(
                    QSizePolicy.Policy.Minimum,
                    QSizePolicy.Policy.Fixed,
                )
                self._layout.insertWidget(insert_at, button)
                insert_at += 1
                self._button_texts.append(action.text().replace("&", ""))
            if section_index != len(sections) - 1:
                spacer = QLabel("  ")
                spacer.setSizePolicy(
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
                self._layout.insertWidget(insert_at, spacer)
                insert_at += 1

    def section_labels(self) -> list[str]:
        return list(self._section_labels)

    def button_texts(self) -> list[str]:
        return list(self._button_texts)

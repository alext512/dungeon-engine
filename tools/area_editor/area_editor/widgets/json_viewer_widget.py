"""Read-only JSON viewer widget.

Displays the contents of a JSON file with indentation in a monospace
read-only text area.  Used as the tab content for entity templates,
dialogues, named commands, and non-image assets.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class JsonViewerWidget(QPlainTextEdit):
    """Read-only, monospace display of a JSON (or plain-text) file."""

    def __init__(self, file_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self._file_path = file_path
        self._load()

    @property
    def file_path(self) -> Path:
        return self._file_path

    def _load(self) -> None:
        try:
            text = self._file_path.read_text(encoding="utf-8")
            # Re-indent JSON for consistent display
            if self._file_path.suffix.lower() == ".json":
                try:
                    data = json.loads(text)
                    text = json.dumps(data, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass  # show raw text if JSON is malformed
            self.setPlainText(text)
        except OSError as exc:
            self.setPlainText(f"Error reading file:\n{exc}")

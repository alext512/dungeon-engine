"""Guarded JSON/text viewer with optional editing and save support."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class JsonViewerWidget(QPlainTextEdit):
    """Monospace text viewer with opt-in editing and save support."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, file_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self._file_path = file_path
        self._editing_enabled = False
        self._dirty = False
        self._loading = False
        self.textChanged.connect(self._on_text_changed)
        self._load()

    @property
    def file_path(self) -> Path:
        return self._file_path

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self.setReadOnly(not enabled)
        self.editing_enabled_changed.emit(enabled)

    def save_to_file(self) -> None:
        text = self.toPlainText()
        if self._file_path.suffix.lower() == ".json":
            data = json.loads(text)
            text = json.dumps(data, indent=2, ensure_ascii=False)
        self._file_path.write_text(f"{text}\n", encoding="utf-8")
        self._load()

    def set_document_text(self, text: str, *, dirty: bool) -> None:
        """Replace the editor contents programmatically and control dirty state."""
        self._loading = True
        try:
            self.setPlainText(text)
        finally:
            self._loading = False
        self._set_dirty(dirty)

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
            self._loading = True
            try:
                self.setPlainText(text)
            finally:
                self._loading = False
            self._set_dirty(False)
        except OSError as exc:
            self.setPlainText(f"Error reading file:\n{exc}")

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

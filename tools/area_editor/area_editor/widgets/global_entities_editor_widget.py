"""Focused editor for the ``global_entities`` array inside ``project.json``."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class GlobalEntitiesEditorWidget(QWidget):
    """Edit just the manifest's ``global_entities`` array."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, project_file: Path, parent=None) -> None:
        super().__init__(parent)
        self._project_file = project_file
        self._editing_enabled = False
        self._dirty = False
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Project Global Entities")
        layout.addWidget(self._target_label)

        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        self._load()

    @property
    def file_path(self) -> Path:
        return self._project_file

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._editor.setReadOnly(not enabled)
        self.editing_enabled_changed.emit(enabled)

    def toPlainText(self) -> str:  # noqa: N802
        return self._editor.toPlainText()

    def setPlainText(self, text: str) -> None:  # noqa: N802
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._set_dirty(self._editing_enabled)

    def select_entity_id(self, entity_id: str | None) -> None:
        if entity_id:
            self._target_label.setText(f"Project Global Entities -> {entity_id}")
        else:
            self._target_label.setText("Project Global Entities")

    def save_to_file(self) -> None:
        array_data = json.loads(self.toPlainText())
        if not isinstance(array_data, list):
            raise ValueError("global_entities must be a JSON array.")
        manifest_data = json.loads(self._project_file.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            raise ValueError("project.json must contain a JSON object.")
        manifest_data["global_entities"] = array_data
        self._project_file.write_text(
            f"{json.dumps(manifest_data, indent=2, ensure_ascii=False)}\n",
            encoding="utf-8",
        )
        self._load()

    def _load(self) -> None:
        manifest_data = json.loads(self._project_file.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            raise ValueError("project.json must contain a JSON object.")
        array_data = manifest_data.get("global_entities", [])
        if not isinstance(array_data, list):
            raise ValueError("project.json global_entities must be a JSON array when present.")
        self._loading = True
        try:
            self._editor.setPlainText(json.dumps(array_data, indent=2, ensure_ascii=False))
        finally:
            self._loading = False
        self._set_dirty(False)

    def _on_text_changed(self) -> None:
        if self._loading or not self._editing_enabled:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

"""Template editor with a focused visuals surface plus full raw JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.widgets.json_viewer_widget import JsonViewerWidget


class _TemplateVisualsEditor(QWidget):
    """Small focused editor for one template's `visuals` array."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, template_id: str, parent=None) -> None:
        super().__init__(parent)
        self._template_id = template_id
        self._dirty = False
        self._loading = False
        self._editing_enabled = False
        self._current_data: dict[str, Any] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Template: {template_id}")
        layout.addWidget(self._target_label)

        summary = QFormLayout()
        self._space_label = QLabel("world")
        summary.addRow("space", self._space_label)
        layout.addLayout(summary)

        note = QLabel("Edit the template's `visuals` array here. Use the Raw JSON tab for the full file.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(note)

        self._visuals_text = QPlainTextEdit()
        self._visuals_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._visuals_text.setFixedHeight(220)
        self._visuals_text.setPlaceholderText(
            "[\n"
            "  {\n"
            '    "id": "main",\n'
            '    "path": "assets/project/sprites/example.png",\n'
            '    "frame_width": 16,\n'
            '    "frame_height": 16\n'
            "  }\n"
            "]"
        )
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._visuals_text.setFont(font)
        self._visuals_text.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._visuals_text, 1)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.set_editing_enabled(False)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def visuals_text(self) -> str:
        return self._visuals_text.toPlainText()

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._visuals_text.setReadOnly(not enabled)
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def load_template_data(self, data: dict[str, Any]) -> None:
        self._current_data = json.loads(json.dumps(data))
        self._loading = True
        try:
            self._space_label.setText(str(data.get("space", "world")))
            visuals = data.get("visuals", [])
            self._visuals_text.setPlainText(json.dumps(visuals, indent=2, ensure_ascii=False))
        finally:
            self._loading = False
        self._set_dirty(False)

    def build_updated_template_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        visuals_text = self._visuals_text.toPlainText().strip()
        try:
            visuals_value = json.loads(visuals_text) if visuals_text else []
        except json.JSONDecodeError as exc:
            raise ValueError(f"Visuals must be valid JSON.\n{exc}") from exc
        if not isinstance(visuals_value, list):
            raise ValueError("Visuals must be a JSON array.")
        updated = json.loads(json.dumps(base_data))
        updated["visuals"] = visuals_value
        return updated

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class EntityTemplateEditorWidget(QWidget):
    """Central-tab template editor with focused visuals and raw JSON."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, content_id: str, file_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._content_id = content_id
        self._file_path = file_path
        self._editing_enabled = False
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._fields_editor = _TemplateVisualsEditor(content_id)
        self._raw_json = JsonViewerWidget(file_path)
        self._tabs.addTab(self._fields_editor, "Template Editor")
        self._tabs.addTab(self._raw_json, "Raw JSON")

        self._fields_editor.apply_requested.connect(self._on_apply_fields)
        self._fields_editor.revert_requested.connect(self._on_revert_fields)
        self._fields_editor.dirty_changed.connect(self._on_surface_dirty_changed)
        self._raw_json.dirty_changed.connect(self._on_surface_dirty_changed)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._reload_fields_from_saved_file()

    @property
    def file_path(self) -> Path:
        return self._file_path

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def raw_json_widget(self) -> JsonViewerWidget:
        return self._raw_json

    @property
    def fields_editor(self) -> _TemplateVisualsEditor:
        return self._fields_editor

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._raw_json.set_editing_enabled(enabled)
        self._fields_editor.set_editing_enabled(enabled)
        self.editing_enabled_changed.emit(enabled)

    def save_to_file(self) -> None:
        if self._fields_editor.is_dirty:
            self._apply_fields_to_raw()
        self._raw_json.save_to_file()
        self._reload_fields_from_saved_file()
        self._set_dirty(False)

    def _on_apply_fields(self) -> None:
        try:
            self._apply_fields_to_raw()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Template Visuals", str(exc))

    def _on_revert_fields(self) -> None:
        try:
            if self._raw_json.is_dirty:
                self._reload_fields_from_current_raw()
            else:
                self._reload_fields_from_saved_file()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Raw JSON", str(exc))

    def _apply_fields_to_raw(self) -> None:
        base_data = self._current_raw_data()
        updated = self._fields_editor.build_updated_template_data(base_data)
        text = json.dumps(updated, indent=2, ensure_ascii=False)
        self._raw_json.set_document_text(text, dirty=True)
        self._fields_editor.load_template_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = json.loads(self._file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Entity template JSON must be a JSON object.")
        self._fields_editor.load_template_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        data = self._current_raw_data()
        self._fields_editor.load_template_data(data)

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = json.loads(self._raw_json.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Raw JSON must be valid before template fields can apply.\n{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Entity template JSON must be a JSON object.")
        return data

    def _on_surface_dirty_changed(self, *_args) -> None:
        self._set_dirty(self._raw_json.is_dirty or self._fields_editor.is_dirty)

    def _on_tab_changed(self, index: int) -> None:
        if index != 0:
            return
        if self._fields_editor.is_dirty:
            return
        try:
            self._reload_fields_from_current_raw()
        except ValueError:
            # Let the raw tab remain the recovery surface when the JSON is invalid.
            pass

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

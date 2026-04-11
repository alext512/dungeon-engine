"""Template editor with a focused visuals surface plus full raw JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
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

from area_editor.json_io import (
    JsonDataDecodeError,
    compose_json_file_text,
    dumps_for_clone,
    load_json_data,
    loads_json_data,
)
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow


def _parse_persistence_policy(
    raw_persistence: object,
) -> tuple[bool, dict[str, bool]]:
    if raw_persistence is None:
        return False, {}
    if not isinstance(raw_persistence, dict):
        raise ValueError("Persistence must be a JSON object.")

    raw_entity_state = raw_persistence.get("entity_state", False)
    if not isinstance(raw_entity_state, bool):
        raise ValueError("Persistence 'entity_state' must be true or false.")

    raw_variables = raw_persistence.get("variables", {})
    if raw_variables is None:
        raw_variables = {}
    if not isinstance(raw_variables, dict):
        raise ValueError("Persistence 'variables' must be a JSON object.")

    variables: dict[str, bool] = {}
    for raw_name, raw_value in raw_variables.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("Persistence variable overrides must not use blank names.")
        if not isinstance(raw_value, bool):
            raise ValueError(f"Persistence variable '{name}' must be true or false.")
        variables[name] = raw_value
    return bool(raw_entity_state), variables


def _build_persistence_policy(
    *,
    entity_state: bool,
    variables_text: str,
) -> dict[str, Any] | None:
    raw_variables_text = variables_text.strip()
    variables: dict[str, bool] = {}
    if raw_variables_text:
        try:
            parsed = loads_json_data(
                raw_variables_text,
                source_name="Persistence variables",
            )
        except JsonDataDecodeError as exc:
            raise ValueError(f"Persistence variables must be valid JSON.\n{exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Persistence variables must be a JSON object.")
        for raw_name, raw_value in parsed.items():
            name = str(raw_name).strip()
            if not name:
                raise ValueError("Persistence variables must not use blank names.")
            if not isinstance(raw_value, bool):
                raise ValueError(f"Persistence variable '{name}' must be true or false.")
            variables[name] = raw_value

    if not entity_state and not variables:
        return None

    payload: dict[str, Any] = {"entity_state": bool(entity_state)}
    if variables:
        payload["variables"] = variables
    return payload


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
        self._persistence_editable = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Template: {template_id}")
        layout.addWidget(self._target_label)

        summary = QFormLayout()
        self._space_label = QLabel("world")
        summary.addRow("space", self._space_label)
        layout.addLayout(summary)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._sections_tabs = QTabWidget()
        self._sections_tabs.setDocumentMode(True)
        configure_tab_widget_overflow(self._sections_tabs)
        layout.addWidget(self._sections_tabs, 1)

        visuals_tab = QWidget()
        visuals_layout = QVBoxLayout(visuals_tab)
        visuals_layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel("Edit the template's `visuals` array here. Use the Raw JSON tab for the full file.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-style: italic;")
        visuals_layout.addWidget(note)

        self._visuals_text = QPlainTextEdit()
        self._visuals_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
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
        self._visuals_text.setFont(font)
        self._visuals_text.textChanged.connect(self._on_text_changed)
        visuals_layout.addWidget(self._visuals_text, 1)
        self._sections_tabs.addTab(visuals_tab, "Visuals")

        persistence_tab = QWidget()
        persistence_layout = QVBoxLayout(persistence_tab)
        persistence_layout.setContentsMargins(0, 0, 0, 0)

        self._persistence_warning = QLabel("")
        self._persistence_warning.setWordWrap(True)
        self._persistence_warning.setStyleSheet("color: #a25b00;")
        self._persistence_warning.hide()
        persistence_layout.addWidget(self._persistence_warning)

        persistence_form = QFormLayout()
        self._entity_state_check = QCheckBox("Persist entity state")
        self._entity_state_check.toggled.connect(self._on_text_changed)
        persistence_form.addRow("persistence.entity_state", self._entity_state_check)
        persistence_layout.addLayout(persistence_form)

        persistence_note = QLabel(
            "Optional per-variable persistence overrides. Use JSON object syntax."
        )
        persistence_note.setWordWrap(True)
        persistence_note.setStyleSheet("color: #666; font-style: italic;")
        persistence_layout.addWidget(persistence_note)

        self._persistence_variables_text = QPlainTextEdit()
        self._persistence_variables_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._persistence_variables_text.setPlaceholderText(
            '{\n'
            '  "shake_timer": false,\n'
            '  "times_pushed": true\n'
            '}'
        )
        self._persistence_variables_text.setFont(font)
        self._persistence_variables_text.textChanged.connect(self._on_text_changed)
        persistence_layout.addWidget(self._persistence_variables_text, 1)
        self._sections_tabs.addTab(persistence_tab, "Persistence")

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
        self._entity_state_check.setEnabled(enabled and self._persistence_editable)
        self._persistence_variables_text.setReadOnly(not (enabled and self._persistence_editable))
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def load_template_data(self, data: dict[str, Any]) -> None:
        self._current_data = dumps_for_clone(data)
        raw_persistence = data.get("persistence")
        persistence_warning: str | None = None
        persistence_entity_state = False
        persistence_variables: dict[str, bool] = {}
        try:
            persistence_entity_state, persistence_variables = _parse_persistence_policy(
                raw_persistence
            )
            self._persistence_editable = True
        except ValueError as exc:
            persistence_warning = (
                "Persistence is not using the supported object shape. "
                "Use the Raw JSON tab to edit it.\n"
                f"{exc}"
            )
            self._persistence_editable = False
        self._loading = True
        try:
            self._space_label.setText(str(data.get("space", "world")))
            visuals = data.get("visuals", [])
            self._visuals_text.setPlainText(json.dumps(visuals, indent=2, ensure_ascii=False))
            self._entity_state_check.setChecked(persistence_entity_state)
            self._persistence_variables_text.setPlainText(
                json.dumps(persistence_variables, indent=2, ensure_ascii=False)
                if persistence_variables
                else ""
            )
        finally:
            self._loading = False
        if persistence_warning:
            self._persistence_warning.setText(persistence_warning)
            self._persistence_warning.show()
        else:
            self._persistence_warning.hide()
        self._entity_state_check.setEnabled(self._editing_enabled and self._persistence_editable)
        self._persistence_variables_text.setReadOnly(
            not (self._editing_enabled and self._persistence_editable)
        )
        self._set_dirty(False)

    def build_updated_template_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        visuals_text = self._visuals_text.toPlainText().strip()
        try:
            visuals_value = (
                loads_json_data(visuals_text, source_name="Template visuals")
                if visuals_text
                else []
            )
        except JsonDataDecodeError as exc:
            raise ValueError(f"Visuals must be valid JSON.\n{exc}") from exc
        if not isinstance(visuals_value, list):
            raise ValueError("Visuals must be a JSON array.")
        updated = dumps_for_clone(base_data)
        updated["visuals"] = visuals_value
        if self._persistence_editable:
            persistence_value = _build_persistence_policy(
                entity_state=bool(self._entity_state_check.isChecked()),
                variables_text=self._persistence_variables_text.toPlainText(),
            )
            if persistence_value is None:
                updated.pop("persistence", None)
            else:
                updated["persistence"] = persistence_value
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
        configure_tab_widget_overflow(self._tabs)
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
        self._raw_json.set_document_text(
            compose_json_file_text(
                text,
                original_text=self._raw_json.toPlainText(),
            ),
            dirty=True,
        )
        self._fields_editor.load_template_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = load_json_data(self._file_path)
        if not isinstance(data, dict):
            raise ValueError("Entity template JSON must be a JSON object.")
        self._fields_editor.load_template_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        data = self._current_raw_data()
        self._fields_editor.load_template_data(data)

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = loads_json_data(
                self._raw_json.toPlainText(),
                source_name=str(self._file_path),
            )
        except JsonDataDecodeError as exc:
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

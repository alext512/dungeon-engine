"""Focused editor for practical ``shared_variables.json`` fields plus raw JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow


def _parse_shared_variables_fields(data: dict[str, Any]) -> tuple[int, int, int]:
    display = data.get("display", {})
    movement = data.get("movement", {})
    if display is None:
        display = {}
    if movement is None:
        movement = {}
    if not isinstance(display, dict):
        raise ValueError("'display' must be a JSON object.")
    if not isinstance(movement, dict):
        raise ValueError("'movement' must be a JSON object.")

    width = display.get("internal_width", 320)
    height = display.get("internal_height", 240)
    ticks = movement.get("ticks_per_tile", 16)
    try:
        width_value = max(1, int(width))
    except (TypeError, ValueError) as exc:
        raise ValueError("'display.internal_width' must be a positive integer.") from exc
    try:
        height_value = max(1, int(height))
    except (TypeError, ValueError) as exc:
        raise ValueError("'display.internal_height' must be a positive integer.") from exc
    try:
        ticks_value = max(1, int(ticks))
    except (TypeError, ValueError) as exc:
        raise ValueError("'movement.ticks_per_tile' must be a positive integer.") from exc
    return width_value, height_value, ticks_value


class _SharedVariablesFieldsEditor(QWidget):
    """Focused editor for display and movement shared variables."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, file_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._dirty = False
        self._loading = False
        self._editing_enabled = False
        self._structured_editable = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Shared Variables: {file_path.name}")
        layout.addWidget(self._target_label)

        note = QLabel(
            "Edit the most practical shared variables here. Use the Raw JSON tab for the full file."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(note)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #a25b00;")
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        form = QFormLayout()
        layout.addLayout(form)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 8192)
        self._width_spin.valueChanged.connect(self._on_changed)
        form.addRow("display.internal_width", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 8192)
        self._height_spin.valueChanged.connect(self._on_changed)
        form.addRow("display.internal_height", self._height_spin)

        self._ticks_spin = QSpinBox()
        self._ticks_spin.setRange(1, 8192)
        self._ticks_spin.valueChanged.connect(self._on_changed)
        form.addRow("movement.ticks_per_tile", self._ticks_spin)

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

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        active = enabled and self._structured_editable
        self._width_spin.setEnabled(active)
        self._height_spin.setEnabled(active)
        self._ticks_spin.setEnabled(active)
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def load_shared_variables_data(self, data: dict[str, Any]) -> None:
        warning: str | None = None
        try:
            width, height, ticks = _parse_shared_variables_fields(data)
            self._structured_editable = True
        except ValueError as exc:
            width, height, ticks = 320, 240, 16
            warning = (
                "The current shared variables file is not using the supported object shape "
                "for the focused fields. Use the Raw JSON tab to edit it.\n"
                f"{exc}"
            )
            self._structured_editable = False

        self._loading = True
        try:
            self._width_spin.setValue(width)
            self._height_spin.setValue(height)
            self._ticks_spin.setValue(ticks)
        finally:
            self._loading = False

        if warning:
            self._warning_label.setText(warning)
            self._warning_label.show()
        else:
            self._warning_label.hide()

        active = self._editing_enabled and self._structured_editable
        self._width_spin.setEnabled(active)
        self._height_spin.setEnabled(active)
        self._ticks_spin.setEnabled(active)
        self._set_dirty(False)

    def build_updated_shared_variables_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        if not self._structured_editable:
            raise ValueError("Use the Raw JSON tab to edit the current shared variables shape.")
        updated = json.loads(json.dumps(base_data))
        display = updated.get("display")
        movement = updated.get("movement")
        if display is None:
            display = {}
            updated["display"] = display
        if movement is None:
            movement = {}
            updated["movement"] = movement
        if not isinstance(display, dict):
            raise ValueError("'display' must be a JSON object.")
        if not isinstance(movement, dict):
            raise ValueError("'movement' must be a JSON object.")

        display["internal_width"] = self._width_spin.value()
        display["internal_height"] = self._height_spin.value()
        movement["ticks_per_tile"] = self._ticks_spin.value()
        return updated

    def _on_changed(self) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class SharedVariablesEditorWidget(QWidget):
    """Central-tab shared-variables editor with focused fields and raw JSON."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, file_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._editing_enabled = False
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        configure_tab_widget_overflow(self._tabs)
        layout.addWidget(self._tabs)

        self._fields_editor = _SharedVariablesFieldsEditor(file_path)
        self._raw_json = JsonViewerWidget(file_path)
        self._tabs.addTab(self._fields_editor, "Shared Variables")
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
    def fields_editor(self) -> _SharedVariablesFieldsEditor:
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
            QMessageBox.warning(self, "Invalid Shared Variables", str(exc))

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
        updated = self._fields_editor.build_updated_shared_variables_data(base_data)
        text = json.dumps(updated, indent=2, ensure_ascii=False)
        self._raw_json.set_document_text(text, dirty=True)
        self._fields_editor.load_shared_variables_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = json.loads(self._file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("shared_variables.json must be a JSON object.")
        self._fields_editor.load_shared_variables_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        self._fields_editor.load_shared_variables_data(self._current_raw_data())

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = json.loads(self._raw_json.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Raw JSON must be valid before shared variables can apply.\n{exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("shared_variables.json must be a JSON object.")
        return data

    def _on_surface_dirty_changed(self, *_args) -> None:
        self._set_dirty(self._raw_json.is_dirty or self._fields_editor.is_dirty)

    def _on_tab_changed(self, index: int) -> None:
        if index != 0 or self._fields_editor.is_dirty:
            return
        try:
            self._reload_fields_from_current_raw()
        except ValueError:
            pass

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

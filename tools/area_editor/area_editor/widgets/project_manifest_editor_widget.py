"""Focused editor for practical ``project.json`` fields plus raw JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.widgets.json_viewer_widget import JsonViewerWidget


def _validate_relative_project_path(
    project_root: Path,
    raw_path: str,
    *,
    field_label: str,
) -> str:
    normalized = raw_path.strip().replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{field_label} must not be blank.")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"{field_label} must stay relative to the project root.")
    resolved = (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{field_label} must stay inside the project root.") from exc
    return normalized


class _ProjectManifestFieldsEditor(QWidget):
    """Focused editor for the most practical project manifest fields."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, project_file: Path, *, area_ids: list[str], parent=None) -> None:
        super().__init__(parent)
        self._project_root = project_file.parent.resolve()
        self._dirty = False
        self._loading = False
        self._editing_enabled = False
        self._known_area_ids = sorted({str(area_id).strip() for area_id in area_ids if str(area_id).strip()})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Project: {self._project_root.name}")
        layout.addWidget(self._target_label)

        note = QLabel(
            "Edit the most common manifest settings here. Use the Raw JSON tab for the full file."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(note)

        form = QFormLayout()
        layout.addLayout(form)

        self._startup_area_combo = QComboBox()
        self._startup_area_combo.currentIndexChanged.connect(self._on_changed)
        form.addRow("startup_area", self._startup_area_combo)

        self._startup_warning = QLabel("")
        self._startup_warning.setWordWrap(True)
        self._startup_warning.setStyleSheet("color: #a25b00;")
        self._startup_warning.hide()
        form.addRow("", self._startup_warning)

        self._debug_check = QCheckBox("Enable debug inspection commands")
        self._debug_check.toggled.connect(self._on_changed)
        form.addRow("debug_inspection_enabled", self._debug_check)

        self._save_dir_edit = QLineEdit()
        self._save_dir_edit.textChanged.connect(self._on_changed)
        form.addRow("save_dir", self._save_dir_edit)

        self._shared_variables_path_edit = QLineEdit()
        self._shared_variables_path_edit.textChanged.connect(self._on_changed)
        form.addRow("shared_variables_path", self._shared_variables_path_edit)

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
        self._populate_startup_area_options(None)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._startup_area_combo.setEnabled(enabled)
        self._debug_check.setEnabled(enabled)
        self._save_dir_edit.setReadOnly(not enabled)
        self._shared_variables_path_edit.setReadOnly(not enabled)
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def current_startup_area(self) -> str | None:
        value = self._startup_area_combo.currentData()
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return None

    def load_manifest_data(self, data: dict[str, Any]) -> None:
        startup_area = self._normalize_optional_str(data.get("startup_area"))
        self._loading = True
        try:
            self._populate_startup_area_options(startup_area)
            self._debug_check.setChecked(bool(data.get("debug_inspection_enabled", False)))
            self._save_dir_edit.setText(self._normalize_optional_str(data.get("save_dir")) or "")
            self._shared_variables_path_edit.setText(
                self._normalize_optional_str(data.get("shared_variables_path")) or ""
            )
        finally:
            self._loading = False
        self._update_startup_warning()
        self._set_dirty(False)

    def build_updated_manifest_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        updated = json.loads(json.dumps(base_data))

        startup_area = self.current_startup_area()
        if startup_area is None:
            updated.pop("startup_area", None)
        else:
            if startup_area not in self._known_area_ids:
                raise ValueError(
                    f"startup_area '{startup_area}' does not match any discovered area."
                )
            updated["startup_area"] = startup_area

        updated["debug_inspection_enabled"] = bool(self._debug_check.isChecked())

        save_dir = self._save_dir_edit.text().strip()
        if save_dir:
            updated["save_dir"] = _validate_relative_project_path(
                self._project_root,
                save_dir,
                field_label="save_dir",
            )
        else:
            updated.pop("save_dir", None)

        shared_variables_path = self._shared_variables_path_edit.text().strip()
        if shared_variables_path:
            updated["shared_variables_path"] = _validate_relative_project_path(
                self._project_root,
                shared_variables_path,
                field_label="shared_variables_path",
            )
        else:
            updated.pop("shared_variables_path", None)
        return updated

    def _populate_startup_area_options(self, current_value: str | None) -> None:
        selected = (current_value or "").strip()
        self._startup_area_combo.blockSignals(True)
        try:
            self._startup_area_combo.clear()
            self._startup_area_combo.addItem("(none)", "")
            for area_id in self._known_area_ids:
                self._startup_area_combo.addItem(area_id, area_id)
            if selected and selected not in self._known_area_ids:
                self._startup_area_combo.addItem(f"{selected} (missing)", selected)
            index = self._startup_area_combo.findData(selected)
            if index < 0:
                index = 0
            self._startup_area_combo.setCurrentIndex(index)
        finally:
            self._startup_area_combo.blockSignals(False)
        self._update_startup_warning()

    def _update_startup_warning(self) -> None:
        startup_area = self.current_startup_area()
        if startup_area and startup_area not in self._known_area_ids:
            self._startup_warning.setText(
                "The current startup_area does not match any discovered area. "
                "Pick a valid area or use the Raw JSON tab to investigate."
            )
            self._startup_warning.show()
            return
        self._startup_warning.hide()

    @staticmethod
    def _normalize_optional_str(raw_value: object) -> str | None:
        if raw_value in (None, ""):
            return None
        value = str(raw_value).strip()
        return value or None

    def _on_changed(self) -> None:
        self._update_startup_warning()
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class ProjectManifestEditorWidget(QWidget):
    """Central-tab project manifest editor with focused fields and raw JSON."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, file_path: Path, *, area_ids: list[str], parent=None) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._editing_enabled = False
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._fields_editor = _ProjectManifestFieldsEditor(file_path, area_ids=area_ids)
        self._raw_json = JsonViewerWidget(file_path)
        self._tabs.addTab(self._fields_editor, "Project Settings")
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
    def fields_editor(self) -> _ProjectManifestFieldsEditor:
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
            QMessageBox.warning(self, "Invalid Project Settings", str(exc))

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
        updated = self._fields_editor.build_updated_manifest_data(base_data)
        text = json.dumps(updated, indent=2, ensure_ascii=False)
        self._raw_json.set_document_text(text, dirty=True)
        self._fields_editor.load_manifest_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = json.loads(self._file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("project.json must be a JSON object.")
        self._fields_editor.load_manifest_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        self._fields_editor.load_manifest_data(self._current_raw_data())

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = json.loads(self._raw_json.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Raw JSON must be valid before project settings can apply.\n{exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("project.json must be a JSON object.")
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

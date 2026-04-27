"""Item editor with focused fields plus full raw JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
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
from area_editor.widgets.command_list_dialog import CommandListDialog
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow


class _ItemArtObjectEditor(QWidget):
    """Focused editor for one optional item art object."""

    changed = Signal()

    def __init__(
        self,
        label: str,
        *,
        browse_asset_callback: Callable[[], str | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._browse_asset_callback = browse_asset_callback
        self._editing_enabled = False
        self._loading = False
        self._editable = True
        self._base_object: dict[str, Any] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #a25b00;")
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        form = QFormLayout()
        layout.addLayout(form)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.textChanged.connect(self._on_changed)
        path_row.addWidget(self._path_edit, 1)
        self._browse_button = QPushButton("Browse...")
        self._browse_button.clicked.connect(self._on_browse_clicked)
        path_row.addWidget(self._browse_button)
        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self._on_clear_clicked)
        path_row.addWidget(self._clear_button)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        form.addRow("path", path_widget)

        self._frame_width_spin = QSpinBox()
        self._frame_width_spin.setRange(1, 8192)
        self._frame_width_spin.valueChanged.connect(self._on_changed)
        form.addRow("frame_width", self._frame_width_spin)

        self._frame_height_spin = QSpinBox()
        self._frame_height_spin.setRange(1, 8192)
        self._frame_height_spin.valueChanged.connect(self._on_changed)
        form.addRow("frame_height", self._frame_height_spin)

        self._frame_spin = QSpinBox()
        self._frame_spin.setRange(0, 8192)
        self._frame_spin.valueChanged.connect(self._on_changed)
        form.addRow("frame", self._frame_spin)

        self.set_editing_enabled(False)

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        active = enabled and self._editable
        self._path_edit.setReadOnly(not active)
        self._browse_button.setEnabled(active and self._browse_asset_callback is not None)
        self._clear_button.setEnabled(active)
        self._frame_width_spin.setEnabled(active)
        self._frame_height_spin.setEnabled(active)
        self._frame_spin.setEnabled(active)

    def load_object(self, raw_value: object) -> None:
        warning: str | None = None
        self._editable = True
        self._base_object = None
        path_value = ""
        frame_width = 16
        frame_height = 16
        frame = 0

        if raw_value not in (None, ""):
            if not isinstance(raw_value, dict):
                warning = (
                    f"{self._label} is not using a supported object shape. "
                    "Use the Raw JSON tab to edit it."
                )
                self._editable = False
            else:
                self._base_object = dumps_for_clone(raw_value)
                path_value = str(raw_value.get("path", "") or "")
                frame_width = self._coerce_positive_int(raw_value.get("frame_width", 16), 16)
                frame_height = self._coerce_positive_int(raw_value.get("frame_height", 16), 16)
                frame = self._coerce_non_negative_int(raw_value.get("frame", 0), 0)

        self._loading = True
        try:
            self._path_edit.setText(path_value)
            self._frame_width_spin.setValue(frame_width)
            self._frame_height_spin.setValue(frame_height)
            self._frame_spin.setValue(frame)
        finally:
            self._loading = False

        if warning:
            self._warning_label.setText(warning)
            self._warning_label.show()
        else:
            self._warning_label.hide()
        self.set_editing_enabled(self._editing_enabled)

    def build_object(self) -> dict[str, Any] | None:
        if not self._editable:
            return dumps_for_clone(self._base_object) if self._base_object is not None else None
        path_value = self._path_edit.text().strip()
        if not path_value:
            return None
        result = dumps_for_clone(self._base_object) if self._base_object is not None else {}
        result["path"] = path_value
        result["frame_width"] = self._frame_width_spin.value()
        result["frame_height"] = self._frame_height_spin.value()
        result["frame"] = self._frame_spin.value()
        return result

    @staticmethod
    def _coerce_positive_int(raw_value: object, default: int) -> int:
        try:
            return max(1, int(raw_value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_non_negative_int(raw_value: object, default: int) -> int:
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return default

    def _on_browse_clicked(self) -> None:
        if not self._editing_enabled or self._browse_asset_callback is None:
            return
        selected = self._browse_asset_callback()
        if selected:
            self._path_edit.setText(selected)

    def _on_clear_clicked(self) -> None:
        if not self._editing_enabled or not self._editable:
            return
        self._path_edit.clear()
        self._frame_width_spin.setValue(16)
        self._frame_height_spin.setValue(16)
        self._frame_spin.setValue(0)

    def _on_changed(self, *_args) -> None:
        if self._loading:
            return
        self.changed.emit()


class _ItemFieldsEditor(QWidget):
    """Focused editor for common item fields plus art blocks."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(
        self,
        item_id: str,
        *,
        browse_asset_callback: Callable[[], str | None] | None = None,
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[
            [str], dict[str, dict[str, Any]] | None
        ]
        | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._item_id = item_id
        self._dirty = False
        self._loading = False
        self._editing_enabled = False
        self._area_picker = area_picker
        self._asset_picker = asset_picker
        self._entity_picker = entity_picker
        self._entity_command_picker = entity_command_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._item_picker = item_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._project_command_inputs_provider = project_command_inputs_provider
        self._visual_picker = visual_picker
        self._animation_picker = animation_picker
        self._use_commands: list[dict[str, Any]] = []
        self._use_commands_base: Any = None
        self._use_commands_editable = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Item: {item_id}")
        layout.addWidget(self._target_label)

        form = QFormLayout()
        layout.addLayout(form)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_changed)
        form.addRow("name", self._name_edit)

        self._description_edit = QPlainTextEdit()
        self._description_edit.setFixedHeight(80)
        self._description_edit.textChanged.connect(self._on_changed)
        form.addRow("description", self._description_edit)

        self._max_stack_spin = QSpinBox()
        self._max_stack_spin.setRange(1, 9999)
        self._max_stack_spin.valueChanged.connect(self._on_changed)
        form.addRow("max_stack", self._max_stack_spin)

        self._consume_spin = QSpinBox()
        self._consume_spin.setRange(0, 9999)
        self._consume_spin.valueChanged.connect(self._on_changed)
        form.addRow("consume_quantity_on_use", self._consume_spin)

        self._icon_note = QLabel("Optional `icon` art object.")
        self._icon_note.setWordWrap(True)
        self._icon_note.setStyleSheet("color: #666; font-style: italic;")
        form.addRow("Icon", self._icon_note)
        self._icon_editor = _ItemArtObjectEditor(
            "Icon",
            browse_asset_callback=browse_asset_callback,
        )
        self._icon_editor.changed.connect(self._on_changed)
        form.addRow(self._icon_editor)

        self._portrait_note = QLabel("Optional `portrait` art object.")
        self._portrait_note.setWordWrap(True)
        self._portrait_note.setStyleSheet("color: #666; font-style: italic;")
        form.addRow("Portrait", self._portrait_note)
        self._portrait_editor = _ItemArtObjectEditor(
            "Portrait",
            browse_asset_callback=browse_asset_callback,
        )
        self._portrait_editor.changed.connect(self._on_changed)
        form.addRow(self._portrait_editor)

        self._use_commands_warning = QLabel("")
        self._use_commands_warning.setWordWrap(True)
        self._use_commands_warning.setStyleSheet("color: #a25b00;")
        self._use_commands_warning.hide()
        layout.addWidget(self._use_commands_warning)

        commands_row = QHBoxLayout()
        self._use_commands_summary = QLabel("No use commands")
        commands_row.addWidget(self._use_commands_summary, 1)
        self._edit_use_commands_button = QPushButton("Edit Use Commands...")
        self._edit_use_commands_button.clicked.connect(self._on_edit_use_commands)
        commands_row.addWidget(self._edit_use_commands_button)
        commands_widget = QWidget()
        commands_widget.setLayout(commands_row)
        form.addRow("use_commands", commands_widget)

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
        self._name_edit.setReadOnly(not enabled)
        self._description_edit.setReadOnly(not enabled)
        self._max_stack_spin.setEnabled(enabled)
        self._consume_spin.setEnabled(enabled)
        self._icon_editor.set_editing_enabled(enabled)
        self._portrait_editor.set_editing_enabled(enabled)
        self._edit_use_commands_button.setEnabled(enabled and self._use_commands_editable)
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def load_item_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._name_edit.setText(str(data.get("name", "")))
            self._description_edit.setPlainText(str(data.get("description", "")))
            self._max_stack_spin.setValue(int(data.get("max_stack", 1)))
            self._consume_spin.setValue(int(data.get("consume_quantity_on_use", 0)))
            self._icon_editor.load_object(data.get("icon"))
            self._portrait_editor.load_object(data.get("portrait"))
            self._load_use_commands(data.get("use_commands"))
        finally:
            self._loading = False
        self._set_dirty(False)

    def build_updated_item_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        updated = dumps_for_clone(base_data)
        updated["name"] = self._name_edit.text().strip()
        description = self._description_edit.toPlainText().strip()
        if description:
            updated["description"] = description
        else:
            updated.pop("description", None)
        updated["max_stack"] = self._max_stack_spin.value()
        updated["consume_quantity_on_use"] = self._consume_spin.value()
        self._apply_optional_object(updated, "icon", self._icon_editor.build_object())
        self._apply_optional_object(updated, "portrait", self._portrait_editor.build_object())
        self._apply_use_commands(updated, base_data)
        return updated

    def _apply_optional_object(
        self, target: dict[str, Any], key: str, value: dict[str, Any] | None
    ) -> None:
        if value is None:
            target.pop(key, None)
            return
        target[key] = value

    def _load_use_commands(self, raw_commands: Any) -> None:
        self._use_commands_base = dumps_for_clone(raw_commands)
        self._use_commands_editable = True
        if raw_commands is None:
            self._use_commands = []
            self._use_commands_warning.hide()
        elif isinstance(raw_commands, list):
            self._use_commands = dumps_for_clone(raw_commands)
            self._use_commands_warning.hide()
        else:
            self._use_commands = []
            self._use_commands_editable = False
            self._use_commands_warning.setText(
                "use_commands is not using a supported array shape. Use the Raw JSON tab to edit it."
            )
            self._use_commands_warning.show()
        self._sync_use_commands_summary()
        self.set_editing_enabled(self._editing_enabled)

    def _apply_use_commands(self, target: dict[str, Any], base_data: dict[str, Any]) -> None:
        if not self._use_commands_editable:
            if self._use_commands_base is None:
                target.pop("use_commands", None)
            else:
                target["use_commands"] = dumps_for_clone(self._use_commands_base)
            return
        if self._use_commands or "use_commands" in base_data:
            target["use_commands"] = dumps_for_clone(self._use_commands)
        else:
            target.pop("use_commands", None)

    def _sync_use_commands_summary(self) -> None:
        if not self._use_commands_editable:
            self._use_commands_summary.setText("Raw JSON only")
            return
        count = len(self._use_commands)
        if count == 0:
            self._use_commands_summary.setText("No use commands")
        elif count == 1:
            self._use_commands_summary.setText("1 use command")
        else:
            self._use_commands_summary.setText(f"{count} use commands")

    def _on_edit_use_commands(self) -> None:
        if not self._editing_enabled or not self._use_commands_editable:
            return
        dialog = CommandListDialog(
            self,
            area_picker=self._area_picker,
            asset_picker=self._asset_picker,
            entity_picker=self._entity_picker,
            entity_command_picker=self._entity_command_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            item_picker=self._item_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            project_command_inputs_provider=self._project_command_inputs_provider,
            visual_picker=self._visual_picker,
            animation_picker=self._animation_picker,
        )
        dialog.setWindowTitle(f"Edit Use Commands - {self._item_id}")
        dialog.load_commands(self._use_commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._use_commands = dialog.commands()
        self._sync_use_commands_summary()
        self._on_changed()

    def _on_changed(self) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class ItemEditorWidget(QWidget):
    """Central-tab item editor with focused fields and raw JSON."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(
        self,
        content_id: str,
        file_path: Path,
        *,
        browse_asset_callback: Callable[[], str | None] | None = None,
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[
            [str], dict[str, dict[str, Any]] | None
        ]
        | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
        parent=None,
    ) -> None:
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

        self._fields_editor = _ItemFieldsEditor(
            content_id,
            browse_asset_callback=browse_asset_callback,
            area_picker=area_picker,
            asset_picker=asset_picker,
            entity_picker=entity_picker,
            entity_command_picker=entity_command_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            item_picker=item_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            project_command_inputs_provider=project_command_inputs_provider,
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )
        self._raw_json = JsonViewerWidget(file_path)
        self._tabs.addTab(self._fields_editor, "Item Editor")
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
    def fields_editor(self) -> _ItemFieldsEditor:
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
            QMessageBox.warning(self, "Invalid Item Data", str(exc))

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
        updated = self._fields_editor.build_updated_item_data(base_data)
        text = json.dumps(updated, indent=2, ensure_ascii=False)
        self._raw_json.set_document_text(
            compose_json_file_text(
                text,
                original_text=self._raw_json.toPlainText(),
            ),
            dirty=True,
        )
        self._fields_editor.load_item_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = load_json_data(self._file_path)
        if not isinstance(data, dict):
            raise ValueError("Item JSON must be a JSON object.")
        self._fields_editor.load_item_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        self._fields_editor.load_item_data(self._current_raw_data())

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = loads_json_data(
                self._raw_json.toPlainText(),
                source_name=str(self._file_path),
            )
        except JsonDataDecodeError as exc:
            raise ValueError(
                f"Raw JSON must be valid before item fields can apply.\n{exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("Item JSON must be a JSON object.")
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

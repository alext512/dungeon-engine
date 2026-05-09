"""Focused editor for reusable project command definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
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


_INPUT_TYPES = (
    "string",
    "int",
    "float",
    "bool",
    "enum",
    "json",
    "area_id",
    "entity_id",
    "item_id",
    "dialogue_id",
    "project_command_id",
    "asset_path",
    "image_path",
    "sound_path",
    "visual_id",
    "animation_id",
    "entity_command_id",
    "entity_dialogue_id",
)
_OF_PARENT_TYPES: dict[str, set[str]] = {
    "visual_id": {"entity_id"},
    "animation_id": {"visual_id"},
    "entity_command_id": {"entity_id"},
    "entity_dialogue_id": {"entity_id"},
}


def _format_default_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _parse_default_value(input_id: str, input_type: str, text: str) -> Any:
    value = text.strip()
    if not value:
        return None
    if input_type == "int":
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Default for '{input_id}' must be an integer.") from exc
    if input_type == "float":
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Default for '{input_id}' must be a number.") from exc
    if input_type == "bool":
        normalized = value.casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"Default for '{input_id}' must be true or false.")
    if input_type == "json":
        try:
            return loads_json_data(value, source_name=f"default for {input_id}")
        except JsonDataDecodeError as exc:
            raise ValueError(f"Default for '{input_id}' must be valid JSON.\n{exc}") from exc
    return value


def _parse_enum_values(input_id: str, text: str) -> list[str]:
    value = text.strip()
    if not value:
        raise ValueError(f"Enum input '{input_id}' must have at least one value.")
    if value.startswith("["):
        try:
            raw_values = loads_json_data(value, source_name=f"values for {input_id}")
        except JsonDataDecodeError as exc:
            raise ValueError(f"Enum values for '{input_id}' must be valid JSON.\n{exc}") from exc
        if not isinstance(raw_values, list):
            raise ValueError(f"Enum values for '{input_id}' must be a JSON array.")
        values = [str(item).strip() for item in raw_values]
    else:
        values = [part.strip() for part in value.split(",")]
    clean_values: list[str] = []
    for item in values:
        if not item:
            continue
        if item not in clean_values:
            clean_values.append(item)
    if not clean_values:
        raise ValueError(f"Enum input '{input_id}' must have at least one value.")
    return clean_values


def _format_enum_values(values: object) -> str:
    if isinstance(values, list):
        return ", ".join(str(value) for value in values)
    return ""


class _CommandInputRow(QWidget):
    """One editable project-command input row."""

    changed = Signal()
    remove_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self._editing_enabled = False
        self._extra: dict[str, Any] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("input_id")
        self._id_edit.textChanged.connect(self._on_changed)
        top_row.addWidget(QLabel("id"))
        top_row.addWidget(self._id_edit, 2)

        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(list(_INPUT_TYPES))
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        top_row.addWidget(QLabel("type"))
        top_row.addWidget(self._type_combo, 1)

        self._move_up_button = QToolButton()
        self._move_up_button.setText("Up")
        self._move_up_button.clicked.connect(lambda: self.move_up_requested.emit(self))
        top_row.addWidget(self._move_up_button)
        self._move_down_button = QToolButton()
        self._move_down_button.setText("Down")
        self._move_down_button.clicked.connect(lambda: self.move_down_requested.emit(self))
        top_row.addWidget(self._move_down_button)
        self._remove_button = QToolButton()
        self._remove_button.setText("Remove")
        self._remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        top_row.addWidget(self._remove_button)
        outer.addLayout(top_row)

        detail_row = QHBoxLayout()
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(6)
        self._of_combo = QComboBox()
        self._of_combo.addItem("None", "")
        self._of_combo.currentIndexChanged.connect(self._on_changed)
        detail_row.addWidget(QLabel("of"))
        detail_row.addWidget(self._of_combo, 1)

        self._default_edit = QLineEdit()
        self._default_edit.setPlaceholderText("optional default")
        self._default_edit.textChanged.connect(self._on_changed)
        detail_row.addWidget(QLabel("default"))
        detail_row.addWidget(self._default_edit, 2)

        self._values_edit = QLineEdit()
        self._values_edit.setPlaceholderText("enum values, comma-separated")
        self._values_edit.textChanged.connect(self._on_changed)
        detail_row.addWidget(QLabel("values"))
        detail_row.addWidget(self._values_edit, 2)
        outer.addLayout(detail_row)

        self.load_input("", {"type": "string"})
        self.set_editing_enabled(False)

    @property
    def input_id(self) -> str:
        return self._id_edit.text().strip()

    @property
    def input_type(self) -> str:
        return self._type_combo.currentText().strip()

    def load_input(self, input_id: str, spec: dict[str, Any]) -> None:
        self._loading = True
        try:
            known_keys = {"type", "label", "of", "default", "values"}
            self._extra = {
                key: dumps_for_clone(value)
                for key, value in spec.items()
                if key not in known_keys
            }
            self._id_edit.setText(input_id)
            self._set_type(str(spec.get("type", "string")).strip() or "string")
            if "default" in spec and spec.get("default") is None:
                self._default_edit.setText("null")
            else:
                self._default_edit.setText(_format_default_value(spec.get("default")))
            self._values_edit.setText(_format_enum_values(spec.get("values")))
            self.refresh_of_choices([], selected=str(spec.get("of", "") or ""))
            self._sync_type_state()
        finally:
            self._loading = False

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._id_edit.setReadOnly(not enabled)
        self._type_combo.setEnabled(enabled)
        self._of_combo.setEnabled(enabled and self._of_combo.count() > 1)
        self._default_edit.setReadOnly(not enabled)
        self._values_edit.setEnabled(enabled and self.input_type == "enum")
        self._values_edit.setReadOnly(not enabled or self.input_type != "enum")
        self._move_up_button.setEnabled(enabled and self._move_up_button.isEnabled())
        self._move_down_button.setEnabled(enabled and self._move_down_button.isEnabled())
        self._remove_button.setEnabled(enabled)

    def set_row_buttons_enabled(self, *, can_move_up: bool, can_move_down: bool) -> None:
        self._move_up_button.setEnabled(self._editing_enabled and can_move_up)
        self._move_down_button.setEnabled(self._editing_enabled and can_move_down)

    def refresh_of_choices(
        self,
        previous_inputs: list[tuple[str, str]],
        *,
        selected: str | None = None,
    ) -> None:
        current = self._of_combo.currentData()
        if selected is not None:
            current = selected
        allowed_parent_types = _OF_PARENT_TYPES.get(self.input_type, set())
        choices = [
            (input_id, input_type)
            for input_id, input_type in previous_inputs
            if input_id and input_type in allowed_parent_types
        ]
        self._of_combo.blockSignals(True)
        try:
            self._of_combo.clear()
            self._of_combo.addItem("None", "")
            for input_id, input_type in choices:
                self._of_combo.addItem(f"{input_id} ({input_type})", input_id)
            index = 0
            if current:
                for candidate_index in range(self._of_combo.count()):
                    if self._of_combo.itemData(candidate_index) == current:
                        index = candidate_index
                        break
            self._of_combo.setCurrentIndex(index)
        finally:
            self._of_combo.blockSignals(False)
        self._of_combo.setEnabled(self._editing_enabled and self._of_combo.count() > 1)

    def build_spec(self) -> dict[str, Any]:
        input_id = self.input_id
        input_type = self.input_type
        if not input_id:
            raise ValueError("Input id cannot be blank.")
        if not input_type:
            raise ValueError(f"Input '{input_id}' must have a type.")
        spec = dumps_for_clone(self._extra)
        spec["type"] = input_type
        of_value = self._of_combo.currentData()
        if isinstance(of_value, str) and of_value.strip():
            spec["of"] = of_value.strip()
        else:
            spec.pop("of", None)
        raw_default_text = self._default_edit.text().strip()
        if raw_default_text.casefold() == "null":
            spec["default"] = None
        else:
            default_value = _parse_default_value(input_id, input_type, raw_default_text)
            if default_value is not None:
                spec["default"] = default_value
            else:
                spec.pop("default", None)
        if input_type == "enum":
            values = _parse_enum_values(input_id, self._values_edit.text())
            spec["values"] = values
            if "default" in spec and spec["default"] is not None and spec["default"] not in values:
                raise ValueError(f"Default for enum input '{input_id}' must be one of its values.")
        else:
            spec.pop("values", None)
        return spec

    def _set_type(self, value: str) -> None:
        index = self._type_combo.findText(value)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)
        else:
            self._type_combo.setEditText(value)

    def _on_type_changed(self, _text: str) -> None:
        self._sync_type_state()
        if not self._loading:
            self.changed.emit()

    def _sync_type_state(self) -> None:
        self._values_edit.setEnabled(self._editing_enabled and self.input_type == "enum")
        self._values_edit.setReadOnly(not self._editing_enabled or self.input_type != "enum")

    def _on_changed(self, *_args) -> None:
        if self._loading:
            return
        self.changed.emit()


class _ProjectCommandFieldsEditor(QWidget):
    """Focused editor for project-command inputs and command body."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(
        self,
        command_id: str,
        *,
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
        self._command_id = command_id
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
        self._commands: list[dict[str, Any]] = []
        self._commands_base: Any = None
        self._commands_editable = True
        self._inputs_editable = True
        self._rows: list[_CommandInputRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Project Command: {command_id}")
        layout.addWidget(self._target_label)

        inputs_header = QHBoxLayout()
        inputs_header.addWidget(QLabel("Inputs"), 1)
        self._add_input_button = QPushButton("Add Input")
        self._add_input_button.clicked.connect(lambda: self._add_input_row())
        inputs_header.addWidget(self._add_input_button)
        layout.addLayout(inputs_header)

        self._inputs_warning = QLabel("")
        self._inputs_warning.setWordWrap(True)
        self._inputs_warning.setStyleSheet("color: #a25b00;")
        self._inputs_warning.hide()
        layout.addWidget(self._inputs_warning)

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch(1)
        self._rows_scroll = QScrollArea()
        self._rows_scroll.setWidgetResizable(True)
        self._rows_scroll.setWidget(self._rows_widget)
        layout.addWidget(self._rows_scroll, 2)

        self._commands_warning = QLabel("")
        self._commands_warning.setWordWrap(True)
        self._commands_warning.setStyleSheet("color: #a25b00;")
        self._commands_warning.hide()
        layout.addWidget(self._commands_warning)

        commands_row = QHBoxLayout()
        self._commands_summary = QLabel("No commands")
        commands_row.addWidget(self._commands_summary, 1)
        self._edit_commands_button = QPushButton("Edit Commands...")
        self._edit_commands_button.clicked.connect(self._on_edit_commands)
        commands_row.addWidget(self._edit_commands_button)
        layout.addLayout(commands_row)

        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setText("Advanced")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setChecked(False)
        self._advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._advanced_toggle.toggled.connect(self._sync_advanced_state)
        layout.addWidget(self._advanced_toggle)

        self._advanced_widget = QWidget()
        advanced_form = QFormLayout(self._advanced_widget)
        advanced_form.setContentsMargins(12, 0, 0, 0)
        self._deferred_param_shapes_edit = QPlainTextEdit()
        self._deferred_param_shapes_edit.setFixedHeight(72)
        self._deferred_param_shapes_edit.setPlaceholderText('{\n  "hook": "command_payload"\n}')
        self._deferred_param_shapes_edit.textChanged.connect(
            self._on_deferred_param_shapes_changed
        )
        advanced_form.addRow("deferred_param_shapes", self._deferred_param_shapes_edit)
        layout.addWidget(self._advanced_widget)
        self._advanced_widget.hide()

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
        self._add_input_button.setEnabled(enabled and self._inputs_editable)
        self._deferred_param_shapes_edit.setReadOnly(not enabled)
        self._edit_commands_button.setEnabled(enabled and self._commands_editable)
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)
        for row in self._rows:
            row.set_editing_enabled(enabled and self._inputs_editable)
        self._refresh_row_controls()
        self._sync_advanced_state(self._advanced_toggle.isChecked())

    def load_command_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._clear_input_rows()
            self._inputs_editable = True
            raw_inputs = data.get("inputs")
            if isinstance(raw_inputs, dict):
                self._inputs_warning.hide()
                for input_id, raw_spec in raw_inputs.items():
                    spec = raw_spec if isinstance(raw_spec, dict) else {"type": "string"}
                    self._add_input_row(str(input_id), dumps_for_clone(spec), mark_dirty=False)
            elif raw_inputs is not None:
                self._inputs_warning.setText(
                    "inputs is not using a supported object shape. Use the Raw JSON tab to edit it."
                )
                self._inputs_warning.show()
                self._inputs_editable = False
            else:
                raw_params = data.get("params", [])
                if isinstance(raw_params, list):
                    self._inputs_warning.hide()
                    for raw_param in raw_params:
                        if isinstance(raw_param, str) and raw_param.strip():
                            self._add_input_row(
                                raw_param.strip(),
                                {"type": "string"},
                                mark_dirty=False,
                            )
                elif raw_params is not None:
                    self._inputs_warning.setText(
                        "params is not using a supported array shape. Use the Raw JSON tab to edit it."
                    )
                    self._inputs_warning.show()
                    self._inputs_editable = False

            raw_deferred = data.get("deferred_param_shapes")
            if isinstance(raw_deferred, dict):
                self._deferred_param_shapes_edit.setPlainText(
                    json.dumps(raw_deferred, indent=2, ensure_ascii=False)
                )
            elif raw_deferred in (None, ""):
                self._deferred_param_shapes_edit.clear()
            else:
                self._deferred_param_shapes_edit.setPlainText(
                    json.dumps(raw_deferred, indent=2, ensure_ascii=False)
                )

            self._load_commands(data.get("commands"))
        finally:
            self._loading = False
        self._refresh_all_of_choices()
        self.set_editing_enabled(self._editing_enabled)
        self._refresh_row_controls()
        self._sync_advanced_state(self._advanced_toggle.isChecked())
        self._set_dirty(False)

    def build_updated_command_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
        updated = dumps_for_clone(base_data)
        if self._inputs_editable:
            inputs: dict[str, dict[str, Any]] = {}
            seen: set[str] = set()
            for row in self._rows:
                input_id = row.input_id
                if not input_id:
                    raise ValueError("Input id cannot be blank.")
                if input_id in seen:
                    raise ValueError(f"Duplicate input id '{input_id}'.")
                seen.add(input_id)
                inputs[input_id] = row.build_spec()
            updated["inputs"] = inputs
            updated.pop("params", None)

        deferred_text = self._deferred_param_shapes_edit.toPlainText().strip()
        if deferred_text:
            try:
                deferred_value = loads_json_data(
                    deferred_text,
                    source_name=f"deferred_param_shapes for {self._command_id}",
                )
            except JsonDataDecodeError as exc:
                raise ValueError(f"deferred_param_shapes must be valid JSON.\n{exc}") from exc
            if not isinstance(deferred_value, dict):
                raise ValueError("deferred_param_shapes must be a JSON object.")
            updated["deferred_param_shapes"] = deferred_value
        else:
            updated.pop("deferred_param_shapes", None)

        if not self._commands_editable:
            if self._commands_base is None:
                updated.pop("commands", None)
            else:
                updated["commands"] = dumps_for_clone(self._commands_base)
        else:
            updated["commands"] = dumps_for_clone(self._commands)
        return updated

    def _add_input_row(
        self,
        input_id: str = "",
        spec: dict[str, Any] | None = None,
        *,
        mark_dirty: bool = True,
    ) -> _CommandInputRow:
        row = _CommandInputRow()
        row.changed.connect(self._on_input_row_changed)
        row.remove_requested.connect(self._on_remove_input_row)
        row.move_up_requested.connect(self._on_move_input_row_up)
        row.move_down_requested.connect(self._on_move_input_row_down)
        row.load_input(input_id, spec or {"type": "string"})
        row.set_editing_enabled(self._editing_enabled)
        self._rows.append(row)
        self._rows_layout.insertWidget(max(0, self._rows_layout.count() - 1), row)
        self._refresh_all_of_choices()
        self._refresh_row_controls()
        if mark_dirty and not self._loading:
            self._set_dirty(True)
        return row

    def _clear_input_rows(self) -> None:
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

    def _refresh_all_of_choices(self) -> None:
        previous: list[tuple[str, str]] = []
        for row in self._rows:
            row.refresh_of_choices(previous)
            previous.append((row.input_id, row.input_type))

    def _refresh_row_controls(self) -> None:
        last_index = len(self._rows) - 1
        for index, row in enumerate(self._rows):
            row.set_row_buttons_enabled(
                can_move_up=index > 0,
                can_move_down=index < last_index,
            )

    def _load_commands(self, raw_commands: Any) -> None:
        self._commands_base = dumps_for_clone(raw_commands)
        self._commands_editable = True
        if raw_commands is None:
            self._commands = []
            self._commands_warning.hide()
        elif isinstance(raw_commands, list):
            self._commands = dumps_for_clone(raw_commands)
            self._commands_warning.hide()
        else:
            self._commands = []
            self._commands_editable = False
            self._commands_warning.setText(
                "commands is not using a supported array shape. Use the Raw JSON tab to edit it."
            )
            self._commands_warning.show()
        self._sync_commands_summary()
        self.set_editing_enabled(self._editing_enabled)

    def _sync_commands_summary(self) -> None:
        if not self._commands_editable:
            self._commands_summary.setText("Raw JSON only")
            return
        count = len(self._commands)
        if count == 0:
            self._commands_summary.setText("No commands")
        elif count == 1:
            self._commands_summary.setText("1 command")
        else:
            self._commands_summary.setText(f"{count} commands")

    def _sync_advanced_state(self, checked: bool) -> None:
        set_count = 1 if self._deferred_param_shapes_edit.toPlainText().strip() else 0
        self._advanced_toggle.setText(
            f"Advanced ({set_count} set)" if set_count else "Advanced"
        )
        self._advanced_widget.setVisible(bool(checked))
        self._advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

    def _on_deferred_param_shapes_changed(self) -> None:
        self._sync_advanced_state(self._advanced_toggle.isChecked())
        self._on_changed()

    def _on_edit_commands(self) -> None:
        if not self._editing_enabled or not self._commands_editable:
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
        dialog.setWindowTitle(f"Edit Commands - {self._command_id}")
        dialog.load_commands(self._commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._commands = dialog.commands()
        self._sync_commands_summary()
        self._on_changed()

    def _on_input_row_changed(self) -> None:
        if self._loading:
            return
        self._refresh_all_of_choices()
        self._set_dirty(True)

    def _on_remove_input_row(self, row_obj: object) -> None:
        if not self._editing_enabled or not isinstance(row_obj, _CommandInputRow):
            return
        if row_obj not in self._rows:
            return
        self._rows.remove(row_obj)
        self._rows_layout.removeWidget(row_obj)
        row_obj.deleteLater()
        self._refresh_all_of_choices()
        self._refresh_row_controls()
        self._set_dirty(True)

    def _on_move_input_row_up(self, row_obj: object) -> None:
        self._move_input_row(row_obj, -1)

    def _on_move_input_row_down(self, row_obj: object) -> None:
        self._move_input_row(row_obj, 1)

    def _move_input_row(self, row_obj: object, delta: int) -> None:
        if not self._editing_enabled or not isinstance(row_obj, _CommandInputRow):
            return
        try:
            index = self._rows.index(row_obj)
        except ValueError:
            return
        new_index = index + delta
        if new_index < 0 or new_index >= len(self._rows):
            return
        self._rows[index], self._rows[new_index] = self._rows[new_index], self._rows[index]
        self._rows_layout.removeWidget(row_obj)
        self._rows_layout.insertWidget(new_index, row_obj)
        self._refresh_all_of_choices()
        self._refresh_row_controls()
        self._set_dirty(True)

    def _on_changed(self, *_args) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class ProjectCommandEditorWidget(QWidget):
    """Central-tab project command editor with focused fields and raw JSON."""

    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(
        self,
        content_id: str,
        file_path: Path,
        *,
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

        self._fields_editor = _ProjectCommandFieldsEditor(
            content_id,
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
        self._tabs.addTab(self._fields_editor, "Command Editor")
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
    def fields_editor(self) -> _ProjectCommandFieldsEditor:
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
            QMessageBox.warning(self, "Invalid Command Data", str(exc))

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
        updated = self._fields_editor.build_updated_command_data(base_data)
        text = json.dumps(updated, indent=2, ensure_ascii=False)
        self._raw_json.set_document_text(
            compose_json_file_text(
                text,
                original_text=self._raw_json.toPlainText(),
            ),
            dirty=True,
        )
        self._fields_editor.load_command_data(updated)
        self._set_dirty(True)

    def _reload_fields_from_saved_file(self) -> None:
        data = load_json_data(self._file_path)
        if not isinstance(data, dict):
            raise ValueError("Project command JSON must be a JSON object.")
        self._fields_editor.load_command_data(data)

    def _reload_fields_from_current_raw(self) -> None:
        self._fields_editor.load_command_data(self._current_raw_data())

    def _current_raw_data(self) -> dict[str, Any]:
        try:
            data = loads_json_data(
                self._raw_json.toPlainText(),
                source_name=str(self._file_path),
            )
        except JsonDataDecodeError as exc:
            raise ValueError(
                f"Raw JSON must be valid before command fields can apply.\n{exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("Project command JSON must be a JSON object.")
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

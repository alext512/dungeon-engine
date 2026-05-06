"""Dockable entity-instance editor with JSON and structured field tabs."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument
from area_editor.entity_field_coverage import ENTITY_INSTANCE_FIELDS_TAB_EXTRA_FIELDS
from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.widgets.dialogue_definition_dialog import (
    DialogueDefinitionDialog,
    EntityDialoguesDialog,
    normalize_entity_dialogues,
    rename_active_dialogue_value,
    rename_self_target_dialogue_id_references,
    summarize_entity_dialogues,
    summarize_dialogue_definition,
)
from area_editor.widgets.reference_picker_support import (
    EntityReferencePickerRequest,
    call_reference_picker_callback,
)
from area_editor.widgets.entity_structured_fields import (
    DEFAULT_ENTITY_COLOR,
    ENTITY_BOOL_DEFAULTS,
    ENTITY_FACING_VALUES,
    ENTITY_INT_DEFAULTS,
    build_input_map,
    build_entity_commands,
    build_inventory,
    build_persistence_policy,
    entity_command_command_list,
    parse_color,
    parse_entity_commands,
    parse_tag_list,
    parse_input_map,
    parse_inventory,
    parse_persistence_policy,
    replace_entity_command_command_list,
    suggested_entity_command_copy_name,
    suggested_entity_command_names,
    summarize_entity_commands,
)
from area_editor.widgets.command_list_dialog import CommandListDialog
from area_editor.widgets.entity_variables_table import EntityVariablesTable
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow

_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
_EXACT_TEMPLATE_TOKEN_RE = re.compile(
    r"^\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$"
)
_ENTITY_BOOL_DEFAULTS = ENTITY_BOOL_DEFAULTS
_ENTITY_INT_DEFAULTS = ENTITY_INT_DEFAULTS
_MANAGED_EXTRA_KEYS = set(ENTITY_INSTANCE_FIELDS_TAB_EXTRA_FIELDS)

_ENTITY_REFERENCE_PARAMETER_NAMES = {
    "entity_id",
    "source_entity_id",
    "actor_id",
    "caller_id",
    "target_id",
}
_ENTITY_COMMAND_PARAMETER_NAMES = {
    "target_press_command_id",
    "target_release_command_id",
    "target_activate_command_id",
    "target_deactivate_command_id",
    "on_completed_command_id",
    "on_uncompleted_command_id",
    "group_fill_command_id",
    "filled_command_id",
}
_AREA_REFERENCE_PARAMETER_NAMES = {
    "area_id",
    "target_area",
    "source_area_id",
    "destination_area_id",
}


@dataclass
class _ParameterFieldState:
    name: str
    spec: dict[str, Any] | None
    default_value: object
    explicit_original: bool
    control_kind: str
    explicit_override_enabled: bool
    edit: QLineEdit | None = None
    checkbox: QCheckBox | None = None
    picker_button: QPushButton | None = None
    action_button: QPushButton | None = None
    use_default_button: QPushButton | None = None
    status_label: QLabel | None = None
    summary_label: QLabel | None = None
    structured_value: object | None = None


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _set_row_visible(label: QWidget, field: QWidget, visible: bool) -> None:
    label.setVisible(visible)
    field.setVisible(visible)


def _parameter_placeholder_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _parse_parameter_text(text: str):
    stripped = text.strip()
    if not stripped:
        return None, False
    if stripped[0] in "[{":
        try:
            return json.loads(stripped), True
        except json.JSONDecodeError:
            return text, True
    if stripped in {"true", "false", "null"} or _JSON_NUMBER_RE.fullmatch(stripped):
        try:
            return json.loads(stripped), True
        except json.JSONDecodeError:
            return text, True
    return text, True


def _extract_exact_template_token_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _EXACT_TEMPLATE_TOKEN_RE.fullmatch(value.strip())
    if match is None:
        return None
    return match.group("braced") or match.group("plain")


def _filtered_unmanaged_extra(extra: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in extra.items()
        if key not in _MANAGED_EXTRA_KEYS
    }


def _parameter_reference_kind(name: str) -> str | None:
    normalized = str(name).strip()
    if not normalized:
        return None
    if normalized in _ENTITY_COMMAND_PARAMETER_NAMES:
        return None
    if normalized == "item_id" or normalized.endswith("_item_id"):
        return "item"
    if normalized == "dialogue_path" or normalized.endswith("_dialogue_path"):
        return "dialogue"
    if normalized == "command_id" or normalized.endswith("_command_id"):
        return "command"
    if normalized in _AREA_REFERENCE_PARAMETER_NAMES or normalized.endswith("_area_id"):
        return "area"
    if (
        normalized in _ENTITY_REFERENCE_PARAMETER_NAMES
        or normalized.endswith("_entity_id")
    ):
        return "entity"
    return None


def _parameter_spec_reference_kind(spec: object) -> str | None:
    if not isinstance(spec, dict):
        return None
    spec_type = str(spec.get("type", "")).strip()
    if spec_type == "area_id":
        return "area"
    if spec_type == "entity_id":
        return "entity"
    if spec_type == "entity_command_id":
        return "entity_command"
    if spec_type == "entity_dialogue_id":
        return "entity_dialogue"
    if spec_type == "visual_id":
        return "visual"
    if spec_type == "animation_id":
        return "animation"
    if spec_type == "item_id":
        return "item"
    if spec_type == "dialogue_path":
        return "dialogue"
    if spec_type == "project_command_id":
        return "command"
    if spec_type == "asset_path":
        return "asset"
    return None


def _parse_parameter_text_for_spec(name: str, text: str, spec: object):
    if not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
        return _parse_parameter_text(text)

    stripped = text.strip()
    if not stripped:
        return None, False

    spec_type = str(spec["type"]).strip()
    if spec_type in {
        "string",
        "text",
        "entity_id",
        "entity_command_id",
        "entity_dialogue_id",
        "visual_id",
        "animation_id",
        "area_id",
        "item_id",
        "dialogue_path",
        "project_command_id",
        "entity_template_id",
        "asset_path",
    }:
        return stripped, True

    if spec_type == "bool":
        lowered = stripped.lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"Parameter '{name}' must be true or false.")
        return lowered == "true", True

    if spec_type == "int":
        try:
            return int(stripped), True
        except ValueError as exc:
            raise ValueError(f"Parameter '{name}' must be an integer.") from exc

    if spec_type == "number":
        try:
            number = float(stripped)
        except ValueError as exc:
            raise ValueError(f"Parameter '{name}' must be a number.") from exc
        return int(number) if number.is_integer() else number, True

    if spec_type == "enum":
        return _parse_parameter_text(text)

    if spec_type in {"array", "json", "dialogue_definition", "color_rgb"}:
        try:
            parsed = loads_json_data(stripped, source_name=f"Parameter '{name}'")
        except JsonDataDecodeError as exc:
            raise ValueError(f"Parameter '{name}' must be valid JSON.\n{exc}") from exc
        if spec_type == "array" and not isinstance(parsed, list):
            raise ValueError(f"Parameter '{name}' must be a JSON array.")
        if spec_type == "dialogue_definition":
            if not isinstance(parsed, dict):
                raise ValueError(f"Parameter '{name}' must be a JSON object.")
            if not isinstance(parsed.get("segments"), list):
                raise ValueError(
                    f"Parameter '{name}' must include a 'segments' JSON array."
                )
        if spec_type == "color_rgb":
            if (
                not isinstance(parsed, list)
                or len(parsed) != 3
                or not all(isinstance(channel, int) for channel in parsed)
            ):
                raise ValueError(
                    f"Parameter '{name}' must be an RGB array of three integers."
                )
        return parsed, True

    return _parse_parameter_text(text)


class _EntityInstanceJsonEditor(QWidget):
    """Shows one selected entity instance as editable JSON."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        layout.addWidget(self._target_label)

        self._editor = QPlainTextEdit()
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)
        self._editor.setReadOnly(True)
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._entity_id: str | None = None
        self._editing_enabled = False
        self._dirty = False
        self._loading = False
        self._set_buttons_enabled(False)

    @property
    def entity_id(self) -> str | None:
        return self._entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def json_text(self) -> str:
        return self._editor.toPlainText()

    @property
    def editor(self) -> QPlainTextEdit:
        return self._editor

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled and self._entity_id is not None
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(self._entity_id is not None)
        self.editing_enabled_changed.emit(self._editing_enabled)

    def clear_entity(self) -> None:
        self._entity_id = None
        self._editing_enabled = False
        self._loading = True
        try:
            self._editor.setPlainText("")
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._set_dirty(False)
        self._editor.setReadOnly(True)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity_id = entity.id
        text = json.dumps(entity.to_dict(), indent=2, ensure_ascii=False)
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._set_dirty(False)
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(True)

    def set_json_text(self, text: str) -> None:
        self._loading = True
        try:
            self._editor.setPlainText(text)
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

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class _EntityInstanceParametersEditor(QWidget):
    """Focused editor for template parameters."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        outer.addWidget(self._target_label)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #a25b00;")
        self._warning_label.hide()
        outer.addWidget(self._warning_label)

        self._empty_label = QLabel("No template parameters for this entity.")
        self._empty_label.setStyleSheet("color: #666; font-style: italic;")
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        outer.addWidget(self._empty_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll, 1)

        container = QWidget()
        self._form = QFormLayout(container)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._scroll.setWidget(container)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self._template_catalog: TemplateCatalog | None = None
        self._entity: EntityDocument | None = None
        self._current_area_id: str | None = None
        self._loading = False
        self._dirty = False
        self._parameters_editable = True
        self._parameter_specs: dict[str, Any] = {}
        self._template_defaults: dict[str, Any] = {}
        self._parameter_fields: dict[str, _ParameterFieldState] = {}
        self._parameter_browse_buttons: dict[str, QPushButton] = {}
        self._parameter_edits: dict[str, QLineEdit] = {}
        self._reference_picker_callbacks: dict[
            str,
            Callable[..., str | None] | None,
        ] = {
            "area": None,
            "entity": None,
            "entity_command": None,
            "entity_dialogue": None,
            "item": None,
            "dialogue": None,
            "command": None,
            "project_command_inputs": None,
            "asset": None,
            "visual": None,
            "animation": None,
        }
        self._named_dialogues_edit_callback: (
            Callable[[], tuple[dict[str, dict[str, Any]], str | None] | None] | None
        ) = None
        self._dialogues_shortcut_visible = False
        self._dialogues_shortcut_value: dict[str, dict[str, Any]] = {}
        self._dialogues_shortcut_active: str | None = None
        self._dialogues_shortcut_summary: QLabel | None = None
        self._dialogues_shortcut_button: QPushButton | None = None
        self._hidden_bridge_parameter_names: set[str] = set()
        self._preserve_hidden_bridge_parameters = True
        self._set_buttons_enabled(False)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def has_parameters(self) -> bool:
        return bool(self._parameter_fields or self._dialogues_shortcut_visible)

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._template_catalog = catalog

    def set_area_context(self, area_id: str | None) -> None:
        self._current_area_id = str(area_id).strip() or None if area_id else None

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._reference_picker_callbacks = {
            "area": area_picker,
            "entity": entity_picker,
            "entity_command": entity_command_picker,
            "entity_dialogue": entity_dialogue_picker,
            "item": item_picker,
            "dialogue": dialogue_picker,
            "command": command_picker,
            "project_command_inputs": project_command_inputs_provider,
            "asset": asset_picker,
            "visual": visual_picker,
            "animation": animation_picker,
        }
        self._sync_entity_command_picker_buttons()

    def set_named_dialogues_edit_callback(
        self,
        callback: Callable[
            [],
            tuple[dict[str, dict[str, Any]], str | None] | None,
        ]
        | None,
    ) -> None:
        self._named_dialogues_edit_callback = callback

    def clear_entity(self) -> None:
        self._entity = None
        self._target_label.setText("Selected Entity: None")
        self._warning_label.hide()
        self._template_defaults = {}
        self._parameters_editable = True
        self._dialogues_shortcut_visible = False
        self._dialogues_shortcut_value = {}
        self._dialogues_shortcut_active = None
        self._dialogues_shortcut_summary = None
        self._dialogues_shortcut_button = None
        self._hidden_bridge_parameter_names = set()
        self._preserve_hidden_bridge_parameters = True
        self._clear_parameter_rows()
        self._set_empty_visible(False)
        self._set_dirty(False)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity = entity
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._rebuild_parameter_rows(entity)
        self._set_dirty(False)
        self._set_buttons_enabled(True)

    def build_parameters_value(self):
        if self._entity is None:
            return None
        if not self._parameters_editable:
            return self._entity.parameters
        parameters: dict[str, object] = {}
        for name, field in self._parameter_fields.items():
            if field.control_kind == "bool":
                if not field.explicit_override_enabled or field.checkbox is None:
                    continue
                parameters[name] = bool(field.checkbox.isChecked())
                continue
            if field.control_kind == "dialogue_definition":
                if not field.explicit_override_enabled:
                    continue
                parameters[name] = copy.deepcopy(self._dialogue_parameter_effective_value(field))
                continue
            if field.edit is None:
                continue
            value, keep = _parse_parameter_text_for_spec(
                name,
                field.edit.text(),
                field.spec,
            )
            if not keep:
                continue
            parameters[name] = value
        if (
            self._preserve_hidden_bridge_parameters
            and isinstance(self._entity.parameters, dict)
        ):
            for name in self._hidden_bridge_parameter_names:
                if name in self._entity.parameters:
                    parameters[name] = copy.deepcopy(self._entity.parameters[name])
        return parameters or None

    def _rebuild_parameter_rows(self, entity: EntityDocument) -> None:
        self._clear_parameter_rows()
        parameters = entity.parameters
        self._template_defaults = {}
        self._parameter_specs = {}
        self._dialogues_shortcut_visible = False
        self._dialogues_shortcut_value = {}
        self._dialogues_shortcut_active = None
        self._dialogues_shortcut_summary = None
        self._dialogues_shortcut_button = None
        self._hidden_bridge_parameter_names = set()
        self._preserve_hidden_bridge_parameters = True
        if parameters is not None and not isinstance(parameters, dict):
            self._parameters_editable = False
            self._warning_label.setText(
                "Parameters are not a JSON object for this entity. "
                "Use the JSON tab to edit them."
            )
            self._warning_label.show()
            self._set_empty_visible(True)
            return

        self._parameters_editable = True
        self._warning_label.hide()
        parameter_names: set[str] = set()
        dialogue_bridge_parameter_names: set[str] = set()
        if entity.template and self._template_catalog is not None:
            parameter_names.update(
                self._template_catalog.get_template_parameter_names(entity.template)
            )
            self._template_defaults = self._template_catalog.get_template_parameter_defaults(
                entity.template
            )
            self._parameter_specs = self._template_catalog.get_template_parameter_specs(
                entity.template
            )
            (
                self._dialogues_shortcut_value,
                self._dialogues_shortcut_active,
                dialogue_bridge_parameter_names,
            ) = self._compute_template_dialogues_shortcut(entity)
            self._dialogues_shortcut_visible = bool(self._dialogues_shortcut_value)
            if not self._dialogues_shortcut_visible:
                dialogue_bridge_parameter_names.clear()
        if isinstance(parameters, dict):
            parameter_names.update(parameters.keys())
        parameter_names.update(self._template_defaults.keys())
        parameter_names.update(self._parameter_specs.keys())

        parameter_names.difference_update(dialogue_bridge_parameter_names)
        self._hidden_bridge_parameter_names = set(dialogue_bridge_parameter_names)

        if not parameter_names and not self._dialogues_shortcut_visible:
            self._set_empty_visible(True)
            return

        self._set_empty_visible(False)
        if self._dialogues_shortcut_visible:
            self._add_dialogues_shortcut_row()
        for name in sorted(parameter_names):
            self._add_parameter_row(
                name,
                None if not isinstance(parameters, dict) else parameters.get(name),
                self._template_defaults.get(name),
                self._parameter_specs.get(name)
                if isinstance(self._parameter_specs.get(name), dict)
                else None,
            )
        self._sync_entity_command_picker_buttons()

    def _compute_template_dialogues_shortcut(
        self,
        entity: EntityDocument,
    ) -> tuple[dict[str, dict[str, Any]], str | None, set[str]]:
        if not entity.template or self._template_catalog is None:
            return {}, None, set()
        template = self._template_catalog.get_template_data(entity.template)
        raw_dialogues = template.get("dialogues")
        bridge_names: set[str] = set()
        if isinstance(raw_dialogues, dict):
            for raw_entry in raw_dialogues.values():
                if not isinstance(raw_entry, dict):
                    continue
                definition_name = _extract_exact_template_token_name(
                    raw_entry.get("dialogue_definition")
                )
                if definition_name:
                    bridge_names.add(definition_name)
                path_name = _extract_exact_template_token_name(
                    raw_entry.get("dialogue_path")
                )
                if path_name:
                    bridge_names.add(path_name)

        template_parameters = self._template_defaults or self._template_catalog.get_template_parameter_defaults(
            entity.template
        )
        resolved_parameters = copy.deepcopy(template_parameters)
        if isinstance(entity.parameters, dict):
            resolved_parameters.update(copy.deepcopy(entity.parameters))
        resolved_template = self._template_catalog.substitute_template_parameters(
            template,
            resolved_parameters,
        )
        try:
            dialogues = normalize_entity_dialogues(resolved_template.get("dialogues"))
        except ValueError:
            dialogues = {}
        active_dialogue = None
        raw_variables = resolved_template.get("variables")
        if isinstance(raw_variables, dict):
            active_value = str(raw_variables.get("active_dialogue", "")).strip()
            active_dialogue = active_value or None
        if not active_dialogue and len(dialogues) == 1:
            active_dialogue = next(iter(dialogues), None)
        return dialogues, active_dialogue, bridge_names

    def _add_dialogues_shortcut_row(self) -> None:
        label = QLabel("dialogues")
        summary_label = QLabel("")
        summary_label.setWordWrap(True)
        status_label = QLabel("Named entity-owned dialogues.")
        status_label.setStyleSheet("color: #666;")
        text_column = QWidget()
        text_layout = QVBoxLayout(text_column)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(summary_label)
        text_layout.addWidget(status_label)

        action_button = QPushButton("Edit...")
        action_button.clicked.connect(self._on_edit_dialogues_shortcut)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(text_column, 1)
        row_layout.addWidget(action_button)

        self._dialogues_shortcut_summary = summary_label
        self._dialogues_shortcut_button = action_button
        self._form.addRow(label, row_widget)
        self._sync_dialogues_shortcut_row()

    def _sync_dialogues_shortcut_row(self) -> None:
        if self._dialogues_shortcut_summary is None:
            return
        self._dialogues_shortcut_summary.setText(
            summarize_entity_dialogues(
                self._dialogues_shortcut_value,
                self._dialogues_shortcut_active,
            )
        )
        if self._dialogues_shortcut_button is not None:
            self._dialogues_shortcut_button.setEnabled(
                self._parameters_editable and self._named_dialogues_edit_callback is not None
            )

    def set_dialogues_shortcut_state(
        self,
        dialogues_value: object,
        active_dialogue: object,
    ) -> None:
        if not self._dialogues_shortcut_visible:
            return
        self._dialogues_shortcut_value = normalize_entity_dialogues(dialogues_value)
        active_name = str(active_dialogue).strip() if active_dialogue is not None else ""
        if not active_name and len(self._dialogues_shortcut_value) == 1:
            active_name = next(iter(self._dialogues_shortcut_value), "")
        self._dialogues_shortcut_active = active_name or None
        self._preserve_hidden_bridge_parameters = False
        self._sync_dialogues_shortcut_row()

    def _add_parameter_row(
        self,
        name: str,
        current_value: object,
        default_value: object,
        spec: dict[str, Any] | None,
    ) -> None:
        label = QLabel(name)
        spec_type = str(spec.get("type", "")).strip() if isinstance(spec, dict) else ""
        if spec_type == "bool":
            checkbox = QCheckBox()
            status_label = QLabel("")
            status_label.setStyleSheet("color: #666;")
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(checkbox)
            row_layout.addWidget(status_label)
            row_layout.addStretch(1)
            use_default_button = QPushButton("Use Default")
            row_layout.addWidget(use_default_button)

            explicit_override_enabled = current_value is not None
            bool_value = (
                bool(current_value)
                if current_value is not None
                else bool(default_value) if isinstance(default_value, bool) else False
            )
            blockers = [QSignalBlocker(checkbox)]
            checkbox.setChecked(bool_value)
            del blockers
            checkbox.toggled.connect(
                lambda _checked=False, parameter_name=name: self._on_bool_parameter_toggled(
                    parameter_name
                )
            )
            use_default_button.clicked.connect(
                lambda _checked=False, parameter_name=name: self._on_bool_parameter_reset(
                    parameter_name
                )
            )

            field = _ParameterFieldState(
                name=name,
                spec=spec,
                default_value=default_value,
                explicit_original=current_value is not None,
                control_kind="bool",
                explicit_override_enabled=explicit_override_enabled,
                checkbox=checkbox,
                use_default_button=use_default_button,
                status_label=status_label,
            )
            self._parameter_fields[name] = field
            self._form.addRow(label, row_widget)
            self._sync_bool_field_state(name)
            return

        if spec_type == "dialogue_definition":
            summary_label = QLabel("")
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet("color: #444;")
            status_label = QLabel("")
            status_label.setStyleSheet("color: #666;")
            action_button = QPushButton("Edit...")
            action_button.clicked.connect(
                lambda _checked=False, parameter_name=name: self._on_edit_dialogue_parameter(
                    parameter_name
                )
            )
            use_default_button = QPushButton("Use Default")
            use_default_button.clicked.connect(
                lambda _checked=False, parameter_name=name: self._on_dialogue_parameter_reset(
                    parameter_name
                )
            )

            text_column = QWidget()
            text_layout = QVBoxLayout(text_column)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)
            text_layout.addWidget(summary_label)
            text_layout.addWidget(status_label)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(text_column, 1)
            row_layout.addWidget(action_button)
            row_layout.addWidget(use_default_button)

            structured_value = (
                copy.deepcopy(current_value)
                if current_value is not None
                else copy.deepcopy(default_value)
            )
            field = _ParameterFieldState(
                name=name,
                spec=spec,
                default_value=default_value,
                explicit_original=current_value is not None,
                control_kind="dialogue_definition",
                explicit_override_enabled=current_value is not None,
                action_button=action_button,
                use_default_button=use_default_button,
                status_label=status_label,
                summary_label=summary_label,
                structured_value=structured_value,
            )
            self._parameter_fields[name] = field
            self._form.addRow(label, row_widget)
            self._sync_dialogue_parameter_state(name)
            return

        edit = QLineEdit()
        if current_value is None:
            edit.setText("")
            edit.setPlaceholderText(_parameter_placeholder_text(default_value))
        elif isinstance(current_value, str):
            edit.setText(current_value)
        else:
            edit.setText(json.dumps(current_value, ensure_ascii=False))
        edit.textChanged.connect(self._on_parameter_text_changed)

        picker_kind = self._picker_kind_for_parameter(name)
        picker_callback = (
            None if picker_kind is None else self._reference_picker_callbacks.get(picker_kind)
        )
        row_widget: QWidget = edit
        browse_button: QPushButton | None = None
        if picker_callback is not None:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(edit, 1)
            button_text = (
                "Pick..."
                if picker_kind in {"entity", "entity_command", "entity_dialogue"}
                else "Browse..."
            )
            browse_button = QPushButton(button_text)
            browse_button.clicked.connect(
                lambda _checked=False, parameter_name=name: self._on_pick_parameter_value(
                    parameter_name
                )
            )
            row_layout.addWidget(browse_button)
            self._parameter_browse_buttons[name] = browse_button
        field = _ParameterFieldState(
            name=name,
            spec=spec,
            default_value=default_value,
            explicit_original=current_value is not None,
            control_kind="text",
            explicit_override_enabled=current_value is not None,
            edit=edit,
            picker_button=browse_button,
        )
        self._parameter_fields[name] = field
        self._parameter_edits[name] = edit
        self._form.addRow(label, row_widget)

    def _picker_kind_for_parameter(self, name: str) -> str | None:
        spec = self._parameter_specs.get(name)
        if isinstance(spec, dict) and isinstance(spec.get("type"), str):
            return _parameter_spec_reference_kind(spec)
        return _parameter_reference_kind(name)

    @staticmethod
    def _parameter_spec_parent_name(spec: object) -> str:
        if not isinstance(spec, dict):
            return ""
        return str(spec.get("of", "")).strip()

    def _parameter_parent_name_for_type(self, name: str, parent_type: str) -> str:
        field = self._parameter_fields.get(name)
        parent_name = self._parameter_spec_parent_name(field.spec if field else None)
        if not parent_name:
            return ""
        parent_field = self._parameter_fields.get(parent_name)
        parent_spec = parent_field.spec if parent_field is not None else None
        if not isinstance(parent_spec, dict):
            return ""
        if str(parent_spec.get("type", "")).strip() != parent_type:
            return ""
        return parent_name

    def _parameter_effective_text_value(self, name: str) -> str:
        field = self._parameter_fields.get(name)
        if field is None:
            return ""
        if field.edit is not None:
            text = field.edit.text().strip()
            if text:
                return text
        if field.default_value is not None:
            return _parameter_placeholder_text(field.default_value).strip()
        return ""

    def _entity_parent_value_for_parameter(self, name: str) -> str:
        direct_parent = self._parameter_parent_name_for_type(name, "entity_id")
        if direct_parent:
            return self._parameter_effective_text_value(direct_parent)
        visual_parent = self._parameter_parent_name_for_type(name, "visual_id")
        if visual_parent:
            entity_parent = self._parameter_parent_name_for_type(visual_parent, "entity_id")
            if entity_parent:
                return self._parameter_effective_text_value(entity_parent)
        field = self._parameter_fields.get(name)
        spec_type = (
            str(field.spec.get("type", "")).strip()
            if field is not None and isinstance(field.spec, dict)
            else ""
        )
        if spec_type in {"visual_id", "animation_id"} and self._entity is not None:
            return self._entity.id
        return ""

    def _visual_parent_value_for_parameter(self, name: str) -> str:
        visual_parent = self._parameter_parent_name_for_type(name, "visual_id")
        if visual_parent:
            return self._parameter_effective_text_value(visual_parent)
        return ""

    def _clear_parameter_rows(self) -> None:
        self._parameter_fields.clear()
        self._parameter_browse_buttons.clear()
        self._parameter_edits.clear()
        while self._form.rowCount() > 0:
            self._form.removeRow(0)

    def _set_empty_visible(self, visible: bool) -> None:
        self._empty_label.setVisible(visible)
        self._scroll.setVisible(not visible)

    def _on_parameter_text_changed(self, *_args) -> None:
        if self._loading:
            return
        self._sync_entity_command_picker_buttons()
        self._set_dirty(True)

    def _on_bool_parameter_toggled(self, name: str) -> None:
        if self._loading:
            return
        field = self._parameter_fields.get(name)
        if field is None:
            return
        field.explicit_override_enabled = True
        self._sync_bool_field_state(name)
        self._set_dirty(True)

    def _on_bool_parameter_reset(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None or field.checkbox is None:
            return
        self._loading = True
        try:
            field.explicit_override_enabled = False
            reset_value = (
                bool(field.default_value)
                if isinstance(field.default_value, bool)
                else False
            )
            field.checkbox.setChecked(reset_value)
        finally:
            self._loading = False
        self._sync_bool_field_state(name)
        self._set_dirty(True)

    def _dialogue_parameter_effective_value(self, field: _ParameterFieldState) -> object:
        if field.structured_value is not None:
            return field.structured_value
        if field.default_value is not None:
            return field.default_value
        return {"segments": []}

    def _sync_dialogue_parameter_state(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None:
            return
        effective_value = self._dialogue_parameter_effective_value(field)
        if field.summary_label is not None:
            field.summary_label.setText(summarize_dialogue_definition(effective_value))
        if field.status_label is not None:
            if field.explicit_override_enabled:
                field.status_label.setText("authored override")
            elif field.default_value is not None:
                field.status_label.setText("using template default")
            else:
                field.status_label.setText("unset")
        if field.use_default_button is not None:
            field.use_default_button.setEnabled(
                field.explicit_override_enabled and field.default_value is not None
            )

    def _on_edit_dialogues_shortcut(self) -> None:
        if self._named_dialogues_edit_callback is None:
            return
        updated = self._named_dialogues_edit_callback()
        if updated is None:
            return
        dialogues_value, active_dialogue = updated
        self._dialogues_shortcut_value = copy.deepcopy(dialogues_value)
        self._preserve_hidden_bridge_parameters = False
        active_name = str(active_dialogue).strip() if active_dialogue is not None else ""
        if not active_name and len(self._dialogues_shortcut_value) == 1:
            active_name = next(iter(self._dialogues_shortcut_value), "")
        self._dialogues_shortcut_active = active_name or None
        self._sync_dialogues_shortcut_row()

    def _open_dialogue_definition_dialog(
        self,
        name: str,
        value: object,
    ) -> dict[str, Any] | None:
        dialog = DialogueDefinitionDialog(
            self,
            area_picker=self._reference_picker_callbacks.get("area"),
            asset_picker=self._reference_picker_callbacks.get("asset"),
            entity_picker=self._reference_picker_callbacks.get("entity"),
            entity_command_picker=self._reference_picker_callbacks.get("entity_command"),
            entity_dialogue_picker=self._reference_picker_callbacks.get("entity_dialogue"),
            item_picker=self._reference_picker_callbacks.get("item"),
            dialogue_picker=self._reference_picker_callbacks.get("dialogue"),
            command_picker=self._reference_picker_callbacks.get("command"),
            project_command_inputs_provider=self._reference_picker_callbacks.get(
                "project_command_inputs"
            ),
            visual_picker=self._reference_picker_callbacks.get("visual"),
            animation_picker=self._reference_picker_callbacks.get("animation"),
            current_entity_id=self._entity.id if self._entity is not None else None,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names(),
            current_entity_dialogue_names=list(self._dialogues_shortcut_value.keys()),
        )
        dialog.setWindowTitle(f"Edit Dialogue: {name}")
        dialog.load_definition(value)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.definition()

    def _on_edit_dialogue_parameter(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None:
            return
        updated = self._open_dialogue_definition_dialog(
            name,
            self._dialogue_parameter_effective_value(field),
        )
        if updated is None:
            return
        field.structured_value = copy.deepcopy(updated)
        field.explicit_override_enabled = True
        self._sync_dialogue_parameter_state(name)
        self._set_dirty(True)

    def _on_dialogue_parameter_reset(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None:
            return
        field.explicit_override_enabled = False
        field.structured_value = copy.deepcopy(field.default_value)
        self._sync_dialogue_parameter_state(name)
        self._set_dirty(True)

    def _sync_bool_field_state(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None:
            return
        if field.status_label is not None:
            if field.explicit_override_enabled:
                field.status_label.setText("authored")
            elif isinstance(field.default_value, bool):
                field.status_label.setText(
                    f"default: {str(bool(field.default_value)).lower()}"
                )
            else:
                field.status_label.setText("unset")
        if field.use_default_button is not None:
            field.use_default_button.setEnabled(field.explicit_override_enabled)

    def _current_parameter_values_for_picker(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name, field in self._parameter_fields.items():
            if field.control_kind == "bool":
                if field.checkbox is None:
                    continue
                if field.explicit_override_enabled:
                    values[name] = bool(field.checkbox.isChecked())
                elif field.default_value is not None:
                    values[name] = field.default_value
                continue
            if field.edit is None:
                continue
            text = field.edit.text().strip()
            if text:
                values[name] = text
            elif field.default_value is not None:
                values[name] = field.default_value
        return values

    def _current_entity_command_names(self) -> list[str]:
        names: set[str] = set()
        if (
            self._entity is not None
            and self._entity.template
            and self._template_catalog is not None
        ):
            names.update(
                self._template_catalog.get_template_entity_command_names(
                    self._entity.template
                )
            )
        raw_entity_commands = (
            self._entity._extra.get("entity_commands")
            if self._entity is not None and isinstance(self._entity._extra, dict)
            else None
        )
        try:
            names.update(parse_entity_commands(raw_entity_commands).keys())
        except ValueError:
            pass
        return sorted(str(name).strip() for name in names if str(name).strip())

    def _sync_entity_command_picker_buttons(self) -> None:
        current_values = self._current_parameter_values_for_picker()
        for name, field in self._parameter_fields.items():
            if field.picker_button is None:
                continue
            spec_type = (
                str(field.spec.get("type", "")).strip()
                if isinstance(field.spec, dict)
                else ""
            )
            if spec_type not in {
                "entity_command_id",
                "entity_dialogue_id",
                "visual_id",
                "animation_id",
            }:
                area_parameter = self._parameter_spec_parent_name(field.spec)
                if spec_type == "entity_id" and area_parameter:
                    area_value = str(current_values.get(area_parameter, "")).strip()
                    enabled = bool(area_value)
                    field.picker_button.setEnabled(enabled)
                    field.picker_button.setToolTip(
                        "" if enabled else "Pick the target area first."
                    )
                else:
                    field.picker_button.setEnabled(True)
                    field.picker_button.setToolTip("")
                continue
            if spec_type == "animation_id":
                visual_value = self._visual_parent_value_for_parameter(name)
                entity_value = self._entity_parent_value_for_parameter(name)
                enabled = bool(entity_value and visual_value)
                missing = "target visual" if entity_value else "target entity"
                field.picker_button.setEnabled(enabled)
                field.picker_button.setToolTip(
                    "" if enabled else f"Pick the {missing} first."
                )
                continue
            entity_value = self._entity_parent_value_for_parameter(name)
            enabled = bool(entity_value)
            field.picker_button.setEnabled(enabled)
            field.picker_button.setToolTip(
                "" if enabled else "Pick the target entity first."
            )

    def _on_pick_parameter_value(self, name: str) -> None:
        field = self._parameter_fields.get(name)
        if field is None or field.edit is None:
            return
        picker_kind = self._picker_kind_for_parameter(name)
        if picker_kind is None:
            return
        callback = self._reference_picker_callbacks.get(picker_kind)
        if callback is None:
            return
        parameter_values = self._current_parameter_values_for_picker()
        if picker_kind in {"entity_command", "entity_dialogue", "visual", "animation"}:
            entity_value = self._entity_parent_value_for_parameter(name)
            if entity_value:
                parameter_values.setdefault("entity_id", entity_value)
        if picker_kind == "animation":
            visual_value = self._visual_parent_value_for_parameter(name)
            if visual_value:
                parameter_values.setdefault("visual_id", visual_value)
        request = EntityReferencePickerRequest(
            parameter_name=name,
            current_value=field.edit.text().strip(),
            parameter_spec=field.spec,
            current_area_id=self._current_area_id,
            entity_id=self._entity.id if self._entity is not None else None,
            entity_template_id=self._entity.template if self._entity is not None else None,
            parameter_values=parameter_values,
        )
        selected = call_reference_picker_callback(
            callback,
            field.edit.text().strip(),
            request=request,
        )
        if selected:
            field.edit.setText(selected)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class _EntityInstanceFieldsEditor(QWidget):
    """Structured editor for high-value entity instance fields."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    named_dialogues_changed = Signal(object, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        outer.addWidget(self._target_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll, 1)

        container = QWidget()
        self._form = QFormLayout(container)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._scroll.setWidget(container)

        self._form.addRow(_section_label("Identity"))
        self._id_label = QLabel("id")
        self._id_edit = QLineEdit()
        self._form.addRow(self._id_label, self._id_edit)

        self._template_label_title = QLabel("template")
        self._template_label = QLineEdit()
        self._template_label.setReadOnly(True)
        self._template_label.setText("-")
        self._form.addRow(self._template_label_title, self._template_label)

        self._kind_label = QLabel("kind")
        self._kind_edit = QLineEdit()
        self._form.addRow(self._kind_label, self._kind_edit)

        self._tags_label = QLabel("tags")
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("comma,separated,tags")
        self._form.addRow(self._tags_label, self._tags_edit)

        self._form.addRow(_section_label("Position"))
        self._space_label_title = QLabel("space")
        self._space_label = QLabel("world")
        self._form.addRow(self._space_label_title, self._space_label)

        self._scope_label = QLabel("scope")
        self._scope_combo = QComboBox()
        self._scope_combo.addItems(["area", "global"])
        self._form.addRow(self._scope_label, self._scope_combo)

        self._x_label = QLabel("grid_x")
        self._x_spin = QSpinBox()
        self._x_spin.setRange(0, 0)
        self._form.addRow(self._x_label, self._x_spin)

        self._y_label = QLabel("grid_y")
        self._y_spin = QSpinBox()
        self._y_spin.setRange(0, 0)
        self._form.addRow(self._y_label, self._y_spin)

        self._pixel_x_label = QLabel("pixel_x")
        self._pixel_x_row = QWidget()
        self._pixel_x_check = QCheckBox("Use pixel offset")
        self._pixel_x_spin = QSpinBox()
        self._pixel_x_spin.setRange(-999999, 999999)
        pixel_x_layout = QHBoxLayout(self._pixel_x_row)
        pixel_x_layout.setContentsMargins(0, 0, 0, 0)
        pixel_x_layout.addWidget(self._pixel_x_check)
        pixel_x_layout.addWidget(self._pixel_x_spin, 1)
        self._form.addRow(self._pixel_x_label, self._pixel_x_row)

        self._pixel_y_label = QLabel("pixel_y")
        self._pixel_y_row = QWidget()
        self._pixel_y_check = QCheckBox("Use pixel offset")
        self._pixel_y_spin = QSpinBox()
        self._pixel_y_spin.setRange(-999999, 999999)
        pixel_y_layout = QHBoxLayout(self._pixel_y_row)
        pixel_y_layout.setContentsMargins(0, 0, 0, 0)
        pixel_y_layout.addWidget(self._pixel_y_check)
        pixel_y_layout.addWidget(self._pixel_y_spin, 1)
        self._form.addRow(self._pixel_y_label, self._pixel_y_row)

        self._facing_label = QLabel("facing")
        self._facing_combo = QComboBox()
        self._facing_combo.addItems(list(ENTITY_FACING_VALUES))
        self._form.addRow(self._facing_label, self._facing_combo)

        self._form.addRow(_section_label("Physics / Interaction"))

        self._solid_label = QLabel("solid")
        self._solid_check = QCheckBox()
        self._form.addRow(self._solid_label, self._solid_check)

        self._pushable_label = QLabel("pushable")
        self._pushable_check = QCheckBox()
        self._form.addRow(self._pushable_label, self._pushable_check)

        self._weight_label = QLabel("weight")
        self._weight_spin = QSpinBox()
        self._weight_spin.setRange(1, 999999)
        self._form.addRow(self._weight_label, self._weight_spin)

        self._push_strength_label = QLabel("push_strength")
        self._push_strength_spin = QSpinBox()
        self._push_strength_spin.setRange(0, 999999)
        self._form.addRow(self._push_strength_label, self._push_strength_spin)

        self._collision_push_strength_label = QLabel("collision_push_strength")
        self._collision_push_strength_spin = QSpinBox()
        self._collision_push_strength_spin.setRange(0, 999999)
        self._form.addRow(
            self._collision_push_strength_label,
            self._collision_push_strength_spin,
        )

        self._interactable_label = QLabel("interactable")
        self._interactable_check = QCheckBox()
        self._form.addRow(self._interactable_label, self._interactable_check)

        self._interaction_priority_label = QLabel("interaction_priority")
        self._interaction_priority_spin = QSpinBox()
        self._interaction_priority_spin.setRange(0, 999999)
        self._form.addRow(
            self._interaction_priority_label,
            self._interaction_priority_spin,
        )

        self._form.addRow(_section_label("Visibility"))

        self._present_label = QLabel("present")
        self._present_check = QCheckBox()
        self._form.addRow(self._present_label, self._present_check)

        self._visible_label = QLabel("visible")
        self._visible_check = QCheckBox()
        self._form.addRow(self._visible_label, self._visible_check)

        self._entity_commands_enabled_label = QLabel("entity_commands_enabled")
        self._entity_commands_enabled_check = QCheckBox()
        self._form.addRow(
            self._entity_commands_enabled_label,
            self._entity_commands_enabled_check,
        )

        self._form.addRow(_section_label("Color / Tint"))
        self._color_warning = QLabel("")
        self._color_warning.setWordWrap(True)
        self._color_warning.setStyleSheet("color: #a25b00;")
        self._color_warning.hide()
        self._form.addRow(self._color_warning)

        self._color_check_label = QLabel("color")
        self._color_check = QCheckBox("Use custom RGB color")
        self._form.addRow(self._color_check_label, self._color_check)

        self._color_rgb_label = QLabel("rgb")
        self._color_rgb_row = QWidget()
        color_layout = QHBoxLayout(self._color_rgb_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self._color_red_spin = QSpinBox()
        self._color_red_spin.setRange(0, 255)
        self._color_red_spin.setPrefix("R ")
        self._color_green_spin = QSpinBox()
        self._color_green_spin.setRange(0, 255)
        self._color_green_spin.setPrefix("G ")
        self._color_blue_spin = QSpinBox()
        self._color_blue_spin.setRange(0, 255)
        self._color_blue_spin.setPrefix("B ")
        color_layout.addWidget(self._color_red_spin)
        color_layout.addWidget(self._color_green_spin)
        color_layout.addWidget(self._color_blue_spin)
        self._form.addRow(self._color_rgb_label, self._color_rgb_row)

        self._render_note = QLabel("Render properties are in the Render Properties panel ->")
        self._render_note.setStyleSheet("color: #666; font-style: italic;")
        self._render_note.setWordWrap(True)
        self._form.addRow(self._render_note)

        self._input_routing_label = _section_label("Input Routing")
        self._input_routing_label.hide()
        self._form.addRow(self._input_routing_label)
        self._input_map_warning = QLabel("")
        self._input_map_warning.setWordWrap(True)
        self._input_map_warning.setStyleSheet("color: #a25b00;")
        self._input_map_warning.hide()
        self._form.addRow(self._input_map_warning)

        self._input_map_note = QLabel(
            "Optional JSON object mapping logical actions to entity-command names."
        )
        self._input_map_note.setWordWrap(True)
        self._input_map_note.setStyleSheet("color: #666; font-style: italic;")
        self._input_map_note.hide()
        self._form.addRow(self._input_map_note)

        self._input_map_text = QPlainTextEdit()
        self._input_map_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._input_map_text.setFixedHeight(100)
        self._input_map_text.setPlaceholderText(
            '{\n'
            '  "interact": "interact",\n'
            '  "menu": "menu"\n'
            '}'
        )
        input_map_font = QFont("Consolas", 10)
        input_map_font.setStyleHint(QFont.StyleHint.Monospace)
        self._input_map_text.setFont(input_map_font)
        self._input_map_text.hide()
        self._form.addRow(self._input_map_text)

        self._form.addRow(_section_label("Entity Commands"))
        self._entity_commands_warning = QLabel("")
        self._entity_commands_warning.setWordWrap(True)
        self._entity_commands_warning.setStyleSheet("color: #a25b00;")
        self._entity_commands_warning.hide()
        self._form.addRow(self._entity_commands_warning)

        self._entity_commands_note = QLabel(
            "Optional JSON object mapping entity-command names to command arrays "
            "or {enabled, commands} objects. Standard hooks: interact, "
            "on_blocked, on_occupant_enter, on_occupant_leave."
        )
        self._entity_commands_note.setWordWrap(True)
        self._entity_commands_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._entity_commands_note)

        entity_commands_controls = QHBoxLayout()
        self._entity_commands_summary = QLabel("No entity commands")
        entity_commands_controls.addWidget(self._entity_commands_summary, 1)
        self._add_entity_command_button = QPushButton("Add...")
        self._add_entity_command_button.clicked.connect(self._on_add_entity_command_clicked)
        entity_commands_controls.addWidget(self._add_entity_command_button)
        self._edit_entity_command_button = QPushButton("Edit...")
        self._edit_entity_command_button.clicked.connect(self._on_edit_entity_command_clicked)
        entity_commands_controls.addWidget(self._edit_entity_command_button)
        self._duplicate_entity_command_button = QPushButton("Duplicate...")
        self._duplicate_entity_command_button.clicked.connect(
            self._on_duplicate_entity_command_clicked
        )
        entity_commands_controls.addWidget(self._duplicate_entity_command_button)
        self._remove_entity_command_button = QPushButton("Remove")
        self._remove_entity_command_button.clicked.connect(
            self._on_remove_entity_command_clicked
        )
        entity_commands_controls.addWidget(self._remove_entity_command_button)
        entity_commands_controls_widget = QWidget()
        entity_commands_controls_widget.setLayout(entity_commands_controls)
        self._form.addRow(entity_commands_controls_widget)

        self._entity_commands_text = QPlainTextEdit()
        self._entity_commands_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._entity_commands_text.setFixedHeight(140)
        self._entity_commands_text.setPlaceholderText(
            '{\n'
            '  "interact": [\n'
            '    {"type": "run_project_command", "command_id": "commands/example"}\n'
            "  ]\n"
            "}"
        )
        entity_commands_font = QFont("Consolas", 10)
        entity_commands_font.setStyleHint(QFont.StyleHint.Monospace)
        self._entity_commands_text.setFont(entity_commands_font)
        self._form.addRow(self._entity_commands_text)

        self._parameters_section_label = _section_label("Parameters")
        self._form.addRow(self._parameters_section_label)
        self._parameter_warning = QLabel("")
        self._parameter_warning.setWordWrap(True)
        self._parameter_warning.setStyleSheet("color: #a25b00;")
        self._parameter_warning.hide()
        self._form.addRow(self._parameter_warning)

        self._parameters_widget = QWidget()
        self._parameters_layout = QFormLayout(self._parameters_widget)
        self._parameters_layout.setContentsMargins(0, 0, 0, 0)
        self._parameters_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._form.addRow(self._parameters_widget)

        self._form.addRow(_section_label("Dialogues"))
        self._dialogues_warning = QLabel("")
        self._dialogues_warning.setWordWrap(True)
        self._dialogues_warning.setStyleSheet("color: #a25b00;")
        self._dialogues_warning.hide()
        self._form.addRow(self._dialogues_warning)

        self._dialogues_note = QLabel(
            "Manage named entity-owned dialogues here. Mark one active to drive "
            "`open_entity_dialogue` when no dialogue id is passed."
        )
        self._dialogues_note.setWordWrap(True)
        self._dialogues_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._dialogues_note)

        self._dialogues_row_label = QLabel("dialogues")
        self._dialogues_row = QWidget()
        dialogues_row_layout = QHBoxLayout(self._dialogues_row)
        dialogues_row_layout.setContentsMargins(0, 0, 0, 0)
        self._dialogues_summary = QLabel("No dialogues")
        self._dialogues_summary.setWordWrap(True)
        dialogues_row_layout.addWidget(self._dialogues_summary, 1)
        self._dialogues_edit_button = QPushButton("Edit...")
        self._dialogues_edit_button.clicked.connect(self._on_edit_dialogues_clicked)
        dialogues_row_layout.addWidget(self._dialogues_edit_button)
        self._form.addRow(self._dialogues_row_label, self._dialogues_row)

        self._form.addRow(_section_label("Variables"))
        self._variables_note = QLabel(
            "Entity variables. Use plain text for strings, or JSON literals for "
            "numbers, true/false, null, arrays, and objects."
        )
        self._variables_note.setWordWrap(True)
        self._variables_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._variables_note)

        self._variables_warning = QLabel("")
        self._variables_warning.setWordWrap(True)
        self._variables_warning.setStyleSheet("color: #a25b00;")
        self._variables_warning.hide()
        self._form.addRow(self._variables_warning)

        self._variables_table = EntityVariablesTable(
            empty_message="No instance variables defined."
        )
        self._variables_table.changed.connect(self._on_variables_table_changed)
        self._form.addRow(self._variables_table)

        self._variables_text = QPlainTextEdit()
        self._variables_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._variables_text.setFixedHeight(120)
        self._variables_text.setPlaceholderText("{\n  \"key\": true\n}")
        variables_font = QFont("Consolas", 10)
        variables_font.setStyleHint(QFont.StyleHint.Monospace)
        self._variables_text.setFont(variables_font)
        self._variables_text.hide()
        self._form.addRow(self._variables_text)

        self._form.addRow(_section_label("Inventory"))
        self._inventory_warning = QLabel("")
        self._inventory_warning.setWordWrap(True)
        self._inventory_warning.setStyleSheet("color: #a25b00;")
        self._inventory_warning.hide()
        self._form.addRow(self._inventory_warning)

        self._inventory_check_label = QLabel("inventory")
        self._inventory_check = QCheckBox("Define entity-owned inventory")
        self._form.addRow(self._inventory_check_label, self._inventory_check)

        self._inventory_max_stacks_label = QLabel("max_stacks")
        self._inventory_max_stacks_spin = QSpinBox()
        self._inventory_max_stacks_spin.setRange(0, 999999)
        self._form.addRow(
            self._inventory_max_stacks_label,
            self._inventory_max_stacks_spin,
        )

        self._inventory_stacks_note = QLabel(
            "Optional stack array. Each stack needs item_id and quantity."
        )
        self._inventory_stacks_note.setWordWrap(True)
        self._inventory_stacks_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow("stacks", self._inventory_stacks_note)

        self._inventory_stacks_text = QPlainTextEdit()
        self._inventory_stacks_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._inventory_stacks_text.setFixedHeight(120)
        self._inventory_stacks_text.setPlaceholderText(
            "[\n"
            "  {\n"
            '    "item_id": "items/light_orb",\n'
            '    "quantity": 1\n'
            "  }\n"
            "]"
        )
        inventory_font = QFont("Consolas", 10)
        inventory_font.setStyleHint(QFont.StyleHint.Monospace)
        self._inventory_stacks_text.setFont(inventory_font)
        self._form.addRow(self._inventory_stacks_text)

        self._form.addRow(_section_label("Visuals"))
        self._visuals_note = QLabel(
            "Instance-level visuals override. Use JSON array syntax."
        )
        self._visuals_note.setWordWrap(True)
        self._visuals_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._visuals_note)

        self._visuals_text = QPlainTextEdit()
        self._visuals_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._visuals_text.setFixedHeight(140)
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
        visuals_font = QFont("Consolas", 10)
        visuals_font.setStyleHint(QFont.StyleHint.Monospace)
        self._visuals_text.setFont(visuals_font)
        self._form.addRow(self._visuals_text)

        self._form.addRow(_section_label("Persistence"))
        self._persistence_warning = QLabel("")
        self._persistence_warning.setWordWrap(True)
        self._persistence_warning.setStyleSheet("color: #a25b00;")
        self._persistence_warning.hide()
        self._form.addRow(self._persistence_warning)

        self._persistence_entity_state_label = QLabel("Default save behavior")
        self._persistence_entity_state_check = QCheckBox(
            "Save this entity's changes by default"
        )
        self._form.addRow(
            self._persistence_entity_state_label,
            self._persistence_entity_state_check,
        )

        self._persistence_variables_note = QLabel(
            "Entity variables are listed automatically. Choose a save rule only "
            "when a variable should ignore the default above."
        )
        self._persistence_variables_note.setWordWrap(True)
        self._persistence_variables_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._persistence_variables_note)

        persistence_buttons = QHBoxLayout()
        self._add_persistence_variable_button = QPushButton("Add Unlisted Variable")
        self._add_persistence_variable_button.clicked.connect(
            self._on_add_persistence_variable_clicked
        )
        persistence_buttons.addWidget(self._add_persistence_variable_button)
        self._remove_persistence_variable_button = QPushButton("Clear Rule")
        self._remove_persistence_variable_button.clicked.connect(
            self._on_remove_persistence_variable_clicked
        )
        persistence_buttons.addWidget(self._remove_persistence_variable_button)
        persistence_buttons.addStretch(1)
        persistence_buttons_widget = QWidget()
        persistence_buttons_widget.setLayout(persistence_buttons)
        self._form.addRow(persistence_buttons_widget)

        self._persistence_variables_table = QTableWidget(0, 2)
        self._persistence_variables_table.setHorizontalHeaderLabels(
            ["Variable", "Save Rule"]
        )
        self._persistence_variables_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._persistence_variables_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._persistence_variables_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._persistence_variables_table.horizontalHeader().setStretchLastSection(True)
        self._persistence_variables_table.setFixedHeight(140)
        self._persistence_variables_table.cellChanged.connect(
            self._on_persistence_variables_table_changed
        )
        self._persistence_variables_table.currentCellChanged.connect(
            lambda *_args: self._set_persistence_controls_enabled(
                self._persistence_editable
            )
        )
        self._persistence_variables_table.customContextMenuRequested.connect(
            self._show_persistence_variables_context_menu
        )
        self._form.addRow(self._persistence_variables_table)

        self._persistence_empty_label = QLabel(
            "No variables are defined for this entity. Add variables on this editor's "
            "Variables section or add an unlisted variable only when commands create it later."
        )
        self._persistence_empty_label.setWordWrap(True)
        self._persistence_empty_label.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow(self._persistence_empty_label)

        self._persistence_variables_text = QPlainTextEdit()
        self._persistence_variables_text.hide()
        self._persistence_variables_text.textChanged.connect(
            self._on_legacy_persistence_variables_text_changed
        )

        self._form.addRow(_section_label("Extra"))
        self._extra_label = QLabel("extra")
        self._extra_text = QPlainTextEdit()
        self._extra_text.setReadOnly(True)
        self._extra_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        extra_font = QFont("Consolas", 10)
        extra_font.setStyleHint(QFont.StyleHint.Monospace)
        self._extra_text.setFont(extra_font)
        self._extra_text.setMaximumBlockCount(0)
        self._extra_text.setFixedHeight(120)
        self._form.addRow(self._extra_label, self._extra_text)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self._template_catalog: TemplateCatalog | None = None
        self._entity: EntityDocument | None = None
        self._effective_space = "world"
        self._effective_field_defaults = self._default_managed_field_defaults()
        self._current_area_id: str | None = None
        self._loading = False
        self._dirty = False
        self._area_width = 0
        self._area_height = 0
        self._parameter_edits: dict[str, QLineEdit] = {}
        self._parameter_browse_buttons: dict[str, QPushButton] = {}
        self._parameter_specs: dict[str, Any] = {}
        self._reference_picker_callbacks: dict[
            str,
            Callable[..., str | None] | None,
        ] = {
            "area": None,
            "entity": None,
            "entity_command": None,
            "item": None,
            "dialogue": None,
            "command": None,
            "asset": None,
        }
        self._parameters_editable = True
        self._color_editable = True
        self._input_map_editable = True
        self._entity_commands_editable = True
        self._inventory_editable = True
        self._variables_editable = True
        self._persistence_editable = True
        self._dialogues_editable = True
        self._dialogues_value: dict[str, dict[str, Any]] = {}
        self._dialogues_default_value: dict[str, dict[str, Any]] = {}
        self._template_active_dialogue_default: str | None = None

        self._id_edit.textChanged.connect(self._on_field_changed)
        self._kind_edit.textChanged.connect(self._on_field_changed)
        self._tags_edit.textChanged.connect(self._on_field_changed)
        self._scope_combo.currentIndexChanged.connect(self._on_field_changed)
        self._x_spin.valueChanged.connect(self._on_field_changed)
        self._y_spin.valueChanged.connect(self._on_field_changed)
        self._pixel_x_check.toggled.connect(self._on_pixel_check_toggled)
        self._pixel_y_check.toggled.connect(self._on_pixel_check_toggled)
        self._pixel_x_spin.valueChanged.connect(self._on_field_changed)
        self._pixel_y_spin.valueChanged.connect(self._on_field_changed)
        self._facing_combo.currentIndexChanged.connect(self._on_field_changed)
        self._solid_check.toggled.connect(self._on_field_changed)
        self._pushable_check.toggled.connect(self._on_field_changed)
        self._weight_spin.valueChanged.connect(self._on_field_changed)
        self._push_strength_spin.valueChanged.connect(self._on_field_changed)
        self._collision_push_strength_spin.valueChanged.connect(self._on_field_changed)
        self._interactable_check.toggled.connect(self._on_field_changed)
        self._interaction_priority_spin.valueChanged.connect(self._on_field_changed)
        self._present_check.toggled.connect(self._on_field_changed)
        self._visible_check.toggled.connect(self._on_field_changed)
        self._entity_commands_enabled_check.toggled.connect(self._on_field_changed)
        self._color_check.toggled.connect(self._on_color_check_toggled)
        self._color_red_spin.valueChanged.connect(self._on_field_changed)
        self._color_green_spin.valueChanged.connect(self._on_field_changed)
        self._color_blue_spin.valueChanged.connect(self._on_field_changed)
        self._input_map_text.textChanged.connect(self._on_field_changed)
        self._entity_commands_text.textChanged.connect(self._on_entity_commands_text_changed)
        self._variables_text.textChanged.connect(self._on_variables_text_changed)
        self._inventory_check.toggled.connect(self._on_inventory_check_toggled)
        self._inventory_max_stacks_spin.valueChanged.connect(self._on_field_changed)
        self._inventory_stacks_text.textChanged.connect(self._on_field_changed)
        self._visuals_text.textChanged.connect(self._on_field_changed)
        self._persistence_entity_state_check.toggled.connect(self._on_field_changed)

        self._set_buttons_enabled(False)
        self._clear_parameter_rows()
        self._parameters_section_label.hide()
        self._parameter_warning.hide()
        self._parameters_widget.hide()
        self._set_extra_visible(False)
        self._set_color_controls_enabled(True)
        self._set_entity_commands_controls_enabled(True)
        self._set_inventory_controls_enabled(True)
        self._sync_pixel_spin_enabled()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._template_catalog = catalog

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._reference_picker_callbacks = {
            "area": area_picker,
            "entity": entity_picker,
            "entity_command": entity_command_picker,
            "entity_dialogue": entity_dialogue_picker,
            "item": item_picker,
            "dialogue": dialogue_picker,
            "command": command_picker,
            "project_command_inputs": project_command_inputs_provider,
            "asset": asset_picker,
            "visual": visual_picker,
            "animation": animation_picker,
        }

    def set_area_context(self, area_id: str | None) -> None:
        self._current_area_id = str(area_id).strip() or None if area_id else None

    def set_area_bounds(self, width: int, height: int) -> None:
        self._area_width = max(0, width)
        self._area_height = max(0, height)
        max_x = max(0, self._area_width - 1)
        max_y = max(0, self._area_height - 1)
        blockers = [QSignalBlocker(self._x_spin), QSignalBlocker(self._y_spin)]
        self._x_spin.setRange(0, max_x)
        self._y_spin.setRange(0, max_y)
        del blockers

    def _field_signal_blockers(self) -> list[QSignalBlocker]:
        return [
            QSignalBlocker(self._id_edit),
            QSignalBlocker(self._kind_edit),
            QSignalBlocker(self._tags_edit),
            QSignalBlocker(self._scope_combo),
            QSignalBlocker(self._x_spin),
            QSignalBlocker(self._y_spin),
            QSignalBlocker(self._pixel_x_check),
            QSignalBlocker(self._pixel_y_check),
            QSignalBlocker(self._pixel_x_spin),
            QSignalBlocker(self._pixel_y_spin),
            QSignalBlocker(self._facing_combo),
            QSignalBlocker(self._solid_check),
            QSignalBlocker(self._pushable_check),
            QSignalBlocker(self._weight_spin),
            QSignalBlocker(self._push_strength_spin),
            QSignalBlocker(self._collision_push_strength_spin),
            QSignalBlocker(self._interactable_check),
            QSignalBlocker(self._interaction_priority_spin),
            QSignalBlocker(self._present_check),
            QSignalBlocker(self._visible_check),
            QSignalBlocker(self._entity_commands_enabled_check),
            QSignalBlocker(self._color_check),
            QSignalBlocker(self._color_red_spin),
            QSignalBlocker(self._color_green_spin),
            QSignalBlocker(self._color_blue_spin),
            QSignalBlocker(self._input_map_text),
            QSignalBlocker(self._entity_commands_text),
            QSignalBlocker(self._variables_text),
            QSignalBlocker(self._inventory_check),
            QSignalBlocker(self._inventory_max_stacks_spin),
            QSignalBlocker(self._inventory_stacks_text),
            QSignalBlocker(self._visuals_text),
            QSignalBlocker(self._persistence_entity_state_check),
            QSignalBlocker(self._persistence_variables_table),
            QSignalBlocker(self._persistence_variables_text),
        ]

    def _reset_field_values(self) -> None:
        self._id_edit.clear()
        self._kind_edit.clear()
        self._tags_edit.clear()
        self._template_label.setText("-")
        self._space_label.setText("world")
        self._scope_combo.setCurrentText("area")
        self._x_spin.setValue(0)
        self._y_spin.setValue(0)
        self._pixel_x_check.setChecked(False)
        self._pixel_y_check.setChecked(False)
        self._pixel_x_spin.setValue(0)
        self._pixel_y_spin.setValue(0)
        self._facing_combo.setCurrentText("down")
        self._solid_check.setChecked(False)
        self._pushable_check.setChecked(False)
        self._weight_spin.setValue(_ENTITY_INT_DEFAULTS["weight"])
        self._push_strength_spin.setValue(_ENTITY_INT_DEFAULTS["push_strength"])
        self._collision_push_strength_spin.setValue(
            _ENTITY_INT_DEFAULTS["collision_push_strength"]
        )
        self._interactable_check.setChecked(False)
        self._interaction_priority_spin.setValue(
            _ENTITY_INT_DEFAULTS["interaction_priority"]
        )
        self._present_check.setChecked(True)
        self._visible_check.setChecked(True)
        self._entity_commands_enabled_check.setChecked(True)
        self._color_check.setChecked(False)
        self._color_red_spin.setValue(DEFAULT_ENTITY_COLOR[0])
        self._color_green_spin.setValue(DEFAULT_ENTITY_COLOR[1])
        self._color_blue_spin.setValue(DEFAULT_ENTITY_COLOR[2])
        self._input_map_text.clear()
        self._entity_commands_text.clear()
        self._dialogues_summary.setText("No dialogues")
        self._variables_text.clear()
        self._variables_table.set_variables({})
        self._inventory_check.setChecked(False)
        self._inventory_max_stacks_spin.setValue(0)
        self._inventory_stacks_text.clear()
        self._visuals_text.clear()
        self._persistence_entity_state_check.setChecked(False)
        self._persistence_variables_table.setRowCount(0)
        self._persistence_variables_text.clear()

    def _load_persistence_ui_state(
        self,
        raw_persistence: object,
    ) -> tuple[bool, dict[str, bool], str | None]:
        try:
            entity_state, variables = parse_persistence_policy(raw_persistence)
            self._persistence_editable = True
            return entity_state, variables, None
        except ValueError as exc:
            self._persistence_editable = False
            warning = (
                "Persistence is not using the supported object shape. "
                f"Use the JSON tab to edit it.\n{exc}"
            )
            return False, {}, warning

    def _load_input_map_ui_state(
        self,
        raw_input_map: object,
    ) -> tuple[dict[str, str], str | None]:
        try:
            input_map = parse_input_map(raw_input_map)
            self._input_map_editable = True
            return input_map, None
        except ValueError as exc:
            self._input_map_editable = False
            warning = (
                "Input map is not using the supported object-of-strings shape. "
                f"Use the JSON tab to edit it.\n{exc}"
            )
            return {}, warning

    def _load_entity_commands_ui_state(
        self,
        raw_entity_commands: object,
    ) -> tuple[dict[str, object], str | None]:
        try:
            entity_commands = parse_entity_commands(raw_entity_commands)
            self._entity_commands_editable = True
            return entity_commands, None
        except ValueError as exc:
            self._entity_commands_editable = False
            warning = (
                "Entity commands are not using the supported object shape. "
                f"Use the JSON tab to edit them.\n{exc}"
            )
            return {}, warning

    def _load_inventory_ui_state(
        self,
        raw_inventory: object,
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            inventory = parse_inventory(raw_inventory)
            self._inventory_editable = True
            return inventory, None
        except ValueError as exc:
            self._inventory_editable = False
            warning = (
                "Inventory is not using the supported object shape. "
                f"Use the JSON tab to edit it.\n{exc}"
            )
            return None, warning

    def _load_variables_ui_state(
        self,
        raw_variables: object,
    ) -> tuple[dict[str, Any], str | None]:
        try:
            self._variables_table.set_variables(raw_variables)
            self._variables_editable = True
            return raw_variables if isinstance(raw_variables, dict) else {}, None
        except ValueError as exc:
            self._variables_editable = False
            warning = (
                "Variables are not using the supported object shape. "
                f"Use the JSON tab to edit them.\n{exc}"
            )
            return {}, warning

    def _load_dialogues_ui_state(
        self,
        raw_dialogues: object,
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        try:
            dialogues = normalize_entity_dialogues(raw_dialogues)
            self._dialogues_editable = True
            return dialogues, None
        except ValueError as exc:
            self._dialogues_editable = False
            warning = (
                "Dialogues are not using the supported named-dialogue shape. "
                f"Use the JSON tab to edit them.\n{exc}"
            )
            return {}, warning

    def _load_color_ui_state(
        self,
        raw_color: object,
    ) -> tuple[tuple[int, int, int] | None, str | None]:
        try:
            color = parse_color(raw_color)
            self._color_editable = True
            return color, None
        except ValueError as exc:
            self._color_editable = False
            warning = (
                "Color is not using the supported RGB array shape. "
                f"Use the JSON tab to edit it.\n{exc}"
            )
            return None, warning

    def _populate_field_values(
        self,
        entity: EntityDocument,
        *,
        tag_text: str,
        has_pixel_x: bool,
        has_pixel_y: bool,
        color: tuple[int, int, int] | None,
        input_map: dict[str, str],
        entity_commands: dict[str, object],
        inventory: dict[str, object] | None,
        raw_variables: object,
        variables: dict[str, Any],
        has_visuals_override: bool,
        raw_visuals: object,
        persistence_entity_state: bool,
        persistence_variables: dict[str, bool],
    ) -> None:
        defaults = self._effective_field_defaults
        self._id_edit.setText(entity.id)
        self._kind_edit.setText(str(entity._extra.get("kind", "")))
        self._tags_edit.setText(tag_text)
        self._template_label.setText(entity.template or "-")
        self._template_label.setCursorPosition(0)
        self._space_label.setText(self._effective_space)
        self._scope_combo.setCurrentText(str(entity._extra.get("scope", defaults["scope"])))
        self._x_spin.setValue(entity.x)
        self._y_spin.setValue(entity.y)
        self._pixel_x_check.setChecked(has_pixel_x)
        self._pixel_y_check.setChecked(has_pixel_y)
        self._pixel_x_spin.setValue(entity.pixel_x or 0)
        self._pixel_y_spin.setValue(entity.pixel_y or 0)
        self._facing_combo.setCurrentText(str(entity._extra.get("facing", defaults["facing"])))
        self._solid_check.setChecked(bool(entity._extra.get("solid", defaults["solid"])))
        self._pushable_check.setChecked(
            bool(entity._extra.get("pushable", defaults["pushable"]))
        )
        self._weight_spin.setValue(int(entity._extra.get("weight", defaults["weight"])))
        self._push_strength_spin.setValue(
            int(entity._extra.get("push_strength", defaults["push_strength"]))
        )
        self._collision_push_strength_spin.setValue(
            int(
                entity._extra.get(
                    "collision_push_strength",
                    defaults["collision_push_strength"],
                )
            )
        )
        self._interactable_check.setChecked(
            bool(entity._extra.get("interactable", defaults["interactable"]))
        )
        self._interaction_priority_spin.setValue(
            int(
                entity._extra.get(
                    "interaction_priority",
                    defaults["interaction_priority"],
                )
            )
        )
        self._present_check.setChecked(bool(entity._extra.get("present", defaults["present"])))
        self._visible_check.setChecked(bool(entity._extra.get("visible", defaults["visible"])))
        self._entity_commands_enabled_check.setChecked(
            bool(
                entity._extra.get(
                    "entity_commands_enabled",
                    defaults["entity_commands_enabled"],
                )
            )
        )
        has_color = color is not None
        red, green, blue = color or DEFAULT_ENTITY_COLOR
        self._color_check.setChecked(has_color)
        self._color_red_spin.setValue(red)
        self._color_green_spin.setValue(green)
        self._color_blue_spin.setValue(blue)
        self._input_map_text.setPlainText(
            json.dumps(input_map, indent=2, ensure_ascii=False)
            if input_map
            else ""
        )
        self._entity_commands_text.setPlainText(
            json.dumps(entity_commands, indent=2, ensure_ascii=False)
            if entity_commands
            else ""
        )
        self._variables_text.setPlainText(
            json.dumps(raw_variables, indent=2, ensure_ascii=False)
        )
        self._variables_table.set_variables(variables)
        has_inventory = inventory is not None
        self._inventory_check.setChecked(has_inventory)
        self._inventory_max_stacks_spin.setValue(
            int(inventory.get("max_stacks", 0)) if inventory else 0
        )
        self._inventory_stacks_text.setPlainText(
            json.dumps(inventory.get("stacks", []), indent=2, ensure_ascii=False)
            if inventory
            else ""
        )
        self._visuals_text.setPlainText(
            json.dumps(raw_visuals, indent=2, ensure_ascii=False)
            if has_visuals_override
            else ""
        )
        self._persistence_entity_state_check.setChecked(persistence_entity_state)
        self._persistence_variables_text.setPlainText(
            json.dumps(persistence_variables, indent=2, ensure_ascii=False)
            if persistence_variables
            else ""
        )
        self._set_persistence_variables_table(persistence_variables)

    def _show_unmanaged_extra(self, extra: dict[str, object]) -> None:
        if extra:
            self._extra_text.setPlainText(json.dumps(extra, indent=2, ensure_ascii=False))
            self._set_extra_visible(True)
        else:
            self._set_extra_visible(False)

    def _apply_persistence_warning(self, warning: str | None) -> None:
        if warning:
            self._persistence_warning.setText(warning)
            self._persistence_warning.show()
        else:
            self._persistence_warning.hide()

    def _apply_input_map_warning(self, warning: str | None) -> None:
        if warning:
            self._input_map_warning.setText(warning)
            self._input_map_warning.show()
        else:
            self._input_map_warning.hide()

    def _apply_entity_commands_warning(self, warning: str | None) -> None:
        if warning:
            self._entity_commands_warning.setText(warning)
            self._entity_commands_warning.show()
        else:
            self._entity_commands_warning.hide()

    def _apply_inventory_warning(self, warning: str | None) -> None:
        if warning:
            self._inventory_warning.setText(warning)
            self._inventory_warning.show()
        else:
            self._inventory_warning.hide()

    def _apply_variables_warning(self, warning: str | None) -> None:
        if warning:
            self._variables_warning.setText(warning)
            self._variables_warning.show()
        else:
            self._variables_warning.hide()

    def _apply_color_warning(self, warning: str | None) -> None:
        if warning:
            self._color_warning.setText(warning)
            self._color_warning.show()
        else:
            self._color_warning.hide()

    def _current_position_fields(self) -> tuple[str, int, int, int | None, int | None]:
        assert self._entity is not None
        if self._effective_space == "screen":
            return (
                "screen",
                self._entity.grid_x,
                self._entity.grid_y,
                self._pixel_x_spin.value(),
                self._pixel_y_spin.value(),
            )
        return (
            self._entity.space,
            self._x_spin.value(),
            self._y_spin.value(),
            self._pixel_x_spin.value() if self._pixel_x_check.isChecked() else None,
            self._pixel_y_spin.value() if self._pixel_y_check.isChecked() else None,
        )

    def _parse_optional_json_block(
        self,
        text: str,
        *,
        label: str,
        expected_type: type,
        invalid_shape_message: str,
    ):
        stripped = text.strip()
        if not stripped:
            return None
        try:
            parsed = loads_json_data(stripped, source_name=label)
        except JsonDataDecodeError as exc:
            raise ValueError(f"{label} must be valid JSON.\n{exc}") from exc
        if not isinstance(parsed, expected_type):
            raise ValueError(invalid_shape_message)
        return parsed

    def _current_variables_value_for_dialogues(self) -> dict[str, Any] | None:
        stripped = self._variables_text.toPlainText().strip()
        if not stripped:
            return {}
        try:
            parsed = loads_json_data(stripped, source_name="Variables")
        except JsonDataDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _current_active_dialogue_name(self) -> str | None:
        variables = self._current_variables_value_for_dialogues()
        if not isinstance(variables, dict):
            return None
        active = str(variables.get("active_dialogue", "")).strip()
        if active:
            return active
        if len(self._dialogues_value) == 1:
            return next(iter(self._dialogues_value), None)
        return self._template_active_dialogue_default

    def _sync_dialogues_summary(self) -> None:
        active_dialogue = self._current_active_dialogue_name()
        if self._current_variables_value_for_dialogues() is None:
            self._dialogues_summary.setText(
                f"{summarize_entity_dialogues(self._dialogues_value)}; active: unavailable (invalid variables)"
            )
            return
        self._dialogues_summary.setText(
            summarize_entity_dialogues(self._dialogues_value, active_dialogue)
        )

    def _compute_template_dialogues_default(
        self,
        entity: EntityDocument,
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        if not entity.template or self._template_catalog is None:
            return {}, None
        template = self._template_catalog.get_template_data(entity.template)
        template_parameters = self._template_catalog.get_template_parameter_defaults(
            entity.template
        )
        if isinstance(entity.parameters, dict):
            template_parameters.update(copy.deepcopy(entity.parameters))
        template = self._template_catalog.substitute_template_parameters(
            template,
            template_parameters,
        )
        try:
            dialogues = normalize_entity_dialogues(template.get("dialogues"))
        except ValueError:
            dialogues = {}
        raw_variables = template.get("variables")
        active_dialogue = None
        if isinstance(raw_variables, dict):
            active_value = str(raw_variables.get("active_dialogue", "")).strip()
            active_dialogue = active_value or None
        if not active_dialogue and len(dialogues) == 1:
            active_dialogue = next(iter(dialogues), None)
        return dialogues, active_dialogue

    def current_named_dialogues_state(
        self,
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        return copy.deepcopy(self._dialogues_value), self._current_active_dialogue_name()

    def _open_entity_dialogues_dialog(
        self,
        dialogues: object,
        *,
        active_dialogue: object,
    ) -> tuple[dict[str, dict[str, Any]], str | None, dict[str, str]] | None:
        dialog = EntityDialoguesDialog(
            self,
            area_picker=self._reference_picker_callbacks.get("area"),
            asset_picker=self._reference_picker_callbacks.get("asset"),
            entity_picker=self._reference_picker_callbacks.get("entity"),
            entity_command_picker=self._reference_picker_callbacks.get("entity_command"),
            entity_dialogue_picker=self._reference_picker_callbacks.get("entity_dialogue"),
            item_picker=self._reference_picker_callbacks.get("item"),
            dialogue_picker=self._reference_picker_callbacks.get("dialogue"),
            command_picker=self._reference_picker_callbacks.get("command"),
            project_command_inputs_provider=self._reference_picker_callbacks.get(
                "project_command_inputs"
            ),
            visual_picker=self._reference_picker_callbacks.get("visual"),
            animation_picker=self._reference_picker_callbacks.get("animation"),
            current_entity_id=self._entity.id if self._entity is not None else None,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names(),
        )
        dialog.load_dialogues(dialogues, active_dialogue=active_dialogue)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.dialogues(), dialog.active_dialogue(), dialog.rename_map()

    def _current_entity_command_names(self) -> list[str]:
        names: set[str] = set()
        if (
            self._entity is not None
            and self._entity.template
            and self._template_catalog is not None
        ):
            names.update(
                self._template_catalog.get_template_entity_command_names(
                    self._entity.template
                )
            )
        raw_text = self._entity_commands_text.toPlainText().strip()
        if raw_text:
            try:
                parsed = loads_json_data(raw_text, source_name="Entity commands")
            except JsonDataDecodeError:
                parsed = None
            if parsed is not None:
                try:
                    names.update(parse_entity_commands(parsed).keys())
                except ValueError:
                    pass
        return sorted(str(name).strip() for name in names if str(name).strip())

    def _current_entity_commands_value(self) -> dict[str, Any] | None:
        raw_text = self._entity_commands_text.toPlainText().strip()
        if not raw_text:
            return {}
        try:
            parsed = loads_json_data(raw_text, source_name="Entity commands")
            return parse_entity_commands(parsed)
        except (JsonDataDecodeError, ValueError):
            return None

    def _set_entity_commands_value(self, entity_commands: dict[str, Any]) -> None:
        self._entity_commands_text.setPlainText(
            json.dumps(entity_commands, indent=2, ensure_ascii=False)
            if entity_commands
            else ""
        )

    def _sync_entity_commands_summary(self) -> None:
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            self._entity_commands_summary.setText("Invalid entity commands")
            return
        self._entity_commands_summary.setText(summarize_entity_commands(entity_commands))

    def _prompt_entity_command_name(
        self,
        *,
        title: str,
        current_name: str = "",
        existing_names: set[str] | None = None,
    ) -> str | None:
        suggestions = suggested_entity_command_names(
            existing_names=existing_names,
            current_name=current_name,
        )
        current = current_name.strip()
        current_index = suggestions.index(current) if current in suggestions else 0
        value, accepted = QInputDialog.getItem(
            self,
            title,
            "Command name (choose one or type a custom name)",
            suggestions,
            current_index,
            True,
        )
        if not accepted:
            return None
        normalized = value.strip()
        if not normalized:
            QMessageBox.warning(
                self,
                "Invalid Entity Command",
                "Entity command name must not be blank.",
            )
            return None
        return normalized

    def _select_entity_command_name(
        self,
        *,
        title: str,
        entity_commands: dict[str, Any],
    ) -> str | None:
        names = sorted(str(name) for name in entity_commands.keys() if str(name).strip())
        if not names:
            QMessageBox.information(
                self,
                title,
                "No entity commands are available yet.",
            )
            return None
        selected, accepted = QInputDialog.getItem(
            self,
            title,
            "Entity command",
            names,
            0,
            False,
        )
        if not accepted:
            return None
        return str(selected).strip() or None

    def _open_entity_command_list_dialog(
        self,
        command_name: str,
        commands: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        dialog = CommandListDialog(
            self,
            area_picker=self._reference_picker_callbacks.get("area"),
            asset_picker=self._reference_picker_callbacks.get("asset"),
            entity_picker=self._reference_picker_callbacks.get("entity"),
            entity_command_picker=self._reference_picker_callbacks.get("entity_command"),
            entity_dialogue_picker=self._reference_picker_callbacks.get("entity_dialogue"),
            item_picker=self._reference_picker_callbacks.get("item"),
            dialogue_picker=self._reference_picker_callbacks.get("dialogue"),
            command_picker=self._reference_picker_callbacks.get("command"),
            project_command_inputs_provider=self._reference_picker_callbacks.get(
                "project_command_inputs"
            ),
            visual_picker=self._reference_picker_callbacks.get("visual"),
            animation_picker=self._reference_picker_callbacks.get("animation"),
            current_entity_id=self._entity.id if self._entity is not None else None,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names(),
            current_entity_dialogue_names=sorted(self._dialogues_value.keys()),
        )
        dialog.setWindowTitle(f"Edit Entity Command - {command_name}")
        dialog.load_commands(commands)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.commands()

    def _on_add_entity_command_clicked(self) -> None:
        if not self._entity_commands_editable:
            return
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            return
        command_name = self._prompt_entity_command_name(
            title="Add Entity Command",
            existing_names=set(entity_commands.keys()),
        )
        if command_name is None:
            return
        if command_name in entity_commands:
            QMessageBox.warning(
                self,
                "Entity Command Exists",
                f"Entity command '{command_name}' already exists.",
            )
            return
        commands = self._open_entity_command_list_dialog(command_name, [])
        if commands is None:
            return
        entity_commands[command_name] = commands
        self._set_entity_commands_value(entity_commands)
        self._on_field_changed()

    def _on_edit_entity_command_clicked(self) -> None:
        if not self._entity_commands_editable:
            return
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            return
        command_name = self._select_entity_command_name(
            title="Edit Entity Command",
            entity_commands=entity_commands,
        )
        if command_name is None:
            return
        commands = self._open_entity_command_list_dialog(
            command_name,
            entity_command_command_list(entity_commands.get(command_name)),
        )
        if commands is None:
            return
        entity_commands[command_name] = replace_entity_command_command_list(
            entity_commands.get(command_name),
            commands,
        )
        self._set_entity_commands_value(entity_commands)
        self._on_field_changed()

    def _on_duplicate_entity_command_clicked(self) -> None:
        if not self._entity_commands_editable:
            return
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            return
        source_name = self._select_entity_command_name(
            title="Duplicate Entity Command",
            entity_commands=entity_commands,
        )
        if source_name is None:
            return
        new_name = self._prompt_entity_command_name(
            title="Duplicate Entity Command",
            current_name=suggested_entity_command_copy_name(
                source_name,
                set(entity_commands.keys()),
            ),
            existing_names=set(entity_commands.keys()),
        )
        if new_name is None:
            return
        if new_name in entity_commands:
            QMessageBox.warning(
                self,
                "Entity Command Exists",
                f"Entity command '{new_name}' already exists.",
            )
            return
        entity_commands[new_name] = copy.deepcopy(entity_commands[source_name])
        self._set_entity_commands_value(entity_commands)
        self._on_field_changed()

    def _on_remove_entity_command_clicked(self) -> None:
        if not self._entity_commands_editable:
            return
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            return
        command_name = self._select_entity_command_name(
            title="Remove Entity Command",
            entity_commands=entity_commands,
        )
        if command_name is None:
            return
        entity_commands.pop(command_name, None)
        self._set_entity_commands_value(entity_commands)
        self._on_field_changed()

    def edit_named_dialogues(
        self,
    ) -> tuple[dict[str, dict[str, Any]], str | None] | None:
        if not self._dialogues_editable:
            return None
        variables = self._current_variables_value_for_dialogues()
        if variables is None:
            QMessageBox.warning(
                self,
                "Invalid Variables",
                "Fix the Variables JSON before editing named dialogues.",
            )
            return None
        updated = self._open_entity_dialogues_dialog(
            self._dialogues_value,
            active_dialogue=variables.get("active_dialogue"),
        )
        if updated is None:
            return None
        if len(updated) == 3:
            dialogues_value, active_dialogue, rename_map = updated
        else:
            dialogues_value, active_dialogue = updated
            rename_map = {}
        self._dialogues_value = copy.deepcopy(dialogues_value)
        next_variables = rename_active_dialogue_value(variables, rename_map)
        if active_dialogue:
            next_variables["active_dialogue"] = active_dialogue
        else:
            next_variables.pop("active_dialogue", None)
        blockers = [QSignalBlocker(self._variables_text)]
        self._variables_table.set_variables(next_variables)
        self._variables_text.setPlainText(
            json.dumps(next_variables, indent=2, ensure_ascii=False)
            if next_variables
            else ""
        )
        del blockers
        self._apply_dialogue_rename_map_to_entity_commands(rename_map)
        self._sync_dialogues_summary()
        self._set_dirty(True)
        self.named_dialogues_changed.emit(
            copy.deepcopy(self._dialogues_value),
            self._current_active_dialogue_name(),
        )
        return self.current_named_dialogues_state()

    def _on_edit_dialogues_clicked(self) -> None:
        self.edit_named_dialogues()

    def _apply_dialogue_rename_map_to_entity_commands(
        self,
        rename_map: dict[str, str],
    ) -> None:
        if not rename_map or not self._entity_commands_editable:
            return
        raw_text = self._entity_commands_text.toPlainText().strip()
        if not raw_text:
            return
        try:
            parsed = loads_json_data(raw_text, source_name="Entity commands")
        except JsonDataDecodeError:
            return
        if not isinstance(parsed, dict):
            return
        rewritten = rename_self_target_dialogue_id_references(
            parsed,
            rename_map,
            current_entity_id=self._entity.id if self._entity is not None else None,
        )
        if rewritten == parsed:
            return
        blockers = [QSignalBlocker(self._entity_commands_text)]
        self._entity_commands_text.setPlainText(
            json.dumps(rewritten, indent=2, ensure_ascii=False)
        )
        del blockers
        self._sync_entity_commands_summary()

    def _apply_toggle_extra_values(self, extra: dict[str, object]) -> None:
        for key, widget in (
            ("solid", self._solid_check),
            ("pushable", self._pushable_check),
            ("interactable", self._interactable_check),
            ("present", self._present_check),
            ("visible", self._visible_check),
            ("entity_commands_enabled", self._entity_commands_enabled_check),
        ):
            self._apply_extra_value(
                extra,
                key=key,
                value=bool(widget.isChecked()),
                default=self._effective_field_defaults[key],
            )

    def _apply_numeric_extra_values(self, extra: dict[str, object]) -> None:
        for key, widget in (
            ("weight", self._weight_spin),
            ("push_strength", self._push_strength_spin),
            ("collision_push_strength", self._collision_push_strength_spin),
            ("interaction_priority", self._interaction_priority_spin),
        ):
            self._apply_extra_value(
                extra,
                key=key,
                value=int(widget.value()),
                default=self._effective_field_defaults[key],
            )

    def clear_entity(self) -> None:
        self._entity = None
        self._effective_space = "world"
        self._effective_field_defaults = self._default_managed_field_defaults()
        self._loading = True
        try:
            blockers = self._field_signal_blockers()
            self._reset_field_values()
            del blockers
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._clear_parameter_rows()
        self._parameters_section_label.hide()
        self._parameter_warning.hide()
        self._parameters_widget.hide()
        self._parameters_editable = True
        self._color_warning.hide()
        self._color_editable = True
        self._set_color_controls_enabled(True)
        self._input_map_warning.hide()
        self._input_map_editable = False
        self._set_input_map_controls_enabled(False)
        self._entity_commands_warning.hide()
        self._entity_commands_editable = True
        self._sync_entity_commands_summary()
        self._set_entity_commands_controls_enabled(True)
        self._dialogues_warning.hide()
        self._dialogues_editable = True
        self._dialogues_value = {}
        self._dialogues_default_value = {}
        self._template_active_dialogue_default = None
        self._dialogues_edit_button.setEnabled(True)
        self._dialogues_summary.setText("No dialogues")
        self._variables_warning.hide()
        self._variables_editable = True
        self._set_variables_controls_enabled(True)
        self._inventory_warning.hide()
        self._inventory_editable = True
        self._set_inventory_controls_enabled(True)
        self._persistence_warning.hide()
        self._persistence_editable = True
        self._set_persistence_controls_enabled(True)
        self._set_extra_visible(False)
        self._apply_space_visibility(has_pixel_x=False, has_pixel_y=False)
        self._sync_pixel_spin_enabled()
        self._set_dirty(False)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity = entity
        self._effective_space = self._compute_effective_space(entity)
        self._effective_field_defaults = self._compute_effective_field_defaults(entity)
        (
            self._dialogues_default_value,
            self._template_active_dialogue_default,
        ) = self._compute_template_dialogues_default(entity)
        has_pixel_x = entity.pixel_x is not None
        has_pixel_y = entity.pixel_y is not None
        raw_tags = entity._extra.get("tags", [])
        tag_text = ", ".join(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else ""
        color, color_warning = self._load_color_ui_state(entity._extra.get("color"))
        raw_entity_commands = entity._extra.get("entity_commands")
        raw_variables = entity._extra.get("variables", {})
        raw_dialogues = entity._extra.get("dialogues")
        raw_inventory = entity._extra.get("inventory")
        has_visuals_override = "visuals" in entity._extra
        raw_visuals = entity._extra.get("visuals", [])
        input_map: dict[str, str] = {}
        input_map_warning: str | None = None
        self._input_map_editable = False
        entity_commands, entity_commands_warning = self._load_entity_commands_ui_state(
            raw_entity_commands
        )
        effective_raw_dialogues = (
            raw_dialogues
            if "dialogues" in entity._extra
            else self._dialogues_default_value
        )
        dialogues, dialogues_warning = self._load_dialogues_ui_state(effective_raw_dialogues)
        inventory, inventory_warning = self._load_inventory_ui_state(raw_inventory)
        variables, variables_warning = self._load_variables_ui_state(raw_variables)
        raw_persistence = entity._extra.get("persistence")
        persistence_entity_state, persistence_variables, persistence_warning = (
            self._load_persistence_ui_state(raw_persistence)
        )
        self._loading = True
        try:
            blockers = self._field_signal_blockers()
            self._populate_field_values(
                entity,
                tag_text=tag_text,
                has_pixel_x=has_pixel_x,
                has_pixel_y=has_pixel_y,
                color=color,
                input_map=input_map,
                entity_commands=entity_commands,
                inventory=inventory,
                raw_variables=raw_variables,
                variables=variables,
                has_visuals_override=has_visuals_override,
                raw_visuals=raw_visuals,
                persistence_entity_state=persistence_entity_state,
                persistence_variables=persistence_variables,
            )
            del blockers
        finally:
            self._loading = False
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._apply_space_visibility(has_pixel_x=has_pixel_x, has_pixel_y=has_pixel_y)
        self._sync_pixel_spin_enabled()
        self._rebuild_parameter_rows(entity)
        self._parameters_section_label.hide()
        self._parameter_warning.hide()
        self._parameters_widget.hide()
        self._show_unmanaged_extra(_filtered_unmanaged_extra(entity._extra))
        self._apply_color_warning(color_warning)
        self._set_color_controls_enabled(self._color_editable)
        self._apply_input_map_warning(input_map_warning)
        self._set_input_map_controls_enabled(self._input_map_editable)
        self._apply_entity_commands_warning(entity_commands_warning)
        self._sync_entity_commands_summary()
        self._set_entity_commands_controls_enabled(self._entity_commands_editable)
        self._dialogues_value = copy.deepcopy(dialogues)
        if dialogues_warning:
            self._dialogues_warning.setText(dialogues_warning)
            self._dialogues_warning.show()
        else:
            self._dialogues_warning.hide()
        self._dialogues_edit_button.setEnabled(self._dialogues_editable)
        self._sync_dialogues_summary()
        self._apply_inventory_warning(inventory_warning)
        self._set_inventory_controls_enabled(self._inventory_editable)
        self._apply_variables_warning(variables_warning)
        self._set_variables_controls_enabled(self._variables_editable)
        self._apply_persistence_warning(persistence_warning)
        self._set_persistence_controls_enabled(self._persistence_editable)
        self._set_dirty(False)
        self._set_buttons_enabled(True)

    def build_entity_document(self) -> EntityDocument:
        if self._entity is None:
            raise RuntimeError("No entity is currently loaded.")

        parameters = self._entity.parameters
        extra = dict(self._entity._extra)
        for key in _MANAGED_EXTRA_KEYS:
            extra.pop(key, None)

        space, grid_x, grid_y, pixel_x, pixel_y = self._current_position_fields()

        kind = self._kind_edit.text().strip()
        if kind:
            extra["kind"] = kind

        self._apply_extra_value(
            extra,
            key="scope",
            value=self._scope_combo.currentText(),
            default=self._effective_field_defaults["scope"],
        )

        tags = parse_tag_list(self._tags_edit.text())
        if tags:
            extra["tags"] = tags

        self._apply_extra_value(
            extra,
            key="facing",
            value=self._facing_combo.currentText(),
            default=self._effective_field_defaults["facing"],
        )

        self._apply_toggle_extra_values(extra)
        self._apply_numeric_extra_values(extra)

        if self._color_editable:
            if self._color_check.isChecked():
                extra["color"] = [
                    int(self._color_red_spin.value()),
                    int(self._color_green_spin.value()),
                    int(self._color_blue_spin.value()),
                ]
        elif "color" in self._entity._extra:
            extra["color"] = self._entity._extra["color"]

        if "input_map" in self._entity._extra:
            extra["input_map"] = self._entity._extra["input_map"]

        if self._entity_commands_editable:
            entity_commands_value = build_entity_commands(
                self._entity_commands_text.toPlainText()
            )
            if entity_commands_value is not None:
                extra["entity_commands"] = entity_commands_value
        elif "entity_commands" in self._entity._extra:
            extra["entity_commands"] = self._entity._extra["entity_commands"]

        if self._variables_editable:
            variables_value = self._variables_table.variables()
            if variables_value:
                extra["variables"] = variables_value
        elif "variables" in self._entity._extra:
            extra["variables"] = self._entity._extra["variables"]

        if self._dialogues_editable:
            has_authored_override = "dialogues" in self._entity._extra
            if (
                self._dialogues_value != self._dialogues_default_value
                or has_authored_override
            ):
                extra["dialogues"] = copy.deepcopy(self._dialogues_value)
        elif "dialogues" in self._entity._extra:
            extra["dialogues"] = self._entity._extra["dialogues"]

        if self._inventory_editable:
            inventory_value = build_inventory(
                enabled=bool(self._inventory_check.isChecked()),
                max_stacks=int(self._inventory_max_stacks_spin.value()),
                stacks_text=self._inventory_stacks_text.toPlainText(),
                base_inventory=self._entity._extra.get("inventory"),
            )
            if inventory_value is not None:
                extra["inventory"] = inventory_value
        elif "inventory" in self._entity._extra:
            extra["inventory"] = self._entity._extra["inventory"]

        visuals_value = self._parse_optional_json_block(
            self._visuals_text.toPlainText(),
            label="Visuals",
            expected_type=list,
            invalid_shape_message="Visuals must be a JSON array.",
        )
        if visuals_value is not None:
            extra["visuals"] = visuals_value

        if self._persistence_editable:
            persistence_value = self._build_persistence_policy_from_table()
            if persistence_value is not None:
                extra["persistence"] = persistence_value
        elif "persistence" in self._entity._extra:
            extra["persistence"] = self._entity._extra["persistence"]

        return EntityDocument(
            id=self._id_edit.text().strip(),
            grid_x=grid_x,
            grid_y=grid_y,
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            space=space,
            template=self._entity.template,
            parameters=parameters,
            _extra=extra,
        )

    def _apply_extra_value(self, extra: dict[str, object], *, key: str, value, default) -> None:
        if value != default or key in self._entity._extra:
            extra[key] = value

    def _compute_effective_space(self, entity: EntityDocument) -> str:
        effective_space = entity.space
        if (
            effective_space == "world"
            and entity.template
            and self._template_catalog is not None
        ):
            template_space = self._template_catalog.get_template_space(entity.template)
            if template_space is not None:
                effective_space = template_space
        return effective_space

    @staticmethod
    def _default_managed_field_defaults() -> dict[str, object]:
        defaults: dict[str, object] = {
            "scope": "area",
            "facing": "down",
        }
        defaults.update(_ENTITY_BOOL_DEFAULTS)
        defaults.update(_ENTITY_INT_DEFAULTS)
        return defaults

    def _compute_effective_field_defaults(self, entity: EntityDocument) -> dict[str, object]:
        defaults = self._default_managed_field_defaults()
        if not entity.template or self._template_catalog is None:
            return defaults

        template = self._template_catalog.get_template_data(entity.template)
        if not template:
            return defaults

        scope = str(template.get("scope", defaults["scope"])).strip().lower()
        if scope in {"area", "global"}:
            defaults["scope"] = scope

        facing = template.get("facing")
        if isinstance(facing, str) and facing in ENTITY_FACING_VALUES:
            defaults["facing"] = facing

        for key in _ENTITY_BOOL_DEFAULTS:
            value = template.get(key)
            if isinstance(value, bool):
                defaults[key] = value

        for key in _ENTITY_INT_DEFAULTS:
            value = template.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                defaults[key] = value

        return defaults

    def _apply_space_visibility(self, *, has_pixel_x: bool, has_pixel_y: bool) -> None:
        is_screen = self._effective_space == "screen"
        _set_row_visible(self._x_label, self._x_spin, not is_screen)
        _set_row_visible(self._y_label, self._y_spin, not is_screen)

        pixel_rows_visible = is_screen or has_pixel_x or has_pixel_y
        _set_row_visible(self._pixel_x_label, self._pixel_x_row, pixel_rows_visible)
        _set_row_visible(self._pixel_y_label, self._pixel_y_row, pixel_rows_visible)

        self._pixel_x_check.setVisible(not is_screen)
        self._pixel_y_check.setVisible(not is_screen)
        if is_screen:
            blockers = [QSignalBlocker(self._pixel_x_check), QSignalBlocker(self._pixel_y_check)]
            self._pixel_x_check.setChecked(True)
            self._pixel_y_check.setChecked(True)
            del blockers

    def _rebuild_parameter_rows(self, entity: EntityDocument) -> None:
        self._clear_parameter_rows()
        parameters = entity.parameters
        template_defaults: dict[str, object] = {}
        template_specs: dict[str, Any] = {}
        if parameters is not None and not isinstance(parameters, dict):
            self._parameters_editable = False
            self._parameters_widget.hide()
            self._parameter_specs = {}
            self._parameter_warning.setText(
                "Parameters are not a JSON object for this entity. "
                "Use the JSON tab to edit them."
            )
            self._parameter_warning.show()
            return

        self._parameters_editable = True
        self._parameters_widget.show()
        self._parameter_warning.hide()
        parameter_names: set[str] = set()
        if entity.template and self._template_catalog is not None:
            parameter_names.update(
                self._template_catalog.get_template_parameter_names(entity.template)
            )
            template_defaults = self._template_catalog.get_template_parameter_defaults(
                entity.template
            )
            template_specs = self._template_catalog.get_template_parameter_specs(
                entity.template
            )
        if isinstance(parameters, dict):
            parameter_names.update(parameters.keys())
        parameter_names.update(template_defaults.keys())
        parameter_names.update(template_specs.keys())
        self._parameter_specs = template_specs

        for name in sorted(parameter_names):
            label = QLabel(name)
            edit = QLineEdit()
            value = None if not isinstance(parameters, dict) else parameters.get(name)
            default_value = template_defaults.get(name)
            if value is None:
                edit.setText("")
                if default_value is None:
                    edit.setPlaceholderText("")
                elif isinstance(default_value, str):
                    edit.setPlaceholderText(default_value)
                else:
                    edit.setPlaceholderText(json.dumps(default_value, ensure_ascii=False))
            elif isinstance(value, str):
                edit.setText(value)
            else:
                edit.setText(json.dumps(value, ensure_ascii=False))
            edit.textChanged.connect(self._on_field_changed)
            row_widget: QWidget = edit
            picker_kind = self._picker_kind_for_parameter(name)
            picker_callback = (
                None if picker_kind is None else self._reference_picker_callbacks.get(picker_kind)
            )
            if picker_callback is not None:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(edit, 1)
                button_text = (
                    "Pick..."
                    if picker_kind in {"entity", "entity_command", "entity_dialogue"}
                    else "Browse..."
                )
                browse_button = QPushButton(button_text)
                browse_button.clicked.connect(
                    lambda _checked=False, parameter_name=name: self._on_pick_parameter_value(
                        parameter_name
                    )
                )
                row_layout.addWidget(browse_button)
                self._parameter_browse_buttons[name] = browse_button
            self._parameters_layout.addRow(label, row_widget)
            self._parameter_edits[name] = edit

    def _picker_kind_for_parameter(self, name: str) -> str | None:
        spec = self._parameter_specs.get(name)
        if isinstance(spec, dict) and isinstance(spec.get("type"), str):
            return _parameter_spec_reference_kind(spec)
        return _parameter_reference_kind(name)

    def _clear_parameter_rows(self) -> None:
        self._parameter_edits.clear()
        self._parameter_browse_buttons.clear()
        self._parameter_specs = {}
        while self._parameters_layout.rowCount() > 0:
            self._parameters_layout.removeRow(0)

    def _build_parameters_value(self):
        if self._entity is None:
            return None
        if not self._parameters_editable:
            return self._entity.parameters
        parameters: dict[str, object] = {}
        for name, edit in self._parameter_edits.items():
            value, keep = _parse_parameter_text_for_spec(
                name,
                edit.text(),
                self._parameter_specs.get(name),
            )
            if not keep:
                continue
            parameters[name] = value
        return parameters or None

    def _set_extra_visible(self, visible: bool) -> None:
        _set_row_visible(self._extra_label, self._extra_text, visible)
        if not visible:
            self._extra_text.clear()

    def _set_persistence_controls_enabled(self, enabled: bool) -> None:
        self._persistence_entity_state_check.setEnabled(enabled)
        self._persistence_variables_text.setReadOnly(not enabled)
        self._persistence_variables_table.setEnabled(enabled)
        self._add_persistence_variable_button.setEnabled(enabled)
        self._remove_persistence_variable_button.setEnabled(
            enabled and self._persistence_variables_table.currentRow() >= 0
        )
        self._persistence_empty_label.setVisible(
            self._persistence_variables_table.rowCount() == 0
        )

    def _show_persistence_variables_context_menu(self, pos) -> None:
        if not self._persistence_editable:
            return
        row = self._persistence_variables_table.rowAt(pos.y())
        if row >= 0:
            self._persistence_variables_table.setCurrentCell(row, 0)

        menu = QMenu(self)
        add_action = menu.addAction("Add Unlisted Variable")
        remove_action = None
        if self._persistence_variables_table.currentRow() >= 0:
            remove_action = menu.addAction("Clear Rule")

        chosen = menu.exec(self._persistence_variables_table.viewport().mapToGlobal(pos))
        if chosen == add_action:
            self._on_add_persistence_variable_clicked()
        elif remove_action is not None and chosen == remove_action:
            self._on_remove_persistence_variable_clicked()

    def _current_entity_variable_names(self) -> list[str] | None:
        names: list[str] = []

        if self._entity is not None and self._entity.template and self._template_catalog:
            template = self._template_catalog.get_template_data(self._entity.template)
            raw_template_variables = template.get("variables")
            if isinstance(raw_template_variables, dict):
                for raw_name in raw_template_variables.keys():
                    name = str(raw_name).strip()
                    if name and name not in names:
                        names.append(name)

        variables_text = self._variables_text.toPlainText().strip()
        if variables_text:
            try:
                parsed = loads_json_data(
                    variables_text,
                    source_name="Entity variables",
                )
            except JsonDataDecodeError:
                return None
            if not isinstance(parsed, dict):
                return None
            for raw_name in parsed.keys():
                name = str(raw_name).strip()
                if name and name not in names:
                    names.append(name)

        return names

    def _make_persistence_value_combo(self, rule: bool | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Use default", None)
        combo.addItem("Save", True)
        combo.addItem("Do not save", False)
        index = combo.findData(rule)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(self._on_persistence_variables_table_changed)
        return combo

    def _insert_persistence_variable_row(
        self,
        *,
        variable_name: str,
        rule: bool | None,
        custom: bool,
    ) -> int:
        row = self._persistence_variables_table.rowCount()
        self._persistence_variables_table.insertRow(row)

        name_item = QTableWidgetItem(variable_name)
        name_item.setData(Qt.ItemDataRole.UserRole, custom)
        if not custom:
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._persistence_variables_table.setItem(row, 0, name_item)

        combo = self._make_persistence_value_combo(rule)
        self._persistence_variables_table.setCellWidget(row, 1, combo)
        return row

    def _set_persistence_variables_table(
        self,
        variables: dict[str, bool],
        *,
        variable_names: list[str] | None = None,
    ) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            self._persistence_variables_table.setRowCount(0)
            known_names = (
                variable_names
                if variable_names is not None
                else self._current_entity_variable_names()
            )
            if known_names is None:
                known_names = []
            ordered_names = list(known_names)
            for variable_name in variables:
                if variable_name not in ordered_names:
                    ordered_names.append(variable_name)
            for variable_name in ordered_names:
                self._insert_persistence_variable_row(
                    variable_name=str(variable_name),
                    rule=variables[variable_name] if variable_name in variables else None,
                    custom=variable_name not in known_names,
                )
        finally:
            self._loading = was_loading
        self._set_persistence_controls_enabled(self._persistence_editable)

    def _persistence_row_is_custom(self, row: int) -> bool:
        item = self._persistence_variables_table.item(row, 0)
        return bool(item is not None and item.data(Qt.ItemDataRole.UserRole))

    def _sync_persistence_row_enabled(self, row: int) -> None:
        return

    def _sync_all_persistence_row_enabled(self) -> None:
        for row in range(self._persistence_variables_table.rowCount()):
            self._sync_persistence_row_enabled(row)

    def _build_persistence_variables_from_table(self) -> dict[str, bool]:
        variables: dict[str, bool] = {}
        for row in range(self._persistence_variables_table.rowCount()):
            name_item = self._persistence_variables_table.item(row, 0)
            name = name_item.text().strip() if name_item is not None else ""
            combo = self._persistence_variables_table.cellWidget(row, 1)
            if isinstance(combo, QComboBox):
                rule = combo.currentData()
            else:
                rule_item = self._persistence_variables_table.item(row, 1)
                rule_text = (
                    rule_item.text().strip().lower() if rule_item is not None else ""
                )
                if rule_text in {"", "default", "use default"}:
                    rule = None
                elif rule_text in {"true", "save"}:
                    rule = True
                elif rule_text in {"false", "do not save", "don't save"}:
                    rule = False
                else:
                    raise ValueError(
                        f"Persistence variable '{name}' rule must be Use default, Save, or Do not save."
                    )
            if rule is None:
                continue
            if not name:
                raise ValueError("Persistence variable names must not be blank.")
            if name in variables:
                raise ValueError(f"Duplicate persistence variable '{name}'.")
            variables[name] = bool(rule)
        return variables

    def _build_persistence_policy_from_table(self) -> dict[str, Any] | None:
        variables = self._build_persistence_variables_from_table()
        entity_state = bool(self._persistence_entity_state_check.isChecked())
        if not entity_state and not variables:
            return None
        payload: dict[str, Any] = {"entity_state": entity_state}
        if variables:
            payload["variables"] = variables
        return payload

    def _sync_persistence_variables_text_from_table(self) -> None:
        variables = self._build_persistence_variables_from_table()
        was_loading = self._loading
        self._loading = True
        try:
            self._persistence_variables_text.setPlainText(
                json.dumps(variables, indent=2, ensure_ascii=False)
                if variables
                else ""
            )
        finally:
            self._loading = was_loading

    def _on_add_persistence_variable_clicked(self) -> None:
        variable_name, accepted = QInputDialog.getText(
            self,
            "Add Unlisted Variable",
            "Variable name:",
        )
        if not accepted:
            return
        self._add_persistence_variable_rule(variable_name)

    def _add_persistence_variable_rule(
        self,
        variable_name: str,
        *,
        rule: bool | None = True,
    ) -> None:
        variable_name = variable_name.strip()
        if not variable_name:
            self._persistence_warning.setText("Persistence variable names must not be blank.")
            self._persistence_warning.show()
            return
        for row in range(self._persistence_variables_table.rowCount()):
            name_item = self._persistence_variables_table.item(row, 0)
            if name_item is not None and name_item.text().strip() == variable_name:
                self._persistence_variables_table.setCurrentCell(row, 0)
                self._persistence_warning.setText(
                    f"Persistence variable '{variable_name}' is already listed."
                )
                self._persistence_warning.show()
                return
        row = self._insert_persistence_variable_row(
            variable_name=variable_name,
            rule=rule,
            custom=True,
        )
        self._persistence_variables_table.setCurrentCell(row, 0)
        self._set_persistence_controls_enabled(self._persistence_editable)
        self._set_dirty(True)

    def _on_remove_persistence_variable_clicked(self) -> None:
        row = self._persistence_variables_table.currentRow()
        if row < 0:
            return
        if self._persistence_row_is_custom(row):
            self._persistence_variables_table.removeRow(row)
        else:
            combo = self._persistence_variables_table.cellWidget(row, 1)
            if isinstance(combo, QComboBox):
                combo.setCurrentIndex(combo.findData(None))
        try:
            self._sync_persistence_variables_text_from_table()
        except ValueError:
            pass
        self._set_persistence_controls_enabled(self._persistence_editable)
        self._set_dirty(True)

    def _on_persistence_variables_table_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._sync_all_persistence_row_enabled()
        try:
            self._sync_persistence_variables_text_from_table()
            self._persistence_warning.hide()
        except ValueError as exc:
            self._persistence_warning.setText(str(exc))
            self._persistence_warning.show()
        self._set_dirty(True)

    def _on_legacy_persistence_variables_text_changed(self) -> None:
        if self._loading:
            return
        try:
            policy = build_persistence_policy(
                entity_state=False,
                variables_text=self._persistence_variables_text.toPlainText(),
            )
        except ValueError as exc:
            self._persistence_warning.setText(str(exc))
            self._persistence_warning.show()
            return
        variables = {}
        if policy:
            raw_variables = policy.get("variables", {})
            variables = raw_variables if isinstance(raw_variables, dict) else {}
        self._persistence_warning.hide()
        self._set_persistence_variables_table(variables)
        self._set_dirty(True)

    def _set_color_controls_enabled(self, enabled: bool) -> None:
        active = enabled and self._color_check.isChecked()
        self._color_check.setEnabled(enabled)
        self._color_red_spin.setEnabled(active)
        self._color_green_spin.setEnabled(active)
        self._color_blue_spin.setEnabled(active)

    def _set_input_map_controls_enabled(self, enabled: bool) -> None:
        self._input_map_text.setReadOnly(not enabled)

    def _set_entity_commands_controls_enabled(self, enabled: bool) -> None:
        self._entity_commands_text.setReadOnly(not enabled)
        entity_commands = self._current_entity_commands_value()
        has_commands = bool(entity_commands)
        can_use_buttons = enabled and entity_commands is not None
        self._add_entity_command_button.setEnabled(can_use_buttons)
        self._edit_entity_command_button.setEnabled(can_use_buttons and has_commands)
        self._duplicate_entity_command_button.setEnabled(can_use_buttons and has_commands)
        self._remove_entity_command_button.setEnabled(can_use_buttons and has_commands)

    def _set_inventory_controls_enabled(self, enabled: bool) -> None:
        active = enabled and self._inventory_check.isChecked()
        self._inventory_check.setEnabled(enabled)
        self._inventory_max_stacks_spin.setEnabled(active)
        self._inventory_stacks_text.setReadOnly(not active)

    def _set_variables_controls_enabled(self, enabled: bool) -> None:
        self._variables_text.setReadOnly(not enabled)
        self._variables_table.set_editing_enabled(enabled)

    def _on_pick_parameter_value(self, name: str) -> None:
        edit = self._parameter_edits.get(name)
        if edit is None:
            return
        picker_kind = self._picker_kind_for_parameter(name)
        if picker_kind is None:
            return
        callback = self._reference_picker_callbacks.get(picker_kind)
        if callback is None:
            return
        request = None
        if picker_kind == "entity":
            request = EntityReferencePickerRequest(
                parameter_name=name,
                current_value=edit.text().strip(),
                parameter_spec=(
                    self._parameter_specs.get(name)
                    if isinstance(self._parameter_specs.get(name), dict)
                    else None
                ),
                current_area_id=self._current_area_id,
                entity_id=self._entity.id if self._entity is not None else None,
                entity_template_id=self._entity.template if self._entity is not None else None,
            )
        selected = call_reference_picker_callback(
            callback,
            edit.text().strip(),
            request=request,
        )
        if selected:
            edit.setText(selected)

    def _on_pixel_check_toggled(self) -> None:
        if self._loading:
            return
        self._sync_pixel_spin_enabled()
        self._set_dirty(True)

    def _on_color_check_toggled(self) -> None:
        if self._loading:
            return
        self._set_color_controls_enabled(self._color_editable)
        self._set_dirty(True)

    def _on_inventory_check_toggled(self) -> None:
        if self._loading:
            return
        self._set_inventory_controls_enabled(self._inventory_editable)
        self._set_dirty(True)

    def _sync_variables_text_from_table(self) -> None:
        variables = self._variables_table.variables()
        was_loading = self._loading
        self._loading = True
        try:
            self._variables_text.setPlainText(
                json.dumps(variables, indent=2, ensure_ascii=False)
                if variables
                else "{}"
            )
        finally:
            self._loading = was_loading

    def _after_variables_changed(self) -> None:
        self._sync_dialogues_summary()
        variable_names = self._current_entity_variable_names()
        if variable_names is not None and self._persistence_editable:
            try:
                variables = self._build_persistence_variables_from_table()
            except ValueError:
                variables = {}
            self._set_persistence_variables_table(
                variables,
                variable_names=variable_names,
            )
        self._set_dirty(True)

    def _on_variables_table_changed(self) -> None:
        if self._loading:
            return
        try:
            self._sync_variables_text_from_table()
            self._variables_warning.hide()
        except ValueError as exc:
            self._variables_warning.setText(str(exc))
            self._variables_warning.show()
        self._after_variables_changed()

    def _on_variables_text_changed(self) -> None:
        if self._loading:
            return
        stripped = self._variables_text.toPlainText().strip()
        try:
            variables = loads_json_data(stripped, source_name="Variables") if stripped else {}
            if not isinstance(variables, dict):
                raise ValueError("Variables must be a JSON object.")
        except (JsonDataDecodeError, ValueError) as exc:
            self._variables_warning.setText(f"Variables must be valid JSON.\n{exc}")
            self._variables_warning.show()
            self._set_dirty(True)
            return
        self._variables_table.set_variables(variables)
        self._variables_warning.hide()
        self._after_variables_changed()

    def _sync_pixel_spin_enabled(self) -> None:
        screen_space = self._effective_space == "screen"
        self._pixel_x_spin.setEnabled(screen_space or self._pixel_x_check.isChecked())
        self._pixel_y_spin.setEnabled(screen_space or self._pixel_y_check.isChecked())

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _on_entity_commands_text_changed(self) -> None:
        self._sync_entity_commands_summary()
        self._set_entity_commands_controls_enabled(self._entity_commands_editable)
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class EntityInstanceEditorWidget(QWidget):
    """Entity-instance editor with JSON and structured field tabs."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)
    fields_apply_requested = Signal()
    fields_revert_requested = Signal()
    fields_dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EntityInstanceEditorWidget")

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        configure_tab_widget_overflow(self._tabs)

        self._parameters_editor = _EntityInstanceParametersEditor()
        self._json_editor = _EntityInstanceJsonEditor()
        self._fields_editor = _EntityInstanceFieldsEditor()
        self._parameters_editor.set_named_dialogues_edit_callback(
            self._edit_named_dialogues_from_parameters
        )

        self._tabs.addTab(self._parameters_editor, "Parameters")
        self._tabs.addTab(self._fields_editor, "Entity Instance Editor")
        self._tabs.addTab(self._json_editor, "Entity Instance JSON")
        self._tabs.setCurrentIndex(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)
        self.setMinimumWidth(300)
        self._editor = self._json_editor.editor

        self._json_editor.apply_requested.connect(self.apply_requested.emit)
        self._json_editor.revert_requested.connect(self.revert_requested.emit)
        self._json_editor.dirty_changed.connect(self._on_json_dirty_changed)
        self._json_editor.editing_enabled_changed.connect(
            self.editing_enabled_changed.emit
        )
        self._parameters_editor.apply_requested.connect(self.fields_apply_requested.emit)
        self._parameters_editor.revert_requested.connect(self.fields_revert_requested.emit)
        self._parameters_editor.dirty_changed.connect(self._on_fields_dirty_changed)
        self._fields_editor.apply_requested.connect(self.fields_apply_requested.emit)
        self._fields_editor.revert_requested.connect(self.fields_revert_requested.emit)
        self._fields_editor.dirty_changed.connect(self._on_fields_dirty_changed)
        self._fields_editor.named_dialogues_changed.connect(
            self._parameters_editor.set_dialogues_shortcut_state
        )
        self._sync_editor_lock_state()

    @property
    def entity_id(self) -> str | None:
        return self._json_editor.entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._json_editor.editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._json_editor.is_dirty

    @property
    def fields_dirty(self) -> bool:
        return self._parameters_editor.is_dirty or self._fields_editor.is_dirty

    @property
    def has_parameters(self) -> bool:
        return self._parameters_editor.has_parameters

    @property
    def json_text(self) -> str:
        return self._json_editor.json_text

    @property
    def editor(self) -> QPlainTextEdit:
        return self._json_editor.editor

    @property
    def tab_count(self) -> int:
        return self._tabs.count()

    def tab_titles(self) -> list[str]:
        return [self._tabs.tabText(index) for index in range(self._tabs.count())]

    def current_tab_title(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    def set_current_tab(self, index: int) -> bool:
        if index < 0 or index >= self._tabs.count():
            return False
        self._tabs.setCurrentIndex(index)
        return True

    def set_current_tab_title(self, title: str) -> bool:
        for index in range(self._tabs.count()):
            if self._tabs.tabText(index) == title:
                self._tabs.setCurrentIndex(index)
                return True
        return False

    def set_editing_enabled(self, enabled: bool) -> None:
        self._json_editor.set_editing_enabled(enabled)
        self._sync_editor_lock_state()

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._parameters_editor.set_template_catalog(catalog)
        self._fields_editor.set_template_catalog(catalog)

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._parameters_editor.set_reference_picker_callbacks(
            area_picker=area_picker,
            entity_picker=entity_picker,
            entity_command_picker=entity_command_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            item_picker=item_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            project_command_inputs_provider=project_command_inputs_provider,
            asset_picker=asset_picker,
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )
        self._fields_editor.set_reference_picker_callbacks(
            area_picker=area_picker,
            entity_picker=entity_picker,
            entity_command_picker=entity_command_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            item_picker=item_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            project_command_inputs_provider=project_command_inputs_provider,
            asset_picker=asset_picker,
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )

    def set_area_context(self, area_id: str | None) -> None:
        self._parameters_editor.set_area_context(area_id)
        self._fields_editor.set_area_context(area_id)

    def set_area_bounds(self, width: int, height: int) -> None:
        self._fields_editor.set_area_bounds(width, height)

    def clear_entity(self) -> None:
        self._parameters_editor.clear_entity()
        self._json_editor.clear_entity()
        self._fields_editor.clear_entity()
        self._sync_editor_lock_state()

    def load_entity(self, entity: EntityDocument) -> None:
        self._parameters_editor.load_entity(entity)
        self._json_editor.load_entity(entity)
        self._fields_editor.load_entity(entity)
        self._sync_editor_lock_state()

    def set_json_text(self, text: str) -> None:
        self._json_editor.set_json_text(text)
        self._sync_editor_lock_state()

    def build_entity_from_fields(self) -> EntityDocument:
        document = self._fields_editor.build_entity_document()
        document.parameters = self._parameters_editor.build_parameters_value()
        return document

    def _edit_named_dialogues_from_parameters(
        self,
    ) -> tuple[dict[str, dict[str, Any]], str | None] | None:
        return self._fields_editor.edit_named_dialogues()

    def _on_json_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.dirty_changed.emit(dirty)

    def _on_fields_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.fields_dirty_changed.emit(dirty)

    def _sync_editor_lock_state(self) -> None:
        structured_dirty = self.fields_dirty
        self._json_editor.setEnabled(not structured_dirty)
        self._parameters_editor.setEnabled(not self._json_editor.is_dirty)
        self._fields_editor.setEnabled(not self._json_editor.is_dirty)


class EntityInstanceJsonPanel(QDockWidget):
    """Dockable entity-instance editor with internal tabs."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)
    fields_apply_requested = Signal()
    fields_revert_requested = Signal()
    fields_dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Entity Instance", parent)
        self.setObjectName("EntityInstanceJsonPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._editor_widget = EntityInstanceEditorWidget()
        self.setWidget(self._editor_widget)

        self._tabs = self._editor_widget._tabs
        self._parameters_editor = self._editor_widget._parameters_editor
        self._json_editor = self._editor_widget._json_editor
        self._fields_editor = self._editor_widget._fields_editor
        self._editor = self._editor_widget.editor

        self._editor_widget.apply_requested.connect(self.apply_requested.emit)
        self._editor_widget.revert_requested.connect(self.revert_requested.emit)
        self._editor_widget.dirty_changed.connect(self.dirty_changed.emit)
        self._editor_widget.editing_enabled_changed.connect(
            self.editing_enabled_changed.emit
        )
        self._editor_widget.fields_apply_requested.connect(
            self.fields_apply_requested.emit
        )
        self._editor_widget.fields_revert_requested.connect(
            self.fields_revert_requested.emit
        )
        self._editor_widget.fields_dirty_changed.connect(
            self.fields_dirty_changed.emit
        )

    @property
    def editor_widget(self) -> EntityInstanceEditorWidget:
        return self._editor_widget

    @property
    def entity_id(self) -> str | None:
        return self._editor_widget.entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._editor_widget.editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._editor_widget.is_dirty

    @property
    def fields_dirty(self) -> bool:
        return self._editor_widget.fields_dirty

    @property
    def json_text(self) -> str:
        return self._editor_widget.json_text

    @property
    def editor(self) -> QPlainTextEdit:
        return self._editor_widget.editor

    @property
    def tab_count(self) -> int:
        return self._editor_widget.tab_count

    def tab_titles(self) -> list[str]:
        return self._editor_widget.tab_titles()

    def current_tab_title(self) -> str:
        return self._editor_widget.current_tab_title()

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editor_widget.set_editing_enabled(enabled)

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._editor_widget.set_template_catalog(catalog)

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._editor_widget.set_reference_picker_callbacks(
            area_picker=area_picker,
            entity_picker=entity_picker,
            entity_command_picker=entity_command_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            item_picker=item_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            project_command_inputs_provider=project_command_inputs_provider,
            asset_picker=asset_picker,
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )

    def set_area_context(self, area_id: str | None) -> None:
        self._editor_widget.set_area_context(area_id)

    def set_area_bounds(self, width: int, height: int) -> None:
        self._editor_widget.set_area_bounds(width, height)

    def clear_entity(self) -> None:
        self._editor_widget.clear_entity()

    def load_entity(self, entity: EntityDocument) -> None:
        self._editor_widget.load_entity(entity)

    def set_json_text(self, text: str) -> None:
        self._editor_widget.set_json_text(text)

    def build_entity_from_fields(self) -> EntityDocument:
        return self._editor_widget.build_entity_from_fields()

"""Dockable entity-instance editor with JSON and structured field tabs."""

from __future__ import annotations

import json
import re
from typing import Callable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument
from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow

_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
_ENTITY_BOOL_DEFAULTS = {
    "solid": False,
    "pushable": False,
    "interactable": False,
    "present": True,
    "visible": True,
    "entity_commands_enabled": True,
}
_ENTITY_INT_DEFAULTS = {
    "weight": 1,
    "push_strength": 0,
    "collision_push_strength": 0,
    "interaction_priority": 0,
}
_MANAGED_EXTRA_KEYS = {
    "kind",
    "scope",
    "tags",
    "facing",
    *list(_ENTITY_BOOL_DEFAULTS.keys()),
    *list(_ENTITY_INT_DEFAULTS.keys()),
    "variables",
    "visuals",
    "persistence",
}

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


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _set_row_visible(label: QWidget, field: QWidget, visible: bool) -> None:
    label.setVisible(visible)
    field.setVisible(visible)


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


def _parse_tag_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _filtered_unmanaged_extra(extra: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in extra.items()
        if key not in _MANAGED_EXTRA_KEYS
    }


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
            raise ValueError(
                f"Persistence variable '{name}' must be true or false."
            )
        variables[name] = raw_value
    return bool(raw_entity_state), variables


def _build_persistence_policy(
    *,
    entity_state: bool,
    variables_text: str,
) -> dict[str, object] | None:
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
                raise ValueError(
                    f"Persistence variable '{name}' must be true or false."
                )
            variables[name] = raw_value

    if not entity_state and not variables:
        return None

    payload: dict[str, object] = {"entity_state": bool(entity_state)}
    if variables:
        payload["variables"] = variables
    return payload


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


class _EntityInstanceFieldsEditor(QWidget):
    """Structured editor for high-value entity instance fields."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

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
        self._facing_combo.addItems(["down", "up", "left", "right"])
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

        self._render_note = QLabel("Render properties are in the Render Properties panel ->")
        self._render_note.setStyleSheet("color: #666; font-style: italic;")
        self._render_note.setWordWrap(True)
        self._form.addRow(self._render_note)

        self._form.addRow(_section_label("Parameters"))
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

        self._form.addRow(_section_label("Variables"))
        self._variables_text = QPlainTextEdit()
        self._variables_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._variables_text.setFixedHeight(120)
        self._variables_text.setPlaceholderText("{\n  \"key\": true\n}")
        variables_font = QFont("Consolas", 10)
        variables_font.setStyleHint(QFont.StyleHint.Monospace)
        self._variables_text.setFont(variables_font)
        self._form.addRow(self._variables_text)

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

        self._persistence_entity_state_label = QLabel("entity_state")
        self._persistence_entity_state_check = QCheckBox("Persist entity state")
        self._form.addRow(
            self._persistence_entity_state_label,
            self._persistence_entity_state_check,
        )

        self._persistence_variables_note = QLabel(
            "Optional per-variable persistence overrides. Use JSON object syntax."
        )
        self._persistence_variables_note.setWordWrap(True)
        self._persistence_variables_note.setStyleSheet("color: #666; font-style: italic;")
        self._form.addRow("variables", self._persistence_variables_note)

        self._persistence_variables_text = QPlainTextEdit()
        self._persistence_variables_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._persistence_variables_text.setFixedHeight(120)
        self._persistence_variables_text.setPlaceholderText(
            '{\n'
            '  "shake_timer": false,\n'
            '  "times_pushed": true\n'
            '}'
        )
        persistence_font = QFont("Consolas", 10)
        persistence_font.setStyleHint(QFont.StyleHint.Monospace)
        self._persistence_variables_text.setFont(persistence_font)
        self._form.addRow(self._persistence_variables_text)

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
        self._loading = False
        self._dirty = False
        self._area_width = 0
        self._area_height = 0
        self._parameter_edits: dict[str, QLineEdit] = {}
        self._parameter_browse_buttons: dict[str, QPushButton] = {}
        self._reference_picker_callbacks: dict[
            str,
            Callable[[str], str | None] | None,
        ] = {
            "area": None,
            "entity": None,
            "item": None,
            "dialogue": None,
            "command": None,
        }
        self._parameters_editable = True
        self._persistence_editable = True

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
        self._variables_text.textChanged.connect(self._on_field_changed)
        self._visuals_text.textChanged.connect(self._on_field_changed)
        self._persistence_entity_state_check.toggled.connect(self._on_field_changed)
        self._persistence_variables_text.textChanged.connect(self._on_field_changed)

        self._set_buttons_enabled(False)
        self._clear_parameter_rows()
        self._set_extra_visible(False)
        self._sync_pixel_spin_enabled()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._template_catalog = catalog

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[[str], str | None] | None = None,
        entity_picker: Callable[[str], str | None] | None = None,
        item_picker: Callable[[str], str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
    ) -> None:
        self._reference_picker_callbacks = {
            "area": area_picker,
            "entity": entity_picker,
            "item": item_picker,
            "dialogue": dialogue_picker,
            "command": command_picker,
        }

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
            QSignalBlocker(self._variables_text),
            QSignalBlocker(self._visuals_text),
            QSignalBlocker(self._persistence_entity_state_check),
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
        self._variables_text.clear()
        self._visuals_text.clear()
        self._persistence_entity_state_check.setChecked(False)
        self._persistence_variables_text.clear()

    def _load_persistence_ui_state(
        self,
        raw_persistence: object,
    ) -> tuple[bool, dict[str, bool], str | None]:
        try:
            entity_state, variables = _parse_persistence_policy(raw_persistence)
            self._persistence_editable = True
            return entity_state, variables, None
        except ValueError as exc:
            self._persistence_editable = False
            warning = (
                "Persistence is not using the supported object shape. "
                f"Use the JSON tab to edit it.\n{exc}"
            )
            return False, {}, warning

    def _populate_field_values(
        self,
        entity: EntityDocument,
        *,
        tag_text: str,
        has_pixel_x: bool,
        has_pixel_y: bool,
        raw_variables: object,
        has_visuals_override: bool,
        raw_visuals: object,
        persistence_entity_state: bool,
        persistence_variables: dict[str, bool],
    ) -> None:
        self._id_edit.setText(entity.id)
        self._kind_edit.setText(str(entity._extra.get("kind", "")))
        self._tags_edit.setText(tag_text)
        self._template_label.setText(entity.template or "-")
        self._template_label.setCursorPosition(0)
        self._space_label.setText(self._effective_space)
        self._scope_combo.setCurrentText(str(entity._extra.get("scope", "area")))
        self._x_spin.setValue(entity.x)
        self._y_spin.setValue(entity.y)
        self._pixel_x_check.setChecked(has_pixel_x)
        self._pixel_y_check.setChecked(has_pixel_y)
        self._pixel_x_spin.setValue(entity.pixel_x or 0)
        self._pixel_y_spin.setValue(entity.pixel_y or 0)
        self._facing_combo.setCurrentText(str(entity._extra.get("facing", "down")))
        self._solid_check.setChecked(bool(entity._extra.get("solid", False)))
        self._pushable_check.setChecked(bool(entity._extra.get("pushable", False)))
        self._weight_spin.setValue(int(entity._extra.get("weight", 1)))
        self._push_strength_spin.setValue(int(entity._extra.get("push_strength", 0)))
        self._collision_push_strength_spin.setValue(
            int(entity._extra.get("collision_push_strength", 0))
        )
        self._interactable_check.setChecked(bool(entity._extra.get("interactable", False)))
        self._interaction_priority_spin.setValue(
            int(entity._extra.get("interaction_priority", 0))
        )
        self._present_check.setChecked(bool(entity._extra.get("present", True)))
        self._visible_check.setChecked(bool(entity._extra.get("visible", True)))
        self._entity_commands_enabled_check.setChecked(
            bool(entity._extra.get("entity_commands_enabled", True))
        )
        self._variables_text.setPlainText(
            json.dumps(raw_variables, indent=2, ensure_ascii=False)
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
                default=_ENTITY_BOOL_DEFAULTS[key],
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
                default=_ENTITY_INT_DEFAULTS[key],
            )

    def clear_entity(self) -> None:
        self._entity = None
        self._effective_space = "world"
        self._loading = True
        try:
            blockers = self._field_signal_blockers()
            self._reset_field_values()
            del blockers
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._clear_parameter_rows()
        self._parameter_warning.hide()
        self._parameters_widget.show()
        self._parameters_editable = True
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
        has_pixel_x = entity.pixel_x is not None
        has_pixel_y = entity.pixel_y is not None
        raw_tags = entity._extra.get("tags", [])
        tag_text = ", ".join(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else ""
        raw_variables = entity._extra.get("variables", {})
        has_visuals_override = "visuals" in entity._extra
        raw_visuals = entity._extra.get("visuals", [])
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
                raw_variables=raw_variables,
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
        self._show_unmanaged_extra(_filtered_unmanaged_extra(entity._extra))
        self._apply_persistence_warning(persistence_warning)
        self._set_persistence_controls_enabled(self._persistence_editable)
        self._set_dirty(False)
        self._set_buttons_enabled(True)

    def build_entity_document(self) -> EntityDocument:
        if self._entity is None:
            raise RuntimeError("No entity is currently loaded.")

        parameters = self._build_parameters_value()
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
            default="area",
        )

        tags = _parse_tag_list(self._tags_edit.text())
        if tags:
            extra["tags"] = tags

        self._apply_extra_value(
            extra,
            key="facing",
            value=self._facing_combo.currentText(),
            default="down",
        )

        self._apply_toggle_extra_values(extra)
        self._apply_numeric_extra_values(extra)

        variables_value = self._parse_optional_json_block(
            self._variables_text.toPlainText(),
            label="Variables",
            expected_type=dict,
            invalid_shape_message="Variables must be a JSON object.",
        )
        if variables_value:
            extra["variables"] = variables_value

        visuals_value = self._parse_optional_json_block(
            self._visuals_text.toPlainText(),
            label="Visuals",
            expected_type=list,
            invalid_shape_message="Visuals must be a JSON array.",
        )
        if visuals_value is not None:
            extra["visuals"] = visuals_value

        if self._persistence_editable:
            persistence_value = _build_persistence_policy(
                entity_state=bool(self._persistence_entity_state_check.isChecked()),
                variables_text=self._persistence_variables_text.toPlainText(),
            )
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
        if parameters is not None and not isinstance(parameters, dict):
            self._parameters_editable = False
            self._parameters_widget.hide()
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
        if isinstance(parameters, dict):
            parameter_names.update(parameters.keys())
        parameter_names.update(template_defaults.keys())

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
            picker_kind = _parameter_reference_kind(name)
            picker_callback = (
                None if picker_kind is None else self._reference_picker_callbacks.get(picker_kind)
            )
            if picker_callback is not None:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(edit, 1)
                browse_button = QPushButton("Browse...")
                browse_button.clicked.connect(
                    lambda _checked=False, parameter_name=name: self._on_pick_parameter_value(
                        parameter_name
                    )
                )
                row_layout.addWidget(browse_button)
                self._parameter_browse_buttons[name] = browse_button
            self._parameters_layout.addRow(label, row_widget)
            self._parameter_edits[name] = edit

    def _clear_parameter_rows(self) -> None:
        self._parameter_edits.clear()
        self._parameter_browse_buttons.clear()
        while self._parameters_layout.rowCount() > 0:
            self._parameters_layout.removeRow(0)

    def _build_parameters_value(self):
        if self._entity is None:
            return None
        if not self._parameters_editable:
            return self._entity.parameters
        parameters: dict[str, object] = {}
        for name, edit in self._parameter_edits.items():
            value, keep = _parse_parameter_text(edit.text())
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

    def _on_pick_parameter_value(self, name: str) -> None:
        edit = self._parameter_edits.get(name)
        if edit is None:
            return
        picker_kind = _parameter_reference_kind(name)
        if picker_kind is None:
            return
        callback = self._reference_picker_callbacks.get(picker_kind)
        if callback is None:
            return
        selected = callback(edit.text().strip())
        if selected:
            edit.setText(selected)

    def _on_pixel_check_toggled(self) -> None:
        if self._loading:
            return
        self._sync_pixel_spin_enabled()
        self._set_dirty(True)

    def _sync_pixel_spin_enabled(self) -> None:
        screen_space = self._effective_space == "screen"
        self._pixel_x_spin.setEnabled(screen_space or self._pixel_x_check.isChecked())
        self._pixel_y_spin.setEnabled(screen_space or self._pixel_y_check.isChecked())

    def _on_field_changed(self, *_args) -> None:
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

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        configure_tab_widget_overflow(self._tabs)

        self._json_editor = _EntityInstanceJsonEditor()
        self._fields_editor = _EntityInstanceFieldsEditor()

        self._tabs.addTab(self._json_editor, "Entity Instance JSON")
        self._tabs.addTab(self._fields_editor, "Entity Instance Editor")
        self.setWidget(self._tabs)
        self.setMinimumWidth(300)
        self._editor = self._json_editor.editor

        self._json_editor.apply_requested.connect(self.apply_requested.emit)
        self._json_editor.revert_requested.connect(self.revert_requested.emit)
        self._json_editor.dirty_changed.connect(self._on_json_dirty_changed)
        self._json_editor.editing_enabled_changed.connect(
            self.editing_enabled_changed.emit
        )
        self._fields_editor.apply_requested.connect(self.fields_apply_requested.emit)
        self._fields_editor.revert_requested.connect(self.fields_revert_requested.emit)
        self._fields_editor.dirty_changed.connect(self._on_fields_dirty_changed)
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
        return self._fields_editor.is_dirty

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

    def set_editing_enabled(self, enabled: bool) -> None:
        self._json_editor.set_editing_enabled(enabled)
        self._sync_editor_lock_state()

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._fields_editor.set_template_catalog(catalog)

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[[str], str | None] | None = None,
        entity_picker: Callable[[str], str | None] | None = None,
        item_picker: Callable[[str], str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
    ) -> None:
        self._fields_editor.set_reference_picker_callbacks(
            area_picker=area_picker,
            entity_picker=entity_picker,
            item_picker=item_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
        )

    def set_area_bounds(self, width: int, height: int) -> None:
        self._fields_editor.set_area_bounds(width, height)

    def clear_entity(self) -> None:
        self._json_editor.clear_entity()
        self._fields_editor.clear_entity()
        self._sync_editor_lock_state()

    def load_entity(self, entity: EntityDocument) -> None:
        self._json_editor.load_entity(entity)
        self._fields_editor.load_entity(entity)
        self._sync_editor_lock_state()

    def set_json_text(self, text: str) -> None:
        self._json_editor.set_json_text(text)
        self._sync_editor_lock_state()

    def build_entity_from_fields(self) -> EntityDocument:
        return self._fields_editor.build_entity_document()

    def _on_json_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.dirty_changed.emit(dirty)

    def _on_fields_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.fields_dirty_changed.emit(dirty)

    def _sync_editor_lock_state(self) -> None:
        self._json_editor.setEnabled(not self._fields_editor.is_dirty)
        self._fields_editor.setEnabled(not self._json_editor.is_dirty)

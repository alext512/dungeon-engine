"""Template editor with a focused visuals surface plus full raw JSON."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
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
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.entity_structured_fields import (
    DEFAULT_ENTITY_COLOR,
    ENTITY_BOOL_DEFAULTS,
    ENTITY_FACING_VALUES,
    ENTITY_INT_DEFAULTS,
    build_entity_commands,
    build_input_map,
    build_inventory,
    build_persistence_policy,
    default_entity_render_order,
    default_entity_y_sort,
    parse_color,
    parse_entity_commands,
    parse_input_map,
    parse_inventory,
    parse_persistence_policy,
    parse_tag_list,
)
from area_editor.widgets.dialogue_definition_dialog import (
    EntityDialoguesDialog,
    normalize_entity_dialogues,
    rename_active_dialogue_value,
    rename_self_target_dialogue_id_references,
    summarize_entity_dialogues,
)
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow


class _TemplateFieldsEditor(QWidget):
    """Focused structured editor for high-value entity template fields."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    section_changed = Signal(int)

    def __init__(self, template_id: str, parent=None) -> None:
        super().__init__(parent)
        self._template_id = template_id
        self._dirty = False
        self._loading = False
        self._editing_enabled = False
        self._current_data: dict[str, Any] | None = None
        self._color_editable = True
        self._input_map_editable = True
        self._entity_commands_editable = True
        self._inventory_editable = True
        self._persistence_editable = True
        self._dialogues_editable = True
        self._dialogues_value: dict[str, dict[str, Any]] = {}
        self._reference_picker_callbacks: dict[str, Callable[..., str | None] | None] = {
            "entity": None,
            "dialogue": None,
            "command": None,
        }
        self._render_default_space = "world"
        self._render_defaults_explicit: dict[str, bool] = {
            "render_order": False,
            "y_sort": False,
        }
        self._raw_json_tab_index: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel(f"Template: {template_id}")
        layout.addWidget(self._target_label)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._sections_tabs = QTabWidget()
        self._sections_tabs.setDocumentMode(True)
        configure_tab_widget_overflow(self._sections_tabs)
        self._sections_tabs.currentChanged.connect(self.section_changed.emit)
        layout.addWidget(self._sections_tabs, 1)

        basics_tab = QWidget()
        basics_layout = QVBoxLayout(basics_tab)
        basics_layout.setContentsMargins(0, 0, 0, 0)
        basics_form = QFormLayout()

        self._kind_edit = QLineEdit()
        self._kind_edit.textChanged.connect(self._on_text_changed)
        basics_form.addRow("kind", self._kind_edit)

        self._space_combo = QComboBox()
        self._space_combo.addItems(["world", "screen"])
        self._space_combo.currentIndexChanged.connect(self._on_space_changed)
        basics_form.addRow("space", self._space_combo)

        self._scope_combo = QComboBox()
        self._scope_combo.addItems(["area", "global"])
        self._scope_combo.currentIndexChanged.connect(self._on_text_changed)
        basics_form.addRow("scope", self._scope_combo)

        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("comma,separated,tags")
        self._tags_edit.textChanged.connect(self._on_text_changed)
        basics_form.addRow("tags", self._tags_edit)

        self._facing_combo = QComboBox()
        self._facing_combo.addItems(list(ENTITY_FACING_VALUES))
        self._facing_combo.currentIndexChanged.connect(self._on_text_changed)
        basics_form.addRow("facing", self._facing_combo)

        self._solid_check = QCheckBox()
        self._solid_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("solid", self._solid_check)

        self._pushable_check = QCheckBox()
        self._pushable_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("pushable", self._pushable_check)

        self._weight_spin = QSpinBox()
        self._weight_spin.setRange(1, 999999)
        self._weight_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("weight", self._weight_spin)

        self._push_strength_spin = QSpinBox()
        self._push_strength_spin.setRange(0, 999999)
        self._push_strength_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("push_strength", self._push_strength_spin)

        self._collision_push_strength_spin = QSpinBox()
        self._collision_push_strength_spin.setRange(0, 999999)
        self._collision_push_strength_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow(
            "collision_push_strength",
            self._collision_push_strength_spin,
        )

        self._interactable_check = QCheckBox()
        self._interactable_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("interactable", self._interactable_check)

        self._interaction_priority_spin = QSpinBox()
        self._interaction_priority_spin.setRange(0, 999999)
        self._interaction_priority_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("interaction_priority", self._interaction_priority_spin)

        self._present_check = QCheckBox()
        self._present_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("present", self._present_check)

        self._visible_check = QCheckBox()
        self._visible_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("visible", self._visible_check)

        self._entity_commands_enabled_check = QCheckBox()
        self._entity_commands_enabled_check.toggled.connect(self._on_text_changed)
        basics_form.addRow(
            "entity_commands_enabled",
            self._entity_commands_enabled_check,
        )

        self._color_warning = QLabel("")
        self._color_warning.setWordWrap(True)
        self._color_warning.setStyleSheet("color: #a25b00;")
        self._color_warning.hide()
        basics_form.addRow(self._color_warning)

        self._color_check = QCheckBox("Use custom RGB color")
        self._color_check.toggled.connect(self._on_color_check_toggled)
        basics_form.addRow("color", self._color_check)

        color_row = QWidget()
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self._color_red_spin = QSpinBox()
        self._color_red_spin.setRange(0, 255)
        self._color_red_spin.setPrefix("R ")
        self._color_red_spin.valueChanged.connect(self._on_text_changed)
        self._color_green_spin = QSpinBox()
        self._color_green_spin.setRange(0, 255)
        self._color_green_spin.setPrefix("G ")
        self._color_green_spin.valueChanged.connect(self._on_text_changed)
        self._color_blue_spin = QSpinBox()
        self._color_blue_spin.setRange(0, 255)
        self._color_blue_spin.setPrefix("B ")
        self._color_blue_spin.valueChanged.connect(self._on_text_changed)
        color_layout.addWidget(self._color_red_spin)
        color_layout.addWidget(self._color_green_spin)
        color_layout.addWidget(self._color_blue_spin)
        basics_form.addRow("rgb", color_row)

        self._render_order_spin = QSpinBox()
        self._render_order_spin.setRange(-9999, 9999)
        self._render_order_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("render_order", self._render_order_spin)

        self._y_sort_check = QCheckBox()
        self._y_sort_check.toggled.connect(self._on_text_changed)
        basics_form.addRow("y_sort", self._y_sort_check)

        self._sort_y_offset_spin = QDoubleSpinBox()
        self._sort_y_offset_spin.setRange(-4096.0, 4096.0)
        self._sort_y_offset_spin.setDecimals(2)
        self._sort_y_offset_spin.setSingleStep(1.0)
        self._sort_y_offset_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("sort_y_offset", self._sort_y_offset_spin)

        self._stack_order_spin = QSpinBox()
        self._stack_order_spin.setRange(-9999, 9999)
        self._stack_order_spin.valueChanged.connect(self._on_text_changed)
        basics_form.addRow("stack_order", self._stack_order_spin)
        basics_layout.addLayout(basics_form)

        variables_note = QLabel(
            "Optional template-level default variables. Use JSON object syntax."
        )
        variables_note.setWordWrap(True)
        variables_note.setStyleSheet("color: #666; font-style: italic;")
        basics_layout.addWidget(variables_note)

        self._variables_text = QPlainTextEdit()
        self._variables_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._variables_text.setPlaceholderText("{\n  \"opened\": false\n}")
        self._variables_text.setFont(font)
        self._variables_text.textChanged.connect(self._on_variables_text_changed)
        basics_layout.addWidget(self._variables_text, 1)
        self._sections_tabs.addTab(basics_tab, "Basics")

        dialogues_tab = QWidget()
        dialogues_layout = QVBoxLayout(dialogues_tab)
        dialogues_layout.setContentsMargins(0, 0, 0, 0)

        self._dialogues_warning = QLabel("")
        self._dialogues_warning.setWordWrap(True)
        self._dialogues_warning.setStyleSheet("color: #a25b00;")
        self._dialogues_warning.hide()
        dialogues_layout.addWidget(self._dialogues_warning)

        dialogues_note = QLabel(
            "Manage the template's named dialogues here. Mark one active to drive "
            "`open_entity_dialogue` when no dialogue id is passed."
        )
        dialogues_note.setWordWrap(True)
        dialogues_note.setStyleSheet("color: #666; font-style: italic;")
        dialogues_layout.addWidget(dialogues_note)

        self._dialogues_summary = QLabel("No dialogues")
        self._dialogues_summary.setWordWrap(True)
        dialogues_layout.addWidget(self._dialogues_summary)

        dialogues_buttons = QHBoxLayout()
        self._dialogues_edit_button = QPushButton("Edit Dialogues...")
        self._dialogues_edit_button.clicked.connect(self._on_edit_dialogues_clicked)
        dialogues_buttons.addWidget(self._dialogues_edit_button)
        dialogues_buttons.addStretch(1)
        dialogues_layout.addLayout(dialogues_buttons)
        dialogues_layout.addStretch(1)
        self._sections_tabs.addTab(dialogues_tab, "Dialogues")

        visuals_tab = QWidget()
        visuals_layout = QVBoxLayout(visuals_tab)
        visuals_layout.setContentsMargins(0, 0, 0, 0)

        note = QLabel("Edit the template's `visuals` array here. Use Raw JSON for the full file.")
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

        input_map_tab = QWidget()
        input_map_layout = QVBoxLayout(input_map_tab)
        input_map_layout.setContentsMargins(0, 0, 0, 0)

        self._input_map_warning = QLabel("")
        self._input_map_warning.setWordWrap(True)
        self._input_map_warning.setStyleSheet("color: #a25b00;")
        self._input_map_warning.hide()
        input_map_layout.addWidget(self._input_map_warning)

        input_map_note = QLabel(
            "Optional JSON object mapping logical actions to entity-command names."
        )
        input_map_note.setWordWrap(True)
        input_map_note.setStyleSheet("color: #666; font-style: italic;")
        input_map_layout.addWidget(input_map_note)

        self._input_map_text = QPlainTextEdit()
        self._input_map_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._input_map_text.setPlaceholderText(
            '{\n'
            '  "interact": "interact",\n'
            '  "menu": "menu"\n'
            '}'
        )
        self._input_map_text.setFont(font)
        self._input_map_text.textChanged.connect(self._on_text_changed)
        input_map_layout.addWidget(self._input_map_text, 1)
        self._sections_tabs.addTab(input_map_tab, "Input Map")

        entity_commands_tab = QWidget()
        entity_commands_layout = QVBoxLayout(entity_commands_tab)
        entity_commands_layout.setContentsMargins(0, 0, 0, 0)

        self._entity_commands_warning = QLabel("")
        self._entity_commands_warning.setWordWrap(True)
        self._entity_commands_warning.setStyleSheet("color: #a25b00;")
        self._entity_commands_warning.hide()
        entity_commands_layout.addWidget(self._entity_commands_warning)

        entity_commands_note = QLabel(
            "Optional JSON object mapping entity-command names to command arrays "
            "or {enabled, commands} objects."
        )
        entity_commands_note.setWordWrap(True)
        entity_commands_note.setStyleSheet("color: #666; font-style: italic;")
        entity_commands_layout.addWidget(entity_commands_note)

        self._entity_commands_text = QPlainTextEdit()
        self._entity_commands_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._entity_commands_text.setPlaceholderText(
            '{\n'
            '  "interact": [\n'
            '    {"type": "run_project_command", "command_id": "commands/example"}\n'
            "  ]\n"
            "}"
        )
        self._entity_commands_text.setFont(font)
        self._entity_commands_text.textChanged.connect(self._on_text_changed)
        entity_commands_layout.addWidget(self._entity_commands_text, 1)
        self._sections_tabs.addTab(entity_commands_tab, "Entity Commands")

        inventory_tab = QWidget()
        inventory_layout = QVBoxLayout(inventory_tab)
        inventory_layout.setContentsMargins(0, 0, 0, 0)

        self._inventory_warning = QLabel("")
        self._inventory_warning.setWordWrap(True)
        self._inventory_warning.setStyleSheet("color: #a25b00;")
        self._inventory_warning.hide()
        inventory_layout.addWidget(self._inventory_warning)

        inventory_form = QFormLayout()
        self._inventory_check = QCheckBox("Define entity-owned inventory")
        self._inventory_check.toggled.connect(self._on_inventory_check_toggled)
        inventory_form.addRow("inventory", self._inventory_check)

        self._inventory_max_stacks_spin = QSpinBox()
        self._inventory_max_stacks_spin.setRange(0, 999999)
        self._inventory_max_stacks_spin.valueChanged.connect(self._on_text_changed)
        inventory_form.addRow("max_stacks", self._inventory_max_stacks_spin)
        inventory_layout.addLayout(inventory_form)

        inventory_note = QLabel(
            "Optional stack array. Each stack needs item_id and quantity."
        )
        inventory_note.setWordWrap(True)
        inventory_note.setStyleSheet("color: #666; font-style: italic;")
        inventory_layout.addWidget(inventory_note)

        self._inventory_stacks_text = QPlainTextEdit()
        self._inventory_stacks_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._inventory_stacks_text.setPlaceholderText(
            "[\n"
            "  {\n"
            '    "item_id": "items/light_orb",\n'
            '    "quantity": 1\n'
            "  }\n"
            "]"
        )
        self._inventory_stacks_text.setFont(font)
        self._inventory_stacks_text.textChanged.connect(self._on_text_changed)
        inventory_layout.addWidget(self._inventory_stacks_text, 1)
        self._sections_tabs.addTab(inventory_tab, "Inventory")

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
        self._apply_button = QPushButton("Apply Structured Edits")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert Structured Edits")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.set_editing_enabled(False)

    def set_reference_picker_callbacks(
        self,
        *,
        entity_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._reference_picker_callbacks = {
            "entity": entity_picker,
            "entity_dialogue": entity_dialogue_picker,
            "dialogue": dialogue_picker,
            "command": command_picker,
        }

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def visuals_text(self) -> str:
        return self._visuals_text.toPlainText()

    def add_raw_json_tab(self, widget: QWidget) -> None:
        self._raw_json_tab_index = self._sections_tabs.addTab(widget, "Raw JSON")

    def is_raw_json_tab_index(self, index: int) -> bool:
        return self._raw_json_tab_index is not None and index == self._raw_json_tab_index

    def section_labels(self) -> list[str]:
        return [self._sections_tabs.tabText(index) for index in range(self._sections_tabs.count())]

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._kind_edit.setEnabled(enabled)
        self._space_combo.setEnabled(enabled)
        self._scope_combo.setEnabled(enabled)
        self._tags_edit.setEnabled(enabled)
        self._facing_combo.setEnabled(enabled)
        self._solid_check.setEnabled(enabled)
        self._pushable_check.setEnabled(enabled)
        self._weight_spin.setEnabled(enabled)
        self._push_strength_spin.setEnabled(enabled)
        self._collision_push_strength_spin.setEnabled(enabled)
        self._interactable_check.setEnabled(enabled)
        self._interaction_priority_spin.setEnabled(enabled)
        self._present_check.setEnabled(enabled)
        self._visible_check.setEnabled(enabled)
        self._entity_commands_enabled_check.setEnabled(enabled)
        self._set_color_controls_enabled(enabled and self._color_editable)
        self._render_order_spin.setEnabled(enabled)
        self._y_sort_check.setEnabled(enabled)
        self._sort_y_offset_spin.setEnabled(enabled)
        self._stack_order_spin.setEnabled(enabled)
        self._variables_text.setReadOnly(not enabled)
        self._dialogues_edit_button.setEnabled(enabled and self._dialogues_editable)
        self._visuals_text.setReadOnly(not enabled)
        self._input_map_text.setReadOnly(not (enabled and self._input_map_editable))
        self._entity_commands_text.setReadOnly(
            not (enabled and self._entity_commands_editable)
        )
        self._set_inventory_controls_enabled(enabled and self._inventory_editable)
        self._entity_state_check.setEnabled(enabled and self._persistence_editable)
        self._persistence_variables_text.setReadOnly(not (enabled and self._persistence_editable))
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)

    def load_template_data(self, data: dict[str, Any]) -> None:
        self._current_data = dumps_for_clone(data)
        raw_persistence = data.get("persistence")
        color_warning: str | None = None
        color: tuple[int, int, int] | None = None
        persistence_warning: str | None = None
        persistence_entity_state = False
        persistence_variables: dict[str, bool] = {}
        input_map_warning: str | None = None
        input_map: dict[str, str] = {}
        entity_commands_warning: str | None = None
        entity_commands: dict[str, Any] = {}
        inventory_warning: str | None = None
        inventory: dict[str, Any] | None = None
        dialogues_warning: str | None = None
        try:
            color = parse_color(data.get("color"))
            self._color_editable = True
        except ValueError as exc:
            color_warning = (
                "Color is not using the supported RGB array shape. "
                "Use the Raw JSON tab to edit it.\n"
                f"{exc}"
            )
            self._color_editable = False
        try:
            input_map = parse_input_map(data.get("input_map"))
            self._input_map_editable = True
        except ValueError as exc:
            input_map_warning = (
                "Input map is not using the supported object-of-strings shape. "
                "Use the Raw JSON tab to edit it.\n"
                f"{exc}"
            )
            self._input_map_editable = False
        try:
            entity_commands = parse_entity_commands(data.get("entity_commands"))
            self._entity_commands_editable = True
        except ValueError as exc:
            entity_commands_warning = (
                "Entity commands are not using the supported object shape. "
                "Use the Raw JSON tab to edit them.\n"
                f"{exc}"
            )
            self._entity_commands_editable = False
        try:
            inventory = parse_inventory(data.get("inventory"))
            self._inventory_editable = True
        except ValueError as exc:
            inventory_warning = (
                "Inventory is not using the supported object shape. "
                "Use the Raw JSON tab to edit it.\n"
                f"{exc}"
            )
            self._inventory_editable = False
        try:
            self._dialogues_value = normalize_entity_dialogues(data.get("dialogues"))
            self._dialogues_editable = True
        except ValueError as exc:
            dialogues_warning = (
                "Dialogues are not using the supported named-dialogue shape. "
                "Use the Raw JSON tab to edit them.\n"
                f"{exc}"
            )
            self._dialogues_value = {}
            self._dialogues_editable = False
        try:
            persistence_entity_state, persistence_variables = parse_persistence_policy(
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
            self._kind_edit.setText(str(data.get("kind", "")))
            self._space_combo.setCurrentText(str(data.get("space", "world")))
            self._scope_combo.setCurrentText(str(data.get("scope", "area")))
            raw_tags = data.get("tags", [])
            tag_text = ", ".join(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else ""
            self._tags_edit.setText(tag_text)
            self._facing_combo.setCurrentText(str(data.get("facing", "down")))
            self._solid_check.setChecked(bool(data.get("solid", False)))
            self._pushable_check.setChecked(bool(data.get("pushable", False)))
            self._weight_spin.setValue(int(data.get("weight", 1)))
            self._push_strength_spin.setValue(int(data.get("push_strength", 0)))
            self._collision_push_strength_spin.setValue(
                int(data.get("collision_push_strength", 0))
            )
            self._interactable_check.setChecked(bool(data.get("interactable", False)))
            self._interaction_priority_spin.setValue(
                int(data.get("interaction_priority", 0))
            )
            self._present_check.setChecked(bool(data.get("present", True)))
            self._visible_check.setChecked(bool(data.get("visible", True)))
            self._entity_commands_enabled_check.setChecked(
                bool(data.get("entity_commands_enabled", True))
            )
            has_color = color is not None
            red, green, blue = color or DEFAULT_ENTITY_COLOR
            self._color_check.setChecked(has_color)
            self._color_red_spin.setValue(red)
            self._color_green_spin.setValue(green)
            self._color_blue_spin.setValue(blue)
            self._render_default_space = self._space_combo.currentText()
            self._render_defaults_explicit = {
                "render_order": "render_order" in data,
                "y_sort": "y_sort" in data,
            }
            self._render_order_spin.setValue(
                int(
                    data.get(
                        "render_order",
                        default_entity_render_order(self._render_default_space),
                    )
                )
            )
            self._y_sort_check.setChecked(
                bool(
                    data.get(
                        "y_sort",
                        default_entity_y_sort(self._render_default_space),
                    )
                )
            )
            self._sort_y_offset_spin.setValue(float(data.get("sort_y_offset", 0.0)))
            self._stack_order_spin.setValue(int(data.get("stack_order", 0)))
            raw_variables = data.get("variables", {})
            self._variables_text.setPlainText(
                json.dumps(raw_variables, indent=2, ensure_ascii=False)
                if raw_variables
                else ""
            )
            visuals = data.get("visuals", [])
            self._visuals_text.setPlainText(json.dumps(visuals, indent=2, ensure_ascii=False))
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
            self._entity_state_check.setChecked(persistence_entity_state)
            self._persistence_variables_text.setPlainText(
                json.dumps(persistence_variables, indent=2, ensure_ascii=False)
                if persistence_variables
                else ""
            )
        finally:
            self._loading = False
        if color_warning:
            self._color_warning.setText(color_warning)
            self._color_warning.show()
        else:
            self._color_warning.hide()
        if persistence_warning:
            self._persistence_warning.setText(persistence_warning)
            self._persistence_warning.show()
        else:
            self._persistence_warning.hide()
        if input_map_warning:
            self._input_map_warning.setText(input_map_warning)
            self._input_map_warning.show()
        else:
            self._input_map_warning.hide()
        if entity_commands_warning:
            self._entity_commands_warning.setText(entity_commands_warning)
            self._entity_commands_warning.show()
        else:
            self._entity_commands_warning.hide()
        if dialogues_warning:
            self._dialogues_warning.setText(dialogues_warning)
            self._dialogues_warning.show()
        else:
            self._dialogues_warning.hide()
        self._dialogues_edit_button.setEnabled(self._editing_enabled and self._dialogues_editable)
        self._sync_dialogues_summary()
        if inventory_warning:
            self._inventory_warning.setText(inventory_warning)
            self._inventory_warning.show()
        else:
            self._inventory_warning.hide()
        self._set_color_controls_enabled(
            self._editing_enabled and self._color_editable
        )
        self._input_map_text.setReadOnly(not (self._editing_enabled and self._input_map_editable))
        self._entity_commands_text.setReadOnly(
            not (self._editing_enabled and self._entity_commands_editable)
        )
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )
        self._entity_state_check.setEnabled(self._editing_enabled and self._persistence_editable)
        self._persistence_variables_text.setReadOnly(
            not (self._editing_enabled and self._persistence_editable)
        )
        self._set_dirty(False)

    def _current_variables_value_for_dialogues(self) -> dict[str, Any] | None:
        variables_text = self._variables_text.toPlainText().strip()
        if not variables_text:
            return {}
        try:
            parsed = loads_json_data(
                variables_text,
                source_name="Template variables",
            )
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
        return None

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

    def _open_entity_dialogues_dialog(
        self,
        dialogues: object,
        *,
        active_dialogue: object,
    ) -> tuple[dict[str, dict[str, Any]], str | None, dict[str, str]] | None:
        dialog = EntityDialoguesDialog(
            self,
            entity_picker=self._reference_picker_callbacks.get("entity"),
            entity_dialogue_picker=self._reference_picker_callbacks.get("entity_dialogue"),
            dialogue_picker=self._reference_picker_callbacks.get("dialogue"),
            command_picker=self._reference_picker_callbacks.get("command"),
            current_entity_id=None,
        )
        dialog.load_dialogues(dialogues, active_dialogue=active_dialogue)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.dialogues(), dialog.active_dialogue(), dialog.rename_map()

    def _on_edit_dialogues_clicked(self) -> None:
        if not self._dialogues_editable:
            return
        variables = self._current_variables_value_for_dialogues()
        if variables is None:
            QMessageBox.warning(
                self,
                "Invalid Variables",
                "Fix the Variables JSON before editing named dialogues.",
            )
            return
        updated = self._open_entity_dialogues_dialog(
            self._dialogues_value,
            active_dialogue=variables.get("active_dialogue"),
        )
        if updated is None:
            return
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
        self._loading = True
        try:
            self._variables_text.setPlainText(
                json.dumps(next_variables, indent=2, ensure_ascii=False)
                if next_variables
                else ""
            )
        finally:
            self._loading = False
        self._apply_dialogue_rename_map_to_entity_commands(rename_map)
        self._sync_dialogues_summary()
        self._set_dirty(True)

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
            parsed = loads_json_data(raw_text, source_name="Template entity commands")
        except JsonDataDecodeError:
            return
        if not isinstance(parsed, dict):
            return
        rewritten = rename_self_target_dialogue_id_references(
            parsed,
            rename_map,
            current_entity_id=None,
        )
        if rewritten == parsed:
            return
        self._loading = True
        try:
            self._entity_commands_text.setPlainText(
                json.dumps(rewritten, indent=2, ensure_ascii=False)
            )
        finally:
            self._loading = False

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
        kind_value = self._kind_edit.text().strip()
        if kind_value:
            updated["kind"] = kind_value
        else:
            updated.pop("kind", None)

        space_value = self._space_combo.currentText()
        if space_value != "world" or "space" in base_data:
            updated["space"] = space_value
        else:
            updated.pop("space", None)

        scope_value = self._scope_combo.currentText()
        if scope_value != "area" or "scope" in base_data:
            updated["scope"] = scope_value
        else:
            updated.pop("scope", None)

        tags = parse_tag_list(self._tags_edit.text())
        if tags:
            updated["tags"] = tags
        else:
            updated.pop("tags", None)

        self._apply_defaulted_field(
            updated,
            base_data,
            key="facing",
            value=self._facing_combo.currentText(),
            default="down",
        )
        for key, widget in (
            ("solid", self._solid_check),
            ("pushable", self._pushable_check),
            ("interactable", self._interactable_check),
            ("present", self._present_check),
            ("visible", self._visible_check),
            ("entity_commands_enabled", self._entity_commands_enabled_check),
        ):
            self._apply_defaulted_field(
                updated,
                base_data,
                key=key,
                value=bool(widget.isChecked()),
                default=ENTITY_BOOL_DEFAULTS[key],
            )
        for key, widget in (
            ("weight", self._weight_spin),
            ("push_strength", self._push_strength_spin),
            ("collision_push_strength", self._collision_push_strength_spin),
            ("interaction_priority", self._interaction_priority_spin),
        ):
            self._apply_defaulted_field(
                updated,
                base_data,
                key=key,
                value=int(widget.value()),
                default=ENTITY_INT_DEFAULTS[key],
            )

        if self._color_editable:
            if self._color_check.isChecked():
                updated["color"] = [
                    int(self._color_red_spin.value()),
                    int(self._color_green_spin.value()),
                    int(self._color_blue_spin.value()),
                ]
            else:
                updated.pop("color", None)
        elif "color" in base_data:
            updated["color"] = base_data["color"]
        else:
            updated.pop("color", None)

        self._apply_defaulted_field(
            updated,
            base_data,
            key="render_order",
            value=int(self._render_order_spin.value()),
            default=default_entity_render_order(space_value),
        )
        self._apply_defaulted_field(
            updated,
            base_data,
            key="y_sort",
            value=bool(self._y_sort_check.isChecked()),
            default=default_entity_y_sort(space_value),
        )
        self._apply_defaulted_field(
            updated,
            base_data,
            key="sort_y_offset",
            value=float(self._sort_y_offset_spin.value()),
            default=0.0,
        )
        self._apply_defaulted_field(
            updated,
            base_data,
            key="stack_order",
            value=int(self._stack_order_spin.value()),
            default=0,
        )

        variables_value = self._build_variables_value()
        if variables_value:
            updated["variables"] = variables_value
        else:
            updated.pop("variables", None)

        if self._dialogues_editable:
            if self._dialogues_value:
                updated["dialogues"] = copy.deepcopy(self._dialogues_value)
            else:
                updated.pop("dialogues", None)
        elif "dialogues" in base_data:
            updated["dialogues"] = copy.deepcopy(base_data["dialogues"])
        else:
            updated.pop("dialogues", None)

        updated["visuals"] = visuals_value
        if self._input_map_editable:
            input_map_value = build_input_map(
                self._input_map_text.toPlainText(),
                source_name="Template input map",
            )
            if input_map_value is None:
                updated.pop("input_map", None)
            else:
                updated["input_map"] = input_map_value
        elif "input_map" in base_data:
            updated["input_map"] = base_data["input_map"]
        else:
            updated.pop("input_map", None)
        if self._entity_commands_editable:
            entity_commands_value = build_entity_commands(
                self._entity_commands_text.toPlainText(),
                source_name="Template entity commands",
            )
            if entity_commands_value is None:
                updated.pop("entity_commands", None)
            else:
                updated["entity_commands"] = entity_commands_value
        elif "entity_commands" in base_data:
            updated["entity_commands"] = base_data["entity_commands"]
        else:
            updated.pop("entity_commands", None)
        if self._inventory_editable:
            inventory_value = build_inventory(
                enabled=bool(self._inventory_check.isChecked()),
                max_stacks=int(self._inventory_max_stacks_spin.value()),
                stacks_text=self._inventory_stacks_text.toPlainText(),
                base_inventory=base_data.get("inventory"),
                source_name="Template inventory stacks",
            )
            if inventory_value is None:
                updated.pop("inventory", None)
            else:
                updated["inventory"] = inventory_value
        elif "inventory" in base_data:
            updated["inventory"] = base_data["inventory"]
        else:
            updated.pop("inventory", None)
        if self._persistence_editable:
            persistence_value = build_persistence_policy(
                entity_state=bool(self._entity_state_check.isChecked()),
                variables_text=self._persistence_variables_text.toPlainText(),
            )
            if persistence_value is None:
                updated.pop("persistence", None)
            else:
                updated["persistence"] = persistence_value
        elif "persistence" in base_data:
            updated["persistence"] = base_data["persistence"]
        else:
            updated.pop("persistence", None)
        return updated

    def _build_variables_value(self) -> dict[str, Any] | None:
        variables_text = self._variables_text.toPlainText().strip()
        if not variables_text:
            return None
        try:
            variables_value = loads_json_data(
                variables_text,
                source_name="Template variables",
            )
        except JsonDataDecodeError as exc:
            raise ValueError(f"Variables must be valid JSON.\n{exc}") from exc
        if not isinstance(variables_value, dict):
            raise ValueError("Variables must be a JSON object.")
        return variables_value

    def _apply_defaulted_field(
        self,
        updated: dict[str, Any],
        base_data: dict[str, Any],
        *,
        key: str,
        value: Any,
        default: Any,
    ) -> None:
        if value != default or key in base_data:
            updated[key] = value
        else:
            updated.pop(key, None)

    def _on_space_changed(self) -> None:
        if self._loading:
            return
        old_space = self._render_default_space
        new_space = self._space_combo.currentText()
        if (
            not self._render_defaults_explicit.get("render_order", False)
            and int(self._render_order_spin.value())
            == default_entity_render_order(old_space)
        ):
            self._render_order_spin.setValue(default_entity_render_order(new_space))
        if (
            not self._render_defaults_explicit.get("y_sort", False)
            and bool(self._y_sort_check.isChecked())
            == default_entity_y_sort(old_space)
        ):
            self._y_sort_check.setChecked(default_entity_y_sort(new_space))
        self._render_default_space = new_space
        self._set_dirty(True)

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _on_variables_text_changed(self) -> None:
        if self._loading:
            return
        self._sync_dialogues_summary()
        self._set_dirty(True)

    def _on_color_check_toggled(self) -> None:
        if self._loading:
            return
        self._set_color_controls_enabled(
            self._editing_enabled and self._color_editable
        )
        self._set_dirty(True)

    def _on_inventory_check_toggled(self) -> None:
        if self._loading:
            return
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )
        self._set_dirty(True)

    def _set_color_controls_enabled(self, enabled: bool) -> None:
        active = enabled and self._color_check.isChecked()
        self._color_check.setEnabled(enabled)
        self._color_red_spin.setEnabled(active)
        self._color_green_spin.setEnabled(active)
        self._color_blue_spin.setEnabled(active)

    def _set_inventory_controls_enabled(self, enabled: bool) -> None:
        active = enabled and self._inventory_check.isChecked()
        self._inventory_check.setEnabled(enabled)
        self._inventory_max_stacks_spin.setEnabled(active)
        self._inventory_stacks_text.setReadOnly(not active)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)


class EntityTemplateEditorWidget(QWidget):
    """Central-tab template editor with structured sections and raw JSON."""

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

        self._fields_editor = _TemplateFieldsEditor(content_id)
        self._raw_json = JsonViewerWidget(file_path)
        self._fields_editor.add_raw_json_tab(self._raw_json)
        layout.addWidget(self._fields_editor)

        self._fields_editor.apply_requested.connect(self._on_apply_fields)
        self._fields_editor.revert_requested.connect(self._on_revert_fields)
        self._fields_editor.dirty_changed.connect(self._on_surface_dirty_changed)
        self._fields_editor.section_changed.connect(self._on_section_tab_changed)
        self._raw_json.dirty_changed.connect(self._on_surface_dirty_changed)

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
    def fields_editor(self) -> _TemplateFieldsEditor:
        return self._fields_editor

    def set_reference_picker_callbacks(
        self,
        *,
        entity_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._fields_editor.set_reference_picker_callbacks(
            entity_picker=entity_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
        )

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
            QMessageBox.warning(self, "Invalid Template Fields", str(exc))

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

    def _on_section_tab_changed(self, index: int) -> None:
        if self._fields_editor.is_raw_json_tab_index(index):
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

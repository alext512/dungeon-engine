"""Template editor with a focused visuals surface plus full raw JSON."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
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
    build_persistence_policy,
    default_entity_render_order,
    default_entity_y_sort,
    entity_command_command_list,
    parse_color,
    parse_entity_commands,
    parse_input_map,
    parse_inventory,
    parse_inventory_stacks,
    parse_persistence_policy,
    parse_tag_list,
    replace_entity_command_command_list,
    suggested_entity_command_copy_name,
    summarize_entity_commands,
)
from area_editor.widgets.entity_visuals_editor import (
    EntityVisualsEditor,
    parse_visuals,
)
from area_editor.widgets.command_list_dialog import CommandListDialog
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
        self._visuals_editable = True
        self._dialogues_editable = True
        self._dialogues_value: dict[str, dict[str, Any]] = {}
        self._reference_picker_callbacks: dict[str, Callable[..., str | None] | None] = {
            "area": None,
            "asset": None,
            "entity": None,
            "entity_command": None,
            "entity_dialogue": None,
            "item": None,
            "dialogue": None,
            "command": None,
            "project_command_inputs": None,
            "visual": None,
            "animation": None,
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

        note = QLabel(
            "Edit the template's visuals here. Right-click the list to add or duplicate; "
            "drag to reorder. Use Raw JSON for the full file."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-style: italic;")
        visuals_layout.addWidget(note)

        self._visuals_warning = QLabel("")
        self._visuals_warning.setWordWrap(True)
        self._visuals_warning.setStyleSheet("color: #a25b00;")
        self._visuals_warning.hide()
        visuals_layout.addWidget(self._visuals_warning)

        self._visuals_editor = EntityVisualsEditor()
        self._visuals_editor.changed.connect(self._on_visuals_changed)
        visuals_layout.addWidget(self._visuals_editor, 1)

        self._visuals_text = QPlainTextEdit()
        self._visuals_text.hide()
        self._visuals_text.textChanged.connect(self._on_legacy_visuals_text_changed)
        self._sections_tabs.addTab(visuals_tab, "Visuals")

        self._input_map_tab = QWidget()
        input_map_layout = QVBoxLayout(self._input_map_tab)
        input_map_layout.setContentsMargins(0, 0, 0, 0)

        self._input_map_warning = QLabel("")
        self._input_map_warning.setWordWrap(True)
        self._input_map_warning.setStyleSheet("color: #a25b00;")
        self._input_map_warning.hide()
        input_map_layout.addWidget(self._input_map_warning)

        input_map_note = QLabel(
            "Optional mapping from logical actions to entity-command names."
        )
        input_map_note.setWordWrap(True)
        input_map_note.setStyleSheet("color: #666; font-style: italic;")
        input_map_layout.addWidget(input_map_note)

        input_map_buttons = QHBoxLayout()
        self._add_input_map_row_button = QPushButton("Add Route")
        self._add_input_map_row_button.clicked.connect(self._on_add_input_map_row_clicked)
        input_map_buttons.addWidget(self._add_input_map_row_button)
        self._remove_input_map_row_button = QPushButton("Remove Selected")
        self._remove_input_map_row_button.clicked.connect(
            self._on_remove_input_map_row_clicked
        )
        input_map_buttons.addWidget(self._remove_input_map_row_button)
        input_map_buttons.addStretch(1)
        input_map_layout.addLayout(input_map_buttons)

        self._input_map_table = QTableWidget(0, 2)
        self._input_map_table.setHorizontalHeaderLabels(["Action", "Entity Command"])
        self._input_map_table.horizontalHeader().setStretchLastSection(True)
        self._input_map_table.cellChanged.connect(self._on_input_map_table_changed)
        self._input_map_table.currentCellChanged.connect(
            lambda *_args: self._set_input_map_controls_enabled(
                self._editing_enabled and self._input_map_editable
            )
        )
        input_map_layout.addWidget(self._input_map_table, 1)

        self._input_map_text = QPlainTextEdit()
        self._input_map_text.hide()
        self._input_map_text.textChanged.connect(self._on_legacy_input_map_text_changed)
        self._input_map_tab.hide()

        entity_commands_tab = QWidget()
        entity_commands_layout = QVBoxLayout(entity_commands_tab)
        entity_commands_layout.setContentsMargins(0, 0, 0, 0)

        self._entity_commands_warning = QLabel("")
        self._entity_commands_warning.setWordWrap(True)
        self._entity_commands_warning.setStyleSheet("color: #a25b00;")
        self._entity_commands_warning.hide()
        entity_commands_layout.addWidget(self._entity_commands_warning)

        entity_commands_note = QLabel(
            "Optional named entity commands. Use Raw JSON for unsupported command metadata."
        )
        entity_commands_note.setWordWrap(True)
        entity_commands_note.setStyleSheet("color: #666; font-style: italic;")
        entity_commands_layout.addWidget(entity_commands_note)

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
        entity_commands_layout.addWidget(entity_commands_controls_widget)

        self._entity_commands_table = QTableWidget(0, 3)
        self._entity_commands_table.setHorizontalHeaderLabels(
            ["Command", "Enabled", "Commands"]
        )
        self._entity_commands_table.horizontalHeader().setStretchLastSection(True)
        self._entity_commands_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._entity_commands_table.currentCellChanged.connect(
            lambda *_args: self._set_entity_commands_controls_enabled(
                self._editing_enabled and self._entity_commands_editable
            )
        )
        self._entity_commands_table.cellDoubleClicked.connect(
            lambda *_args: self._on_edit_entity_command_clicked()
        )
        entity_commands_layout.addWidget(self._entity_commands_table, 1)

        self._entity_commands_text = QPlainTextEdit()
        self._entity_commands_text.hide()
        self._entity_commands_text.textChanged.connect(self._on_entity_commands_text_changed)
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
            "Optional starting stacks. Each stack needs item_id and quantity."
        )
        inventory_note.setWordWrap(True)
        inventory_note.setStyleSheet("color: #666; font-style: italic;")
        inventory_layout.addWidget(inventory_note)

        inventory_buttons = QHBoxLayout()
        self._add_inventory_stack_button = QPushButton("Add Stack")
        self._add_inventory_stack_button.clicked.connect(
            self._on_add_inventory_stack_clicked
        )
        inventory_buttons.addWidget(self._add_inventory_stack_button)
        self._remove_inventory_stack_button = QPushButton("Remove Selected")
        self._remove_inventory_stack_button.clicked.connect(
            self._on_remove_inventory_stack_clicked
        )
        inventory_buttons.addWidget(self._remove_inventory_stack_button)
        inventory_buttons.addStretch(1)
        inventory_layout.addLayout(inventory_buttons)

        self._inventory_stacks_table = QTableWidget(0, 2)
        self._inventory_stacks_table.setHorizontalHeaderLabels(["Item", "Quantity"])
        self._inventory_stacks_table.horizontalHeader().setStretchLastSection(True)
        self._inventory_stacks_table.cellChanged.connect(
            self._on_inventory_stacks_table_changed
        )
        self._inventory_stacks_table.currentCellChanged.connect(
            lambda *_args: self._set_inventory_controls_enabled(
                self._editing_enabled and self._inventory_editable
            )
        )
        inventory_layout.addWidget(self._inventory_stacks_table, 1)

        self._inventory_stacks_text = QPlainTextEdit()
        self._inventory_stacks_text.hide()
        self._inventory_stacks_text.textChanged.connect(
            self._on_legacy_inventory_stacks_text_changed
        )
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
            "Template variables are listed automatically. Check Override to "
            "write a per-variable persistence rule."
        )
        persistence_note.setWordWrap(True)
        persistence_note.setStyleSheet("color: #666; font-style: italic;")
        persistence_layout.addWidget(persistence_note)

        persistence_buttons = QHBoxLayout()
        self._add_persistence_variable_button = QPushButton("Add Extra Variable")
        self._add_persistence_variable_button.clicked.connect(
            self._on_add_persistence_variable_clicked
        )
        persistence_buttons.addWidget(self._add_persistence_variable_button)
        self._remove_persistence_variable_button = QPushButton("Remove Selected")
        self._remove_persistence_variable_button.clicked.connect(
            self._on_remove_persistence_variable_clicked
        )
        persistence_buttons.addWidget(self._remove_persistence_variable_button)
        persistence_buttons.addStretch(1)
        persistence_layout.addLayout(persistence_buttons)

        self._persistence_variables_table = QTableWidget(0, 3)
        self._persistence_variables_table.setHorizontalHeaderLabels(
            ["Variable", "Override", "Persistent"]
        )
        self._persistence_variables_table.horizontalHeader().setStretchLastSection(True)
        self._persistence_variables_table.cellChanged.connect(
            self._on_persistence_variables_table_changed
        )
        self._persistence_variables_table.currentCellChanged.connect(
            lambda *_args: self._set_persistence_variable_controls_enabled(
                self._editing_enabled and self._persistence_editable
            )
        )
        persistence_layout.addWidget(self._persistence_variables_table, 1)

        self._persistence_variables_text = QPlainTextEdit()
        self._persistence_variables_text.hide()
        self._persistence_variables_text.textChanged.connect(
            self._on_legacy_persistence_variables_text_changed
        )
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

    def set_reference_picker_callbacks(
        self,
        *,
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._reference_picker_callbacks = {
            "area": area_picker,
            "asset": asset_picker,
            "entity": entity_picker,
            "entity_command": entity_command_picker,
            "entity_dialogue": entity_dialogue_picker,
            "item": item_picker,
            "dialogue": dialogue_picker,
            "command": command_picker,
            "project_command_inputs": project_command_inputs_provider,
            "visual": visual_picker,
            "animation": animation_picker,
        }
        self._visuals_editor.set_asset_picker(asset_picker)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def visuals_text(self) -> str:
        if not self._visuals_editable:
            return self._visuals_text.toPlainText()
        return self._visuals_editor.visuals_text()

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
        self._visuals_editor.set_editing_enabled(enabled and self._visuals_editable)
        self._set_input_map_controls_enabled(enabled and self._input_map_editable)
        self._set_entity_commands_controls_enabled(
            enabled and self._entity_commands_editable
        )
        self._set_inventory_controls_enabled(enabled and self._inventory_editable)
        self._entity_state_check.setEnabled(enabled and self._persistence_editable)
        self._set_persistence_variable_controls_enabled(
            enabled and self._persistence_editable
        )
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
        input_map: dict[str, str] = {}
        entity_commands_warning: str | None = None
        entity_commands: dict[str, Any] = {}
        inventory_warning: str | None = None
        inventory: dict[str, Any] | None = None
        visuals_warning: str | None = None
        visuals: list[dict[str, Any]] = []
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
            visuals = parse_visuals(data.get("visuals", []))
            self._visuals_editable = True
        except ValueError as exc:
            visuals_warning = (
                "Visuals are not using the supported array-of-objects shape. "
                "Use the Raw JSON tab to edit them.\n"
                f"{exc}"
            )
            self._visuals_editable = False
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
            self._visuals_editor.load_visuals(visuals)
            self._visuals_text.setPlainText(
                json.dumps(data.get("visuals", []), indent=2, ensure_ascii=False)
            )
            self._input_map_text.setPlainText(
                json.dumps(input_map, indent=2, ensure_ascii=False)
                if input_map
                else ""
            )
            self._set_input_map_table(input_map)
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
            self._set_inventory_stacks_table(
                inventory.get("stacks", []) if inventory else []
            )
            self._entity_state_check.setChecked(persistence_entity_state)
            self._persistence_variables_text.setPlainText(
                json.dumps(persistence_variables, indent=2, ensure_ascii=False)
                if persistence_variables
                else ""
            )
            self._set_persistence_variables_table(persistence_variables)
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
        self._input_map_warning.hide()
        if entity_commands_warning:
            self._entity_commands_warning.setText(entity_commands_warning)
            self._entity_commands_warning.show()
        else:
            self._entity_commands_warning.hide()
        self._sync_entity_commands_summary()
        if visuals_warning:
            self._visuals_warning.setText(visuals_warning)
            self._visuals_warning.show()
        else:
            self._visuals_warning.hide()
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
        self._set_input_map_controls_enabled(
            self._editing_enabled and self._input_map_editable
        )
        self._set_entity_commands_controls_enabled(
            self._editing_enabled and self._entity_commands_editable
        )
        self._visuals_editor.set_editing_enabled(
            self._editing_enabled and self._visuals_editable
        )
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )
        self._entity_state_check.setEnabled(self._editing_enabled and self._persistence_editable)
        self._set_persistence_variable_controls_enabled(
            self._editing_enabled and self._persistence_editable
        )
        self._set_dirty(False)

    def _set_input_map_controls_enabled(self, enabled: bool) -> None:
        self._input_map_text.setReadOnly(not enabled)
        self._input_map_table.setEnabled(enabled)
        self._add_input_map_row_button.setEnabled(enabled)
        self._remove_input_map_row_button.setEnabled(
            enabled and self._input_map_table.currentRow() >= 0
        )

    def _set_input_map_table(self, input_map: dict[str, str]) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            self._input_map_table.setRowCount(0)
            for action, command_name in input_map.items():
                row = self._input_map_table.rowCount()
                self._input_map_table.insertRow(row)
                self._input_map_table.setItem(row, 0, QTableWidgetItem(str(action)))
                self._input_map_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(str(command_name)),
                )
        finally:
            self._loading = was_loading
        self._set_input_map_controls_enabled(
            self._editing_enabled and self._input_map_editable
        )

    def _build_input_map_from_table(self) -> dict[str, str] | None:
        input_map: dict[str, str] = {}
        for row in range(self._input_map_table.rowCount()):
            action_item = self._input_map_table.item(row, 0)
            command_item = self._input_map_table.item(row, 1)
            action = action_item.text().strip() if action_item is not None else ""
            command_name = command_item.text().strip() if command_item is not None else ""
            if not action and not command_name:
                continue
            if not action:
                raise ValueError("Input map actions must not be blank.")
            if action in input_map:
                raise ValueError(f"Duplicate input map action '{action}'.")
            input_map[action] = command_name
        return input_map or None

    def _sync_input_map_text_from_table(self) -> None:
        input_map = self._build_input_map_from_table() or {}
        was_loading = self._loading
        self._loading = True
        try:
            self._input_map_text.setPlainText(
                json.dumps(input_map, indent=2, ensure_ascii=False)
                if input_map
                else ""
            )
        finally:
            self._loading = was_loading

    def _on_add_input_map_row_clicked(self) -> None:
        row = self._input_map_table.rowCount()
        self._input_map_table.insertRow(row)
        self._input_map_table.setItem(row, 0, QTableWidgetItem(""))
        self._input_map_table.setItem(row, 1, QTableWidgetItem(""))
        self._input_map_table.setCurrentCell(row, 0)
        self._set_input_map_controls_enabled(
            self._editing_enabled and self._input_map_editable
        )
        self._set_dirty(True)

    def _on_remove_input_map_row_clicked(self) -> None:
        row = self._input_map_table.currentRow()
        if row < 0:
            return
        self._input_map_table.removeRow(row)
        try:
            self._sync_input_map_text_from_table()
        except ValueError:
            pass
        self._set_input_map_controls_enabled(
            self._editing_enabled and self._input_map_editable
        )
        self._set_dirty(True)

    def _on_input_map_table_changed(self, *_args: object) -> None:
        if self._loading:
            return
        try:
            self._sync_input_map_text_from_table()
            self._input_map_warning.hide()
        except ValueError as exc:
            self._input_map_warning.setText(str(exc))
            self._input_map_warning.show()
        self._set_dirty(True)

    def _on_legacy_input_map_text_changed(self) -> None:
        if self._loading:
            return
        try:
            input_map = build_input_map(
                self._input_map_text.toPlainText(),
                source_name="Template input map",
            ) or {}
        except ValueError as exc:
            self._input_map_warning.setText(str(exc))
            self._input_map_warning.show()
            self._set_dirty(True)
            return
        self._input_map_warning.hide()
        self._set_input_map_table(input_map)
        self._set_dirty(True)

    def _set_inventory_stacks_table(self, stacks: object) -> None:
        parsed_stacks = parse_inventory_stacks(stacks)
        was_loading = self._loading
        self._loading = True
        try:
            self._inventory_stacks_table.setRowCount(0)
            for stack in parsed_stacks:
                row = self._inventory_stacks_table.rowCount()
                self._inventory_stacks_table.insertRow(row)
                self._inventory_stacks_table.setItem(
                    row,
                    0,
                    QTableWidgetItem(str(stack.get("item_id", ""))),
                )
                self._inventory_stacks_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(str(stack.get("quantity", ""))),
                )
        finally:
            self._loading = was_loading
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )

    def _build_inventory_stacks_from_table(self) -> list[dict[str, Any]]:
        raw_stacks: list[dict[str, Any]] = []
        for row in range(self._inventory_stacks_table.rowCount()):
            item_id_item = self._inventory_stacks_table.item(row, 0)
            quantity_item = self._inventory_stacks_table.item(row, 1)
            item_id = item_id_item.text().strip() if item_id_item is not None else ""
            quantity_text = (
                quantity_item.text().strip() if quantity_item is not None else ""
            )
            if not item_id and not quantity_text:
                continue
            quantity: object = quantity_text
            if quantity_text:
                try:
                    quantity = int(quantity_text)
                except ValueError:
                    pass
            raw_stacks.append({"item_id": item_id, "quantity": quantity})
        return parse_inventory_stacks(raw_stacks)

    def _build_inventory_from_table(
        self,
        *,
        base_inventory: object | None,
    ) -> dict[str, Any] | None:
        if not self._inventory_check.isChecked():
            return None
        inventory: dict[str, Any]
        if isinstance(base_inventory, dict):
            inventory = copy.deepcopy(base_inventory)
        else:
            inventory = {}
        inventory["max_stacks"] = int(self._inventory_max_stacks_spin.value())
        inventory["stacks"] = self._build_inventory_stacks_from_table()
        return parse_inventory(inventory)

    def _sync_inventory_stacks_text_from_table(self) -> None:
        stacks = self._build_inventory_stacks_from_table()
        was_loading = self._loading
        self._loading = True
        try:
            self._inventory_stacks_text.setPlainText(
                json.dumps(stacks, indent=2, ensure_ascii=False) if stacks else ""
            )
        finally:
            self._loading = was_loading

    def _on_add_inventory_stack_clicked(self) -> None:
        row = self._inventory_stacks_table.rowCount()
        self._inventory_stacks_table.insertRow(row)
        self._inventory_stacks_table.setItem(row, 0, QTableWidgetItem(""))
        self._inventory_stacks_table.setItem(row, 1, QTableWidgetItem("1"))
        self._inventory_stacks_table.setCurrentCell(row, 0)
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )
        self._set_dirty(True)

    def _on_remove_inventory_stack_clicked(self) -> None:
        row = self._inventory_stacks_table.currentRow()
        if row < 0:
            return
        self._inventory_stacks_table.removeRow(row)
        try:
            self._sync_inventory_stacks_text_from_table()
        except ValueError:
            pass
        self._set_inventory_controls_enabled(
            self._editing_enabled and self._inventory_editable
        )
        self._set_dirty(True)

    def _on_inventory_stacks_table_changed(self, *_args: object) -> None:
        if self._loading:
            return
        try:
            self._sync_inventory_stacks_text_from_table()
            self._inventory_warning.hide()
        except ValueError as exc:
            self._inventory_warning.setText(str(exc))
            self._inventory_warning.show()
        self._set_dirty(True)

    def _on_legacy_inventory_stacks_text_changed(self) -> None:
        if self._loading:
            return
        try:
            stacks = (
                loads_json_data(
                    self._inventory_stacks_text.toPlainText(),
                    source_name="Template inventory stacks",
                )
                if self._inventory_stacks_text.toPlainText().strip()
                else []
            )
            self._set_inventory_stacks_table(stacks)
        except (JsonDataDecodeError, ValueError) as exc:
            self._inventory_warning.setText(f"Inventory stacks must be valid JSON.\n{exc}")
            self._inventory_warning.show()
            self._set_dirty(True)
            return
        self._inventory_warning.hide()
        self._set_dirty(True)

    def _set_persistence_variable_controls_enabled(self, enabled: bool) -> None:
        self._persistence_variables_text.setReadOnly(not enabled)
        self._persistence_variables_table.setEnabled(enabled)
        self._add_persistence_variable_button.setEnabled(enabled)
        self._remove_persistence_variable_button.setEnabled(
            enabled and self._persistence_variables_table.currentRow() >= 0
        )

    def _current_template_variable_names(self) -> list[str] | None:
        variables_text = self._variables_text.toPlainText().strip()
        if not variables_text:
            return []
        try:
            parsed = loads_json_data(
                variables_text,
                source_name="Template variables",
            )
        except JsonDataDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        names: list[str] = []
        for raw_name in parsed.keys():
            name = str(raw_name).strip()
            if name and name not in names:
                names.append(name)
        return names

    def _make_persistence_value_combo(self, persistent: bool) -> QComboBox:
        combo = QComboBox()
        combo.addItem("true", True)
        combo.addItem("false", False)
        combo.setCurrentIndex(0 if persistent else 1)
        combo.currentIndexChanged.connect(self._on_persistence_variables_table_changed)
        return combo

    def _insert_persistence_variable_row(
        self,
        *,
        variable_name: str,
        included: bool,
        persistent: bool,
        custom: bool,
    ) -> int:
        row = self._persistence_variables_table.rowCount()
        self._persistence_variables_table.insertRow(row)

        name_item = QTableWidgetItem(variable_name)
        name_item.setData(Qt.ItemDataRole.UserRole, custom)
        if not custom:
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._persistence_variables_table.setItem(row, 0, name_item)

        include_item = QTableWidgetItem("")
        include_item.setFlags(
            include_item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
        )
        include_item.setCheckState(
            Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
        )
        self._persistence_variables_table.setItem(row, 1, include_item)

        combo = self._make_persistence_value_combo(persistent)
        combo.setEnabled(included)
        self._persistence_variables_table.setCellWidget(row, 2, combo)
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
                else self._current_template_variable_names()
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
                    included=variable_name in variables,
                    persistent=variables.get(variable_name, True),
                    custom=variable_name not in known_names,
                )
        finally:
            self._loading = was_loading
        self._set_persistence_variable_controls_enabled(
            self._editing_enabled and self._persistence_editable
        )

    def _persistence_row_is_custom(self, row: int) -> bool:
        item = self._persistence_variables_table.item(row, 0)
        return bool(item is not None and item.data(Qt.ItemDataRole.UserRole))

    def _sync_persistence_row_enabled(self, row: int) -> None:
        include_item = self._persistence_variables_table.item(row, 1)
        included = (
            include_item is not None
            and include_item.checkState() == Qt.CheckState.Checked
        )
        combo = self._persistence_variables_table.cellWidget(row, 2)
        if isinstance(combo, QComboBox):
            combo.setEnabled(included)

    def _sync_all_persistence_row_enabled(self) -> None:
        for row in range(self._persistence_variables_table.rowCount()):
            self._sync_persistence_row_enabled(row)

    def _build_persistence_variables_from_table(self) -> dict[str, bool]:
        variables: dict[str, bool] = {}
        for row in range(self._persistence_variables_table.rowCount()):
            name_item = self._persistence_variables_table.item(row, 0)
            include_item = self._persistence_variables_table.item(row, 1)
            name = name_item.text().strip() if name_item is not None else ""
            included = (
                include_item is not None
                and include_item.checkState() == Qt.CheckState.Checked
            )
            if not included:
                continue
            if not name:
                raise ValueError("Persistence variable names must not be blank.")
            if name in variables:
                raise ValueError(f"Duplicate persistence variable '{name}'.")
            combo = self._persistence_variables_table.cellWidget(row, 2)
            if isinstance(combo, QComboBox):
                variables[name] = bool(combo.currentData())
                continue
            value_item = self._persistence_variables_table.item(row, 2)
            value_text = (
                value_item.text().strip().lower() if value_item is not None else ""
            )
            if value_text not in {"true", "false"}:
                raise ValueError(f"Persistence variable '{name}' must be true or false.")
            variables[name] = value_text == "true"
        return variables

    def _build_persistence_policy_from_table(self) -> dict[str, Any] | None:
        variables = self._build_persistence_variables_from_table()
        entity_state = bool(self._entity_state_check.isChecked())
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
        row = self._insert_persistence_variable_row(
            variable_name="",
            included=True,
            persistent=True,
            custom=True,
        )
        self._persistence_variables_table.setCurrentCell(row, 0)
        self._set_persistence_variable_controls_enabled(
            self._editing_enabled and self._persistence_editable
        )
        self._set_dirty(True)

    def _on_remove_persistence_variable_clicked(self) -> None:
        row = self._persistence_variables_table.currentRow()
        if row < 0:
            return
        if self._persistence_row_is_custom(row):
            self._persistence_variables_table.removeRow(row)
        else:
            include_item = self._persistence_variables_table.item(row, 1)
            if include_item is not None:
                include_item.setCheckState(Qt.CheckState.Unchecked)
            self._sync_persistence_row_enabled(row)
        try:
            self._sync_persistence_variables_text_from_table()
        except ValueError:
            pass
        self._set_persistence_variable_controls_enabled(
            self._editing_enabled and self._persistence_editable
        )
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
            self._set_dirty(True)
            return
        variables = {}
        if isinstance(policy, dict):
            raw_variables = policy.get("variables", {})
            variables = raw_variables if isinstance(raw_variables, dict) else {}
        self._persistence_warning.hide()
        self._set_persistence_variables_table(variables)
        self._set_dirty(True)

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
            current_entity_id=None,
            current_area_id=None,
            current_entity_command_names=self._current_entity_command_names(),
        )
        dialog.load_dialogues(dialogues, active_dialogue=active_dialogue)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.dialogues(), dialog.active_dialogue(), dialog.rename_map()

    def _current_entity_command_names(self) -> list[str]:
        raw_text = self._entity_commands_text.toPlainText().strip()
        if not raw_text:
            return []
        try:
            parsed = loads_json_data(raw_text, source_name="Template entity commands")
        except JsonDataDecodeError:
            return []
        try:
            entity_commands = parse_entity_commands(parsed)
        except ValueError:
            return []
        return sorted(
            str(name).strip() for name in entity_commands.keys() if str(name).strip()
        )

    def _current_entity_commands_value(self) -> dict[str, Any] | None:
        raw_text = self._entity_commands_text.toPlainText().strip()
        if not raw_text:
            return {}
        try:
            parsed = loads_json_data(raw_text, source_name="Template entity commands")
            return parse_entity_commands(parsed)
        except (JsonDataDecodeError, ValueError):
            return None

    def _set_entity_commands_value(self, entity_commands: dict[str, Any]) -> None:
        self._entity_commands_text.setPlainText(
            json.dumps(entity_commands, indent=2, ensure_ascii=False)
            if entity_commands
            else ""
        )
        self._sync_entity_commands_table(entity_commands)

    def _sync_entity_commands_summary(self) -> None:
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            self._entity_commands_summary.setText("Invalid entity commands")
            return
        self._entity_commands_summary.setText(summarize_entity_commands(entity_commands))
        self._sync_entity_commands_table(entity_commands)

    def _sync_entity_commands_table(self, entity_commands: dict[str, Any]) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            selected_name = self._selected_entity_command_name()
            self._entity_commands_table.setRowCount(0)
            selected_row = -1
            for row, (name, definition) in enumerate(entity_commands.items()):
                self._entity_commands_table.insertRow(row)
                name_item = QTableWidgetItem(str(name))
                self._entity_commands_table.setItem(row, 0, name_item)
                enabled = True
                if isinstance(definition, dict):
                    enabled = bool(definition.get("enabled", False))
                self._entity_commands_table.setItem(
                    row,
                    1,
                    QTableWidgetItem("true" if enabled else "false"),
                )
                command_count = len(entity_command_command_list(definition))
                self._entity_commands_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(str(command_count)),
                )
                if str(name) == selected_name:
                    selected_row = row
            if selected_row >= 0:
                self._entity_commands_table.setCurrentCell(selected_row, 0)
        finally:
            self._loading = was_loading
        self._set_entity_commands_controls_enabled(
            self._editing_enabled and self._entity_commands_editable
        )

    def _selected_entity_command_name(self) -> str | None:
        row = self._entity_commands_table.currentRow()
        if row < 0:
            return None
        item = self._entity_commands_table.item(row, 0)
        if item is None:
            return None
        name = item.text().strip()
        return name or None

    def _set_entity_commands_controls_enabled(self, enabled: bool) -> None:
        self._entity_commands_text.setReadOnly(not enabled)
        self._entity_commands_table.setEnabled(enabled)
        entity_commands = self._current_entity_commands_value()
        has_commands = bool(entity_commands)
        can_use_buttons = enabled and entity_commands is not None
        self._add_entity_command_button.setEnabled(can_use_buttons)
        self._edit_entity_command_button.setEnabled(can_use_buttons and has_commands)
        self._duplicate_entity_command_button.setEnabled(can_use_buttons and has_commands)
        self._remove_entity_command_button.setEnabled(can_use_buttons and has_commands)

    def _prompt_entity_command_name(
        self,
        *,
        title: str,
        current_name: str = "",
    ) -> str | None:
        value, accepted = QInputDialog.getText(
            self,
            title,
            "Command name",
            text=current_name,
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
        selected_name = self._selected_entity_command_name()
        if selected_name in entity_commands:
            return selected_name
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
            current_entity_id=None,
            current_area_id=None,
            current_entity_command_names=self._current_entity_command_names(),
            current_entity_dialogue_names=sorted(self._dialogues_value.keys()),
        )
        dialog.setWindowTitle(f"Edit Entity Command - {command_name}")
        dialog.load_commands(commands)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.commands()

    def _on_add_entity_command_clicked(self) -> None:
        if not self._editing_enabled or not self._entity_commands_editable:
            return
        entity_commands = self._current_entity_commands_value()
        if entity_commands is None:
            return
        command_name = self._prompt_entity_command_name(title="Add Entity Command")
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
        self._on_text_changed()

    def _on_edit_entity_command_clicked(self) -> None:
        if not self._editing_enabled or not self._entity_commands_editable:
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
        self._on_text_changed()

    def _on_duplicate_entity_command_clicked(self) -> None:
        if not self._editing_enabled or not self._entity_commands_editable:
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
        suggested_name = suggested_entity_command_copy_name(
            source_name,
            set(entity_commands.keys()),
        )
        new_name = self._prompt_entity_command_name(
            title="Duplicate Entity Command",
            current_name=suggested_name,
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
        self._on_text_changed()

    def _on_remove_entity_command_clicked(self) -> None:
        if not self._editing_enabled or not self._entity_commands_editable:
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
        self._on_text_changed()

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
            self._sync_entity_commands_summary()
        finally:
            self._loading = False

    def build_updated_template_data(self, base_data: dict[str, Any]) -> dict[str, Any]:
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

        if self._visuals_editable:
            updated["visuals"] = self._visuals_editor.visuals()
        elif "visuals" in base_data:
            updated["visuals"] = copy.deepcopy(base_data["visuals"])
        else:
            updated.pop("visuals", None)
        if "input_map" in base_data:
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
            inventory_value = self._build_inventory_from_table(
                base_inventory=base_data.get("inventory"),
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
            persistence_value = self._build_persistence_policy_from_table()
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

    def _on_visuals_changed(self) -> None:
        if self._loading:
            return
        try:
            visuals_text = self._visuals_editor.visuals_text()
        except ValueError:
            visuals_text = ""
        self._loading = True
        try:
            self._visuals_text.setPlainText(visuals_text)
        finally:
            self._loading = False
        self._set_dirty(True)

    def _on_legacy_visuals_text_changed(self) -> None:
        if self._loading:
            return
        raw_text = self._visuals_text.toPlainText().strip()
        try:
            raw_visuals = (
                loads_json_data(raw_text, source_name="Template visuals")
                if raw_text
                else []
            )
            visuals = parse_visuals(raw_visuals)
        except (JsonDataDecodeError, ValueError) as exc:
            self._visuals_warning.setText(f"Visuals must be valid JSON.\n{exc}")
            self._visuals_warning.show()
            self._visuals_editable = False
            self._visuals_editor.set_editing_enabled(False)
            self._set_dirty(True)
            return
        self._loading = True
        try:
            self._visuals_editor.load_visuals(visuals)
        finally:
            self._loading = False
        self._visuals_warning.hide()
        self._visuals_editable = True
        self._visuals_editor.set_editing_enabled(self._editing_enabled)
        self._set_dirty(True)

    def _on_entity_commands_text_changed(self) -> None:
        self._sync_entity_commands_summary()
        self._set_entity_commands_controls_enabled(
            self._editing_enabled and self._entity_commands_editable
        )
        if self._loading:
            return
        self._set_dirty(True)

    def _on_variables_text_changed(self) -> None:
        if self._loading:
            return
        self._sync_dialogues_summary()
        variable_names = self._current_template_variable_names()
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
        self._inventory_stacks_table.setEnabled(active)
        self._add_inventory_stack_button.setEnabled(active)
        self._remove_inventory_stack_button.setEnabled(
            active and self._inventory_stacks_table.currentRow() >= 0
        )

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
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[..., str | None] | None = None,
        command_picker: Callable[..., str | None] | None = None,
        project_command_inputs_provider: Callable[..., dict[str, dict[str, Any]] | None]
        | None = None,
        visual_picker: Callable[..., str | None] | None = None,
        animation_picker: Callable[..., str | None] | None = None,
    ) -> None:
        self._fields_editor.set_reference_picker_callbacks(
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

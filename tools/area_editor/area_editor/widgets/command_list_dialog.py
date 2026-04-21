"""Popup editors for authored command lists and individual commands."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from dungeon_engine.commands.builtin import register_builtin_commands
    from dungeon_engine.commands.registry import CommandRegistry
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from dungeon_engine.commands.builtin import register_builtin_commands
    from dungeon_engine.commands.registry import CommandRegistry

from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.widgets.reference_picker_support import (
    EntityReferencePickerRequest,
    call_reference_picker_callback,
)

_KNOWN_COMMAND_NAMES: tuple[str, ...] | None = None
_SUPPORTED_COMMAND_TYPES = {
    "open_dialogue_session",
    "run_project_command",
    "open_entity_dialogue",
    "set_entity_active_dialogue",
    "step_entity_active_dialogue",
    "set_entity_active_dialogue_by_order",
}
_OWNED_FIELDS_BY_COMMAND_TYPE: dict[str, set[str]] = {
    "open_dialogue_session": {
        "dialogue_path",
        "dialogue_definition",
        "allow_cancel",
        "ui_preset",
        "actor_id",
        "caller_id",
    },
    "run_project_command": {
        "command_id",
    },
    "open_entity_dialogue": {
        "entity_id",
        "dialogue_id",
        "allow_cancel",
        "ui_preset",
        "actor_id",
        "caller_id",
    },
    "set_entity_active_dialogue": {
        "entity_id",
        "dialogue_id",
        "persistent",
    },
    "step_entity_active_dialogue": {
        "entity_id",
        "delta",
        "wrap",
        "persistent",
    },
    "set_entity_active_dialogue_by_order": {
        "entity_id",
        "order",
        "wrap",
        "persistent",
    },
}


def summarize_command_list(commands: object) -> str:
    """Return a short human-readable summary for one command list."""
    normalized = _normalize_command_list(commands)
    count = len(normalized)
    if count <= 0:
        return "none"
    first_type = str(normalized[0].get("type", "")).strip()
    if count == 1:
        if first_type:
            return f"1 command: {first_type}"
        return "1 command"
    if first_type:
        return f"{count} commands: {first_type}..."
    return f"{count} commands"


def _normalize_command_list(commands: object) -> list[dict[str, Any]]:
    if commands in (None, ""):
        return []
    if isinstance(commands, dict):
        return [copy.deepcopy(commands)]
    if not isinstance(commands, list):
        return []
    normalized: list[dict[str, Any]] = []
    for command in commands:
        if isinstance(command, dict):
            normalized.append(copy.deepcopy(command))
    return normalized


def _command_summary(command: object, index: int) -> str:
    if not isinstance(command, dict):
        return f"{index + 1}. invalid command"
    command_type = str(command.get("type", "")).strip() or "(no type)"
    if command_type == "open_dialogue_session":
        dialogue_path = str(command.get("dialogue_path", "")).strip()
        if dialogue_path:
            return f"{index + 1}. {command_type}: {dialogue_path}"
        if isinstance(command.get("dialogue_definition"), dict):
            return (
                f"{index + 1}. {command_type}: "
                f"{_summarize_dialogue_definition(command.get('dialogue_definition'))}"
            )
    if command_type == "run_project_command":
        command_id = str(command.get("command_id", "")).strip()
        if command_id:
            return f"{index + 1}. {command_type}: {command_id}"
    if command_type in {"open_entity_dialogue", "set_entity_active_dialogue"}:
        entity_id = str(command.get("entity_id", "")).strip()
        dialogue_id = str(command.get("dialogue_id", "")).strip()
        parts = [part for part in (entity_id, dialogue_id) if part]
        if parts:
            return f"{index + 1}. {command_type}: {' -> '.join(parts)}"
    if command_type == "step_entity_active_dialogue":
        entity_id = str(command.get("entity_id", "")).strip()
        delta = command.get("delta")
        details = entity_id or f"delta={delta}"
        if entity_id and delta not in (None, ""):
            details = f"{entity_id} delta={delta}"
        return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_entity_active_dialogue_by_order":
        entity_id = str(command.get("entity_id", "")).strip()
        order = command.get("order")
        details = entity_id or f"order={order}"
        if entity_id and order not in (None, ""):
            details = f"{entity_id} order={order}"
        return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_entity_var":
        entity_id = str(command.get("entity_id", "")).strip()
        name = str(command.get("name", "")).strip()
        if entity_id or name:
            parts = [part for part in (entity_id, name) if part]
            return f"{index + 1}. {command_type}: {'.'.join(parts)}"
    return f"{index + 1}. {command_type}"


def _summarize_dialogue_definition(definition: object) -> str:
    if not isinstance(definition, dict):
        return "Invalid dialogue definition"
    segments = definition.get("segments")
    if not isinstance(segments, list):
        return "Dialogue has no segments array"
    segment_count = len(segments)
    choice_count = sum(
        1
        for segment in segments
        if isinstance(segment, dict)
        and str(segment.get("type", "text")).strip() == "choice"
    )
    text_count = max(0, segment_count - choice_count)
    parts = [f"{segment_count} segment{'s' if segment_count != 1 else ''}"]
    if text_count:
        parts.append(f"{text_count} text")
    if choice_count:
        parts.append(f"{choice_count} choice")
    return ", ".join(parts)


def _known_command_names() -> tuple[str, ...]:
    global _KNOWN_COMMAND_NAMES
    if _KNOWN_COMMAND_NAMES is None:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        _KNOWN_COMMAND_NAMES = tuple(
            contract.name
            for contract in registry.iter_command_contracts()
        )
    return _KNOWN_COMMAND_NAMES


def _make_line_with_button(
    *,
    button_text: str,
) -> tuple[QWidget, QLineEdit, QPushButton]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    edit = QLineEdit()
    button = QPushButton(button_text)
    button.setAutoDefault(False)
    button.setDefault(False)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return row, edit, button


class _OptionalTextField(QWidget):
    """Text field with explicit presence control."""

    changed = Signal()

    def __init__(self, parent=None, *, button_text: str | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._enabled_check = QCheckBox("Set")
        self._edit = QLineEdit()
        self._button = QPushButton(button_text) if button_text else None
        if self._button is not None:
            self._button.setAutoDefault(False)
            self._button.setDefault(False)

        layout.addWidget(self._enabled_check)
        layout.addWidget(self._edit, 1)
        if self._button is not None:
            layout.addWidget(self._button)

        self._enabled_check.toggled.connect(self._sync_enabled_state)
        self._enabled_check.toggled.connect(lambda _checked: self.changed.emit())
        self._edit.textChanged.connect(lambda _text: self.changed.emit())
        self._sync_enabled_state(self._enabled_check.isChecked())

    @property
    def edit(self) -> QLineEdit:
        return self._edit

    @property
    def button(self) -> QPushButton | None:
        return self._button

    def set_optional_value(self, value: object) -> None:
        text = str(value).strip() if isinstance(value, str) else ""
        enabled = bool(text)
        blockers = [QSignalBlocker(self._enabled_check), QSignalBlocker(self._edit)]
        self._enabled_check.setChecked(enabled)
        self._edit.setText(text if enabled else "")
        del blockers
        self._sync_enabled_state(enabled)

    def optional_value(self) -> str | None:
        if not self._enabled_check.isChecked():
            return None
        value = self._edit.text().strip()
        return value or None

    def _sync_enabled_state(self, enabled: bool) -> None:
        self._edit.setEnabled(enabled)
        if self._button is not None:
            self._button.setEnabled(enabled)


class _OptionalIntField(QWidget):
    """Integer field with explicit presence control."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        minimum: int,
        maximum: int,
        default_value: int,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._enabled_check = QCheckBox("Set")
        self._spin = QSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(default_value)
        layout.addWidget(self._enabled_check)
        layout.addWidget(self._spin, 1)
        self._enabled_check.toggled.connect(self._sync_enabled_state)
        self._enabled_check.toggled.connect(lambda _checked: self.changed.emit())
        self._spin.valueChanged.connect(lambda _value: self.changed.emit())
        self._sync_enabled_state(self._enabled_check.isChecked())

    @property
    def spin_box(self) -> QSpinBox:
        return self._spin

    def set_optional_value(self, value: object) -> None:
        enabled = value not in (None, "")
        try:
            numeric_value = int(value) if enabled else self._spin.value()
        except (TypeError, ValueError):
            numeric_value = self._spin.value()
            enabled = False
        blockers = [QSignalBlocker(self._enabled_check), QSignalBlocker(self._spin)]
        self._enabled_check.setChecked(enabled)
        self._spin.setValue(numeric_value)
        del blockers
        self._sync_enabled_state(enabled)

    def optional_value(self) -> int | None:
        if not self._enabled_check.isChecked():
            return None
        return int(self._spin.value())

    def _sync_enabled_state(self, enabled: bool) -> None:
        self._spin.setEnabled(enabled)


class _CommandTypePickerDialog(QDialog):
    """Searchable popup for choosing one command type."""

    def __init__(
        self,
        parent=None,
        *,
        command_names: list[str] | tuple[str, ...],
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Command")
        self.resize(420, 480)

        self._all_command_names = [name for name in command_names if str(name).strip()]
        suggested = []
        for name in suggested_command_names or ():
            normalized = str(name).strip()
            if (
                normalized
                and normalized in self._all_command_names
                and normalized not in suggested
            ):
                suggested.append(normalized)
        self._suggested_command_names = suggested

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        outer.addWidget(QLabel("Command Type"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search commands...")
        outer.addWidget(self._search_edit)

        self._command_list = QListWidget()
        outer.addWidget(self._command_list, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._search_edit.textChanged.connect(self._apply_filter)
        self._command_list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._command_list.currentRowChanged.connect(
            lambda _row: self._sync_accept_button()
        )

        self._apply_filter("")

    def selected_command_type(self) -> str | None:
        item = self._command_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _apply_filter(self, search_text: str) -> None:
        needle = str(search_text).strip().casefold()
        filtered = [
            name
            for name in self._all_command_names
            if not needle or needle in name.casefold()
        ]
        self._command_list.blockSignals(True)
        try:
            self._command_list.clear()
            first_selectable_row = -1
            if not needle and self._suggested_command_names:
                self._add_header_item("Suggested")
                for name in self._suggested_command_names:
                    item = self._add_command_item(name)
                    if first_selectable_row < 0:
                        first_selectable_row = self._command_list.row(item)
                remaining = [
                    name
                    for name in self._all_command_names
                    if name not in self._suggested_command_names
                ]
                if remaining:
                    self._add_header_item("All Commands")
                    for name in remaining:
                        item = self._add_command_item(name)
                        if first_selectable_row < 0:
                            first_selectable_row = self._command_list.row(item)
            else:
                for name in filtered:
                    item = self._add_command_item(name)
                    if first_selectable_row < 0:
                        first_selectable_row = self._command_list.row(item)
            if first_selectable_row >= 0:
                self._command_list.setCurrentRow(first_selectable_row)
        finally:
            self._command_list.blockSignals(False)
        self._sync_accept_button()

    def _add_header_item(self, text: str) -> None:
        item = QListWidgetItem(text)
        header_font = item.font()
        header_font.setBold(True)
        item.setFont(header_font)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._command_list.addItem(item)

    def _add_command_item(self, command_name: str) -> QListWidgetItem:
        item = QListWidgetItem(command_name)
        item.setData(Qt.ItemDataRole.UserRole, command_name)
        self._command_list.addItem(item)
        return item

    def _sync_accept_button(self) -> None:
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(self._command_list.currentItem() is not None)

    def accept(self) -> None:  # noqa: D401
        if self.selected_command_type() is None:
            return
        super().accept()


class _ReorderListWidget(QListWidget):
    """List widget that emits one stable visual-order snapshot after drops."""

    visual_order_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        order: list[int] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int):
                order.append(value)
        if order:
            self.visual_order_changed.emit(order)


class CommandEditorDialog(QDialog):
    """Popup editor for one authored command."""

    def __init__(
        self,
        parent=None,
        *,
        entity_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        current_entity_id: str | None = None,
        current_area_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandEditorDialog")
        self.setWindowTitle("Edit Command")
        self.resize(820, 640)

        self._entity_picker = entity_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._current_entity_id = (
            str(current_entity_id).strip() or None if current_entity_id is not None else None
        )
        self._current_area_id = (
            str(current_area_id).strip() or None if current_area_id is not None else None
        )
        self._loaded_command: dict[str, Any] = {"type": ""}
        self._loading = False
        self._syncing_tabs = False
        self._inline_dialogue_definition: dict[str, Any] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        note = QLabel(
            "Edit one command here. Supported commands get structured fields; use the JSON tab "
            "for advanced or unsupported parameters."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        structured = QWidget()
        structured_layout = QVBoxLayout(structured)
        structured_layout.setContentsMargins(0, 0, 0, 0)
        structured_layout.setSpacing(8)

        self._command_header = QLabel("Command")
        header_font = self._command_header.font()
        header_font.setBold(True)
        self._command_header.setFont(header_font)
        structured_layout.addWidget(self._command_header)

        type_row = QHBoxLayout()
        type_row.setContentsMargins(0, 0, 0, 0)
        type_row.addWidget(QLabel("type"))
        self._command_type_combo = QComboBox()
        self._command_type_combo.setEditable(False)
        self._command_type_combo.addItems(list(_known_command_names()))
        type_row.addWidget(self._command_type_combo, 1)
        structured_layout.addLayout(type_row)

        self._command_stack = QStackedWidget()
        structured_layout.addWidget(self._command_stack, 1)

        generic_font = QFont("Consolas", 10)
        generic_font.setStyleHint(QFont.StyleHint.Monospace)

        self._generic_page = QWidget()
        generic_layout = QVBoxLayout(self._generic_page)
        generic_layout.setContentsMargins(0, 0, 0, 0)
        generic_layout.addWidget(QLabel("Parameters JSON"))
        self._generic_params_edit = QPlainTextEdit()
        self._generic_params_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._generic_params_edit.setFont(generic_font)
        self._generic_params_edit.setPlaceholderText('{\n  "entity_id": "player_1"\n}')
        generic_layout.addWidget(self._generic_params_edit, 1)
        self._command_stack.addWidget(self._generic_page)

        self._open_dialogue_page = QWidget()
        open_dialogue_form = QFormLayout(self._open_dialogue_page)
        open_dialogue_form.setContentsMargins(0, 0, 0, 0)
        self._dialogue_source_combo = QComboBox()
        self._dialogue_source_combo.addItems(["Inline Dialogue", "Dialogue File"])
        open_dialogue_form.addRow("dialogue_source", self._dialogue_source_combo)

        dialogue_file_row, self._dialogue_path_edit, self._dialogue_path_browse = _make_line_with_button(
            button_text="Browse..."
        )
        self._dialogue_path_browse.clicked.connect(self._on_browse_dialogue_path)
        open_dialogue_form.addRow("dialogue_path", dialogue_file_row)

        inline_row = QWidget()
        inline_layout = QHBoxLayout(inline_row)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(6)
        self._inline_dialogue_summary = QLabel("0 segments")
        self._edit_inline_dialogue_button = QPushButton("Edit Dialogue...")
        self._edit_inline_dialogue_button.setAutoDefault(False)
        self._edit_inline_dialogue_button.setDefault(False)
        self._edit_inline_dialogue_button.clicked.connect(self._on_edit_inline_dialogue)
        inline_layout.addWidget(self._inline_dialogue_summary, 1)
        inline_layout.addWidget(self._edit_inline_dialogue_button)
        open_dialogue_form.addRow("dialogue_definition", inline_row)

        self._allow_cancel_field = QComboBox()
        self._setup_optional_bool_combo(self._allow_cancel_field)
        open_dialogue_form.addRow("allow_cancel", self._allow_cancel_field)

        self._open_dialogue_advanced_toggle = QToolButton()
        self._open_dialogue_advanced_toggle.setText("Advanced")
        self._open_dialogue_advanced_toggle.setCheckable(True)
        self._open_dialogue_advanced_toggle.setChecked(False)
        self._open_dialogue_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._open_dialogue_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._open_dialogue_advanced_toggle.toggled.connect(
            self._on_open_dialogue_advanced_toggled
        )
        open_dialogue_form.addRow(self._open_dialogue_advanced_toggle)

        self._open_dialogue_advanced_widget = QWidget()
        open_dialogue_advanced_form = QFormLayout(self._open_dialogue_advanced_widget)
        open_dialogue_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._ui_preset_field = _OptionalTextField()
        self._ui_preset_field.changed.connect(self._sync_open_dialogue_advanced_state)
        open_dialogue_advanced_form.addRow("ui_preset", self._ui_preset_field)
        self._actor_id_field = _OptionalTextField(button_text="Pick...")
        self._actor_id_field.changed.connect(self._sync_open_dialogue_advanced_state)
        if self._actor_id_field.button is not None:
            self._actor_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._actor_id_field,
                    parameter_name="actor_id",
                )
            )
        open_dialogue_advanced_form.addRow("actor_id", self._actor_id_field)
        self._caller_id_field = _OptionalTextField(button_text="Pick...")
        self._caller_id_field.changed.connect(self._sync_open_dialogue_advanced_state)
        if self._caller_id_field.button is not None:
            self._caller_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._caller_id_field,
                    parameter_name="caller_id",
                )
            )
        open_dialogue_advanced_form.addRow("caller_id", self._caller_id_field)
        open_dialogue_form.addRow(self._open_dialogue_advanced_widget)
        self._command_stack.addWidget(self._open_dialogue_page)

        self._run_project_command_page = QWidget()
        run_project_form = QFormLayout(self._run_project_command_page)
        run_project_form.setContentsMargins(0, 0, 0, 0)
        command_row, self._project_command_id_edit, self._project_command_browse = _make_line_with_button(
            button_text="Browse..."
        )
        self._project_command_browse.clicked.connect(self._on_browse_project_command_id)
        run_project_form.addRow("command_id", command_row)
        self._command_stack.addWidget(self._run_project_command_page)

        self._open_entity_dialogue_page = QWidget()
        open_entity_form = QFormLayout(self._open_entity_dialogue_page)
        open_entity_form.setContentsMargins(0, 0, 0, 0)
        open_entity_entity_row, self._open_entity_entity_id_edit, self._open_entity_entity_pick = _make_line_with_button(
            button_text="Pick..."
        )
        self._open_entity_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._open_entity_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._open_entity_entity_id_edit.textChanged.connect(
            self._sync_entity_dialogue_picker_button_state
        )
        open_entity_form.addRow("entity_id", open_entity_entity_row)
        self._open_entity_dialogue_id_field = _OptionalTextField(button_text="Pick...")
        if self._open_entity_dialogue_id_field.button is not None:
            self._open_entity_dialogue_id_field.button.clicked.connect(
                lambda: self._pick_dialogue_id_into_optional_field(
                    self._open_entity_dialogue_id_field,
                    entity_id_edit=self._open_entity_entity_id_edit,
                )
            )
        open_entity_form.addRow("dialogue_id", self._open_entity_dialogue_id_field)
        self._open_entity_dialogue_id_note = QLabel(
            "Leave dialogue_id unset to use the entity's active dialogue."
        )
        self._open_entity_dialogue_id_note.setWordWrap(True)
        self._open_entity_dialogue_id_note.setStyleSheet("color: #666;")
        open_entity_form.addRow(self._open_entity_dialogue_id_note)
        self._open_entity_allow_cancel_field = QComboBox()
        self._setup_optional_bool_combo(self._open_entity_allow_cancel_field)
        open_entity_form.addRow("allow_cancel", self._open_entity_allow_cancel_field)

        self._open_entity_advanced_toggle = QToolButton()
        self._open_entity_advanced_toggle.setText("Advanced")
        self._open_entity_advanced_toggle.setCheckable(True)
        self._open_entity_advanced_toggle.setChecked(False)
        self._open_entity_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._open_entity_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._open_entity_advanced_toggle.toggled.connect(
            self._on_open_entity_advanced_toggled
        )
        open_entity_form.addRow(self._open_entity_advanced_toggle)

        self._open_entity_advanced_widget = QWidget()
        open_entity_advanced_form = QFormLayout(self._open_entity_advanced_widget)
        open_entity_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._open_entity_ui_preset_field = _OptionalTextField()
        self._open_entity_ui_preset_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        open_entity_advanced_form.addRow("ui_preset", self._open_entity_ui_preset_field)
        self._open_entity_actor_id_field = _OptionalTextField(button_text="Pick...")
        self._open_entity_actor_id_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        if self._open_entity_actor_id_field.button is not None:
            self._open_entity_actor_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._open_entity_actor_id_field,
                    parameter_name="actor_id",
                )
            )
        open_entity_advanced_form.addRow("actor_id", self._open_entity_actor_id_field)
        self._open_entity_caller_id_field = _OptionalTextField(button_text="Pick...")
        self._open_entity_caller_id_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        if self._open_entity_caller_id_field.button is not None:
            self._open_entity_caller_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._open_entity_caller_id_field,
                    parameter_name="caller_id",
                )
            )
        open_entity_advanced_form.addRow("caller_id", self._open_entity_caller_id_field)
        open_entity_form.addRow(self._open_entity_advanced_widget)
        self._command_stack.addWidget(self._open_entity_dialogue_page)

        self._set_active_dialogue_page = QWidget()
        set_active_form = QFormLayout(self._set_active_dialogue_page)
        set_active_form.setContentsMargins(0, 0, 0, 0)
        set_active_entity_row, self._set_active_entity_id_edit, self._set_active_entity_pick = _make_line_with_button(
            button_text="Pick..."
        )
        self._set_active_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_active_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._set_active_entity_id_edit.textChanged.connect(
            self._sync_entity_dialogue_picker_button_state
        )
        set_active_form.addRow("entity_id", set_active_entity_row)
        (
            set_active_dialogue_row,
            self._set_active_dialogue_id_edit,
            self._set_active_dialogue_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._set_active_dialogue_pick.clicked.connect(
            lambda: self._pick_dialogue_id_into_edit(
                self._set_active_dialogue_id_edit,
                entity_id_edit=self._set_active_entity_id_edit,
            )
        )
        set_active_form.addRow("dialogue_id", set_active_dialogue_row)
        self._set_active_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_persistent_field)
        set_active_form.addRow("persistent", self._set_active_persistent_field)
        self._command_stack.addWidget(self._set_active_dialogue_page)

        self._step_active_dialogue_page = QWidget()
        step_form = QFormLayout(self._step_active_dialogue_page)
        step_form.setContentsMargins(0, 0, 0, 0)
        step_entity_row, self._step_entity_id_edit, self._step_entity_pick = _make_line_with_button(
            button_text="Pick..."
        )
        self._step_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._step_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        step_form.addRow("entity_id", step_entity_row)
        self._step_delta_field = _OptionalIntField(
            minimum=-999999,
            maximum=999999,
            default_value=1,
        )
        step_form.addRow("delta", self._step_delta_field)
        self._step_wrap_field = QComboBox()
        self._setup_optional_bool_combo(self._step_wrap_field)
        step_form.addRow("wrap", self._step_wrap_field)
        self._step_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._step_persistent_field)
        step_form.addRow("persistent", self._step_persistent_field)
        self._command_stack.addWidget(self._step_active_dialogue_page)

        self._set_active_by_order_page = QWidget()
        by_order_form = QFormLayout(self._set_active_by_order_page)
        by_order_form.setContentsMargins(0, 0, 0, 0)
        by_order_entity_row, self._set_active_by_order_entity_id_edit, self._set_active_by_order_entity_pick = _make_line_with_button(
            button_text="Pick..."
        )
        self._set_active_by_order_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_active_by_order_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        by_order_form.addRow("entity_id", by_order_entity_row)
        self._set_active_by_order_spin = QSpinBox()
        self._set_active_by_order_spin.setRange(1, 999999)
        self._set_active_by_order_spin.setValue(1)
        by_order_form.addRow("order", self._set_active_by_order_spin)
        self._set_active_by_order_wrap_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_by_order_wrap_field)
        by_order_form.addRow("wrap", self._set_active_by_order_wrap_field)
        self._set_active_by_order_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_by_order_persistent_field)
        by_order_form.addRow("persistent", self._set_active_by_order_persistent_field)
        self._command_stack.addWidget(self._set_active_by_order_page)

        self._tabs.addTab(structured, "Command Editor")

        self._command_json_edit = QPlainTextEdit()
        self._command_json_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._command_json_edit.setFont(generic_font)
        self._tabs.addTab(self._command_json_edit, "Command JSON")

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._command_type_combo.currentTextChanged.connect(self._on_command_type_changed)
        self._dialogue_source_combo.currentTextChanged.connect(
            self._sync_open_dialogue_source_visibility
        )
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._sync_entity_picker_button_state()
        self._sync_entity_dialogue_picker_button_state()
        self._sync_open_dialogue_advanced_state(expanded=False)
        self._sync_open_entity_advanced_state(expanded=False)

    def load_command(self, command: object) -> None:
        if isinstance(command, dict):
            self._loaded_command = copy.deepcopy(command)
        else:
            self._loaded_command = {"type": ""}
        self._loading = True
        try:
            command_type = str(self._loaded_command.get("type", "")).strip()
            self._ensure_command_type_visible(command_type)
            self._command_type_combo.setCurrentText(command_type)
            self._command_header.setText(command_type or "Command")
            self._generic_params_edit.setPlainText(
                json.dumps(
                    {
                        key: value
                        for key, value in self._loaded_command.items()
                        if key != "type"
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            self._command_json_edit.setPlainText(
                json.dumps(self._loaded_command, indent=2, ensure_ascii=False)
            )
            self._load_supported_fields(self._loaded_command)
            self._sync_structured_page(command_type)
        finally:
            self._loading = False

        self._sync_entity_dialogue_picker_button_state()
        self._sync_open_dialogue_source_visibility()
        if command_type == "open_dialogue_session":
            self._sync_open_dialogue_advanced_state(
                expanded=self._open_dialogue_advanced_field_count() > 0
            )
        if command_type == "open_entity_dialogue":
            self._sync_open_entity_advanced_state(
                expanded=self._open_entity_advanced_field_count() > 0
            )
        self._tabs.setCurrentIndex(0)

    def command(self) -> dict[str, Any]:
        if self._tabs.currentIndex() == 1:
            return self._command_from_json_tab(show_message=True)
        command = self._build_structured_command(show_message=True)
        if command is None:
            raise ValueError("Invalid command")
        return command

    def accept(self) -> None:  # noqa: D401
        try:
            self._loaded_command = self.command()
        except ValueError:
            return
        super().accept()

    @staticmethod
    def _setup_optional_bool_combo(combo: QComboBox) -> None:
        combo.addItem("Not Set", None)
        combo.addItem("True", True)
        combo.addItem("False", False)

    @staticmethod
    def _set_optional_bool_combo_value(combo: QComboBox, value: object) -> None:
        if value is True:
            combo.setCurrentIndex(1)
        elif value is False:
            combo.setCurrentIndex(2)
        else:
            combo.setCurrentIndex(0)

    @staticmethod
    def _optional_bool_combo_value(combo: QComboBox) -> bool | None:
        value = combo.currentData()
        if value is True:
            return True
        if value is False:
            return False
        return None

    def _load_supported_fields(self, command: dict[str, Any]) -> None:
        command_type = str(command.get("type", "")).strip()

        source = "Inline Dialogue"
        if str(command.get("dialogue_path", "")).strip():
            source = "Dialogue File"
        self._dialogue_source_combo.setCurrentText(source)
        self._dialogue_path_edit.setText(str(command.get("dialogue_path", "")))
        dialogue_definition = command.get("dialogue_definition")
        if isinstance(dialogue_definition, dict):
            self._inline_dialogue_definition = copy.deepcopy(dialogue_definition)
        else:
            self._inline_dialogue_definition = {"segments": []}
        self._inline_dialogue_summary.setText(
            _summarize_dialogue_definition(self._inline_dialogue_definition)
        )
        self._set_optional_bool_combo_value(
            self._allow_cancel_field,
            command.get("allow_cancel"),
        )
        self._ui_preset_field.set_optional_value(command.get("ui_preset"))
        self._actor_id_field.set_optional_value(command.get("actor_id"))
        self._caller_id_field.set_optional_value(command.get("caller_id"))

        self._project_command_id_edit.setText(str(command.get("command_id", "")))

        self._open_entity_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._open_entity_dialogue_id_field.set_optional_value(command.get("dialogue_id"))
        self._set_optional_bool_combo_value(
            self._open_entity_allow_cancel_field,
            command.get("allow_cancel"),
        )
        self._open_entity_ui_preset_field.set_optional_value(command.get("ui_preset"))
        self._open_entity_actor_id_field.set_optional_value(command.get("actor_id"))
        self._open_entity_caller_id_field.set_optional_value(command.get("caller_id"))

        self._set_active_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_active_dialogue_id_edit.setText(str(command.get("dialogue_id", "")))
        self._set_optional_bool_combo_value(
            self._set_active_persistent_field,
            command.get("persistent"),
        )

        self._step_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._step_delta_field.set_optional_value(command.get("delta"))
        self._set_optional_bool_combo_value(
            self._step_wrap_field,
            command.get("wrap"),
        )
        self._set_optional_bool_combo_value(
            self._step_persistent_field,
            command.get("persistent"),
        )

        self._set_active_by_order_entity_id_edit.setText(str(command.get("entity_id", "")))
        order = command.get("order")
        try:
            self._set_active_by_order_spin.setValue(max(1, int(order)))
        except (TypeError, ValueError):
            self._set_active_by_order_spin.setValue(1)
        self._set_optional_bool_combo_value(
            self._set_active_by_order_wrap_field,
            command.get("wrap"),
        )
        self._set_optional_bool_combo_value(
            self._set_active_by_order_persistent_field,
            command.get("persistent"),
        )

        if command_type != "open_dialogue_session":
            self._sync_open_dialogue_advanced_state(expanded=False)
        if command_type != "open_entity_dialogue":
            self._sync_open_entity_advanced_state(expanded=False)

    def _entity_picker_request(self, *, parameter_name: str, current_value: str) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name=parameter_name,
            current_value=current_value,
            parameter_spec={"type": "entity_id"},
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values=None,
        )

    def _entity_dialogue_picker_request(
        self,
        *,
        current_value: str,
        entity_id_value: str,
    ) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name="dialogue_id",
            current_value=current_value,
            parameter_spec={
                "type": "entity_dialogue_id",
                "entity_parameter": "entity_id",
            },
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values={
                "entity_id": entity_id_value,
                "dialogue_id": current_value,
            },
        )

    def _pick_entity_into_edit(self, edit: QLineEdit, *, parameter_name: str) -> None:
        selected = call_reference_picker_callback(
            self._entity_picker,
            edit.text().strip(),
            request=self._entity_picker_request(
                parameter_name=parameter_name,
                current_value=edit.text().strip(),
            ),
        )
        if selected:
            edit.setText(selected)

    def _pick_entity_into_optional_field(
        self,
        field: _OptionalTextField,
        *,
        parameter_name: str,
    ) -> None:
        current_value = field.optional_value() or field.edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_picker,
            current_value,
            request=self._entity_picker_request(
                parameter_name=parameter_name,
                current_value=current_value,
            ),
        )
        if selected:
            field.set_optional_value(selected)

    def _sync_entity_picker_button_state(self) -> None:
        enabled = self._entity_picker is not None
        for button in (
            getattr(self, "_open_entity_entity_pick", None),
            getattr(self, "_set_active_entity_pick", None),
            getattr(self, "_step_entity_pick", None),
            getattr(self, "_set_active_by_order_entity_pick", None),
        ):
            if button is not None:
                button.setEnabled(enabled)

    def _pick_dialogue_id_into_edit(
        self,
        edit: QLineEdit,
        *,
        entity_id_edit: QLineEdit,
    ) -> None:
        current_value = edit.text().strip()
        entity_id_value = entity_id_edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_dialogue_picker,
            current_value,
            request=self._entity_dialogue_picker_request(
                current_value=current_value,
                entity_id_value=entity_id_value,
            ),
        )
        if selected:
            edit.setText(selected)

    def _pick_dialogue_id_into_optional_field(
        self,
        field: _OptionalTextField,
        *,
        entity_id_edit: QLineEdit,
    ) -> None:
        current_value = field.optional_value() or field.edit.text().strip()
        entity_id_value = entity_id_edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_dialogue_picker,
            current_value,
            request=self._entity_dialogue_picker_request(
                current_value=current_value,
                entity_id_value=entity_id_value,
            ),
        )
        if selected:
            field.set_optional_value(selected)

    def _sync_entity_dialogue_picker_button_state(self) -> None:
        picker_enabled = self._entity_dialogue_picker is not None
        open_entity_enabled = picker_enabled and bool(
            self._open_entity_entity_id_edit.text().strip()
        )
        if self._open_entity_dialogue_id_field.button is not None:
            self._open_entity_dialogue_id_field.button.setEnabled(open_entity_enabled)
        set_active_enabled = picker_enabled and bool(
            self._set_active_entity_id_edit.text().strip()
        )
        if getattr(self, "_set_active_dialogue_pick", None) is not None:
            self._set_active_dialogue_pick.setEnabled(set_active_enabled)

    def _ensure_command_type_visible(self, command_type: str) -> None:
        if not command_type:
            return
        if self._command_type_combo.findText(command_type) >= 0:
            return
        self._command_type_combo.insertItem(0, command_type)

    def _sync_structured_page(self, command_type: str) -> None:
        page_by_type = {
            "open_dialogue_session": self._open_dialogue_page,
            "run_project_command": self._run_project_command_page,
            "open_entity_dialogue": self._open_entity_dialogue_page,
            "set_entity_active_dialogue": self._set_active_dialogue_page,
            "step_entity_active_dialogue": self._step_active_dialogue_page,
            "set_entity_active_dialogue_by_order": self._set_active_by_order_page,
        }
        self._command_stack.setCurrentWidget(
            page_by_type.get(command_type, self._generic_page)
        )

    def _sync_open_dialogue_source_visibility(self) -> None:
        source = self._dialogue_source_combo.currentText().strip()
        is_file = source == "Dialogue File"
        self._dialogue_path_edit.parentWidget().setVisible(is_file)
        self._inline_dialogue_summary.parentWidget().setVisible(not is_file)

    def _open_dialogue_advanced_field_count(self) -> int:
        count = 0
        for field in (
            self._ui_preset_field,
            self._actor_id_field,
            self._caller_id_field,
        ):
            if field.optional_value() is not None:
                count += 1
        return count

    def _sync_open_dialogue_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._open_dialogue_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._open_dialogue_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._open_dialogue_advanced_toggle)]
            self._open_dialogue_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._open_dialogue_advanced_toggle.isChecked()
        self._open_dialogue_advanced_widget.setVisible(expanded_state)
        self._open_dialogue_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_open_dialogue_advanced_toggled(self, checked: bool) -> None:
        self._sync_open_dialogue_advanced_state(expanded=bool(checked))

    def _open_entity_advanced_field_count(self) -> int:
        count = 0
        for field in (
            self._open_entity_ui_preset_field,
            self._open_entity_actor_id_field,
            self._open_entity_caller_id_field,
        ):
            if field.optional_value() is not None:
                count += 1
        return count

    def _sync_open_entity_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._open_entity_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._open_entity_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._open_entity_advanced_toggle)]
            self._open_entity_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._open_entity_advanced_toggle.isChecked()
        self._open_entity_advanced_widget.setVisible(expanded_state)
        self._open_entity_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_open_entity_advanced_toggled(self, checked: bool) -> None:
        self._sync_open_entity_advanced_state(expanded=bool(checked))

    def _build_structured_command(self, *, show_message: bool) -> dict[str, Any] | None:
        command_type = self._command_type_combo.currentText().strip()
        if not command_type:
            if show_message:
                QMessageBox.warning(self, "Invalid Command", "Command type cannot be blank.")
            return None
        if command_type not in _SUPPORTED_COMMAND_TYPES:
            return self._build_generic_command(command_type, show_message=show_message)

        if str(self._loaded_command.get("type", "")).strip() == command_type:
            base = copy.deepcopy(self._loaded_command)
        else:
            base = {"type": command_type}
        base["type"] = command_type
        for key in _OWNED_FIELDS_BY_COMMAND_TYPE.get(command_type, set()):
            base.pop(key, None)

        if command_type == "open_dialogue_session":
            source = self._dialogue_source_combo.currentText().strip()
            if source == "Dialogue File":
                dialogue_path = self._dialogue_path_edit.text().strip()
                if not dialogue_path:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            "dialogue_path cannot be blank when using Dialogue File.",
                        )
                    return None
                base["dialogue_path"] = dialogue_path
            else:
                base["dialogue_definition"] = copy.deepcopy(
                    self._inline_dialogue_definition or {"segments": []}
                )
            self._set_optional_bool_field(base, "allow_cancel", self._allow_cancel_field)
            self._set_optional_text_field(base, "ui_preset", self._ui_preset_field)
            self._set_optional_text_field(base, "actor_id", self._actor_id_field)
            self._set_optional_text_field(base, "caller_id", self._caller_id_field)
            return base

        if command_type == "run_project_command":
            command_id = self._project_command_id_edit.text().strip()
            if not command_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "command_id cannot be blank.",
                    )
                return None
            base["command_id"] = command_id
            return base

        if command_type == "open_entity_dialogue":
            entity_id = self._open_entity_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "dialogue_id",
                self._open_entity_dialogue_id_field,
            )
            self._set_optional_bool_field(
                base,
                "allow_cancel",
                self._open_entity_allow_cancel_field,
            )
            self._set_optional_text_field(
                base,
                "ui_preset",
                self._open_entity_ui_preset_field,
            )
            self._set_optional_text_field(
                base,
                "actor_id",
                self._open_entity_actor_id_field,
            )
            self._set_optional_text_field(
                base,
                "caller_id",
                self._open_entity_caller_id_field,
            )
            return base

        if command_type == "set_entity_active_dialogue":
            entity_id = self._set_active_entity_id_edit.text().strip()
            dialogue_id = self._set_active_dialogue_id_edit.text().strip()
            if not entity_id or not dialogue_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and dialogue_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["dialogue_id"] = dialogue_id
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_active_persistent_field,
            )
            return base

        if command_type == "step_entity_active_dialogue":
            entity_id = self._step_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_int_field(base, "delta", self._step_delta_field)
            self._set_optional_bool_field(base, "wrap", self._step_wrap_field)
            self._set_optional_bool_field(base, "persistent", self._step_persistent_field)
            return base

        if command_type == "set_entity_active_dialogue_by_order":
            entity_id = self._set_active_by_order_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["order"] = int(self._set_active_by_order_spin.value())
            self._set_optional_bool_field(
                base,
                "wrap",
                self._set_active_by_order_wrap_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_active_by_order_persistent_field,
            )
            return base

        return base

    def _build_generic_command(self, command_type: str, *, show_message: bool) -> dict[str, Any] | None:
        params_text = self._generic_params_edit.toPlainText().strip()
        if not params_text:
            parsed_params: dict[str, Any] = {}
        else:
            try:
                parsed = loads_json_data(
                    params_text,
                    source_name="Command parameters",
                )
            except JsonDataDecodeError as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command Parameters",
                        f"Could not parse command parameters:\n{exc}",
                    )
                return None
            if not isinstance(parsed, dict):
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command Parameters",
                        "Command parameters must be a JSON object.",
                    )
                return None
            parsed_params = copy.deepcopy(parsed)
        parsed_params.pop("type", None)
        return {"type": command_type, **parsed_params}

    @staticmethod
    def _set_optional_text_field(
        target: dict[str, Any],
        key: str,
        field: _OptionalTextField,
    ) -> None:
        value = field.optional_value()
        if value is not None:
            target[key] = value
        else:
            target.pop(key, None)

    @staticmethod
    def _set_optional_int_field(
        target: dict[str, Any],
        key: str,
        field: _OptionalIntField,
    ) -> None:
        value = field.optional_value()
        if value is not None:
            target[key] = value
        else:
            target.pop(key, None)

    @staticmethod
    def _set_optional_bool_field(
        target: dict[str, Any],
        key: str,
        combo: QComboBox,
    ) -> None:
        value = CommandEditorDialog._optional_bool_combo_value(combo)
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value

    def _command_from_json_tab(self, *, show_message: bool) -> dict[str, Any]:
        try:
            parsed = loads_json_data(
                self._command_json_edit.toPlainText(),
                source_name="Command JSON",
            )
        except JsonDataDecodeError as exc:
            if show_message:
                QMessageBox.warning(self, "Invalid Command JSON", str(exc))
            raise ValueError("Invalid command JSON") from exc
        if not isinstance(parsed, dict):
            if show_message:
                QMessageBox.warning(
                    self,
                    "Invalid Command JSON",
                    "Command JSON must be a JSON object.",
                )
            raise ValueError("Command JSON must be an object.")
        if not str(parsed.get("type", "")).strip():
            if show_message:
                QMessageBox.warning(
                    self,
                    "Invalid Command JSON",
                    "Command JSON must include a non-empty 'type'.",
                )
            raise ValueError("Command JSON missing type.")
        return copy.deepcopy(parsed)

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_tabs or self._loading:
            return
        self._syncing_tabs = True
        try:
            if index == 1:
                command = self._build_structured_command(show_message=True)
                if command is None:
                    self._tabs.setCurrentIndex(0)
                    return
                self._command_json_edit.setPlainText(
                    json.dumps(command, indent=2, ensure_ascii=False)
                )
            else:
                try:
                    command = self._command_from_json_tab(show_message=True)
                except ValueError:
                    self._tabs.setCurrentIndex(1)
                    return
                self.load_command(command)
        finally:
            self._syncing_tabs = False

    def _on_command_type_changed(self, command_type: str) -> None:
        if self._loading:
            return
        self._command_header.setText(command_type or "Command")
        self._sync_structured_page(command_type)
        if command_type not in _SUPPORTED_COMMAND_TYPES:
            self._generic_params_edit.setPlainText("{}")

    def _on_browse_dialogue_path(self) -> None:
        if self._dialogue_picker is None:
            return
        selected = self._dialogue_picker(self._dialogue_path_edit.text().strip())
        if selected:
            self._dialogue_path_edit.setText(selected)

    def _on_browse_project_command_id(self) -> None:
        if self._command_picker is None:
            return
        selected = self._command_picker(self._project_command_id_edit.text().strip())
        if selected:
            self._project_command_id_edit.setText(selected)

    def _on_edit_inline_dialogue(self) -> None:
        updated = self._open_inline_dialogue_definition_dialog(
            self._inline_dialogue_definition or {"segments": []}
        )
        if updated is None:
            return
        self._inline_dialogue_definition = copy.deepcopy(updated)
        self._inline_dialogue_summary.setText(
            _summarize_dialogue_definition(self._inline_dialogue_definition)
        )

    def _open_inline_dialogue_definition_dialog(
        self,
        definition: object,
    ) -> dict[str, Any] | None:
        from area_editor.widgets.dialogue_definition_dialog import DialogueDefinitionDialog

        dialog = DialogueDefinitionDialog(
            self,
            entity_picker=self._entity_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            current_entity_id=self._current_entity_id,
        )
        dialog.setWindowTitle("Edit Inline Dialogue")
        dialog.load_definition(definition)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.definition()


class CommandListDialog(QDialog):
    """Popup manager for one authored command list."""

    def __init__(
        self,
        parent=None,
        *,
        entity_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
        current_entity_id: str | None = None,
        current_area_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandListDialog")
        self.setWindowTitle("Edit Commands")
        self.resize(900, 620)

        self._entity_picker = entity_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._suggested_command_names = tuple(
            str(name).strip()
            for name in (suggested_command_names or ())
            if str(name).strip()
        )
        self._current_entity_id = (
            str(current_entity_id).strip() or None if current_entity_id is not None else None
        )
        self._current_area_id = (
            str(current_area_id).strip() or None if current_area_id is not None else None
        )
        self._commands: list[dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        note = QLabel(
            "Manage one command list here. Right-click to add or delete commands, drag to reorder, "
            "and double-click or use Edit to modify the selected command."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Commands"))
        hint = QLabel("Right-click to add or delete. Drag to reorder.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        left_layout.addWidget(hint)
        self._command_list = _ReorderListWidget()
        self._command_list.setMinimumWidth(280)
        left_layout.addWidget(self._command_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._selection_header = QLabel("No command selected")
        header_font = self._selection_header.font()
        header_font.setBold(True)
        self._selection_header.setFont(header_font)
        right_layout.addWidget(self._selection_header)

        self._selection_summary = QLabel("Select a command to edit it.")
        self._selection_summary.setWordWrap(True)
        right_layout.addWidget(self._selection_summary)

        self._selection_note = QLabel(
            "The command editor opens in a separate popup and keeps unsupported fields through JSON fallback."
        )
        self._selection_note.setWordWrap(True)
        self._selection_note.setStyleSheet("color: #666;")
        right_layout.addWidget(self._selection_note)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        self._edit_button = QPushButton("Edit...")
        self._edit_button.setAutoDefault(False)
        self._edit_button.setDefault(False)
        self._edit_button.clicked.connect(self._on_edit_selected)
        buttons_row.addWidget(self._edit_button)
        buttons_row.addStretch(1)
        right_layout.addLayout(buttons_row)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 520])

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._command_list.currentRowChanged.connect(self._on_command_row_changed)
        self._command_list.itemDoubleClicked.connect(lambda _item: self._on_edit_selected())
        self._command_list.customContextMenuRequested.connect(
            self._on_command_context_menu_requested
        )
        self._command_list.visual_order_changed.connect(self._on_command_visual_order_changed)
        self._sync_selection_state()

    def load_commands(self, commands: object) -> None:
        self._commands = _normalize_command_list(commands)
        self._refresh_command_list()
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(0)
        self._sync_selection_state()

    def commands(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._commands)

    def _command_at_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._commands):
            return None
        return self._commands[row]

    def _refresh_command_list(self) -> None:
        current_row = self._command_list.currentRow()
        self._command_list.blockSignals(True)
        try:
            self._command_list.clear()
            for index, command in enumerate(self._commands):
                item = QListWidgetItem(_command_summary(command, index))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._command_list.addItem(item)
        finally:
            self._command_list.blockSignals(False)
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(min(max(current_row, 0), self._command_list.count() - 1))

    def _default_command_for_type(self, command_type: str) -> dict[str, Any]:
        if command_type == "open_dialogue_session":
            return {
                "type": command_type,
                "dialogue_definition": {
                    "segments": [],
                },
            }
        return {"type": command_type}

    def _prompt_command_type(self) -> str | None:
        dialog = _CommandTypePickerDialog(
            self,
            command_names=_known_command_names(),
            suggested_command_names=self._suggested_command_names,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_command_type()

    def _sync_selection_state(self) -> None:
        row = self._command_list.currentRow()
        command = self._command_at_row(row)
        has_selection = command is not None
        self._edit_button.setEnabled(has_selection)
        if command is None:
            self._selection_header.setText("No command selected")
            self._selection_summary.setText("Select a command to edit it.")
            return
        command_type = str(command.get("type", "")).strip() or "(no type)"
        self._selection_header.setText(f"Command {row + 1}: {command_type}")
        self._selection_summary.setText(_command_summary(command, row))

    def _edit_command_at(self, row: int) -> bool:
        command = self._command_at_row(row)
        if command is None:
            return False
        dialog = CommandEditorDialog(
            self,
            entity_picker=self._entity_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
        )
        dialog.load_command(command)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._commands[row] = dialog.command()
        self._refresh_command_list()
        self._command_list.setCurrentRow(row)
        self._sync_selection_state()
        return True

    def _add_command_after(self, after_row: int | None) -> None:
        command_type = self._prompt_command_type()
        if command_type is None:
            return
        dialog = CommandEditorDialog(
            self,
            entity_picker=self._entity_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
        )
        dialog.load_command(self._default_command_for_type(command_type))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        insert_row = len(self._commands)
        if after_row is not None and 0 <= after_row < len(self._commands):
            insert_row = after_row + 1
        self._commands.insert(insert_row, dialog.command())
        self._refresh_command_list()
        self._command_list.setCurrentRow(insert_row)
        self._sync_selection_state()

    def _delete_command_at(self, row: int) -> None:
        if row < 0 or row >= len(self._commands):
            return
        del self._commands[row]
        self._refresh_command_list()
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(min(row, self._command_list.count() - 1))
        self._sync_selection_state()

    def _on_command_context_menu_requested(self, position) -> None:
        item = self._command_list.itemAt(position)
        target_row = self._command_list.row(item) if item is not None else -1
        menu = QMenu(self)
        add_action = menu.addAction("Add Command...")
        edit_action = None
        delete_action = None
        if target_row >= 0:
            edit_action = menu.addAction("Edit...")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._command_list.viewport().mapToGlobal(position))
        if chosen == add_action:
            self._add_command_after(target_row if target_row >= 0 else None)
        elif edit_action is not None and chosen == edit_action:
            self._edit_command_at(target_row)
        elif delete_action is not None and chosen == delete_action:
            self._delete_command_at(target_row)

    def _on_command_visual_order_changed(self, visual_order: list[int]) -> None:
        if len(visual_order) != len(self._commands):
            self._refresh_command_list()
            self._sync_selection_state()
            return
        current_command = self._command_at_row(self._command_list.currentRow())
        reordered = [
            self._commands[index]
            for index in visual_order
            if 0 <= index < len(self._commands)
        ]
        if len(reordered) != len(self._commands):
            self._refresh_command_list()
            self._sync_selection_state()
            return
        self._commands[:] = reordered
        self._refresh_command_list()
        if current_command is not None and current_command in self._commands:
            self._command_list.setCurrentRow(self._commands.index(current_command))
        self._sync_selection_state()

    def _on_command_row_changed(self, _row: int) -> None:
        self._sync_selection_state()

    def _on_edit_selected(self) -> None:
        self._edit_command_at(self._command_list.currentRow())

    def accept(self) -> None:  # noqa: D401
        super().accept()

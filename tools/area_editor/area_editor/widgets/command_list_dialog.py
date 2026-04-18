"""Structured popup editor for one authored command list."""

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

_KNOWN_COMMAND_NAMES: tuple[str, ...] | None = None


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


def _make_line_with_browse(
    *,
    browse_text: str = "Browse...",
) -> tuple[QWidget, QLineEdit, QPushButton]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    edit = QLineEdit()
    button = QPushButton(browse_text)
    button.setAutoDefault(False)
    button.setDefault(False)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return row, edit, button


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
        self._command_list.currentRowChanged.connect(lambda _row: self._sync_accept_button())

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
                remaining = [name for name in self._all_command_names if name not in self._suggested_command_names]
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


class _CommandListStructuredEditor(QWidget):
    """List-based structured editor for one command list."""

    def __init__(
        self,
        parent=None,
        *,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)

        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._suggested_command_names = tuple(
            str(name).strip()
            for name in (suggested_command_names or ())
            if str(name).strip()
        )
        self._commands: list[dict[str, Any]] = []
        self._loading = False
        self._last_valid_row = -1
        self._syncing_tabs = False
        self._inline_dialogue_definition: dict[str, Any] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            "Edit one command list here. Right-click to add or delete commands, drag to reorder, "
            "and use the JSON tab for advanced or unsupported fields."
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
        self._command_list.setMinimumWidth(260)
        left_layout.addWidget(self._command_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._editor_tabs = QTabWidget()
        right_layout.addWidget(self._editor_tabs, 1)

        structured = QWidget()
        structured_layout = QVBoxLayout(structured)
        structured_layout.setContentsMargins(0, 0, 0, 0)
        structured_layout.setSpacing(8)

        self._command_header = QLabel("No command selected")
        font = self._command_header.font()
        font.setBold(True)
        self._command_header.setFont(font)
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

        self._generic_page = QWidget()
        generic_layout = QVBoxLayout(self._generic_page)
        generic_layout.setContentsMargins(0, 0, 0, 0)
        generic_layout.addWidget(
            QLabel("Parameters JSON")
        )
        self._generic_params_edit = QPlainTextEdit()
        self._generic_params_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._generic_params_edit.setFixedHeight(280)
        generic_font = QFont("Consolas", 10)
        generic_font.setStyleHint(QFont.StyleHint.Monospace)
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

        dialogue_file_row, self._dialogue_path_edit, self._dialogue_path_browse = _make_line_with_browse()
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

        self._allow_cancel_check = QCheckBox()
        open_dialogue_form.addRow("allow_cancel", self._allow_cancel_check)

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
        advanced_form = QFormLayout(self._open_dialogue_advanced_widget)
        advanced_form.setContentsMargins(12, 0, 0, 0)
        self._ui_preset_edit = QLineEdit()
        self._ui_preset_edit.textChanged.connect(
            lambda _text: self._sync_open_dialogue_advanced_state()
        )
        advanced_form.addRow("ui_preset", self._ui_preset_edit)
        self._actor_id_edit = QLineEdit()
        self._actor_id_edit.textChanged.connect(
            lambda _text: self._sync_open_dialogue_advanced_state()
        )
        advanced_form.addRow("actor_id", self._actor_id_edit)
        self._caller_id_edit = QLineEdit()
        self._caller_id_edit.textChanged.connect(
            lambda _text: self._sync_open_dialogue_advanced_state()
        )
        advanced_form.addRow("caller_id", self._caller_id_edit)
        open_dialogue_form.addRow(self._open_dialogue_advanced_widget)
        self._command_stack.addWidget(self._open_dialogue_page)

        self._project_command_page = QWidget()
        project_command_form = QFormLayout(self._project_command_page)
        project_command_form.setContentsMargins(0, 0, 0, 0)
        command_row, self._project_command_id_edit, self._project_command_browse = _make_line_with_browse()
        self._project_command_browse.clicked.connect(self._on_browse_project_command_id)
        project_command_form.addRow("command_id", command_row)
        self._command_stack.addWidget(self._project_command_page)

        self._editor_tabs.addTab(structured, "Command Editor")

        self._command_json_edit = QPlainTextEdit()
        self._command_json_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._command_json_edit.setFont(generic_font)
        self._editor_tabs.addTab(self._command_json_edit, "Command JSON")

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 580])

        self._command_list.currentRowChanged.connect(self._on_command_row_changed)
        self._command_list.customContextMenuRequested.connect(self._on_command_context_menu_requested)
        self._command_list.visual_order_changed.connect(self._on_command_visual_order_changed)
        self._editor_tabs.currentChanged.connect(self._on_editor_tab_changed)
        self._command_type_combo.currentTextChanged.connect(self._on_command_type_changed)
        self._dialogue_source_combo.currentTextChanged.connect(self._sync_open_dialogue_source_visibility)
        self._sync_open_dialogue_advanced_state(expanded=False)

    def load_commands(self, commands: object) -> None:
        self._commands = _normalize_command_list(commands)
        self._loading = True
        try:
            self._refresh_command_list()
        finally:
            self._loading = False
        if self._command_list.count() > 0:
            self._command_list.blockSignals(True)
            try:
                self._command_list.setCurrentRow(0)
            finally:
                self._command_list.blockSignals(False)
            self._last_valid_row = 0
        else:
            self._last_valid_row = -1
        self._editor_tabs.setCurrentIndex(0)
        self._load_current_command_editor()

    def commands(self) -> list[dict[str, Any]]:
        if not self._commit_current_command(show_message=True):
            raise ValueError("Command list has invalid fields.")
        return copy.deepcopy(self._commands)

    def _command_at_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._commands):
            return None
        command = self._commands[row]
        if not isinstance(command, dict):
            return None
        return command

    def _current_command(self) -> dict[str, Any] | None:
        return self._command_at_row(self._command_list.currentRow())

    def _refresh_command_list(self) -> None:
        selected_row = self._command_list.currentRow()
        self._command_list.blockSignals(True)
        try:
            self._command_list.clear()
            for index, command in enumerate(self._commands):
                item = QListWidgetItem(_command_summary(command, index))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._command_list.addItem(item)
            if self._command_list.count() > 0:
                selected_row = max(0, min(selected_row, self._command_list.count() - 1))
                self._command_list.setCurrentRow(selected_row)
        finally:
            self._command_list.blockSignals(False)
        if self._command_list.count() <= 0:
            self._last_valid_row = -1
            return
        self._last_valid_row = selected_row

    def _load_current_command_editor(self) -> None:
        command = self._current_command()
        self._loading = True
        try:
            if command is None:
                self._command_header.setText("No command selected")
                self._command_type_combo.setEnabled(False)
                self._generic_params_edit.setPlainText("")
                self._command_json_edit.setPlainText("")
                self._project_command_id_edit.setText("")
                self._dialogue_path_edit.setText("")
                self._ui_preset_edit.setText("")
                self._actor_id_edit.setText("")
                self._caller_id_edit.setText("")
                self._allow_cancel_check.setChecked(False)
                self._inline_dialogue_definition = None
                self._inline_dialogue_summary.setText("0 segments")
                self._sync_open_dialogue_source_visibility()
                self._sync_open_dialogue_advanced_state(expanded=False)
                return

            row = self._command_list.currentRow() + 1
            self._command_header.setText(f"Command {row}")
            self._command_type_combo.setEnabled(True)
            command_type = str(command.get("type", "")).strip()
            self._ensure_command_type_visible(command_type)
            self._command_type_combo.setCurrentText(command_type)
            self._generic_params_edit.setPlainText(
                json.dumps(
                    {key: value for key, value in command.items() if key != "type"},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            self._command_json_edit.setPlainText(
                json.dumps(command, indent=2, ensure_ascii=False)
            )

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
            self._allow_cancel_check.setChecked(bool(command.get("allow_cancel", False)))
            self._ui_preset_edit.setText(str(command.get("ui_preset", "")))
            self._actor_id_edit.setText(str(command.get("actor_id", "")))
            self._caller_id_edit.setText(str(command.get("caller_id", "")))
            self._project_command_id_edit.setText(str(command.get("command_id", "")))
            self._sync_structured_page(command_type)
        finally:
            self._loading = False
        self._sync_open_dialogue_source_visibility()
        if command is not None and command_type == "open_dialogue_session":
            self._sync_open_dialogue_advanced_state(
                expanded=self._open_dialogue_advanced_field_count() > 0
            )

    def _ensure_command_type_visible(self, command_type: str) -> None:
        if not command_type:
            return
        if self._command_type_combo.findText(command_type) >= 0:
            return
        self._command_type_combo.insertItem(0, command_type)

    def _sync_structured_page(self, command_type: str) -> None:
        if command_type == "open_dialogue_session":
            self._command_stack.setCurrentWidget(self._open_dialogue_page)
            return
        if command_type == "run_project_command":
            self._command_stack.setCurrentWidget(self._project_command_page)
            return
        self._command_stack.setCurrentWidget(self._generic_page)

    def _sync_open_dialogue_source_visibility(self) -> None:
        source = self._dialogue_source_combo.currentText().strip()
        is_file = source == "Dialogue File"
        self._dialogue_path_edit.parentWidget().setVisible(is_file)
        self._inline_dialogue_summary.parentWidget().setVisible(not is_file)

    def _open_dialogue_advanced_field_count(self) -> int:
        count = 0
        for edit in (
            self._ui_preset_edit,
            self._actor_id_edit,
            self._caller_id_edit,
        ):
            if edit.text().strip():
                count += 1
        return count

    def _sync_open_dialogue_advanced_state(self, *, expanded: bool | None = None) -> None:
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

    def _build_structured_command(self, *, show_message: bool) -> dict[str, Any] | None:
        base = copy.deepcopy(self._command_at_row(self._last_valid_row) or {})
        command_type = self._command_type_combo.currentText().strip()
        if not command_type:
            if show_message:
                QMessageBox.warning(self, "Invalid Command", "Command type cannot be blank.")
            return None
        base["type"] = command_type

        if command_type == "open_dialogue_session":
            source = self._dialogue_source_combo.currentText().strip()
            if source == "Dialogue File":
                dialogue_path = self._dialogue_path_edit.text().strip()
                if dialogue_path:
                    base["dialogue_path"] = dialogue_path
                else:
                    base.pop("dialogue_path", None)
                base.pop("dialogue_definition", None)
            else:
                base.pop("dialogue_path", None)
                base["dialogue_definition"] = copy.deepcopy(
                    self._inline_dialogue_definition
                    or {"segments": []}
                )
            if self._allow_cancel_check.isChecked():
                base["allow_cancel"] = True
            else:
                base.pop("allow_cancel", None)
            self._set_optional_text_field(base, "ui_preset", self._ui_preset_edit)
            self._set_optional_text_field(base, "actor_id", self._actor_id_edit)
            self._set_optional_text_field(base, "caller_id", self._caller_id_edit)
            return base

        if command_type == "run_project_command":
            self._set_optional_text_field(base, "command_id", self._project_command_id_edit)
            return base

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
    def _set_optional_text_field(target: dict[str, Any], key: str, edit: QLineEdit) -> None:
        value = edit.text().strip()
        if value:
            target[key] = value
        else:
            target.pop(key, None)

    def _commit_current_command(self, *, show_message: bool) -> bool:
        if self._last_valid_row < 0:
            return True
        if self._editor_tabs.currentIndex() == 1:
            try:
                command = self._command_from_json_tab(show_message=show_message)
            except ValueError:
                return False
        else:
            command = self._build_structured_command(show_message=show_message)
            if command is None:
                return False
        self._commands[self._last_valid_row] = copy.deepcopy(command)
        return True

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

    def _insert_command(self, command_type: str, *, after_row: int | None = None) -> None:
        if not self._commit_current_command(show_message=True):
            return
        default_command = self._default_command_for_type(command_type)
        if after_row is None or after_row < 0 or after_row >= len(self._commands):
            insert_row = len(self._commands)
        else:
            insert_row = after_row + 1
        self._commands.insert(insert_row, default_command)
        self._refresh_command_list()
        self._command_list.blockSignals(True)
        try:
            self._command_list.setCurrentRow(insert_row)
        finally:
            self._command_list.blockSignals(False)
        self._last_valid_row = insert_row
        self._editor_tabs.setCurrentIndex(0)
        self._load_current_command_editor()

    def _default_command_for_type(self, command_type: str) -> dict[str, Any]:
        if command_type == "open_dialogue_session":
            return {
                "type": command_type,
                "dialogue_definition": {
                    "segments": [],
                },
            }
        return {"type": command_type}

    def _delete_command_at(self, row: int) -> None:
        if not self._commit_current_command(show_message=True):
            return
        if row < 0 or row >= len(self._commands):
            return
        del self._commands[row]
        self._refresh_command_list()
        if self._command_list.count() > 0:
            target_row = min(row, self._command_list.count() - 1)
            self._command_list.blockSignals(True)
            try:
                self._command_list.setCurrentRow(target_row)
            finally:
                self._command_list.blockSignals(False)
            self._last_valid_row = target_row
        else:
            self._last_valid_row = -1
        self._editor_tabs.setCurrentIndex(0)
        self._load_current_command_editor()

    def _prompt_command_type(self) -> str | None:
        dialog = _CommandTypePickerDialog(
            self,
            command_names=_known_command_names(),
            suggested_command_names=self._suggested_command_names,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_command_type()

    def _on_command_context_menu_requested(self, position) -> None:
        item = self._command_list.itemAt(position)
        target_row = self._command_list.row(item) if item is not None else -1
        menu = QMenu(self)
        add_action = menu.addAction("Add Command...")
        delete_action = None
        if target_row >= 0:
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._command_list.viewport().mapToGlobal(position))
        if chosen == add_action:
            command_type = self._prompt_command_type()
            if command_type is not None:
                self._insert_command(command_type, after_row=target_row if target_row >= 0 else None)
        elif delete_action is not None and chosen == delete_action:
            self._delete_command_at(target_row)

    def _on_command_visual_order_changed(self, visual_order: list[int]) -> None:
        if not self._commit_current_command(show_message=True):
            self._refresh_command_list()
            self._load_current_command_editor()
            return
        if len(visual_order) != len(self._commands):
            self._refresh_command_list()
            self._load_current_command_editor()
            return
        current_command = self._command_at_row(self._last_valid_row)
        reordered = [self._commands[index] for index in visual_order if 0 <= index < len(self._commands)]
        if len(reordered) != len(self._commands):
            self._refresh_command_list()
            self._load_current_command_editor()
            return
        self._commands[:] = reordered
        self._refresh_command_list()
        if current_command is not None and current_command in self._commands:
            target_row = self._commands.index(current_command)
        elif self._command_list.count() > 0:
            target_row = min(self._last_valid_row, self._command_list.count() - 1)
        else:
            target_row = -1
        self._command_list.blockSignals(True)
        try:
            self._command_list.setCurrentRow(target_row)
        finally:
            self._command_list.blockSignals(False)
        self._last_valid_row = target_row
        self._load_current_command_editor()

    def _on_command_row_changed(self, row: int) -> None:
        if self._loading:
            return
        if not self._commit_current_command(show_message=False):
            self._command_list.blockSignals(True)
            try:
                self._command_list.setCurrentRow(self._last_valid_row)
            finally:
                self._command_list.blockSignals(False)
            return
        self._last_valid_row = row
        self._refresh_command_list()
        self._load_current_command_editor()

    def _on_editor_tab_changed(self, index: int) -> None:
        if self._syncing_tabs or self._loading or self._last_valid_row < 0:
            return
        self._syncing_tabs = True
        try:
            if index == 1:
                command = self._build_structured_command(show_message=True)
                if command is None:
                    self._editor_tabs.setCurrentIndex(0)
                    return
                self._command_json_edit.setPlainText(
                    json.dumps(command, indent=2, ensure_ascii=False)
                )
            else:
                try:
                    command = self._command_from_json_tab(show_message=True)
                except ValueError:
                    self._editor_tabs.setCurrentIndex(1)
                    return
                self._commands[self._last_valid_row] = copy.deepcopy(command)
                self._refresh_command_list()
                self._load_current_command_editor()
        finally:
            self._syncing_tabs = False

    def _on_command_type_changed(self, command_type: str) -> None:
        if self._loading:
            return
        self._sync_structured_page(command_type)

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
            self._inline_dialogue_definition
            or {"segments": []}
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
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
        )
        dialog.setWindowTitle("Edit Inline Dialogue")
        dialog.load_definition(definition)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.definition()


class CommandListDialog(QDialog):
    """Popup editor for one command list."""

    def __init__(
        self,
        parent=None,
        *,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandListDialog")
        self.setWindowTitle("Edit Commands")
        self.resize(920, 680)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._structured_editor = _CommandListStructuredEditor(
            self,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            suggested_command_names=suggested_command_names,
        )
        outer.addWidget(self._structured_editor, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._last_loaded_commands: list[dict[str, Any]] = []

    def load_commands(self, commands: object) -> None:
        self._last_loaded_commands = _normalize_command_list(commands)
        self._structured_editor.load_commands(self._last_loaded_commands)

    def commands(self) -> list[dict[str, Any]]:
        return self._structured_editor.commands()

    def accept(self) -> None:  # noqa: D401
        try:
            self._last_loaded_commands = self.commands()
        except ValueError:
            return
        super().accept()

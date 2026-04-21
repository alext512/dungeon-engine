"""Structured popup editor for inline dialogue definitions."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.widgets.command_list_dialog import (
    CommandListDialog,
    summarize_command_list,
)

_DIALOGUE_SUGGESTED_COMMAND_NAMES = (
    "open_dialogue_session",
    "run_project_command",
    "set_entity_var",
    "close_dialogue_session",
)


class _ReorderTreeWidget(QTreeWidget):
    """Tree widget that emits one stable top-level order snapshot after drops."""

    visual_order_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(self.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        order: list[str] = []
        for row in range(self.topLevelItemCount()):
            item = self.topLevelItem(row)
            if item is None:
                continue
            value = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(value, str) and value.strip():
                order.append(value)
        if order:
            self.visual_order_changed.emit(order)


def summarize_dialogue_definition(definition: object) -> str:
    """Return a short human-readable summary for one dialogue definition."""
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


def _ensure_dialogue_definition(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"segments": []}
    definition = copy.deepcopy(value)
    if not isinstance(definition.get("segments"), list):
        definition["segments"] = []
    return definition


def normalize_entity_dialogues(value: object) -> dict[str, dict[str, Any]]:
    """Return a validated copy of an entity-owned dialogue map."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Dialogues must be a JSON object keyed by dialogue id.")

    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_entry in value.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("Dialogue ids must not be blank.")
        if not isinstance(raw_entry, dict):
            raise ValueError(f"Dialogue '{name}' must be a JSON object.")
        entry = copy.deepcopy(raw_entry)
        has_definition = isinstance(entry.get("dialogue_definition"), dict)
        raw_path = entry.get("dialogue_path", "")
        path = str(raw_path).strip() if raw_path is not None else ""
        has_path = bool(path)
        if has_definition == has_path:
            raise ValueError(
                f"Dialogue '{name}' must define exactly one of "
                "'dialogue_definition' or 'dialogue_path'."
            )
        if has_definition:
            entry["dialogue_definition"] = _ensure_dialogue_definition(
                entry.get("dialogue_definition")
            )
            entry.pop("dialogue_path", None)
        else:
            entry["dialogue_path"] = path
            entry.pop("dialogue_definition", None)
        normalized[name] = entry
    return normalized


def summarize_entity_dialogues(
    dialogues: object,
    active_dialogue: object = None,
) -> str:
    """Return a short summary for an entity-owned dialogue map."""
    try:
        normalized = normalize_entity_dialogues(dialogues)
    except ValueError:
        return "Dialogues use an unsupported shape"
    count = len(normalized)
    if count == 0:
        return "No dialogues"
    summary = f"{count} dialogue{'s' if count != 1 else ''}"
    active_name = str(active_dialogue).strip() if active_dialogue is not None else ""
    if not active_name and count == 1:
        active_name = next(iter(normalized), "")
    if active_name:
        if active_name in normalized:
            summary += f"; active: {active_name}"
        else:
            summary += f"; active: {active_name} (missing)"
    return summary


def rename_active_dialogue_value(
    variables: object,
    rename_map: dict[str, str],
) -> object:
    """Return ``variables`` with ``active_dialogue`` rewritten when needed."""
    if not isinstance(variables, dict) or not rename_map:
        return copy.deepcopy(variables)
    rewritten = copy.deepcopy(variables)
    active_value = rewritten.get("active_dialogue")
    if isinstance(active_value, str):
        stripped = active_value.strip()
        if stripped in rename_map:
            rewritten["active_dialogue"] = rename_map[stripped]
    return rewritten


def rename_self_target_dialogue_id_references(
    value: object,
    rename_map: dict[str, str],
    *,
    current_entity_id: str | None = None,
) -> object:
    """Return ``value`` with known self-targeting dialogue-id command refs renamed."""
    rewritten = copy.deepcopy(value)
    if not rename_map:
        return rewritten

    self_tokens = {"$self_id", "${self_id}"}

    def targets_local_entity(command: dict[str, Any]) -> bool:
        raw_entity_id = command.get("entity_id")
        if not isinstance(raw_entity_id, str):
            return False
        normalized = raw_entity_id.strip()
        if not normalized:
            return False
        if normalized in self_tokens:
            return True
        if current_entity_id and normalized == current_entity_id:
            return True
        return False

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        command_type = str(node.get("type", "")).strip()
        if command_type in {"open_entity_dialogue", "set_entity_active_dialogue"}:
            if targets_local_entity(node):
                raw_dialogue_id = node.get("dialogue_id")
                if isinstance(raw_dialogue_id, str):
                    stripped = raw_dialogue_id.strip()
                    if stripped in rename_map:
                        node["dialogue_id"] = rename_map[stripped]

        for child in node.values():
            walk(child)

    walk(rewritten)
    return rewritten


def _segment_summary(segment: object, index: int) -> str:
    if not isinstance(segment, dict):
        return f"{index + 1}. invalid segment"
    segment_type = str(segment.get("type", "text")).strip() or "text"
    raw_text = segment.get("text", "")
    text = "" if raw_text is None else str(raw_text).strip().replace("\n", " ")
    preview = text[:48] + ("..." if len(text) > 48 else "")
    if not preview:
        preview = "(no text)"
    if segment_type == "choice":
        option_count = len(segment.get("options", [])) if isinstance(segment.get("options"), list) else 0
        return f"{index + 1}. choice: {preview} [{option_count} option{'s' if option_count != 1 else ''}]"
    return f"{index + 1}. {segment_type}: {preview}"


def _option_summary(option: object, index: int) -> str:
    if not isinstance(option, dict):
        return f"{index + 1}. invalid option"
    option_id = str(option.get("option_id", "")).strip()
    text = str(option.get("text", "")).strip().replace("\n", " ")
    preview = text[:40] + ("..." if len(text) > 40 else "")
    if not preview:
        preview = "(no text)"
    if option_id:
        return f"{index + 1}. {option_id}: {preview}"
    return f"{index + 1}. {preview}"


def _dialogue_path_from_key(key: object) -> tuple[tuple[int, int], ...]:
    if not isinstance(key, tuple) or len(key) < 2:
        return ()
    raw_path = key[1]
    if not isinstance(raw_path, tuple):
        return ()
    normalized: list[tuple[int, int]] = []
    for part in raw_path:
        if (
            isinstance(part, tuple)
            and len(part) == 2
            and isinstance(part[0], int)
            and isinstance(part[1], int)
        ):
            normalized.append((part[0], part[1]))
    return tuple(normalized)


def _node_kind(key: object) -> str:
    if not isinstance(key, tuple) or not key:
        return ""
    raw_kind = key[0]
    return raw_kind if isinstance(raw_kind, str) else ""


def _dialogue_key(dialogue_path: tuple[tuple[int, int], ...]) -> tuple[object, ...]:
    return ("dialogue", dialogue_path)


def _segment_key(
    dialogue_path: tuple[tuple[int, int], ...],
    segment_index: int,
) -> tuple[object, ...]:
    return ("segment", dialogue_path, int(segment_index))


def _option_key(
    dialogue_path: tuple[tuple[int, int], ...],
    segment_index: int,
    option_index: int,
) -> tuple[object, ...]:
    return ("option", dialogue_path, int(segment_index), int(option_index))


def _file_branch_key(
    dialogue_path: tuple[tuple[int, int], ...],
    segment_index: int,
    option_index: int,
) -> tuple[object, ...]:
    return ("file_branch", dialogue_path, int(segment_index), int(option_index))


def _tree_item_font(*, bold: bool = False, italic: bool = False) -> QFont:
    font = QFont()
    font.setBold(bold)
    font.setItalic(italic)
    return font


def _dialogue_tree_label(
    dialogue_path: tuple[tuple[int, int], ...],
    definition: dict[str, Any] | None,
) -> str:
    if not dialogue_path:
        return "Main Dialogue"
    summary = summarize_dialogue_definition(definition or {"segments": []})
    return f"Inline Dialogue ({summary})"


def _tree_label_with_state(
    label: str,
    *,
    terminal: bool = False,
    unreachable: bool = False,
) -> str:
    parts = [label]
    if terminal:
        parts.append("[Ends]")
    if unreachable:
        parts.append("[Unreachable]")
    return " ".join(parts)


def _decorate_tree_item(
    item: QTreeWidgetItem,
    *,
    bold: bool = False,
    italic: bool = False,
    terminal: bool = False,
    unreachable: bool = False,
    tooltip: str | None = None,
) -> None:
    item.setFont(0, _tree_item_font(bold=bold, italic=italic))
    if unreachable:
        item.setForeground(0, QBrush(QColor("#8a2d2d")))
        item.setBackground(0, QBrush(QColor("#fff1f1")))
    elif terminal:
        item.setForeground(0, QBrush(QColor("#8a4b00")))
    if tooltip:
        item.setToolTip(0, tooltip)


class _DialogueDefinitionStructuredEditor(QWidget):
    """Tree-based structured editor for one dialogue definition."""

    def __init__(
        self,
        parent=None,
        *,
        entity_picker=None,
        entity_dialogue_picker=None,
        dialogue_picker=None,
        command_picker=None,
        current_entity_id: str | None = None,
    ) -> None:
        super().__init__(parent)

        self._entity_picker = entity_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._current_entity_id = current_entity_id
        self._definition: dict[str, Any] = {"segments": []}
        self._loading = False
        self._last_valid_key: tuple[object, ...] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            "Edit the whole local dialogue chain here. Inline branches live in this same tree. "
            "Dialogue-file branches appear as shared references. For advanced fields like "
            "participants or custom data, use the JSON tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Dialogue Tree"))
        tree_hint = QLabel(
            "Right-click tree nodes to add, branch, delete, or reorder pieces."
        )
        tree_hint.setWordWrap(True)
        tree_hint.setStyleSheet("color: #666;")
        left_layout.addWidget(tree_hint)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(320)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self._tree, 1)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._detail_header = QLabel("No item selected")
        font = self._detail_header.font()
        font.setBold(True)
        self._detail_header.setFont(font)
        right_layout.addWidget(self._detail_header)

        self._detail_stack = QStackedWidget()
        right_layout.addWidget(self._detail_stack, 1)

        self._empty_page = QWidget()
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_label = QLabel("Select a dialogue, segment, option, or file reference from the tree.")
        empty_label.setWordWrap(True)
        empty_layout.addWidget(empty_label)
        empty_layout.addStretch(1)
        self._detail_stack.addWidget(self._empty_page)

        self._dialogue_page = QWidget()
        dialogue_layout = QVBoxLayout(self._dialogue_page)
        dialogue_layout.setContentsMargins(0, 0, 0, 0)
        self._dialogue_title_label = QLabel("Dialogue")
        dialogue_layout.addWidget(self._dialogue_title_label)
        self._dialogue_summary_label = QLabel("")
        self._dialogue_summary_label.setWordWrap(True)
        dialogue_layout.addWidget(self._dialogue_summary_label)
        self._dialogue_note_label = QLabel(
            "Right-click this dialogue in the tree to insert segments, or use the buttons below."
        )
        self._dialogue_note_label.setWordWrap(True)
        self._dialogue_note_label.setStyleSheet("color: #666;")
        dialogue_layout.addWidget(self._dialogue_note_label)
        dialogue_buttons = QHBoxLayout()
        self._dialogue_add_text_button = QPushButton("Add Text Segment")
        self._dialogue_add_text_button.setAutoDefault(False)
        self._dialogue_add_text_button.setDefault(False)
        self._dialogue_add_text_button.clicked.connect(self._on_add_text_for_selected_dialogue)
        dialogue_buttons.addWidget(self._dialogue_add_text_button)
        self._dialogue_add_choice_button = QPushButton("Add Choice Segment")
        self._dialogue_add_choice_button.setAutoDefault(False)
        self._dialogue_add_choice_button.setDefault(False)
        self._dialogue_add_choice_button.clicked.connect(self._on_add_choice_for_selected_dialogue)
        dialogue_buttons.addWidget(self._dialogue_add_choice_button)
        dialogue_buttons.addStretch(1)
        dialogue_layout.addLayout(dialogue_buttons)
        dialogue_layout.addStretch(1)
        self._detail_stack.addWidget(self._dialogue_page)

        self._segment_page = QWidget()
        segment_layout = QVBoxLayout(self._segment_page)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_form = QFormLayout()
        self._segment_type_label = QLabel("-")
        segment_form.addRow("type", self._segment_type_label)
        segment_layout.addLayout(segment_form)
        segment_layout.addWidget(QLabel("text"))
        self._segment_text_edit = QPlainTextEdit()
        self._segment_text_edit.setPlaceholderText("Segment text or choice prompt")
        self._segment_text_edit.setFixedHeight(110)
        segment_layout.addWidget(self._segment_text_edit)
        segment_start_row = QHBoxLayout()
        segment_start_row.setContentsMargins(0, 0, 0, 0)
        segment_start_row.addWidget(QLabel("on_start"))
        self._segment_on_start_summary = QLabel("none")
        segment_start_row.addWidget(self._segment_on_start_summary, 1)
        self._segment_on_start_button = QPushButton("Edit...")
        self._segment_on_start_button.setAutoDefault(False)
        self._segment_on_start_button.setDefault(False)
        self._segment_on_start_button.clicked.connect(
            lambda: self._edit_segment_commands("on_start")
        )
        segment_start_row.addWidget(self._segment_on_start_button)
        segment_layout.addLayout(segment_start_row)
        segment_end_row = QHBoxLayout()
        segment_end_row.setContentsMargins(0, 0, 0, 0)
        segment_end_row.addWidget(QLabel("on_end"))
        self._segment_on_end_summary = QLabel("none")
        segment_end_row.addWidget(self._segment_on_end_summary, 1)
        self._segment_on_end_button = QPushButton("Edit...")
        self._segment_on_end_button.setAutoDefault(False)
        self._segment_on_end_button.setDefault(False)
        self._segment_on_end_button.clicked.connect(
            lambda: self._edit_segment_commands("on_end")
        )
        segment_end_row.addWidget(self._segment_on_end_button)
        segment_layout.addLayout(segment_end_row)
        self._segment_end_dialogue_checkbox = QCheckBox("End dialogue after this segment")
        self._segment_end_dialogue_checkbox.stateChanged.connect(
            self._on_segment_end_dialogue_changed
        )
        segment_layout.addWidget(self._segment_end_dialogue_checkbox)
        self._segment_end_dialogue_note = QLabel("")
        self._segment_end_dialogue_note.setWordWrap(True)
        self._segment_end_dialogue_note.setStyleSheet("color: #8a4b00;")
        segment_layout.addWidget(self._segment_end_dialogue_note)
        self._segment_choice_note = QLabel("")
        self._segment_choice_note.setWordWrap(True)
        self._segment_choice_note.setStyleSheet("color: #666;")
        segment_layout.addWidget(self._segment_choice_note)
        segment_actions = QHBoxLayout()
        self._segment_add_option_button = QPushButton("Add Option")
        self._segment_add_option_button.setAutoDefault(False)
        self._segment_add_option_button.setDefault(False)
        self._segment_add_option_button.clicked.connect(self._on_add_option_for_selected_choice)
        segment_actions.addWidget(self._segment_add_option_button)
        segment_actions.addStretch(1)
        segment_layout.addLayout(segment_actions)
        segment_layout.addStretch(1)
        self._detail_stack.addWidget(self._segment_page)

        self._option_page = QWidget()
        option_layout = QVBoxLayout(self._option_page)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_form = QFormLayout()
        self._option_id_edit = QLineEdit()
        option_form.addRow("option_id", self._option_id_edit)
        option_layout.addLayout(option_form)
        option_layout.addWidget(QLabel("text"))
        self._option_text_edit = QPlainTextEdit()
        self._option_text_edit.setFixedHeight(90)
        option_layout.addWidget(self._option_text_edit)
        option_commands_row = QHBoxLayout()
        option_commands_row.setContentsMargins(0, 0, 0, 0)
        option_commands_row.addWidget(QLabel("commands"))
        self._option_commands_summary = QLabel("none")
        option_commands_row.addWidget(self._option_commands_summary, 1)
        self._option_commands_button = QPushButton("Edit...")
        self._option_commands_button.setAutoDefault(False)
        self._option_commands_button.setDefault(False)
        self._option_commands_button.clicked.connect(self._edit_option_commands)
        option_commands_row.addWidget(self._option_commands_button)
        option_layout.addLayout(option_commands_row)
        self._option_end_dialogue_checkbox = QCheckBox("End dialogue on this option")
        self._option_end_dialogue_checkbox.stateChanged.connect(
            self._on_option_end_dialogue_changed
        )
        option_layout.addWidget(self._option_end_dialogue_checkbox)
        self._option_end_dialogue_note = QLabel("")
        self._option_end_dialogue_note.setWordWrap(True)
        self._option_end_dialogue_note.setStyleSheet("color: #8a4b00;")
        option_layout.addWidget(self._option_end_dialogue_note)
        branch_row = QHBoxLayout()
        branch_row.setContentsMargins(0, 0, 0, 0)
        branch_row.addWidget(QLabel("branch"))
        self._option_branch_summary_label = QLabel("This option continues in the current dialogue.")
        self._option_branch_summary_label.setWordWrap(True)
        branch_row.addWidget(self._option_branch_summary_label, 1)
        option_layout.addLayout(branch_row)
        self._option_branch_stack = QStackedWidget()
        option_layout.addWidget(self._option_branch_stack)
        none_branch_page = QWidget()
        none_branch_layout = QVBoxLayout(none_branch_page)
        none_branch_layout.setContentsMargins(0, 0, 0, 0)
        self._option_branch_none_label = QLabel("This option continues in the current dialogue.")
        self._option_branch_none_label.setWordWrap(True)
        none_branch_layout.addWidget(self._option_branch_none_label)
        none_branch_buttons = QHBoxLayout()
        self._add_inline_branch_button = QPushButton("Add Inline Dialogue")
        self._add_inline_branch_button.setAutoDefault(False)
        self._add_inline_branch_button.setDefault(False)
        self._add_inline_branch_button.clicked.connect(self._on_add_inline_branch_from_detail)
        none_branch_buttons.addWidget(self._add_inline_branch_button)
        self._set_file_branch_button = QPushButton("Set Dialogue File")
        self._set_file_branch_button.setAutoDefault(False)
        self._set_file_branch_button.setDefault(False)
        self._set_file_branch_button.clicked.connect(self._on_add_file_branch_from_detail)
        none_branch_buttons.addWidget(self._set_file_branch_button)
        none_branch_buttons.addStretch(1)
        none_branch_layout.addLayout(none_branch_buttons)
        none_branch_layout.addStretch(1)
        self._option_branch_stack.addWidget(none_branch_page)
        inline_branch_page = QWidget()
        inline_branch_layout = QVBoxLayout(inline_branch_page)
        inline_branch_layout.setContentsMargins(0, 0, 0, 0)
        self._inline_branch_summary = QLabel("0 segments")
        self._inline_branch_summary.setWordWrap(True)
        inline_branch_layout.addWidget(self._inline_branch_summary)
        self._inline_branch_note = QLabel(
            "Select the inline child dialogue node in the tree to edit that branch."
        )
        self._inline_branch_note.setWordWrap(True)
        self._inline_branch_note.setStyleSheet("color: #666;")
        inline_branch_layout.addWidget(self._inline_branch_note)
        inline_branch_buttons = QHBoxLayout()
        self._select_inline_branch_button = QPushButton("Select Inline Dialogue")
        self._select_inline_branch_button.setAutoDefault(False)
        self._select_inline_branch_button.setDefault(False)
        self._select_inline_branch_button.clicked.connect(self._on_select_inline_branch)
        inline_branch_buttons.addWidget(self._select_inline_branch_button)
        self._clear_inline_branch_button = QPushButton("Clear Branch")
        self._clear_inline_branch_button.setAutoDefault(False)
        self._clear_inline_branch_button.setDefault(False)
        self._clear_inline_branch_button.clicked.connect(self._on_clear_option_branch_from_detail)
        inline_branch_buttons.addWidget(self._clear_inline_branch_button)
        inline_branch_buttons.addStretch(1)
        inline_branch_layout.addLayout(inline_branch_buttons)
        inline_branch_layout.addStretch(1)
        self._option_branch_stack.addWidget(inline_branch_page)
        file_branch_page = QWidget()
        file_branch_layout = QVBoxLayout(file_branch_page)
        file_branch_layout.setContentsMargins(0, 0, 0, 0)
        self._file_branch_summary = QLabel("No dialogue file selected.")
        self._file_branch_summary.setWordWrap(True)
        file_branch_layout.addWidget(self._file_branch_summary)
        self._file_branch_note = QLabel(
            "Select the dialogue-file node in the tree to edit the shared reference."
        )
        self._file_branch_note.setWordWrap(True)
        self._file_branch_note.setStyleSheet("color: #666;")
        file_branch_layout.addWidget(self._file_branch_note)
        file_branch_buttons = QHBoxLayout()
        self._select_file_branch_button = QPushButton("Select Dialogue File")
        self._select_file_branch_button.setAutoDefault(False)
        self._select_file_branch_button.setDefault(False)
        self._select_file_branch_button.clicked.connect(self._on_select_file_branch)
        file_branch_buttons.addWidget(self._select_file_branch_button)
        self._clear_file_branch_from_option_button = QPushButton("Clear Branch")
        self._clear_file_branch_from_option_button.setAutoDefault(False)
        self._clear_file_branch_from_option_button.setDefault(False)
        self._clear_file_branch_from_option_button.clicked.connect(self._on_clear_option_branch_from_detail)
        file_branch_buttons.addWidget(self._clear_file_branch_from_option_button)
        file_branch_buttons.addStretch(1)
        file_branch_layout.addLayout(file_branch_buttons)
        file_branch_layout.addStretch(1)
        self._option_branch_stack.addWidget(file_branch_page)
        option_layout.addStretch(1)
        self._detail_stack.addWidget(self._option_page)

        self._file_branch_page = QWidget()
        file_layout = QVBoxLayout(self._file_branch_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self._file_branch_warning = QLabel(
            "This is a shared dialogue-file reference. Changing the path here changes which file "
            "this option points to, but it does not localize the file's contents. "
            "When this is converted to an inline copy later, that copy should be treated as shallow."
        )
        self._file_branch_warning.setWordWrap(True)
        self._file_branch_warning.setStyleSheet("color: #666;")
        file_layout.addWidget(self._file_branch_warning)
        file_form = QFormLayout()
        file_row = QWidget()
        file_row_layout = QHBoxLayout(file_row)
        file_row_layout.setContentsMargins(0, 0, 0, 0)
        self._file_branch_path_edit = QLineEdit()
        self._file_branch_path_browse = QPushButton("Browse...")
        self._file_branch_path_browse.setAutoDefault(False)
        self._file_branch_path_browse.setDefault(False)
        self._file_branch_path_browse.clicked.connect(self._on_browse_file_branch_path)
        file_row_layout.addWidget(self._file_branch_path_edit, 1)
        file_row_layout.addWidget(self._file_branch_path_browse)
        file_form.addRow("dialogue_path", file_row)
        file_layout.addLayout(file_form)
        file_actions = QHBoxLayout()
        self._file_branch_clear_button = QPushButton("Clear Branch")
        self._file_branch_clear_button.setAutoDefault(False)
        self._file_branch_clear_button.setDefault(False)
        self._file_branch_clear_button.clicked.connect(self._on_clear_file_branch)
        file_actions.addWidget(self._file_branch_clear_button)
        file_actions.addStretch(1)
        file_layout.addLayout(file_actions)
        file_layout.addStretch(1)
        self._detail_stack.addWidget(self._file_branch_page)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 580])

        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu_requested)

    def load_definition(self, definition: object) -> None:
        self._definition = _ensure_dialogue_definition(definition)
        self._last_valid_key = None
        self._refresh_tree(select_key=_dialogue_key(()))

    def definition(self) -> dict[str, Any]:
        if not self._commit_current_selection(show_message=True):
            raise ValueError("Dialogue definition has invalid fields.")
        return copy.deepcopy(self._definition)

    def _segments_for_dialogue(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
    ) -> list[dict[str, Any]]:
        dialogue = self._dialogue_at_path(dialogue_path)
        if dialogue is None:
            return []
        raw_segments = dialogue.get("segments")
        if not isinstance(raw_segments, list):
            raw_segments = []
            dialogue["segments"] = raw_segments
        return raw_segments

    def _dialogue_at_path(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
    ) -> dict[str, Any] | None:
        dialogue = self._definition
        for segment_index, option_index in dialogue_path:
            segments = dialogue.get("segments")
            if (
                not isinstance(segments, list)
                or segment_index < 0
                or segment_index >= len(segments)
                or not isinstance(segments[segment_index], dict)
            ):
                return None
            segment = segments[segment_index]
            raw_options = segment.get("options")
            if (
                not isinstance(raw_options, list)
                or option_index < 0
                or option_index >= len(raw_options)
                or not isinstance(raw_options[option_index], dict)
            ):
                return None
            option = raw_options[option_index]
            next_definition = option.get("next_dialogue_definition")
            if not isinstance(next_definition, dict):
                return None
            if not isinstance(next_definition.get("segments"), list):
                next_definition["segments"] = []
            dialogue = next_definition
        return dialogue

    def _segment_at_key(self, key: tuple[object, ...] | None) -> dict[str, Any] | None:
        if _node_kind(key) != "segment" or not isinstance(key, tuple) or len(key) < 3:
            return None
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        if not isinstance(segment_index, int):
            return None
        segments = self._segments_for_dialogue(dialogue_path)
        if segment_index < 0 or segment_index >= len(segments):
            return None
        segment = segments[segment_index]
        return segment if isinstance(segment, dict) else None

    def _option_at_key(self, key: tuple[object, ...] | None) -> dict[str, Any] | None:
        if _node_kind(key) not in {"option", "file_branch"} or not isinstance(key, tuple) or len(key) < 4:
            return None
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        option_index = key[3]
        if not isinstance(segment_index, int) or not isinstance(option_index, int):
            return None
        segment = self._segment_at_key(_segment_key(dialogue_path, segment_index))
        if not isinstance(segment, dict):
            return None
        raw_options = segment.get("options")
        if not isinstance(raw_options, list):
            raw_options = []
            segment["options"] = raw_options
        if option_index < 0 or option_index >= len(raw_options):
            return None
        option = raw_options[option_index]
        return option if isinstance(option, dict) else None

    def _segment_end_dialogue_enabled(self, segment: dict[str, Any] | None) -> bool:
        return isinstance(segment, dict) and segment.get("end_dialogue") is True

    def _option_end_dialogue_enabled(self, option: dict[str, Any] | None) -> bool:
        return isinstance(option, dict) and option.get("end_dialogue") is True

    def _current_key(self) -> tuple[object, ...] | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        key = item.data(0, Qt.ItemDataRole.UserRole)
        return key if isinstance(key, tuple) else None

    def _current_dialogue_key(self) -> tuple[object, ...] | None:
        key = self._current_key()
        kind = _node_kind(key)
        if kind == "dialogue":
            return key
        if kind in {"segment", "option", "file_branch"}:
            return _dialogue_key(_dialogue_path_from_key(key))
        return None

    def _commit_current_selection(self, *, show_message: bool) -> bool:
        key = self._last_valid_key
        kind = _node_kind(key)
        if kind == "segment":
            return self._commit_segment(key, show_message=show_message)
        if kind == "option":
            return self._commit_option(key, show_message=show_message)
        if kind == "file_branch":
            return self._commit_file_branch(key, show_message=show_message)
        return True

    def _commit_segment(self, key: tuple[object, ...], *, show_message: bool) -> bool:
        _ = show_message
        segment = self._segment_at_key(key)
        if segment is None:
            return True
        raw_type = str(segment.get("type", "text")).strip() or "text"
        if raw_type not in {"text", "choice"}:
            segment["type"] = "text"
            raw_type = "text"
        raw_text = self._segment_text_edit.toPlainText()
        if raw_text:
            segment["text"] = raw_text
        else:
            segment.pop("text", None)
        if self._segment_end_dialogue_checkbox.isChecked():
            segment["end_dialogue"] = True
        else:
            segment.pop("end_dialogue", None)
        if raw_type != "choice":
            segment.pop("options", None)
        return True

    def _commit_option(self, key: tuple[object, ...], *, show_message: bool) -> bool:
        _ = show_message
        option = self._option_at_key(key)
        if option is None:
            return True
        option_id = self._option_id_edit.text().strip()
        if option_id:
            option["option_id"] = option_id
        else:
            option.pop("option_id", None)
        option_text = self._option_text_edit.toPlainText()
        if option_text:
            option["text"] = option_text
        else:
            option.pop("text", None)
        if self._option_end_dialogue_checkbox.isChecked():
            option["end_dialogue"] = True
        else:
            option.pop("end_dialogue", None)
        return True

    def _commit_file_branch(self, key: tuple[object, ...], *, show_message: bool) -> bool:
        _ = show_message
        option = self._option_at_key(key)
        if option is None:
            return True
        option.pop("next_dialogue_definition", None)
        option["next_dialogue_path"] = self._file_branch_path_edit.text().strip()
        return True

    def _refresh_tree(self, *, select_key: tuple[object, ...] | None = None) -> None:
        self._loading = True
        try:
            with QSignalBlocker(self._tree):
                self._tree.clear()
                root_key = _dialogue_key(())
                root_item = QTreeWidgetItem([_dialogue_tree_label((), self._definition)])
                root_item.setData(0, Qt.ItemDataRole.UserRole, root_key)
                _decorate_tree_item(root_item, bold=True)
                root_item.setExpanded(True)
                self._populate_dialogue_children(root_item, ())
                self._tree.addTopLevelItem(root_item)
                self._tree.expandAll()
                target_key = root_key if select_key is None else select_key
                target_item = self._find_tree_item(target_key)
                if target_item is not None:
                    self._tree.setCurrentItem(target_item)
                else:
                    self._tree.setCurrentItem(root_item)
        finally:
            self._loading = False
        self._load_selected_detail()

    def _populate_dialogue_children(
        self,
        parent_item: QTreeWidgetItem,
        dialogue_path: tuple[tuple[int, int], ...],
        *,
        inherited_unreachable: bool = False,
    ) -> None:
        segments = self._segments_for_dialogue(dialogue_path)
        later_segments_unreachable = inherited_unreachable
        for segment_index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            segment_terminal = self._segment_end_dialogue_enabled(segment)
            segment_unreachable = later_segments_unreachable
            segment_label = _tree_label_with_state(
                _segment_summary(segment, segment_index),
                terminal=segment_terminal,
                unreachable=segment_unreachable,
            )
            segment_item = QTreeWidgetItem([segment_label])
            segment_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                _segment_key(dialogue_path, segment_index),
            )
            segment_tooltip = None
            if segment_terminal:
                segment_tooltip = "This segment ends the dialogue after it finishes."
            if segment_unreachable:
                segment_tooltip = (
                    "This segment will not run because an earlier segment in this dialogue ends the dialogue."
                )
            _decorate_tree_item(
                segment_item,
                bold=str(segment.get("type", "text")).strip() == "choice",
                terminal=segment_terminal,
                unreachable=segment_unreachable,
                tooltip=segment_tooltip,
            )
            parent_item.addChild(segment_item)
            if str(segment.get("type", "text")).strip() != "choice":
                later_segments_unreachable = later_segments_unreachable or segment_terminal
                continue
            raw_options = segment.get("options")
            if not isinstance(raw_options, list):
                later_segments_unreachable = later_segments_unreachable or segment_terminal
                continue
            for option_index, option in enumerate(raw_options):
                if not isinstance(option, dict):
                    continue
                option_terminal = self._option_end_dialogue_enabled(option)
                option_unreachable = segment_unreachable
                option_label = _tree_label_with_state(
                    _option_summary(option, option_index),
                    terminal=option_terminal,
                    unreachable=option_unreachable,
                )
                option_item = QTreeWidgetItem([option_label])
                option_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    _option_key(dialogue_path, segment_index, option_index),
                )
                option_tooltip = None
                if option_terminal:
                    option_tooltip = "This option ends the dialogue after its commands run."
                if option_unreachable:
                    option_tooltip = (
                        "This option will not run because its parent segment is currently unreachable."
                    )
                _decorate_tree_item(
                    option_item,
                    terminal=option_terminal,
                    unreachable=option_unreachable,
                    tooltip=option_tooltip,
                )
                segment_item.addChild(option_item)
                next_definition = option.get("next_dialogue_definition")
                if isinstance(next_definition, dict):
                    child_dialogue_path = dialogue_path + ((segment_index, option_index),)
                    child_unreachable = option_unreachable or option_terminal
                    child_item = QTreeWidgetItem(
                        [
                            _tree_label_with_state(
                                _dialogue_tree_label(child_dialogue_path, next_definition),
                                unreachable=child_unreachable,
                            )
                        ]
                    )
                    child_item.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        _dialogue_key(child_dialogue_path),
                    )
                    child_tooltip = None
                    if child_unreachable:
                        child_tooltip = (
                            "This child dialogue will not run while its parent option ends the dialogue."
                            if option_terminal and not option_unreachable
                            else "This child dialogue is currently unreachable."
                        )
                    _decorate_tree_item(
                        child_item,
                        italic=True,
                        unreachable=child_unreachable,
                        tooltip=child_tooltip,
                    )
                    option_item.addChild(child_item)
                    self._populate_dialogue_children(
                        child_item,
                        child_dialogue_path,
                        inherited_unreachable=child_unreachable,
                    )
                    continue
                if "next_dialogue_path" in option or bool(str(option.get("next_dialogue_path", "")).strip()):
                    dialogue_path_text = str(option.get("next_dialogue_path", "")).strip() or "(unset)"
                    child_unreachable = option_unreachable or option_terminal
                    file_item = QTreeWidgetItem(
                        [
                            _tree_label_with_state(
                                f"Dialogue File: {dialogue_path_text}",
                                unreachable=child_unreachable,
                            )
                        ]
                    )
                    file_item.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        _file_branch_key(dialogue_path, segment_index, option_index),
                    )
                    file_tooltip = (
                        "This file-backed child dialogue will not run while its parent option ends the dialogue."
                        if child_unreachable
                        else "This is a shared dialogue-file reference."
                    )
                    _decorate_tree_item(
                        file_item,
                        italic=True,
                        unreachable=child_unreachable,
                        tooltip=file_tooltip,
                    )
                    option_item.addChild(file_item)
            later_segments_unreachable = later_segments_unreachable or segment_terminal

    def _find_tree_item(self, key: tuple[object, ...]) -> QTreeWidgetItem | None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                return item
            for index in range(item.childCount()):
                found = walk(item.child(index))
                if found is not None:
                    return found
            return None
        for top_index in range(self._tree.topLevelItemCount()):
            top_item = self._tree.topLevelItem(top_index)
            if top_item is None:
                continue
            found = walk(top_item)
            if found is not None:
                return found
        return None

    def _load_selected_detail(self) -> None:
        key = self._current_key()
        kind = _node_kind(key)
        self._loading = True
        try:
            if kind == "dialogue":
                self._load_dialogue_detail(key)
                return
            if kind == "segment":
                self._load_segment_detail(key)
                return
            if kind == "option":
                self._load_option_detail(key)
                return
            if kind == "file_branch":
                self._load_file_branch_detail(key)
                return
            self._detail_header.setText("No item selected")
            self._detail_stack.setCurrentWidget(self._empty_page)
        finally:
            self._loading = False

    def _load_dialogue_detail(self, key: tuple[object, ...]) -> None:
        dialogue_path = _dialogue_path_from_key(key)
        dialogue = self._dialogue_at_path(dialogue_path) or {"segments": []}
        self._detail_header.setText("Dialogue")
        self._dialogue_title_label.setText(
            "Main Dialogue" if not dialogue_path else "Inline Dialogue"
        )
        self._dialogue_summary_label.setText(summarize_dialogue_definition(dialogue))
        self._detail_stack.setCurrentWidget(self._dialogue_page)

    def _load_segment_detail(self, key: tuple[object, ...]) -> None:
        segment = self._segment_at_key(key)
        if segment is None:
            self._detail_header.setText("Missing Segment")
            self._detail_stack.setCurrentWidget(self._empty_page)
            return
        self._detail_header.setText("Segment")
        segment_type = str(segment.get("type", "text")).strip() or "text"
        self._segment_type_label.setText(segment_type)
        self._segment_text_edit.setPlainText(
            "" if segment.get("text") is None else str(segment.get("text", ""))
        )
        with QSignalBlocker(self._segment_end_dialogue_checkbox):
            self._segment_end_dialogue_checkbox.setChecked(
                self._segment_end_dialogue_enabled(segment)
            )
        self._sync_segment_command_buttons(segment)
        is_choice = segment_type == "choice"
        if self._segment_end_dialogue_enabled(segment):
            if is_choice:
                self._segment_end_dialogue_note.setText(
                    "This choice segment still runs the selected option path first, then closes the dialogue. "
                    "Later sibling segments in this dialogue are currently unreachable."
                )
            else:
                self._segment_end_dialogue_note.setText(
                    "Later sibling segments in this dialogue are currently unreachable."
                )
        else:
            self._segment_end_dialogue_note.setText("")
        self._segment_choice_note.setText(
            "This choice segment owns options in the tree below it."
            if is_choice
            else "This segment has no child options."
        )
        self._segment_add_option_button.setVisible(is_choice)
        self._detail_stack.setCurrentWidget(self._segment_page)

    def _load_option_detail(self, key: tuple[object, ...]) -> None:
        option = self._option_at_key(key)
        if option is None:
            self._detail_header.setText("Missing Option")
            self._detail_stack.setCurrentWidget(self._empty_page)
            return
        self._detail_header.setText("Option")
        self._option_id_edit.setText(str(option.get("option_id", "")))
        self._option_text_edit.setPlainText(
            "" if option.get("text") is None else str(option.get("text", ""))
        )
        option_ends_dialogue = self._option_end_dialogue_enabled(option)
        with QSignalBlocker(self._option_end_dialogue_checkbox):
            self._option_end_dialogue_checkbox.setChecked(option_ends_dialogue)
        self._sync_option_command_button(option)
        branch_mode = self._branch_mode_for_option(option)
        if branch_mode == "Inline Dialogue":
            child_definition = option.get("next_dialogue_definition")
            branch_summary = summarize_dialogue_definition(
                child_definition if isinstance(child_definition, dict) else {"segments": []}
            )
            self._option_branch_summary_label.setText(
                f"Inline child dialogue: {branch_summary}"
                + (" (currently unreachable)" if option_ends_dialogue else "")
            )
            self._inline_branch_summary.setText(
                branch_summary
            )
            self._option_branch_stack.setCurrentIndex(1)
        elif branch_mode == "Dialogue File":
            dialogue_path = str(option.get("next_dialogue_path", "")).strip()
            self._option_branch_summary_label.setText(
                (
                    f"Dialogue file: {dialogue_path}"
                    if dialogue_path
                    else "Dialogue file: (unset)"
                )
                + (" (currently unreachable)" if option_ends_dialogue else "")
            )
            self._file_branch_summary.setText(
                f"Shared dialogue file: {dialogue_path}" if dialogue_path else "Shared dialogue file: (unset)"
            )
            self._option_branch_stack.setCurrentIndex(2)
        else:
            self._option_branch_summary_label.setText("This option continues in the current dialogue.")
            self._option_branch_stack.setCurrentIndex(0)
        if option_ends_dialogue:
            self._option_end_dialogue_note.setText(
                "This option closes the dialogue after its commands run. Any child branch under it is currently unreachable."
                if branch_mode != "Continue"
                else "This option closes the dialogue after its commands run."
            )
        else:
            self._option_end_dialogue_note.setText("")
        self._detail_stack.setCurrentWidget(self._option_page)

    def _load_file_branch_detail(self, key: tuple[object, ...]) -> None:
        option = self._option_at_key(key)
        if option is None:
            self._detail_header.setText("Missing Dialogue File")
            self._detail_stack.setCurrentWidget(self._empty_page)
            return
        self._detail_header.setText("Dialogue File Reference")
        self._file_branch_path_edit.setText(str(option.get("next_dialogue_path", "")))
        if self._option_end_dialogue_enabled(option):
            self._file_branch_warning.setText(
                "This is a shared dialogue-file reference, but it is currently unreachable because the parent option ends the dialogue. "
                "When this is converted to an inline copy later, that copy should be treated as shallow."
            )
        else:
            self._file_branch_warning.setText(
                "This is a shared dialogue-file reference. Changing the path here changes which file "
                "this option points to, but it does not localize the file's contents. "
                "When this is converted to an inline copy later, that copy should be treated as shallow."
            )
        self._detail_stack.setCurrentWidget(self._file_branch_page)

    def _sync_segment_command_buttons(self, segment: dict[str, Any] | None) -> None:
        self._segment_on_start_summary.setText(
            summarize_command_list(None if segment is None else segment.get("on_start"))
        )
        self._segment_on_end_summary.setText(
            summarize_command_list(None if segment is None else segment.get("on_end"))
        )
        enabled = segment is not None
        self._segment_on_start_button.setEnabled(enabled)
        self._segment_on_end_button.setEnabled(enabled)

    def _sync_option_command_button(self, option: dict[str, Any] | None) -> None:
        self._option_commands_summary.setText(
            summarize_command_list(None if option is None else option.get("commands"))
        )
        self._option_commands_button.setEnabled(option is not None)

    def _open_command_list_dialog(
        self,
        title: str,
        commands: object,
    ) -> list[dict[str, Any]] | None:
        dialog = CommandListDialog(
            self,
            entity_picker=self._entity_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            suggested_command_names=_DIALOGUE_SUGGESTED_COMMAND_NAMES,
            current_entity_id=self._current_entity_id,
        )
        dialog.setWindowTitle(title)
        dialog.load_commands(commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.commands()

    def _edit_segment_commands(self, field_name: str) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        key = self._current_key()
        segment = self._segment_at_key(key)
        if segment is None:
            return
        updated = self._open_command_list_dialog(
            f"Edit Segment {field_name}",
            segment.get(field_name),
        )
        if updated is None:
            return
        if updated:
            segment[field_name] = copy.deepcopy(updated)
        else:
            segment.pop(field_name, None)
        self._sync_segment_command_buttons(segment)
        self._refresh_tree(select_key=key)

    def _edit_option_commands(self) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        key = self._current_key()
        option = self._option_at_key(key)
        if option is None:
            return
        updated = self._open_command_list_dialog(
            "Edit Option Commands",
            option.get("commands"),
        )
        if updated is None:
            return
        if updated:
            option["commands"] = copy.deepcopy(updated)
        else:
            option.pop("commands", None)
        self._sync_option_command_button(option)
        self._refresh_tree(select_key=key)

    def _on_tree_selection_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if self._loading:
            return
        if not self._commit_current_selection(show_message=False):
            if self._last_valid_key is not None:
                self._loading = True
                try:
                    with QSignalBlocker(self._tree):
                        target_item = self._find_tree_item(self._last_valid_key)
                        if target_item is not None:
                            self._tree.setCurrentItem(target_item)
                finally:
                    self._loading = False
            return
        key = None if current is None else current.data(0, Qt.ItemDataRole.UserRole)
        self._last_valid_key = key if isinstance(key, tuple) else None
        self._refresh_tree(select_key=self._last_valid_key)

    def _insert_segment(
        self,
        segment: dict[str, Any],
        *,
        dialogue_path: tuple[tuple[int, int], ...] | None = None,
        after_row: int | None = None,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        target_dialogue_path = (
            self._current_dialogue_path()
            if dialogue_path is None
            else dialogue_path
        )
        segments = self._segments_for_dialogue(target_dialogue_path)
        if after_row is None or after_row < 0 or after_row >= len(segments):
            insert_row = len(segments)
        else:
            insert_row = after_row + 1
        segments.insert(insert_row, copy.deepcopy(segment))
        target_key = _segment_key(target_dialogue_path, insert_row)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _insert_text_segment(self, *, after_row: int | None = None) -> None:
        self._insert_segment(
            {"type": "text", "text": "New text segment"},
            after_row=after_row,
        )

    def _insert_choice_segment(self, *, after_row: int | None = None) -> None:
        self._insert_segment(
            {
                "type": "choice",
                "text": "New choice prompt",
                "options": [
                    {
                        "option_id": "option_1",
                        "text": "Option 1",
                    }
                ],
            },
            after_row=after_row,
        )

    def _delete_segment_at(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        row: int,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        segments = self._segments_for_dialogue(dialogue_path)
        if row < 0 or row >= len(segments):
            return
        del segments[row]
        target_key = _dialogue_key(dialogue_path)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _insert_option(
        self,
        *,
        dialogue_path: tuple[tuple[int, int], ...] | None = None,
        segment_index: int | None = None,
        after_row: int | None = None,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        resolved_dialogue_path = (
            self._current_dialogue_path()
            if dialogue_path is None
            else dialogue_path
        )
        resolved_segment_index = (
            self._current_choice_segment_index()
            if segment_index is None
            else segment_index
        )
        if resolved_segment_index is None:
            return
        segment = self._segment_at_key(_segment_key(resolved_dialogue_path, resolved_segment_index))
        if segment is None or str(segment.get("type", "text")).strip() != "choice":
            return
        raw_options = segment.get("options")
        if not isinstance(raw_options, list):
            raw_options = []
            segment["options"] = raw_options
        options = raw_options
        option_number = len(options) + 1
        option = {
            "option_id": f"option_{option_number}",
            "text": f"Option {option_number}",
        }
        if after_row is None or after_row < 0 or after_row >= len(options):
            insert_row = len(options)
        else:
            insert_row = after_row + 1
        options.insert(insert_row, option)
        target_key = _option_key(resolved_dialogue_path, resolved_segment_index, insert_row)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _delete_option_at(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        segment_index: int,
        row: int,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        segment = self._segment_at_key(_segment_key(dialogue_path, segment_index))
        if segment is None:
            return
        options = segment.get("options")
        if not isinstance(options, list):
            return
        if row < 0 or row >= len(options):
            return
        del options[row]
        target_key = _segment_key(dialogue_path, segment_index)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _move_segment(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        row: int,
        delta: int,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        segments = self._segments_for_dialogue(dialogue_path)
        target = row + delta
        if row < 0 or target < 0 or row >= len(segments) or target >= len(segments):
            return
        segments[row], segments[target] = segments[target], segments[row]
        target_key = _segment_key(dialogue_path, target)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _move_option(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        segment_index: int,
        row: int,
        delta: int,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        segment = self._segment_at_key(_segment_key(dialogue_path, segment_index))
        if segment is None:
            return
        options = segment.get("options")
        if not isinstance(options, list):
            return
        target = row + delta
        if row < 0 or target < 0 or row >= len(options) or target >= len(options):
            return
        options[row], options[target] = options[target], options[row]
        target_key = _option_key(dialogue_path, segment_index, target)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _on_tree_context_menu_requested(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is not None and item is not self._tree.currentItem():
            self._tree.setCurrentItem(item)
            item = self._tree.currentItem()
        key = None if item is None else item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(key, tuple):
            key = _dialogue_key(())
        kind = _node_kind(key)
        dialogue_path = _dialogue_path_from_key(key)
        menu = QMenu(self)
        if kind == "dialogue":
            add_text_action = menu.addAction("Add Text Segment")
            add_choice_action = menu.addAction("Add Choice Segment")
            delete_branch_action = None
            if dialogue_path:
                menu.addSeparator()
                delete_branch_action = menu.addAction("Delete Inline Dialogue")
            chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
            if chosen == add_text_action:
                self._insert_text_segment(after_row=None)
            elif chosen == add_choice_action:
                self._insert_choice_segment(after_row=None)
            elif delete_branch_action is not None and chosen == delete_branch_action:
                self._delete_inline_dialogue(dialogue_path)
            return
        if kind == "segment" and isinstance(key[2], int):
            segment_index = key[2]
            add_text_action = menu.addAction("Add Text After")
            add_choice_action = menu.addAction("Add Choice After")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            segment = self._segment_at_key(key)
            add_option_action = None
            if isinstance(segment, dict) and str(segment.get("type", "text")).strip() == "choice":
                menu.addSeparator()
                add_option_action = menu.addAction("Add Option")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
            if chosen == add_text_action:
                self._insert_text_segment(after_row=segment_index)
            elif chosen == add_choice_action:
                self._insert_choice_segment(after_row=segment_index)
            elif chosen == move_up_action:
                self._move_segment(dialogue_path, segment_index, -1)
            elif chosen == move_down_action:
                self._move_segment(dialogue_path, segment_index, 1)
            elif add_option_action is not None and chosen == add_option_action:
                self._insert_option(dialogue_path=dialogue_path, segment_index=segment_index)
            elif chosen == delete_action:
                self._delete_segment_at(dialogue_path, segment_index)
            return
        if kind == "option" and isinstance(key[2], int) and isinstance(key[3], int):
            segment_index = key[2]
            option_index = key[3]
            add_option_action = menu.addAction("Add Option After")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            menu.addSeparator()
            set_inline_action = menu.addAction("Set Inline Dialogue")
            set_file_action = menu.addAction("Set Dialogue File")
            clear_branch_action = menu.addAction("Clear Branch")
            menu.addSeparator()
            delete_action = menu.addAction("Delete Option")
            chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
            if chosen == add_option_action:
                self._insert_option(
                    dialogue_path=dialogue_path,
                    segment_index=segment_index,
                    after_row=option_index,
                )
            elif chosen == move_up_action:
                self._move_option(dialogue_path, segment_index, option_index, -1)
            elif chosen == move_down_action:
                self._move_option(dialogue_path, segment_index, option_index, 1)
            elif chosen == set_inline_action:
                self._set_option_branch_inline(dialogue_path, segment_index, option_index, select_branch=True)
            elif chosen == set_file_action:
                self._set_option_branch_file(dialogue_path, segment_index, option_index, browse=True)
            elif chosen == clear_branch_action:
                self._clear_option_branch(dialogue_path, segment_index, option_index)
            elif chosen == delete_action:
                self._delete_option_at(dialogue_path, segment_index, option_index)
            return
        if kind == "file_branch" and isinstance(key[2], int) and isinstance(key[3], int):
            segment_index = key[2]
            option_index = key[3]
            browse_action = menu.addAction("Replace Dialogue File")
            clear_action = menu.addAction("Clear Branch")
            chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
            if chosen == browse_action:
                self._set_option_branch_file(dialogue_path, segment_index, option_index, browse=True, select_branch=True)
            elif chosen == clear_action:
                self._clear_option_branch(dialogue_path, segment_index, option_index)

    def _delete_inline_dialogue(self, dialogue_path: tuple[tuple[int, int], ...]) -> None:
        if not dialogue_path:
            return
        parent_dialogue_path = dialogue_path[:-1]
        segment_index, option_index = dialogue_path[-1]
        option = self._option_at_key(_option_key(parent_dialogue_path, segment_index, option_index))
        if option is None:
            return
        option.pop("next_dialogue_definition", None)
        parent_key = _option_key(parent_dialogue_path, segment_index, option_index)
        self._last_valid_key = parent_key
        self._refresh_tree(select_key=parent_key)

    def _set_option_branch_inline(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        segment_index: int,
        option_index: int,
        *,
        select_branch: bool = False,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        option = self._option_at_key(_option_key(dialogue_path, segment_index, option_index))
        if option is None:
            return
        if not isinstance(option.get("next_dialogue_definition"), dict):
            option["next_dialogue_definition"] = {"segments": []}
        elif not isinstance(option["next_dialogue_definition"].get("segments"), list):
            option["next_dialogue_definition"]["segments"] = []
        option.pop("next_dialogue_path", None)
        target_key = (
            _dialogue_key(dialogue_path + ((segment_index, option_index),))
            if select_branch
            else _option_key(dialogue_path, segment_index, option_index)
        )
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _set_option_branch_file(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        segment_index: int,
        option_index: int,
        *,
        browse: bool = False,
        select_branch: bool = False,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        option = self._option_at_key(_option_key(dialogue_path, segment_index, option_index))
        if option is None:
            return
        option.pop("next_dialogue_definition", None)
        current_path = str(option.get("next_dialogue_path", "")).strip()
        if browse and self._dialogue_picker is not None:
            selected = self._dialogue_picker(current_path)
            if selected is not None:
                current_path = selected
        option["next_dialogue_path"] = current_path
        target_key = (
            _file_branch_key(dialogue_path, segment_index, option_index)
            if select_branch or "next_dialogue_path" in option
            else _option_key(dialogue_path, segment_index, option_index)
        )
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _clear_option_branch(
        self,
        dialogue_path: tuple[tuple[int, int], ...],
        segment_index: int,
        option_index: int,
    ) -> None:
        if not self._commit_current_selection(show_message=True):
            return
        option = self._option_at_key(_option_key(dialogue_path, segment_index, option_index))
        if option is None:
            return
        option.pop("next_dialogue_definition", None)
        option.pop("next_dialogue_path", None)
        target_key = _option_key(dialogue_path, segment_index, option_index)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _branch_mode_for_option(self, option: dict[str, Any] | None) -> str:
        if not isinstance(option, dict):
            return "Continue"
        if isinstance(option.get("next_dialogue_definition"), dict):
            return "Inline Dialogue"
        if "next_dialogue_path" in option or bool(str(option.get("next_dialogue_path", "")).strip()):
            return "Dialogue File"
        return "Continue"

    def _current_dialogue_path(self) -> tuple[tuple[int, int], ...]:
        key = self._current_dialogue_key()
        return _dialogue_path_from_key(key)

    def _current_choice_segment_index(self) -> int | None:
        key = self._current_key()
        kind = _node_kind(key)
        if kind == "segment" and isinstance(key[2], int):
            segment = self._segment_at_key(key)
            if isinstance(segment, dict) and str(segment.get("type", "text")).strip() == "choice":
                return key[2]
            return None
        if kind in {"option", "file_branch"} and isinstance(key[2], int):
            return key[2]
        return None

    def _current_option_coordinates(self) -> tuple[tuple[tuple[int, int], ...], int, int] | None:
        key = self._current_key()
        if _node_kind(key) not in {"option", "file_branch"} or not isinstance(key, tuple):
            return None
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        option_index = key[3]
        if not isinstance(segment_index, int) or not isinstance(option_index, int):
            return None
        return dialogue_path, segment_index, option_index

    def _on_add_text_for_selected_dialogue(self) -> None:
        self._insert_text_segment()

    def _on_add_choice_for_selected_dialogue(self) -> None:
        self._insert_choice_segment()

    def _on_add_option_for_selected_choice(self) -> None:
        self._insert_option()

    def _on_segment_end_dialogue_changed(self) -> None:
        if self._loading:
            return
        key = self._current_key()
        if _node_kind(key) != "segment" or not isinstance(key, tuple):
            return
        segment = self._segment_at_key(key)
        if segment is None:
            return
        if self._segment_end_dialogue_checkbox.isChecked():
            segment["end_dialogue"] = True
        else:
            segment.pop("end_dialogue", None)
        self._last_valid_key = key
        self._refresh_tree(select_key=key)

    def _on_option_end_dialogue_changed(self) -> None:
        if self._loading:
            return
        key = self._current_key()
        option = self._option_at_key(key)
        if option is None:
            return
        if self._option_end_dialogue_checkbox.isChecked():
            option["end_dialogue"] = True
        else:
            option.pop("end_dialogue", None)
        if isinstance(key, tuple):
            self._last_valid_key = key
            self._refresh_tree(select_key=key)

    def _on_add_inline_branch_from_detail(self) -> None:
        coordinates = self._current_option_coordinates()
        if coordinates is None:
            return
        dialogue_path, segment_index, option_index = coordinates
        self._set_option_branch_inline(dialogue_path, segment_index, option_index)

    def _on_add_file_branch_from_detail(self) -> None:
        coordinates = self._current_option_coordinates()
        if coordinates is None:
            return
        dialogue_path, segment_index, option_index = coordinates
        self._set_option_branch_file(dialogue_path, segment_index, option_index, browse=True)

    def _on_clear_option_branch_from_detail(self) -> None:
        coordinates = self._current_option_coordinates()
        if coordinates is None:
            return
        dialogue_path, segment_index, option_index = coordinates
        self._clear_option_branch(dialogue_path, segment_index, option_index)

    def _on_select_inline_branch(self) -> None:
        coordinates = self._current_option_coordinates()
        if coordinates is None:
            return
        dialogue_path, segment_index, option_index = coordinates
        target_key = _dialogue_key(dialogue_path + ((segment_index, option_index),))
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _on_select_file_branch(self) -> None:
        coordinates = self._current_option_coordinates()
        if coordinates is None:
            return
        dialogue_path, segment_index, option_index = coordinates
        target_key = _file_branch_key(dialogue_path, segment_index, option_index)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _on_browse_file_branch_path(self) -> None:
        key = self._current_key()
        if _node_kind(key) != "file_branch" or not isinstance(key, tuple):
            return
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        option_index = key[3]
        if not isinstance(segment_index, int) or not isinstance(option_index, int):
            return
        self._set_option_branch_file(
            dialogue_path,
            segment_index,
            option_index,
            browse=True,
            select_branch=True,
        )

    def _on_clear_file_branch(self) -> None:
        key = self._current_key()
        if _node_kind(key) != "file_branch" or not isinstance(key, tuple):
            return
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        option_index = key[3]
        if not isinstance(segment_index, int) or not isinstance(option_index, int):
            return
        self._clear_option_branch(dialogue_path, segment_index, option_index)

    def _on_segment_visual_order_changed(self, visual_order: list[int]) -> None:
        key = self._current_key()
        dialogue_key = self._current_dialogue_key()
        dialogue_path = _dialogue_path_from_key(dialogue_key)
        if not self._commit_current_selection(show_message=True):
            return
        segments = self._segments_for_dialogue(dialogue_path)
        if len(visual_order) != len(segments):
            return
        reordered = [segments[index] for index in visual_order if 0 <= index < len(segments)]
        if len(reordered) != len(segments):
            return
        segments[:] = reordered
        target_key = dialogue_key or _dialogue_key(dialogue_path)
        if _node_kind(key) == "segment" and isinstance(key, tuple) and isinstance(key[2], int):
            original_segment = None
            if 0 <= key[2] < len(reordered):
                original_segment = reordered[key[2]]
            if original_segment in segments:
                target_key = _segment_key(dialogue_path, segments.index(original_segment))
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)

    def _on_option_visual_order_changed(self, visual_order: list[int]) -> None:
        key = self._current_key()
        if not self._commit_current_selection(show_message=True):
            return
        if _node_kind(key) not in {"option", "file_branch"} or not isinstance(key, tuple):
            return
        dialogue_path = _dialogue_path_from_key(key)
        segment_index = key[2]
        if not isinstance(segment_index, int):
            return
        segment = self._segment_at_key(_segment_key(dialogue_path, segment_index))
        if segment is None:
            return
        options = segment.get("options")
        if not isinstance(options, list) or len(visual_order) != len(options):
            return
        reordered = [options[index] for index in visual_order if 0 <= index < len(options)]
        if len(reordered) != len(options):
            return
        options[:] = reordered
        target_key = _segment_key(dialogue_path, segment_index)
        self._last_valid_key = target_key
        self._refresh_tree(select_key=target_key)


class DialogueDefinitionDialog(QDialog):
    """Popup editor for one inline dialogue definition."""

    def __init__(
        self,
        parent=None,
        *,
        entity_picker=None,
        entity_dialogue_picker=None,
        dialogue_picker=None,
        command_picker=None,
        current_entity_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DialogueDefinitionDialog")
        self.setWindowTitle("Edit Dialogue")
        self.resize(900, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        self._structured_editor = _DialogueDefinitionStructuredEditor(
            entity_picker=entity_picker,
            entity_dialogue_picker=entity_dialogue_picker,
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
            current_entity_id=current_entity_id,
        )
        self._tabs.addTab(self._structured_editor, "Dialogue Editor")

        self._json_editor = QPlainTextEdit()
        self._json_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._json_editor.setFont(font)
        self._tabs.addTab(self._json_editor, "Dialogue JSON")

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._syncing_tabs = False
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._last_loaded_definition: dict[str, Any] = {"segments": []}

    def load_definition(self, definition: object) -> None:
        self._last_loaded_definition = _ensure_dialogue_definition(definition)
        self._structured_editor.load_definition(self._last_loaded_definition)
        self._json_editor.setPlainText(
            json.dumps(self._last_loaded_definition, indent=2, ensure_ascii=False)
        )
        self._tabs.setCurrentIndex(0)

    def definition(self) -> dict[str, Any]:
        if self._tabs.currentIndex() == 1:
            return self._definition_from_json_tab()
        return self._structured_editor.definition()

    def accept(self) -> None:  # noqa: D401
        try:
            self._last_loaded_definition = self.definition()
        except ValueError:
            return
        super().accept()

    def _definition_from_json_tab(self) -> dict[str, Any]:
        try:
            parsed = loads_json_data(
                self._json_editor.toPlainText(),
                source_name="Dialogue JSON",
            )
        except JsonDataDecodeError as exc:
            QMessageBox.warning(self, "Invalid Dialogue JSON", str(exc))
            raise ValueError("Invalid dialogue JSON") from exc
        if not isinstance(parsed, dict):
            QMessageBox.warning(
                self,
                "Invalid Dialogue JSON",
                "Dialogue JSON must be a JSON object.",
            )
            raise ValueError("Dialogue JSON must be an object.")
        segments = parsed.get("segments")
        if not isinstance(segments, list):
            QMessageBox.warning(
                self,
                "Invalid Dialogue JSON",
                "Dialogue JSON must include a 'segments' array.",
            )
            raise ValueError("Dialogue JSON missing segments array.")
        return copy.deepcopy(parsed)

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_tabs:
            return
        self._syncing_tabs = True
        try:
            if index == 1:
                try:
                    definition = self._structured_editor.definition()
                except ValueError:
                    self._tabs.setCurrentIndex(0)
                    return
                self._json_editor.setPlainText(
                    json.dumps(
                        definition,
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                try:
                    definition = self._definition_from_json_tab()
                except ValueError:
                    self._tabs.setCurrentIndex(1)
                    return
                self._structured_editor.load_definition(definition)
        finally:
            self._syncing_tabs = False


class EntityDialoguesDialog(QDialog):
    """Popup editor for an entity-owned map of named dialogues."""

    def __init__(
        self,
        parent=None,
        *,
        entity_picker=None,
        entity_dialogue_picker=None,
        dialogue_picker=None,
        command_picker=None,
        current_entity_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntityDialoguesDialog")
        self.setWindowTitle("Edit Entity Dialogues")
        self.resize(980, 680)

        self._entity_picker = entity_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._current_entity_id = current_entity_id
        self._dialogues: dict[str, dict[str, Any]] = {}
        self._active_dialogue: str | None = None
        self._rename_map: dict[str, str] = {}
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        note = QLabel(
            "Right-click dialogues to add, rename, mark active, or delete them. "
            "Drag to reorder them. "
            "Inline dialogues open in the regular dialogue editor; dialogue-file entries "
            "stay shared references."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        warning = QLabel(
            "Warning: dialogue order affects by-order helpers such as "
            "'step_entity_active_dialogue' and 'set_entity_active_dialogue_by_order'. "
            "If you reorder dialogues, those commands may target different entries."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #8a4b00;")
        outer.addWidget(warning)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Dialogues"))
        self._dialogue_list = _ReorderTreeWidget()
        self._dialogue_list.setHeaderHidden(True)
        self._dialogue_list.setMinimumWidth(300)
        left_layout.addWidget(self._dialogue_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._detail_header = QLabel("No dialogue selected")
        header_font = self._detail_header.font()
        header_font.setBold(True)
        self._detail_header.setFont(header_font)
        right_layout.addWidget(self._detail_header)

        self._detail_stack = QStackedWidget()
        right_layout.addWidget(self._detail_stack, 1)

        self._empty_page = QWidget()
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_label = QLabel("Select a named dialogue from the list.")
        empty_label.setWordWrap(True)
        empty_layout.addWidget(empty_label)
        empty_layout.addStretch(1)
        self._detail_stack.addWidget(self._empty_page)

        self._inline_page = QWidget()
        inline_layout = QVBoxLayout(self._inline_page)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        self._inline_summary_label = QLabel("Inline dialogue")
        self._inline_summary_label.setWordWrap(True)
        inline_layout.addWidget(self._inline_summary_label)
        self._inline_active_label = QLabel("")
        self._inline_active_label.setWordWrap(True)
        self._inline_active_label.setStyleSheet("color: #8a4b00;")
        inline_layout.addWidget(self._inline_active_label)
        self._inline_note_label = QLabel(
            "Use the existing dialogue editor for the selected named dialogue."
        )
        self._inline_note_label.setWordWrap(True)
        self._inline_note_label.setStyleSheet("color: #666;")
        inline_layout.addWidget(self._inline_note_label)
        inline_buttons = QHBoxLayout()
        self._edit_inline_button = QPushButton("Edit Dialogue...")
        self._edit_inline_button.setAutoDefault(False)
        self._edit_inline_button.setDefault(False)
        self._edit_inline_button.clicked.connect(self._on_edit_inline_dialogue)
        inline_buttons.addWidget(self._edit_inline_button)
        inline_buttons.addStretch(1)
        inline_layout.addLayout(inline_buttons)
        inline_layout.addStretch(1)
        self._detail_stack.addWidget(self._inline_page)

        self._file_page = QWidget()
        file_layout = QVBoxLayout(self._file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self._file_summary_label = QLabel("Dialogue file")
        self._file_summary_label.setWordWrap(True)
        file_layout.addWidget(self._file_summary_label)
        self._file_active_label = QLabel("")
        self._file_active_label.setWordWrap(True)
        self._file_active_label.setStyleSheet("color: #8a4b00;")
        file_layout.addWidget(self._file_active_label)
        self._file_note_label = QLabel(
            "This dialogue stays shared through its dialogue file path."
        )
        self._file_note_label.setWordWrap(True)
        self._file_note_label.setStyleSheet("color: #666;")
        file_layout.addWidget(self._file_note_label)
        file_form = QFormLayout()
        file_row = QWidget()
        file_row_layout = QHBoxLayout(file_row)
        file_row_layout.setContentsMargins(0, 0, 0, 0)
        self._dialogue_path_edit = QLineEdit()
        self._dialogue_path_edit.textChanged.connect(self._on_dialogue_path_text_changed)
        self._dialogue_path_browse = QPushButton("Browse...")
        self._dialogue_path_browse.setAutoDefault(False)
        self._dialogue_path_browse.setDefault(False)
        self._dialogue_path_browse.clicked.connect(self._on_browse_dialogue_path)
        self._dialogue_path_browse.setEnabled(self._dialogue_picker is not None)
        file_row_layout.addWidget(self._dialogue_path_edit, 1)
        file_row_layout.addWidget(self._dialogue_path_browse)
        file_form.addRow("dialogue_path", file_row)
        file_layout.addLayout(file_form)
        file_layout.addStretch(1)
        self._detail_stack.addWidget(self._file_page)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 620])

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._dialogue_list.currentItemChanged.connect(
            self._on_dialogue_selection_changed
        )
        self._dialogue_list.customContextMenuRequested.connect(
            self._on_dialogue_context_menu_requested
        )
        self._dialogue_list.visual_order_changed.connect(
            self._on_dialogue_visual_order_changed
        )

    def load_dialogues(
        self,
        dialogues: object,
        *,
        active_dialogue: object = None,
    ) -> None:
        self._dialogues = normalize_entity_dialogues(dialogues)
        active_name = str(active_dialogue).strip() if active_dialogue is not None else ""
        if not active_name and len(self._dialogues) == 1:
            active_name = next(iter(self._dialogues), "")
        self._active_dialogue = active_name or None
        self._rename_map = {}
        select_name = self._active_dialogue
        if select_name is None and self._dialogues:
            select_name = next(iter(self._dialogues))
        self._refresh_dialogue_list(select_name=select_name)

    def dialogues(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._dialogues)

    def active_dialogue(self) -> str | None:
        return self._active_dialogue

    def rename_map(self) -> dict[str, str]:
        return dict(self._rename_map)

    def accept(self) -> None:  # noqa: D401
        try:
            self._dialogues = normalize_entity_dialogues(self._dialogues)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Dialogues", str(exc))
            return
        super().accept()

    def _selected_dialogue_name(self) -> str | None:
        item = self._dialogue_list.currentItem()
        if item is None:
            return None
        name = item.data(0, Qt.ItemDataRole.UserRole)
        return name if isinstance(name, str) and name in self._dialogues else None

    def _refresh_dialogue_list(self, *, select_name: str | None = None) -> None:
        self._loading = True
        try:
            blocker = QSignalBlocker(self._dialogue_list)
            self._dialogue_list.clear()
            for name, entry in self._dialogues.items():
                item = QTreeWidgetItem([self._dialogue_list_label(name, entry)])
                item.setData(0, Qt.ItemDataRole.UserRole, name)
                if name == self._active_dialogue:
                    item.setFont(0, _tree_item_font(bold=True))
                    item.setForeground(0, QBrush(QColor("#8a4b00")))
                item.setToolTip(0, self._dialogue_entry_tooltip(name, entry))
                self._dialogue_list.addTopLevelItem(item)
            del blocker
            if select_name and select_name in self._dialogues:
                self._select_dialogue_item(select_name)
            elif self._dialogue_list.topLevelItemCount() > 0:
                self._dialogue_list.setCurrentItem(self._dialogue_list.topLevelItem(0))
            else:
                self._dialogue_list.setCurrentItem(None)
                self._detail_header.setText("No dialogue selected")
                self._detail_stack.setCurrentWidget(self._empty_page)
        finally:
            self._loading = False
        self._sync_detail_panel()

    def _dialogue_list_label(self, name: str, entry: dict[str, Any]) -> str:
        parts = [name]
        if name == self._active_dialogue:
            parts.append("[Active]")
        if isinstance(entry.get("dialogue_definition"), dict):
            parts.append("- Inline Dialogue")
        else:
            parts.append("- Dialogue File")
        return " ".join(parts)

    def _dialogue_entry_tooltip(self, name: str, entry: dict[str, Any]) -> str:
        if isinstance(entry.get("dialogue_definition"), dict):
            return f"{name}: {summarize_dialogue_definition(entry.get('dialogue_definition'))}"
        return f"{name}: dialogue file {str(entry.get('dialogue_path', '')).strip() or '(unset)'}"

    def _select_dialogue_item(self, name: str) -> None:
        for index in range(self._dialogue_list.topLevelItemCount()):
            item = self._dialogue_list.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == name:
                self._dialogue_list.setCurrentItem(item)
                return

    def _sync_detail_panel(self) -> None:
        name = self._selected_dialogue_name()
        if name is None:
            self._detail_header.setText("No dialogue selected")
            self._detail_stack.setCurrentWidget(self._empty_page)
            return
        entry = self._dialogues.get(name)
        if not isinstance(entry, dict):
            self._detail_header.setText(name)
            self._detail_stack.setCurrentWidget(self._empty_page)
            return
        self._detail_header.setText(name)
        active_text = (
            "This dialogue is currently the active default."
            if name == self._active_dialogue
            else "Right-click this dialogue and choose 'Set Active Dialogue' to make it the current default."
        )
        if isinstance(entry.get("dialogue_definition"), dict):
            self._inline_summary_label.setText(
                summarize_dialogue_definition(entry.get("dialogue_definition"))
            )
            self._inline_active_label.setText(active_text)
            self._detail_stack.setCurrentWidget(self._inline_page)
            return
        blocker = QSignalBlocker(self._dialogue_path_edit)
        self._dialogue_path_edit.setText(str(entry.get("dialogue_path", "")).strip())
        del blocker
        self._file_summary_label.setText(
            "Dialogue file reference for the selected named dialogue."
        )
        self._file_active_label.setText(active_text)
        self._detail_stack.setCurrentWidget(self._file_page)

    def _prompt_for_dialogue_name(
        self,
        *,
        title: str,
        label: str,
        initial: str,
        existing_name: str | None = None,
    ) -> str | None:
        name, accepted = QInputDialog.getText(self, title, label, text=initial)
        if not accepted:
            return None
        normalized = str(name).strip()
        if not normalized:
            QMessageBox.warning(self, "Invalid Dialogue Name", "Dialogue names must not be blank.")
            return None
        if normalized != existing_name and normalized in self._dialogues:
            QMessageBox.warning(
                self,
                "Duplicate Dialogue Name",
                f"A dialogue named '{normalized}' already exists.",
            )
            return None
        return normalized

    def _default_new_dialogue_name(self) -> str:
        if "starting_dialogue" not in self._dialogues:
            return "starting_dialogue"
        counter = 2
        while True:
            candidate = f"dialogue_{counter}"
            if candidate not in self._dialogues:
                return candidate
            counter += 1

    def _add_named_dialogue(self) -> None:
        name = self._prompt_for_dialogue_name(
            title="Add Dialogue",
            label="Dialogue name",
            initial=self._default_new_dialogue_name(),
        )
        if name is None:
            return
        self._dialogues[name] = {"dialogue_definition": {"segments": []}}
        if self._active_dialogue is None:
            self._active_dialogue = name
        self._refresh_dialogue_list(select_name=name)

    def _rename_selected_dialogue(self) -> None:
        current_name = self._selected_dialogue_name()
        if current_name is None:
            return
        renamed = self._prompt_for_dialogue_name(
            title="Rename Dialogue",
            label="Dialogue name",
            initial=current_name,
            existing_name=current_name,
        )
        if renamed is None or renamed == current_name:
            return
        rebuilt: dict[str, dict[str, Any]] = {}
        for name, value in self._dialogues.items():
            if name == current_name:
                rebuilt[renamed] = value
            else:
                rebuilt[name] = value
        self._dialogues = rename_self_target_dialogue_id_references(
            rebuilt,
            {current_name: renamed},
            current_entity_id=self._current_entity_id,
        )
        next_rename_map: dict[str, str] = {}
        for original_name, final_name in self._rename_map.items():
            next_rename_map[original_name] = (
                renamed if final_name == current_name else final_name
            )
        if current_name not in next_rename_map:
            next_rename_map[current_name] = renamed
        self._rename_map = next_rename_map
        if self._active_dialogue == current_name:
            self._active_dialogue = renamed
        self._refresh_dialogue_list(select_name=renamed)

    def _set_selected_dialogue_active(self) -> None:
        current_name = self._selected_dialogue_name()
        if current_name is None:
            return
        self._active_dialogue = current_name
        self._refresh_dialogue_list(select_name=current_name)

    def _delete_selected_dialogue(self) -> None:
        current_name = self._selected_dialogue_name()
        if current_name is None:
            return
        self._dialogues.pop(current_name, None)
        if self._active_dialogue == current_name:
            self._active_dialogue = next(iter(self._dialogues), None)
        next_name = self._active_dialogue or next(iter(self._dialogues), None)
        self._refresh_dialogue_list(select_name=next_name)

    def _on_dialogue_selection_changed(self, *_args) -> None:
        if self._loading:
            return
        self._sync_detail_panel()

    def _on_dialogue_visual_order_changed(self, visual_order: list[str]) -> None:
        if len(visual_order) != len(self._dialogues):
            self._refresh_dialogue_list(select_name=self._selected_dialogue_name())
            return
        current_name = self._selected_dialogue_name()
        reordered: dict[str, dict[str, Any]] = {}
        for name in visual_order:
            if name not in self._dialogues:
                self._refresh_dialogue_list(select_name=current_name)
                return
            reordered[name] = self._dialogues[name]
        if len(reordered) != len(self._dialogues):
            self._refresh_dialogue_list(select_name=current_name)
            return
        self._dialogues = reordered
        self._refresh_dialogue_list(select_name=current_name or self._active_dialogue)

    def _on_dialogue_context_menu_requested(self, position) -> None:
        item = self._dialogue_list.itemAt(position)
        if item is not None:
            self._dialogue_list.setCurrentItem(item)
        menu = QMenu(self)
        add_action = menu.addAction("Add Dialogue")
        rename_action = None
        active_action = None
        delete_action = None
        if item is not None:
            rename_action = menu.addAction("Rename Dialogue")
            active_action = menu.addAction("Set Active Dialogue")
            menu.addSeparator()
            delete_action = menu.addAction("Delete Dialogue")
        chosen = menu.exec(self._dialogue_list.viewport().mapToGlobal(position))
        if chosen == add_action:
            self._add_named_dialogue()
        elif rename_action is not None and chosen == rename_action:
            self._rename_selected_dialogue()
        elif active_action is not None and chosen == active_action:
            self._set_selected_dialogue_active()
        elif delete_action is not None and chosen == delete_action:
            self._delete_selected_dialogue()

    def _on_edit_inline_dialogue(self) -> None:
        name = self._selected_dialogue_name()
        if name is None:
            return
        entry = self._dialogues.get(name)
        if not isinstance(entry, dict):
            return
        definition = entry.get("dialogue_definition")
        if not isinstance(definition, dict):
            return
        dialog = DialogueDefinitionDialog(
            self,
            entity_picker=self._entity_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            current_entity_id=self._current_entity_id,
        )
        dialog.load_definition(definition)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        entry["dialogue_definition"] = dialog.definition()
        self._refresh_dialogue_list(select_name=name)

    def _on_dialogue_path_text_changed(self, text: str) -> None:
        if self._loading:
            return
        name = self._selected_dialogue_name()
        if name is None:
            return
        entry = self._dialogues.get(name)
        if not isinstance(entry, dict):
            return
        entry["dialogue_path"] = text.strip()
        self._sync_detail_panel()

    def _on_browse_dialogue_path(self) -> None:
        if self._dialogue_picker is None:
            return
        name = self._selected_dialogue_name()
        if name is None:
            return
        entry = self._dialogues.get(name)
        if not isinstance(entry, dict):
            return
        current_path = str(entry.get("dialogue_path", "")).strip()
        selected = self._dialogue_picker(current_path)
        if selected is None:
            return
        blocker = QSignalBlocker(self._dialogue_path_edit)
        self._dialogue_path_edit.setText(selected)
        del blocker
        entry["dialogue_path"] = selected
        self._sync_detail_panel()

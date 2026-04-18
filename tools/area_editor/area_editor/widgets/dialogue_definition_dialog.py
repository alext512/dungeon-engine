"""Structured popup editor for inline dialogue definitions."""

from __future__ import annotations

import copy
import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
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
    QTabWidget,
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


class _DialogueDefinitionStructuredEditor(QWidget):
    """List-based structured editor for one dialogue definition."""

    def __init__(
        self,
        parent=None,
        *,
        dialogue_picker=None,
        command_picker=None,
    ) -> None:
        super().__init__(parent)

        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._definition: dict[str, Any] = {"segments": []}
        self._loading = False
        self._last_valid_segment_row = -1
        self._last_valid_option_row = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        note = QLabel(
            "Edit the common dialogue shape here. For advanced fields like participants, "
            "segment hooks, portraits, or custom data, use the JSON tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Segments"))
        segment_hint = QLabel("Right-click to add or delete. Drag to reorder.")
        segment_hint.setWordWrap(True)
        segment_hint.setStyleSheet("color: #666;")
        left_layout.addWidget(segment_hint)

        self._segment_list = _ReorderListWidget()
        self._segment_list.setMinimumWidth(260)
        left_layout.addWidget(self._segment_list, 1)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._segment_header = QLabel("No segment selected")
        font = self._segment_header.font()
        font.setBold(True)
        self._segment_header.setFont(font)
        right_layout.addWidget(self._segment_header)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("type"))
        self._segment_type_label = QLabel("-")
        type_row.addWidget(self._segment_type_label)
        type_row.addStretch(1)
        right_layout.addLayout(type_row)

        self._segment_text_label = QLabel("text")
        right_layout.addWidget(self._segment_text_label)
        self._segment_text_edit = QPlainTextEdit()
        self._segment_text_edit.setPlaceholderText("Segment text or choice prompt")
        self._segment_text_edit.setFixedHeight(96)
        right_layout.addWidget(self._segment_text_edit)

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
        right_layout.addLayout(segment_start_row)

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
        right_layout.addLayout(segment_end_row)

        self._options_section = QWidget()
        options_layout = QVBoxLayout(self._options_section)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(6)

        options_layout.addWidget(QLabel("Choice Options"))
        option_hint = QLabel("Right-click to add or delete. Drag to reorder.")
        option_hint.setWordWrap(True)
        option_hint.setStyleSheet("color: #666;")
        options_layout.addWidget(option_hint)

        self._option_list = _ReorderListWidget()
        self._option_list.setMinimumHeight(120)
        options_layout.addWidget(self._option_list)

        self._option_id_edit = QLineEdit()
        options_layout.addWidget(QLabel("option_id"))
        options_layout.addWidget(self._option_id_edit)
        self._option_text_edit = QPlainTextEdit()
        self._option_text_edit.setFixedHeight(76)
        options_layout.addWidget(QLabel("text"))
        options_layout.addWidget(self._option_text_edit)
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
        options_layout.addLayout(option_commands_row)

        right_layout.addWidget(self._options_section)
        right_layout.addStretch(1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 580])

        self._segment_list.currentRowChanged.connect(self._on_segment_row_changed)
        self._segment_list.customContextMenuRequested.connect(self._on_segment_context_menu_requested)
        self._segment_list.visual_order_changed.connect(self._on_segment_visual_order_changed)
        self._option_list.currentRowChanged.connect(self._on_option_row_changed)
        self._option_list.customContextMenuRequested.connect(self._on_option_context_menu_requested)
        self._option_list.visual_order_changed.connect(self._on_option_visual_order_changed)

    def load_definition(self, definition: object) -> None:
        self._definition = _ensure_dialogue_definition(definition)
        self._loading = True
        try:
            self._refresh_segment_list()
        finally:
            self._loading = False
        if self._segment_list.count() > 0:
            self._segment_list.blockSignals(True)
            try:
                self._segment_list.setCurrentRow(0)
            finally:
                self._segment_list.blockSignals(False)
            self._last_valid_segment_row = 0
        else:
            self._last_valid_segment_row = -1
        self._load_current_segment_editor()

    def definition(self) -> dict[str, Any]:
        if not self._commit_current_editors(show_message=True):
            raise ValueError("Dialogue definition has invalid fields.")
        return copy.deepcopy(self._definition)

    def _segments(self) -> list[dict[str, Any]]:
        segments = self._definition.get("segments")
        if not isinstance(segments, list):
            segments = []
            self._definition["segments"] = segments
        return segments

    def _segment_at_row(self, row: int) -> dict[str, Any] | None:
        segments = self._segments()
        if row < 0 or row >= len(segments):
            return None
        segment = segments[row]
        if not isinstance(segment, dict):
            return None
        return segment

    def _current_segment(self) -> dict[str, Any] | None:
        return self._segment_at_row(self._segment_list.currentRow())

    @staticmethod
    def _options_for_segment(segment: dict[str, Any] | None) -> list[dict[str, Any]]:
        if segment is None:
            return []
        raw_options = segment.get("options")
        if not isinstance(raw_options, list):
            raw_options = []
            segment["options"] = raw_options
        return raw_options

    def _current_options(self) -> list[dict[str, Any]]:
        return self._options_for_segment(self._current_segment())

    def _option_at_row(
        self,
        row: int,
        *,
        segment_row: int | None = None,
    ) -> dict[str, Any] | None:
        options = self._options_for_segment(
            self._current_segment()
            if segment_row is None
            else self._segment_at_row(segment_row)
        )
        if row < 0 or row >= len(options):
            return None
        option = options[row]
        if not isinstance(option, dict):
            return None
        return option

    def _current_option(self) -> dict[str, Any] | None:
        return self._option_at_row(self._option_list.currentRow())

    def _commit_current_editors(self, *, show_message: bool) -> bool:
        return self._commit_current_segment(show_message=show_message)

    def _commit_current_segment(self, *, show_message: bool) -> bool:
        if self._last_valid_segment_row < 0:
            return True
        segment = self._segment_at_row(self._last_valid_segment_row)
        if segment is None:
            return True

        raw_type = str(segment.get("type", "text")).strip() or "text"
        if raw_type not in {"text", "choice"}:
            raw_type = "text"
            segment["type"] = raw_type

        raw_text = self._segment_text_edit.toPlainText()
        if raw_text:
            segment["text"] = raw_text
        else:
            segment.pop("text", None)

        if raw_type != "choice":
            segment.pop("options", None)
            return True

        if not self._commit_current_option(show_message=show_message):
            return False
        options = self._options_for_segment(segment)
        segment["options"] = options
        return True

    def _commit_current_option(self, *, show_message: bool) -> bool:
        _ = show_message
        if self._last_valid_option_row < 0:
            return True
        option = self._option_at_row(
            self._last_valid_option_row,
            segment_row=self._last_valid_segment_row,
        )
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
        return True

    def _refresh_segment_list(self) -> None:
        selected_row = self._segment_list.currentRow()
        self._segment_list.blockSignals(True)
        try:
            self._segment_list.clear()
            for index, segment in enumerate(self._segments()):
                item = QListWidgetItem(_segment_summary(segment, index))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._segment_list.addItem(item)
            if self._segment_list.count() > 0:
                selected_row = max(0, min(selected_row, self._segment_list.count() - 1))
                self._segment_list.setCurrentRow(selected_row)
        finally:
            self._segment_list.blockSignals(False)

        if self._segment_list.count() <= 0:
            self._last_valid_segment_row = -1
            return
        self._last_valid_segment_row = selected_row

    def _refresh_option_list(self) -> None:
        selected_row = self._option_list.currentRow()
        options = self._current_options()

        self._option_list.blockSignals(True)
        try:
            self._option_list.clear()
            for index, option in enumerate(options):
                item = QListWidgetItem(_option_summary(option, index))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._option_list.addItem(item)
            if self._option_list.count() > 0:
                selected_row = max(0, min(selected_row, self._option_list.count() - 1))
                self._option_list.setCurrentRow(selected_row)
        finally:
            self._option_list.blockSignals(False)

        if self._option_list.count() <= 0:
            self._last_valid_option_row = -1
            return
        self._last_valid_option_row = selected_row

    def _load_current_segment_editor(self) -> None:
        segment = self._current_segment()
        self._loading = True
        try:
            if segment is None:
                self._segment_header.setText("No segment selected")
                self._segment_type_label.setText("-")
                self._segment_text_edit.setPlainText("")
                self._segment_text_edit.setEnabled(False)
                self._segment_on_start_summary.setText("none")
                self._segment_on_end_summary.setText("none")
                self._segment_on_start_button.setEnabled(False)
                self._segment_on_end_button.setEnabled(False)
                self._options_section.hide()
                return

            row = self._segment_list.currentRow() + 1
            segment_type = str(segment.get("type", "text")).strip() or "text"
            self._segment_header.setText(f"Segment {row}")
            self._segment_type_label.setText(segment_type)
            self._segment_text_edit.setEnabled(True)
            self._segment_text_edit.setPlainText("" if segment.get("text") is None else str(segment.get("text", "")))
            self._sync_segment_command_buttons(segment)
            if segment_type == "choice":
                self._options_section.show()
                self._refresh_option_list()
                if self._option_list.count() > 0:
                    target_row = max(0, min(self._last_valid_option_row, self._option_list.count() - 1))
                    self._option_list.blockSignals(True)
                    try:
                        self._option_list.setCurrentRow(target_row)
                    finally:
                        self._option_list.blockSignals(False)
                    self._last_valid_option_row = target_row
                else:
                    self._last_valid_option_row = -1
            else:
                self._options_section.hide()
                self._option_list.blockSignals(True)
                try:
                    self._option_list.clear()
                    self._option_list.setCurrentRow(-1)
                finally:
                    self._option_list.blockSignals(False)
                self._load_current_option_editor()
        finally:
            self._loading = False
        if segment is not None and str(segment.get("type", "text")).strip() == "choice":
            self._load_current_option_editor()

    def _load_current_option_editor(self) -> None:
        option = self._current_option()
        self._loading = True
        try:
            if option is None:
                self._option_id_edit.setText("")
                self._option_text_edit.setPlainText("")
                self._option_id_edit.setEnabled(False)
                self._option_text_edit.setEnabled(False)
                self._option_commands_summary.setText("none")
                self._option_commands_button.setEnabled(False)
                return
            self._option_id_edit.setEnabled(True)
            self._option_text_edit.setEnabled(True)
            self._option_id_edit.setText(str(option.get("option_id", "")))
            self._option_text_edit.setPlainText("" if option.get("text") is None else str(option.get("text", "")))
            self._sync_option_command_button(option)
        finally:
            self._loading = False

    def _sync_segment_command_buttons(self, segment: dict[str, Any] | None) -> None:
        if segment is None:
            self._segment_on_start_summary.setText("none")
            self._segment_on_end_summary.setText("none")
            self._segment_on_start_button.setEnabled(False)
            self._segment_on_end_button.setEnabled(False)
            return
        self._segment_on_start_summary.setText(
            summarize_command_list(segment.get("on_start"))
        )
        self._segment_on_end_summary.setText(
            summarize_command_list(segment.get("on_end"))
        )
        self._segment_on_start_button.setEnabled(True)
        self._segment_on_end_button.setEnabled(True)

    def _sync_option_command_button(self, option: dict[str, Any] | None) -> None:
        if option is None:
            self._option_commands_summary.setText("none")
            self._option_commands_button.setEnabled(False)
            return
        self._option_commands_summary.setText(
            summarize_command_list(option.get("commands"))
        )
        self._option_commands_button.setEnabled(True)

    def _open_command_list_dialog(
        self,
        title: str,
        commands: object,
    ) -> list[dict[str, Any]] | None:
        dialog = CommandListDialog(
            self,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            suggested_command_names=_DIALOGUE_SUGGESTED_COMMAND_NAMES,
        )
        dialog.setWindowTitle(title)
        dialog.load_commands(commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.commands()

    def _edit_segment_commands(self, field_name: str) -> None:
        if not self._commit_current_segment(show_message=True):
            return
        segment = self._current_segment()
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
        self._refresh_segment_list()

    def _edit_option_commands(self) -> None:
        if not self._commit_current_segment(show_message=True):
            return
        option = self._current_option()
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
        self._refresh_option_list()

    def _on_segment_row_changed(self, row: int) -> None:
        if self._loading:
            return
        if not self._commit_current_segment(show_message=False):
            self._segment_list.blockSignals(True)
            try:
                self._segment_list.setCurrentRow(self._last_valid_segment_row)
            finally:
                self._segment_list.blockSignals(False)
            return
        self._last_valid_segment_row = row
        self._last_valid_option_row = 0
        self._refresh_segment_list()
        self._load_current_segment_editor()

    def _on_option_row_changed(self, row: int) -> None:
        if self._loading:
            return
        if not self._commit_current_option(show_message=False):
            self._option_list.blockSignals(True)
            try:
                self._option_list.setCurrentRow(self._last_valid_option_row)
            finally:
                self._option_list.blockSignals(False)
            return
        self._last_valid_option_row = row
        self._refresh_option_list()
        self._load_current_option_editor()

    def _insert_segment(self, segment: dict[str, Any], *, after_row: int | None = None) -> None:
        if not self._commit_current_editors(show_message=True):
            return
        segments = self._segments()
        if after_row is None or after_row < 0 or after_row >= len(segments):
            insert_row = len(segments)
        else:
            insert_row = after_row + 1
        segments.insert(insert_row, copy.deepcopy(segment))
        self._refresh_segment_list()
        self._segment_list.blockSignals(True)
        try:
            self._segment_list.setCurrentRow(insert_row)
        finally:
            self._segment_list.blockSignals(False)
        self._last_valid_segment_row = insert_row
        self._last_valid_option_row = 0 if segment.get("type") == "choice" else -1
        self._load_current_segment_editor()

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

    def _delete_segment_at(self, row: int) -> None:
        if not self._commit_current_editors(show_message=True):
            return
        segments = self._segments()
        if row < 0 or row >= len(segments):
            return
        del segments[row]
        self._refresh_segment_list()
        if self._segment_list.count() > 0:
            target_row = min(row, self._segment_list.count() - 1)
            self._segment_list.blockSignals(True)
            try:
                self._segment_list.setCurrentRow(target_row)
            finally:
                self._segment_list.blockSignals(False)
            self._last_valid_segment_row = target_row
        else:
            self._last_valid_segment_row = -1
        self._last_valid_option_row = -1
        self._load_current_segment_editor()

    def _on_segment_context_menu_requested(self, position) -> None:
        item = self._segment_list.itemAt(position)
        target_row = self._segment_list.row(item) if item is not None else -1
        menu = QMenu(self)
        add_text_action = menu.addAction("Add Text")
        add_choice_action = menu.addAction("Add Choice")
        delete_action = None
        if target_row >= 0:
            add_text_action.setText("Add Text After")
            add_choice_action.setText("Add Choice After")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._segment_list.viewport().mapToGlobal(position))
        if chosen == add_text_action:
            self._insert_text_segment(after_row=target_row if target_row >= 0 else None)
        elif chosen == add_choice_action:
            self._insert_choice_segment(after_row=target_row if target_row >= 0 else None)
        elif delete_action is not None and chosen == delete_action:
            self._delete_segment_at(target_row)

    def _on_segment_visual_order_changed(self, visual_order: list[int]) -> None:
        if not self._commit_current_editors(show_message=True):
            self._refresh_segment_list()
            self._load_current_segment_editor()
            return
        segments = self._segments()
        if len(visual_order) != len(segments):
            self._refresh_segment_list()
            self._load_current_segment_editor()
            return
        current_segment = self._segment_at_row(self._last_valid_segment_row)
        reordered = [segments[index] for index in visual_order if 0 <= index < len(segments)]
        if len(reordered) != len(segments):
            self._refresh_segment_list()
            self._load_current_segment_editor()
            return
        segments[:] = reordered
        self._refresh_segment_list()
        if current_segment is not None and current_segment in segments:
            target_row = segments.index(current_segment)
        elif self._segment_list.count() > 0:
            target_row = min(self._last_valid_segment_row, self._segment_list.count() - 1)
        else:
            target_row = -1
        self._segment_list.blockSignals(True)
        try:
            self._segment_list.setCurrentRow(target_row)
        finally:
            self._segment_list.blockSignals(False)
        self._last_valid_segment_row = target_row
        self._load_current_segment_editor()

    def _insert_option(self, *, after_row: int | None = None) -> None:
        if not self._commit_current_segment(show_message=True):
            return
        options = self._current_options()
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
        self._refresh_segment_list()
        self._refresh_option_list()
        self._option_list.blockSignals(True)
        try:
            self._option_list.setCurrentRow(insert_row)
        finally:
            self._option_list.blockSignals(False)
        self._last_valid_option_row = insert_row
        self._load_current_option_editor()

    def _delete_option_at(self, row: int) -> None:
        if not self._commit_current_segment(show_message=True):
            return
        options = self._current_options()
        if row < 0 or row >= len(options):
            return
        del options[row]
        self._refresh_segment_list()
        self._refresh_option_list()
        if self._option_list.count() > 0:
            target_row = min(row, self._option_list.count() - 1)
            self._option_list.blockSignals(True)
            try:
                self._option_list.setCurrentRow(target_row)
            finally:
                self._option_list.blockSignals(False)
            self._last_valid_option_row = target_row
        else:
            self._last_valid_option_row = -1
        self._load_current_option_editor()

    def _on_option_context_menu_requested(self, position) -> None:
        segment = self._current_segment()
        if not isinstance(segment, dict):
            return
        if str(segment.get("type", "text")).strip() != "choice":
            return
        item = self._option_list.itemAt(position)
        target_row = self._option_list.row(item) if item is not None else -1
        menu = QMenu(self)
        add_option_action = menu.addAction("Add Option")
        delete_action = None
        if target_row >= 0:
            add_option_action.setText("Add Option After")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._option_list.viewport().mapToGlobal(position))
        if chosen == add_option_action:
            self._insert_option(after_row=target_row if target_row >= 0 else None)
        elif delete_action is not None and chosen == delete_action:
            self._delete_option_at(target_row)

    def _on_option_visual_order_changed(self, visual_order: list[int]) -> None:
        if not self._commit_current_segment(show_message=True):
            self._refresh_option_list()
            self._load_current_option_editor()
            return
        options = self._current_options()
        if len(visual_order) != len(options):
            self._refresh_option_list()
            self._load_current_option_editor()
            return
        current_option = self._option_at_row(
            self._last_valid_option_row,
            segment_row=self._last_valid_segment_row,
        )
        reordered = [options[index] for index in visual_order if 0 <= index < len(options)]
        if len(reordered) != len(options):
            self._refresh_option_list()
            self._load_current_option_editor()
            return
        options[:] = reordered
        self._refresh_segment_list()
        self._refresh_option_list()
        if current_option is not None and current_option in options:
            target_row = options.index(current_option)
        elif self._option_list.count() > 0:
            target_row = min(self._last_valid_option_row, self._option_list.count() - 1)
        else:
            target_row = -1
        self._option_list.blockSignals(True)
        try:
            self._option_list.setCurrentRow(target_row)
        finally:
            self._option_list.blockSignals(False)
        self._last_valid_option_row = target_row
        self._load_current_option_editor()


class DialogueDefinitionDialog(QDialog):
    """Popup editor for one inline dialogue definition."""

    def __init__(
        self,
        parent=None,
        *,
        dialogue_picker=None,
        command_picker=None,
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
            dialogue_picker=dialogue_picker,
            command_picker=command_picker,
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

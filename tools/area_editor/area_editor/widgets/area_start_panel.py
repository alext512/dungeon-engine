"""Focused editor surface for area enter/start commands."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.json_io import JsonDataDecodeError, loads_json_data


def _format_commands_text(commands: list[Any]) -> str:
    return json.dumps(commands, indent=2, ensure_ascii=False)


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


class AreaStartPanel(QWidget):
    """Compact helper/editor for one area's ``enter_commands`` list."""

    commands_applied = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._area_id: str | None = None
        self._original_commands: list[Any] = []
        self._browse_entity_callback: Callable[[str], str | None] | None = None
        self._browse_dialogue_callback: Callable[[str], str | None] | None = None
        self._browse_command_callback: Callable[[str], str | None] | None = None
        self._browse_asset_callback: Callable[[str], str | None] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._target_label = QLabel("Area Start: None")
        layout.addWidget(self._target_label)

        helper_note = QLabel(
            "Use quick helpers for common area-enter behavior, or edit the real "
            "`enter_commands` JSON directly below."
        )
        helper_note.setWordWrap(True)
        helper_note.setStyleSheet("color: #666;")
        layout.addWidget(helper_note)

        helper_row = QHBoxLayout()
        helper_row.setContentsMargins(0, 0, 0, 0)
        helper_row.setSpacing(6)
        helper_row.addWidget(QLabel("Add Common Command"))
        self._helper_combo = QComboBox()
        self._helper_combo.addItems(
            [
                "Route Inputs To Entity",
                "Run Entity Command",
                "Open Dialogue",
                "Set Camera Follow",
                "Play Music",
            ]
        )
        helper_row.addWidget(self._helper_combo, 1)
        self._add_helper_button = QPushButton("Add")
        self._add_helper_button.setAutoDefault(False)
        self._add_helper_button.setDefault(False)
        helper_row.addWidget(self._add_helper_button)
        layout.addLayout(helper_row)

        self._helper_stack = QStackedWidget()
        layout.addWidget(self._helper_stack)

        self._route_entity_edit: QLineEdit
        self._run_entity_edit: QLineEdit
        self._run_command_edit: QLineEdit
        self._dialogue_path_edit: QLineEdit
        self._dialogue_allow_cancel_check: QCheckBox
        self._camera_entity_edit: QLineEdit
        self._music_path_edit: QLineEdit
        self._music_loop_check: QCheckBox

        self._helper_stack.addWidget(self._build_route_inputs_page())
        self._helper_stack.addWidget(self._build_run_entity_command_page())
        self._helper_stack.addWidget(self._build_open_dialogue_page())
        self._helper_stack.addWidget(self._build_set_camera_follow_page())
        self._helper_stack.addWidget(self._build_play_music_page())

        commands_label = QLabel("Enter Commands")
        commands_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(commands_label)

        self._commands_text = QPlainTextEdit()
        self._commands_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        commands_font = QFont("Consolas", 10)
        commands_font.setStyleHint(QFont.StyleHint.Monospace)
        self._commands_text.setFont(commands_font)
        self._commands_text.setPlaceholderText("[\n  {\n    \"type\": \"route_inputs_to_entity\",\n    \"entity_id\": \"player_1\"\n  }\n]")
        layout.addWidget(self._commands_text, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addStretch(1)
        self._revert_button = QPushButton("Revert")
        self._revert_button.setAutoDefault(False)
        self._revert_button.setDefault(False)
        self._apply_button = QPushButton("Apply")
        self._apply_button.setAutoDefault(False)
        self._apply_button.setDefault(False)
        button_row.addWidget(self._revert_button)
        button_row.addWidget(self._apply_button)
        layout.addLayout(button_row)

        self._helper_combo.currentIndexChanged.connect(self._helper_stack.setCurrentIndex)
        self._add_helper_button.clicked.connect(self._on_add_helper_command)
        self._apply_button.clicked.connect(self._on_apply)
        self._revert_button.clicked.connect(self._on_revert)

        self.clear()

    def set_picker_callbacks(
        self,
        *,
        entity_picker: Callable[[str], str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        asset_picker: Callable[[str], str | None] | None = None,
    ) -> None:
        self._browse_entity_callback = entity_picker
        self._browse_dialogue_callback = dialogue_picker
        self._browse_command_callback = command_picker
        self._browse_asset_callback = asset_picker

    def clear(self) -> None:
        self._area_id = None
        self._original_commands = []
        self._target_label.setText("Area Start: None")
        self._commands_text.clear()
        self._set_enabled(False)
        self._clear_helper_inputs()

    def load_area(self, area_id: str, commands: list[Any]) -> None:
        self._area_id = area_id
        self._original_commands = copy.deepcopy(commands)
        self._target_label.setText(f"Area Start: {area_id}")
        self._commands_text.setPlainText(_format_commands_text(commands))
        self._set_enabled(True)

    def _build_route_inputs_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        row, self._route_entity_edit, browse = _make_line_with_browse()
        browse.clicked.connect(
            lambda: self._pick_into(
                self._route_entity_edit,
                self._browse_entity_callback,
                "Choose Target Entity",
            )
        )
        form.addRow("entity_id", row)
        return page

    def _build_run_entity_command_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        entity_row, self._run_entity_edit, entity_browse = _make_line_with_browse()
        entity_browse.clicked.connect(
            lambda: self._pick_into(
                self._run_entity_edit,
                self._browse_entity_callback,
                "Choose Target Entity",
            )
        )
        self._run_command_edit = QLineEdit()
        form.addRow("entity_id", entity_row)
        form.addRow("command_id", self._run_command_edit)
        return page

    def _build_open_dialogue_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        row, self._dialogue_path_edit, browse = _make_line_with_browse()
        browse.clicked.connect(
            lambda: self._pick_into(
                self._dialogue_path_edit,
                self._browse_dialogue_callback,
                "Choose Dialogue",
            )
        )
        self._dialogue_allow_cancel_check = QCheckBox()
        self._dialogue_allow_cancel_check.setChecked(True)
        form.addRow("dialogue_path", row)
        form.addRow("allow_cancel", self._dialogue_allow_cancel_check)
        return page

    def _build_set_camera_follow_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        row, self._camera_entity_edit, browse = _make_line_with_browse()
        browse.clicked.connect(
            lambda: self._pick_into(
                self._camera_entity_edit,
                self._browse_entity_callback,
                "Choose Camera Follow Entity",
            )
        )
        form.addRow("entity_id", row)
        return page

    def _build_play_music_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        row, self._music_path_edit, browse = _make_line_with_browse()
        browse.clicked.connect(
            lambda: self._pick_into(
                self._music_path_edit,
                self._browse_asset_callback,
                "Choose Music Asset",
            )
        )
        self._music_loop_check = QCheckBox()
        self._music_loop_check.setChecked(True)
        form.addRow("path", row)
        form.addRow("loop", self._music_loop_check)
        return page

    def _pick_into(
        self,
        edit: QLineEdit,
        callback: Callable[[str], str | None] | None,
        title: str,
    ) -> None:
        if callback is None:
            return
        selected = callback(edit.text().strip() or title)
        if selected:
            edit.setText(selected)

    def _set_enabled(self, enabled: bool) -> None:
        self._helper_combo.setEnabled(enabled)
        self._add_helper_button.setEnabled(enabled)
        self._helper_stack.setEnabled(enabled)
        self._commands_text.setReadOnly(not enabled)
        self._revert_button.setEnabled(enabled)
        self._apply_button.setEnabled(enabled)

    def _clear_helper_inputs(self) -> None:
        for edit in (
            self._route_entity_edit,
            self._run_entity_edit,
            self._run_command_edit,
            self._dialogue_path_edit,
            self._camera_entity_edit,
            self._music_path_edit,
        ):
            edit.clear()
        self._dialogue_allow_cancel_check.setChecked(True)
        self._music_loop_check.setChecked(True)

    def _parse_commands_text(self) -> list[Any]:
        raw = self._commands_text.toPlainText().strip()
        if not raw:
            return []
        try:
            parsed = loads_json_data(raw, source_name="Enter commands")
        except JsonDataDecodeError as exc:
            raise ValueError(f"Enter commands must be valid JSON.\n{exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("Enter commands must be a JSON array.")
        return parsed

    def _append_command(self, command: dict[str, Any]) -> None:
        try:
            commands = self._parse_commands_text()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Enter Commands", str(exc))
            return
        commands.append(command)
        self._commands_text.setPlainText(_format_commands_text(commands))

    def _on_add_helper_command(self) -> None:
        try:
            command = self._build_helper_command(self._helper_combo.currentIndex())
        except ValueError as exc:
            QMessageBox.warning(self, "Missing Values", str(exc))
            return
        self._append_command(command)

    def _build_helper_command(self, index: int) -> dict[str, Any]:
        if index == 0:
            entity_id = self._route_entity_edit.text().strip()
            if not entity_id:
                raise ValueError("Choose an entity to route inputs to.")
            return {
                "type": "route_inputs_to_entity",
                "entity_id": entity_id,
            }
        if index == 1:
            entity_id = self._run_entity_edit.text().strip()
            command_id = self._run_command_edit.text().strip()
            if not entity_id or not command_id:
                raise ValueError("Choose both an entity and a command id.")
            return {
                "type": "run_entity_command",
                "entity_id": entity_id,
                "command_id": command_id,
            }
        if index == 2:
            dialogue_path = self._dialogue_path_edit.text().strip()
            if not dialogue_path:
                raise ValueError("Choose a dialogue to open.")
            return {
                "type": "open_dialogue_session",
                "dialogue_path": dialogue_path,
                "allow_cancel": self._dialogue_allow_cancel_check.isChecked(),
            }
        if index == 3:
            entity_id = self._camera_entity_edit.text().strip()
            if not entity_id:
                raise ValueError("Choose an entity for camera follow.")
            return {
                "type": "set_camera_follow",
                "follow": {
                    "mode": "entity",
                    "entity_id": entity_id,
                    "offset_x": 0,
                    "offset_y": 0,
                },
            }
        if index == 4:
            path = self._music_path_edit.text().strip()
            if not path:
                raise ValueError("Choose a music asset path.")
            return {
                "type": "play_music",
                "path": path,
                "loop": self._music_loop_check.isChecked(),
            }
        raise ValueError("Unknown helper command type.")

    def _on_apply(self) -> None:
        try:
            commands = self._parse_commands_text()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Enter Commands", str(exc))
            return
        self._original_commands = copy.deepcopy(commands)
        self.commands_applied.emit(commands)

    def _on_revert(self) -> None:
        self._commands_text.setPlainText(_format_commands_text(self._original_commands))

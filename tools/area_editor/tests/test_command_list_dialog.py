"""Tests for the command-list popup editor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.command_list_dialog import (
    CommandListDialog,
    _CommandTypePickerDialog,
    summarize_command_list,
)


class TestCommandListDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_summary_reports_count_and_first_type(self):
        self.assertEqual(
            summarize_command_list(
                [
                    {"type": "wait_frames", "frames": 1},
                    {"type": "set_entity_var", "entity_id": "player_1"},
                ]
            ),
            "2 commands: wait_frames...",
        )

    def test_command_type_picker_filters_and_returns_selection(self):
        dialog = _CommandTypePickerDialog(
            command_names=[
                "wait_frames",
                "open_dialogue_session",
                "close_dialogue_session",
            ]
        )
        self.addCleanup(dialog.close)

        dialog._search_edit.setText("open")

        self.assertEqual(dialog._command_list.count(), 1)
        self.assertEqual(
            dialog.selected_command_type(),
            "open_dialogue_session",
        )

    def test_command_type_picker_shows_suggested_before_full_list(self):
        dialog = _CommandTypePickerDialog(
            command_names=[
                "wait_frames",
                "open_dialogue_session",
                "close_dialogue_session",
            ],
            suggested_command_names=[
                "open_dialogue_session",
            ],
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._command_list.item(0).text(), "Suggested")
        self.assertEqual(dialog._command_list.item(1).text(), "open_dialogue_session")
        self.assertEqual(dialog.selected_command_type(), "open_dialogue_session")

    def test_structured_editor_can_build_inline_dialogue_command(self):
        dialog = CommandListDialog()
        self.addCleanup(dialog.close)
        dialog.load_commands([])

        editor = dialog._structured_editor
        editor._insert_command("open_dialogue_session")
        editor._allow_cancel_check.setChecked(True)

        with patch.object(
            editor,
            "_open_inline_dialogue_definition_dialog",
            return_value={
                "segments": [
                    {"type": "text", "text": "Nested"},
                ]
            },
        ):
            editor._on_edit_inline_dialogue()

        commands = dialog.commands()

        self.assertEqual(commands[0]["type"], "open_dialogue_session")
        self.assertTrue(commands[0]["allow_cancel"])
        self.assertEqual(
            commands[0]["dialogue_definition"]["segments"][0]["text"],
            "Nested",
        )

    def test_open_dialogue_advanced_section_expands_when_fields_are_set(self):
        dialog = CommandListDialog()
        self.addCleanup(dialog.close)
        dialog.load_commands(
            [
                {
                    "type": "open_dialogue_session",
                    "dialogue_definition": {"segments": []},
                    "actor_id": "npc_1",
                }
            ]
        )

        editor = dialog._structured_editor

        self.assertTrue(editor._open_dialogue_advanced_toggle.isChecked())
        self.assertFalse(editor._open_dialogue_advanced_widget.isHidden())
        self.assertEqual(
            editor._open_dialogue_advanced_toggle.text(),
            "Advanced (1 set)",
        )

    def test_structured_editor_can_reorder_commands_by_visual_order(self):
        dialog = CommandListDialog()
        self.addCleanup(dialog.close)
        dialog.load_commands(
            [
                {"type": "wait_frames", "frames": 1},
                {"type": "set_entity_var", "entity_id": "player_1", "name": "mode", "value": "x"},
                {"type": "close_dialogue_session"},
            ]
        )

        editor = dialog._structured_editor
        editor._command_list.setCurrentRow(2)
        editor._on_command_visual_order_changed([2, 0, 1])

        commands = dialog.commands()

        self.assertEqual(
            [command["type"] for command in commands],
            ["close_dialogue_session", "wait_frames", "set_entity_var"],
        )

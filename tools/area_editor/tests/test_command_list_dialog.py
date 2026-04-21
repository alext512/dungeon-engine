"""Tests for the command-list popup editor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.reference_picker_support import EntityReferencePickerRequest
from area_editor.widgets.command_list_dialog import (
    CommandEditorDialog,
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

    def test_command_editor_can_build_inline_dialogue_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "open_dialogue_session",
                "dialogue_definition": {"segments": []},
            }
        )
        dialog._allow_cancel_field.setCurrentIndex(1)

        with patch.object(
            dialog,
            "_open_inline_dialogue_definition_dialog",
            return_value={
                "segments": [
                    {"type": "text", "text": "Nested"},
                ]
            },
        ):
            dialog._on_edit_inline_dialogue()

        command = dialog.command()

        self.assertEqual(command["type"], "open_dialogue_session")
        self.assertTrue(command["allow_cancel"])
        self.assertEqual(
            command["dialogue_definition"]["segments"][0]["text"],
            "Nested",
        )

    def test_open_dialogue_advanced_section_expands_when_fields_are_set(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            [
                {
                    "type": "open_dialogue_session",
                    "dialogue_definition": {"segments": []},
                    "actor_id": "npc_1",
                }
            ][0]
        )

        self.assertTrue(dialog._open_dialogue_advanced_toggle.isChecked())
        self.assertFalse(dialog._open_dialogue_advanced_widget.isHidden())
        self.assertEqual(
            dialog._open_dialogue_advanced_toggle.text(),
            "Advanced (1 set)",
        )

    def test_command_editor_builds_set_entity_active_dialogue_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_entity_active_dialogue"})

        dialog._set_active_entity_id_edit.setText("$self_id")
        dialog._set_active_dialogue_id_edit.setText("repeat")
        dialog._set_active_persistent_field.setCurrentIndex(1)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "set_entity_active_dialogue",
                "entity_id": "$self_id",
                "dialogue_id": "repeat",
                "persistent": True,
            },
        )

    def test_command_editor_preserves_unsupported_fields_for_supported_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "open_entity_dialogue",
                "entity_id": "$self_id",
                "dialogue_id": "intro",
                "segment_hooks": [{"option_commands_by_id": {"yes": []}}],
            }
        )

        dialog._open_entity_dialogue_id_field.edit.setText("repeat")

        command = dialog.command()

        self.assertEqual(command["dialogue_id"], "repeat")
        self.assertEqual(
            command["segment_hooks"],
            [{"option_commands_by_id": {"yes": []}}],
        )

    def test_command_editor_entity_picker_reuses_shared_callback_shape(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            self.assertEqual(current_value, "")
            return "npc_2"

        dialog = CommandEditorDialog(
            entity_picker=entity_picker,
            current_entity_id="sign_1",
        )
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_entity_active_dialogue"})

        dialog._set_active_entity_pick.click()

        self.assertEqual(dialog._set_active_entity_id_edit.text(), "npc_2")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="entity_id",
                    current_value="",
                    parameter_spec={"type": "entity_id"},
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values=None,
                )
            ],
        )

    def test_command_editor_entity_dialogue_picker_uses_target_entity_context(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_dialogue_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            self.assertEqual(current_value, "intro")
            return "repeat"

        dialog = CommandEditorDialog(
            entity_dialogue_picker=entity_dialogue_picker,
            current_entity_id="sign_1",
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "set_entity_active_dialogue",
                "entity_id": "npc_1",
                "dialogue_id": "intro",
            }
        )

        dialog._set_active_dialogue_pick.click()

        self.assertEqual(dialog._set_active_dialogue_id_edit.text(), "repeat")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="dialogue_id",
                    current_value="intro",
                    parameter_spec={
                        "type": "entity_dialogue_id",
                        "entity_parameter": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "npc_1",
                        "dialogue_id": "intro",
                    },
                )
            ],
        )

    def test_command_list_dialog_can_reorder_commands_by_visual_order(self):
        dialog = CommandListDialog()
        self.addCleanup(dialog.close)
        dialog.load_commands(
            [
                {"type": "wait_frames", "frames": 1},
                {
                    "type": "set_entity_var",
                    "entity_id": "player_1",
                    "name": "mode",
                    "value": "x",
                },
                {"type": "close_dialogue_session"},
            ]
        )

        dialog._command_list.setCurrentRow(2)
        dialog._on_command_visual_order_changed([2, 0, 1])

        commands = dialog.commands()

        self.assertEqual(
            [command["type"] for command in commands],
            ["close_dialogue_session", "wait_frames", "set_entity_var"],
        )

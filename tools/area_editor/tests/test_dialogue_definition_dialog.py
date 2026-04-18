"""Tests for the dialogue-definition popup editor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.dialogue_definition_dialog import (
    DialogueDefinitionDialog,
    summarize_dialogue_definition,
)


class TestDialogueDefinitionDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_summary_reports_segment_and_choice_counts(self):
        self.assertEqual(
            summarize_dialogue_definition(
                {
                    "segments": [
                        {"type": "text", "text": "A"},
                        {"type": "choice", "text": "B", "options": []},
                    ]
                }
            ),
            "2 segments, 1 text, 1 choice",
        )

    def test_json_tab_can_replace_structured_definition(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {
                        "type": "text",
                        "text": "Original",
                    }
                ]
            }
        )

        dialog._tabs.setCurrentIndex(1)
        dialog._json_editor.setPlainText(
            '{\n'
            '  "participants": {\n'
            '    "narrator": { "portrait_path": "assets/project/ui/narrator.png" }\n'
            '  },\n'
            '  "segments": [\n'
            '    {\n'
            '      "type": "text",\n'
            '      "text": "Updated from JSON"\n'
            '    }\n'
            '  ]\n'
            '}'
        )
        dialog._tabs.setCurrentIndex(0)

        definition = dialog.definition()

        self.assertEqual(definition["segments"][0]["text"], "Updated from JSON")
        self.assertIn("participants", definition)

    def test_structured_editor_can_edit_segment_and_option_command_lists(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition({"segments": []})

        editor = dialog._structured_editor
        editor._insert_choice_segment()
        editor._option_id_edit.setText("inspect")
        editor._option_text_edit.setPlainText("Inspect the carving")

        with patch.object(
            editor,
            "_open_command_list_dialog",
            side_effect=[
                [{"type": "wait_frames", "frames": 1}],
                [{"type": "set_entity_var", "entity_id": "marker", "name": "seen", "value": True}],
            ],
        ):
            editor._edit_segment_commands("on_start")
            editor._edit_option_commands()

        definition = dialog.definition()

        self.assertEqual(definition["segments"][0]["type"], "choice")
        self.assertEqual(
            definition["segments"][0]["on_start"][0]["type"],
            "wait_frames",
        )
        self.assertEqual(
            definition["segments"][0]["options"][0]["option_id"],
            "inspect",
        )
        self.assertEqual(
            definition["segments"][0]["options"][0]["commands"][0]["type"],
            "set_entity_var",
        )

    def test_structured_editor_can_reorder_segments_by_visual_order(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {"type": "text", "text": "First"},
                    {"type": "text", "text": "Second"},
                    {"type": "text", "text": "Third"},
                ]
            }
        )

        editor = dialog._structured_editor
        editor._segment_list.setCurrentRow(1)
        editor._on_segment_visual_order_changed([1, 0, 2])

        definition = dialog.definition()

        self.assertEqual(
            [segment["text"] for segment in definition["segments"]],
            ["Second", "First", "Third"],
        )

    def test_structured_editor_can_reorder_choice_options_by_visual_order(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {
                        "type": "choice",
                        "text": "Pick one",
                        "options": [
                            {"option_id": "a", "text": "Alpha"},
                            {"option_id": "b", "text": "Beta"},
                            {"option_id": "c", "text": "Gamma"},
                        ],
                    }
                ]
            }
        )

        editor = dialog._structured_editor
        editor._option_list.setCurrentRow(2)
        editor._on_option_visual_order_changed([2, 0, 1])

        definition = dialog.definition()

        self.assertEqual(
            [option["option_id"] for option in definition["segments"][0]["options"]],
            ["c", "a", "b"],
        )

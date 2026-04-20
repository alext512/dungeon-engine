"""Tests for the dialogue-definition popup editor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from area_editor.widgets.dialogue_definition_dialog import (
    DialogueDefinitionDialog,
    EntityDialoguesDialog,
    summarize_entity_dialogues,
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

    def test_entity_dialogues_summary_reports_active_dialogue(self):
        self.assertEqual(
            summarize_entity_dialogues(
                {
                    "starting_dialogue": {
                        "dialogue_definition": {
                            "segments": [{"type": "text", "text": "Hi"}]
                        }
                    }
                },
                "starting_dialogue",
            ),
            "1 dialogue; active: starting_dialogue",
        )

    def test_entity_dialogues_summary_infers_active_for_single_dialogue(self):
        self.assertEqual(
            summarize_entity_dialogues(
                {
                    "starting_dialogue": {
                        "dialogue_definition": {
                            "segments": [{"type": "text", "text": "Hi"}]
                        }
                    }
                }
            ),
            "1 dialogue; active: starting_dialogue",
        )

    def test_entity_dialogues_dialog_can_add_rename_and_mark_active(self):
        dialog = EntityDialoguesDialog()
        self.addCleanup(dialog.close)
        dialog.load_dialogues(
            {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                }
            },
            active_dialogue="starting_dialogue",
        )

        with patch(
            "area_editor.widgets.dialogue_definition_dialog.QInputDialog.getText",
            side_effect=[("repeat_dialogue", True), ("renamed_dialogue", True)],
        ):
            dialog._add_named_dialogue()
            dialog._select_dialogue_item("repeat_dialogue")
            dialog._rename_selected_dialogue()

        dialog._select_dialogue_item("renamed_dialogue")
        dialog._set_selected_dialogue_active()

        self.assertIn("starting_dialogue", dialog.dialogues())
        self.assertIn("renamed_dialogue", dialog.dialogues())
        self.assertEqual(dialog.active_dialogue(), "renamed_dialogue")

    def test_entity_dialogues_dialog_keeps_single_existing_dialogue_active_when_adding(self):
        dialog = EntityDialoguesDialog()
        self.addCleanup(dialog.close)
        dialog.load_dialogues(
            {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                }
            }
        )

        with patch(
            "area_editor.widgets.dialogue_definition_dialog.QInputDialog.getText",
            return_value=("repeat_dialogue", True),
        ):
            dialog._add_named_dialogue()

        self.assertEqual(dialog.active_dialogue(), "starting_dialogue")

    def test_entity_dialogues_dialog_can_reorder_dialogues_and_keep_active_selection(self):
        dialog = EntityDialoguesDialog()
        self.addCleanup(dialog.close)
        dialog.load_dialogues(
            {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                },
                "repeat_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Again"}]
                    }
                },
            },
            active_dialogue="starting_dialogue",
        )
        dialog._select_dialogue_item("repeat_dialogue")

        dialog._on_dialogue_visual_order_changed(
            ["repeat_dialogue", "starting_dialogue"]
        )

        self.assertEqual(
            list(dialog.dialogues().keys()),
            ["repeat_dialogue", "starting_dialogue"],
        )
        self.assertEqual(dialog.active_dialogue(), "starting_dialogue")

    def test_entity_dialogues_dialog_rename_updates_self_targeting_dialogue_id_refs(self):
        dialog = EntityDialoguesDialog(current_entity_id="sign_1")
        self.addCleanup(dialog.close)
        dialog.load_dialogues(
            {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                },
                "followup": {
                    "dialogue_definition": {
                        "segments": [
                            {
                                "type": "text",
                                "text": "Branch",
                                "on_end": [
                                    {
                                        "type": "open_entity_dialogue",
                                        "entity_id": "$self_id",
                                        "dialogue_id": "starting_dialogue",
                                    }
                                ],
                            }
                        ]
                    }
                },
            },
            active_dialogue="starting_dialogue",
        )

        with patch(
            "area_editor.widgets.dialogue_definition_dialog.QInputDialog.getText",
            return_value=("intro_dialogue", True),
        ):
            dialog._rename_selected_dialogue()

        dialogues = dialog.dialogues()
        self.assertIn("intro_dialogue", dialogues)
        self.assertEqual(dialog.rename_map(), {"starting_dialogue": "intro_dialogue"})
        self.assertEqual(
            dialogues["followup"]["dialogue_definition"]["segments"][0]["on_end"][0]["dialogue_id"],
            "intro_dialogue",
        )

    def test_entity_dialogues_dialog_note_warns_about_by_order_helpers(self):
        dialog = EntityDialoguesDialog()
        self.addCleanup(dialog.close)

        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertTrue(
            any("set_entity_active_dialogue_by_order" in text for text in labels)
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
        segment_item = editor._find_tree_item(("segment", (), 0))
        self.assertIsNotNone(segment_item)
        editor._tree.setCurrentItem(segment_item)

        option_item = editor._find_tree_item(("option", (), 0, 0))
        self.assertIsNotNone(option_item)

        with patch.object(
            editor,
            "_open_command_list_dialog",
            side_effect=[
                [{"type": "wait_frames", "frames": 1}],
                [{"type": "set_entity_var", "entity_id": "marker", "name": "seen", "value": True}],
            ],
        ):
            editor._edit_segment_commands("on_start")
            option_item = editor._find_tree_item(("option", (), 0, 0))
            self.assertIsNotNone(option_item)
            editor._tree.setCurrentItem(option_item)
            editor._option_id_edit.setText("inspect")
            editor._option_text_edit.setPlainText("Inspect the carving")
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
        segment_item = editor._find_tree_item(("segment", (), 1))
        self.assertIsNotNone(segment_item)
        editor._tree.setCurrentItem(segment_item)
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
        option_item = editor._find_tree_item(("option", (), 0, 2))
        self.assertIsNotNone(option_item)
        editor._tree.setCurrentItem(option_item)
        editor._on_option_visual_order_changed([2, 0, 1])

        definition = dialog.definition()

        self.assertEqual(
            [option["option_id"] for option in definition["segments"][0]["options"]],
            ["c", "a", "b"],
        )

    def test_structured_editor_can_create_inline_branch_in_tree(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {
                        "type": "choice",
                        "text": "Pick one",
                        "options": [
                            {"option_id": "read", "text": "Read"},
                        ],
                    }
                ]
            }
        )

        editor = dialog._structured_editor
        option_item = editor._find_tree_item(("option", (), 0, 0))
        self.assertIsNotNone(option_item)
        editor._tree.setCurrentItem(option_item)
        editor._on_add_inline_branch_from_detail()

        branch_item = editor._find_tree_item(("dialogue", ((0, 0),)))
        self.assertIsNotNone(branch_item)
        editor._tree.setCurrentItem(branch_item)
        editor._on_add_text_for_selected_dialogue()

        definition = dialog.definition()

        self.assertEqual(
            definition["segments"][0]["options"][0]["next_dialogue_definition"]["segments"][0]["text"],
            "New text segment",
        )

    def test_structured_editor_marks_terminal_segment_and_unreachable_siblings(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {"type": "text", "text": "First"},
                    {"type": "text", "text": "Second"},
                ]
            }
        )

        editor = dialog._structured_editor
        segment_item = editor._find_tree_item(("segment", (), 0))
        self.assertIsNotNone(segment_item)
        editor._tree.setCurrentItem(segment_item)
        editor._segment_end_dialogue_checkbox.setChecked(True)

        first_item = editor._find_tree_item(("segment", (), 0))
        second_item = editor._find_tree_item(("segment", (), 1))
        self.assertIsNotNone(first_item)
        self.assertIsNotNone(second_item)
        self.assertIn("[Ends]", first_item.text(0))
        self.assertIn("[Unreachable]", second_item.text(0))

        definition = dialog.definition()
        self.assertTrue(definition["segments"][0]["end_dialogue"])

    def test_choice_segment_terminal_note_explains_path_finishes_before_close(self):
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
                        ],
                    },
                    {"type": "text", "text": "After"},
                ]
            }
        )

        editor = dialog._structured_editor
        segment_item = editor._find_tree_item(("segment", (), 0))
        self.assertIsNotNone(segment_item)
        editor._tree.setCurrentItem(segment_item)
        editor._segment_end_dialogue_checkbox.setChecked(True)

        self.assertIn(
            "runs the selected option path first",
            editor._segment_end_dialogue_note.text(),
        )

    def test_structured_editor_marks_terminal_option_branch_unreachable(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {
                        "type": "choice",
                        "text": "Pick one",
                        "options": [
                            {
                                "option_id": "read",
                                "text": "Read",
                                "next_dialogue_definition": {
                                    "segments": [
                                        {"type": "text", "text": "Child"},
                                    ]
                                },
                            },
                        ],
                    }
                ]
            }
        )

        editor = dialog._structured_editor
        option_item = editor._find_tree_item(("option", (), 0, 0))
        self.assertIsNotNone(option_item)
        editor._tree.setCurrentItem(option_item)
        editor._option_end_dialogue_checkbox.setChecked(True)

        option_item = editor._find_tree_item(("option", (), 0, 0))
        branch_item = editor._find_tree_item(("dialogue", ((0, 0),)))
        self.assertIsNotNone(option_item)
        self.assertIsNotNone(branch_item)
        self.assertIn("[Ends]", option_item.text(0))
        self.assertIn("[Unreachable]", branch_item.text(0))

        definition = dialog.definition()
        self.assertTrue(definition["segments"][0]["options"][0]["end_dialogue"])

    def test_file_branch_warning_mentions_shallow_inline_copy(self):
        dialog = DialogueDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_definition(
            {
                "segments": [
                    {
                        "type": "choice",
                        "text": "Pick one",
                        "options": [
                            {
                                "option_id": "read",
                                "text": "Read",
                                "next_dialogue_path": "dialogues/lore/warning.json",
                            },
                        ],
                    }
                ]
            }
        )

        editor = dialog._structured_editor
        file_branch_item = editor._find_tree_item(("file_branch", (), 0, 0))
        self.assertIsNotNone(file_branch_item)
        editor._tree.setCurrentItem(file_branch_item)

        self.assertIn("shallow", editor._file_branch_warning.text())

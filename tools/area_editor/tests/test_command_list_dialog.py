"""Tests for the command-list popup editor."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from area_editor.widgets.reference_picker_support import EntityReferencePickerRequest
from area_editor.widgets.command_list_dialog import (
    CommandEditorDialog,
    CommandListDialog,
    _CommandTypePickerDialog,
    _build_command_help_message_box,
    _command_docs_url,
    _command_help_text,
    _open_command_docs,
    summarize_command_list,
)


class TestCommandListDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def doCleanups(self):
        result = super().doCleanups()
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, (CommandEditorDialog, CommandListDialog, _CommandTypePickerDialog)):
                widget.close()
                widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        return result

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

    def test_command_help_text_describes_known_and_unknown_commands(self):
        help_text = _command_help_text("set_entity_var")

        self.assertIn("Write one variable on an entity", help_text)
        self.assertIn("entity_id", help_text)
        self.assertIn("Target entity id", help_text)
        self.assertIn("name", help_text)

        custom_help = _command_help_text("custom_project_plugin_command")
        self.assertIn("No built-in help", custom_help)

    def test_command_type_picker_help_popup_uses_command_help(self):
        dialog = _CommandTypePickerDialog(
            command_names=[
                "set_entity_var",
                "wait_frames",
            ]
        )
        self.addCleanup(dialog.close)

        with patch(
            "area_editor.widgets.command_list_dialog._show_command_help_dialog"
        ) as show_help:
            dialog._show_command_help("set_entity_var")

        show_help.assert_called_once_with(dialog, "set_entity_var")

    def test_command_list_help_popup_uses_selected_command_type(self):
        dialog = CommandListDialog()
        self.addCleanup(dialog.close)
        dialog.load_commands(
            [
                {
                    "type": "set_entity_var",
                    "entity_id": "$instigator_id",
                    "name": "last_used_item",
                }
            ]
        )

        with patch(
            "area_editor.widgets.command_list_dialog._show_command_help_dialog"
        ) as show_help:
            dialog._show_command_help_at(0)

        show_help.assert_called_once_with(dialog, "set_entity_var")

    def test_command_help_dialog_links_documented_commands(self):
        message_box, open_docs_button = _build_command_help_message_box(
            None,
            "set_entity_active_dialogue",
        )
        self.addCleanup(message_box.deleteLater)

        self.assertIsNotNone(open_docs_button)
        self.assertEqual(open_docs_button.text(), "Open Docs")
        self.assertIn("does not open a dialogue by itself", message_box.text())
        self.assertIn('"dialogue_id": "after_gate_opens"', message_box.text())

        docs_url = _command_docs_url("set_entity_active_dialogue")
        self.assertIsNotNone(docs_url)
        self.assertEqual(docs_url.fragment(), "set_entity_active_dialogue")
        self.assertTrue(
            docs_url.toLocalFile().replace("/", os.sep).endswith(
                os.path.join("docs", "authoring", "commands", "dialogue.md")
            )
        )

        camera_box, camera_docs_button = _build_command_help_message_box(
            None,
            "set_camera_policy",
        )
        self.addCleanup(camera_box.deleteLater)

        self.assertIsNotNone(camera_docs_button)
        self.assertIn("real camera policy primitive", camera_box.text())
        self.assertIn('"bounds"', camera_box.text())

        camera_url = _command_docs_url("set_camera_policy")
        self.assertIsNotNone(camera_url)
        self.assertEqual(camera_url.fragment(), "set_camera_policy")
        self.assertTrue(
            camera_url.toLocalFile().replace("/", os.sep).endswith(
                os.path.join("docs", "authoring", "commands", "camera.md")
            )
        )

        movement_box, movement_docs_button = _build_command_help_message_box(
            None,
            "move_entity_position",
        )
        self.addCleanup(movement_box.deleteLater)

        self.assertIsNotNone(movement_docs_button)
        self.assertIn("real pixel movement primitive", movement_box.text())

        movement_url = _command_docs_url("move_entity_position")
        self.assertIsNotNone(movement_url)
        self.assertEqual(movement_url.fragment(), "move_entity_position")
        self.assertTrue(
            movement_url.toLocalFile().replace("/", os.sep).endswith(
                os.path.join("docs", "authoring", "commands", "movement.md")
            )
        )

    def test_open_command_docs_uses_local_docs_url(self):
        parent = QLabel()
        self.addCleanup(parent.close)
        parent._open_docs_file = Mock()

        self.assertTrue(_open_command_docs("set_entity_active_dialogue", parent))

        parent._open_docs_file.assert_called_once()
        opened_path, opened_anchor = parent._open_docs_file.call_args.args
        self.assertTrue(
            str(opened_path).replace("/", os.sep).endswith(
                os.path.join("docs", "authoring", "commands", "dialogue.md")
            )
        )
        self.assertEqual(opened_anchor, "set_entity_active_dialogue")

        with patch(
            "area_editor.widgets.command_list_dialog.QDesktopServices.openUrl",
            return_value=True,
        ) as open_url:
            self.assertTrue(_open_command_docs("set_entity_active_dialogue"))

        open_url.assert_called_once()
        self.assertEqual(open_url.call_args.args[0].fragment(), "set_entity_active_dialogue")

        self.assertFalse(_open_command_docs("custom_project_plugin_command"))

    def test_open_command_docs_uses_foreground_dialog_from_modal_editor(self):
        owner = QLabel()
        self.addCleanup(owner.close)
        owner._open_docs_file = Mock()
        modal_parent = QDialog(owner)
        self.addCleanup(modal_parent.close)
        modal_parent.setModal(True)

        with patch(
            "area_editor.widgets.command_list_dialog.DocumentationDialog.exec",
            return_value=int(QDialog.DialogCode.Rejected),
        ) as exec_docs:
            self.assertTrue(_open_command_docs("set_entity_active_dialogue", modal_parent))

        exec_docs.assert_called_once()
        owner._open_docs_file.assert_not_called()

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

        self.assertEqual(dialog._command_list.count(), 2)
        self.assertEqual(dialog._command_list.item(0).text(), "Standard Commands")
        self.assertEqual(dialog._command_list.item(1).text(), "open_dialogue_session")
        self.assertEqual(
            dialog.selected_command_type(),
            "open_dialogue_session",
        )
        self.assertIn(
            "Start a dialogue session",
            dialog._command_list.item(1).toolTip(),
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

    def test_command_type_picker_search_keeps_group_headers(self):
        dialog = _CommandTypePickerDialog(
            command_names=[
                "open_dialogue_session",
                "run_project_command",
                "set_current_area_var",
                "append_entity_var",
            ],
            suggested_command_names=[
                "open_dialogue_session",
                "run_project_command",
            ],
        )
        self.addCleanup(dialog.close)

        dialog._search_edit.setText("entity")

        texts = [dialog._command_list.item(i).text() for i in range(dialog._command_list.count())]
        self.assertEqual(
            texts,
            [
                "Advanced / Rare Commands",
                "append_entity_var",
            ],
        )

        dialog._search_edit.setText("open")
        texts = [dialog._command_list.item(i).text() for i in range(dialog._command_list.count())]
        self.assertEqual(
            texts,
            [
                "Suggested",
                "open_dialogue_session",
            ],
        )

    def test_command_type_picker_groups_advanced_rare_commands_separately(self):
        dialog = _CommandTypePickerDialog(
            command_names=[
                "wait_frames",
                "set_current_area_var",
                "if",
                "append_current_area_var",
                "run_commands_for_collection",
                "pop_entity_var",
            ]
        )
        self.addCleanup(dialog.close)

        texts = [dialog._command_list.item(i).text() for i in range(dialog._command_list.count())]
        self.assertEqual(
            texts,
            [
                "Standard Commands",
                "wait_frames",
                "set_current_area_var",
                "Advanced / Rare Commands",
                "if",
                "append_current_area_var",
                "run_commands_for_collection",
                "pop_entity_var",
            ],
        )

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

    def test_suggested_command_pages_show_inline_help_notes(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)

        dialog.load_command({"type": "open_dialogue_session"})
        self.assertIn(
            "Start a dialogue session",
            dialog._open_dialogue_summary_note.text(),
        )
        self.assertIn(
            "Inline Dialogue stores the content directly on this command",
            dialog._open_dialogue_source_note.text(),
        )
        self.assertEqual(dialog._edit_inline_dialogue_button.text(), "Write Dialogue...")
        self.assertIn(
            "add text segments",
            dialog._open_dialogue_definition_note.text(),
        )

        dialog.load_command({"type": "run_project_command"})
        self.assertIn(
            "Run a reusable project command by id",
            dialog._run_project_summary_note.text(),
        )
        self.assertIn(
            "Project-relative command id",
            dialog._run_project_command_id_note.text(),
        )

        dialog.load_command({"type": "set_entity_var"})
        self.assertIn(
            "Write one variable on an entity",
            dialog._set_var_summary_note.text(),
        )
        self.assertIn(
            "Target entity id or token",
            dialog._set_var_entity_id_note.text(),
        )

        dialog.load_command({"type": "close_dialogue_session"})
        self.assertIn(
            "Close the currently active dialogue session",
            dialog._close_dialogue_session_summary_note.text(),
        )
        self.assertIn(
            "This command has no parameters",
            dialog._close_dialogue_session_note.text(),
        )

    def test_supported_command_pages_show_global_help_summary_for_non_suggested_commands(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)

        dialog.load_command({"type": "run_parallel"})
        self.assertFalse(dialog._command_summary_label.isHidden())
        self.assertIn(
            "Start multiple child branches together",
            dialog._command_summary_label.text(),
        )
        self.assertFalse(dialog._command_parameter_help_hint.isHidden())
        self.assertIn(
            "Hover parameter labels",
            dialog._command_parameter_help_hint.text(),
        )

        dialog.load_command({"type": "open_dialogue_session"})
        self.assertTrue(dialog._command_summary_label.isHidden())
        self.assertFalse(dialog._command_parameter_help_hint.isHidden())

    def test_supported_command_pages_apply_parameter_help_tooltips(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)

        dialog.load_command({"type": "run_parallel"})
        commands_label = self._find_label(dialog._run_parallel_page, "commands")
        self.assertIn("parallel branch roots", commands_label.toolTip())

        dialog.load_command({"type": "set_camera_policy"})
        follow_label = self._find_label(dialog._set_camera_policy_page, "follow")
        self.assertIn("umbrella camera-policy command", follow_label.toolTip())

        dialog.load_command({"type": "set_entity_field"})
        field_name_label = self._find_label(dialog._set_entity_field_page, "field_name")
        self.assertEqual(
            field_name_label.toolTip(),
            "Engine-owned entity field name.",
        )

    def test_command_editor_tab_switch_is_free_until_apply(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_project_command"})

        with patch("area_editor.widgets.command_list_dialog.QMessageBox.warning") as warning:
            dialog._tabs.setCurrentIndex(1)
            self.assertEqual(dialog._tabs.currentIndex(), 1)
            dialog._tabs.setCurrentIndex(0)
            self.assertEqual(dialog._tabs.currentIndex(), 0)

        warning.assert_not_called()
        self.assertIn('"type": "run_project_command"', dialog._command_json_edit.toPlainText())

    def test_command_editor_apply_from_structured_syncs_json_tab(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_project_command"})

        dialog._project_command_id_edit.setText("commands/system/open_menu")
        self.assertTrue(dialog._apply_button.isEnabled())

        dialog._tabs.setCurrentIndex(1)
        self.assertNotIn("commands/system/open_menu", dialog._command_json_edit.toPlainText())

        dialog._tabs.setCurrentIndex(0)
        dialog._on_apply_clicked()

        dialog._tabs.setCurrentIndex(1)
        parsed = json.loads(dialog._command_json_edit.toPlainText())
        self.assertEqual(parsed["command_id"], "commands/system/open_menu")
        self.assertFalse(dialog._structured_dirty)
        self.assertFalse(dialog._json_dirty)

    def test_command_editor_apply_from_json_syncs_structured_tab(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_project_command"})

        dialog._tabs.setCurrentIndex(1)
        dialog._command_json_edit.setPlainText(
            json.dumps(
                {
                    "type": "run_project_command",
                    "command_id": "commands/system/open_menu",
                    "source_entity_id": "$self_id",
                },
                indent=2,
            )
        )
        self.assertTrue(dialog._apply_button.isEnabled())

        dialog._on_apply_clicked()

        dialog._tabs.setCurrentIndex(0)
        self.assertEqual(dialog._project_command_id_edit.text(), "commands/system/open_menu")
        self.assertEqual(
            dialog._run_project_source_entity_id_field.optional_value(),
            "$self_id",
        )
        self.assertFalse(dialog._structured_dirty)
        self.assertFalse(dialog._json_dirty)

    @staticmethod
    def _find_label(root, text: str) -> QLabel:
        for label in root.findChildren(QLabel):
            if label.text() == text:
                return label
        raise AssertionError(f"Could not find label {text!r}")

    def test_command_editor_apply_warns_before_overwriting_other_tab_draft(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_project_command"})

        dialog._project_command_id_edit.setText("commands/structured")
        dialog._tabs.setCurrentIndex(1)
        dialog._command_json_edit.setPlainText(
            json.dumps(
                {
                    "type": "run_project_command",
                    "command_id": "commands/json",
                },
                indent=2,
            )
        )

        with patch(
            "area_editor.widgets.command_list_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            dialog._on_apply_clicked()

        question.assert_called_once()
        self.assertEqual(dialog._loaded_command, {"type": "run_project_command"})
        self.assertTrue(dialog._structured_dirty)
        self.assertTrue(dialog._json_dirty)

        with patch(
            "area_editor.widgets.command_list_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            dialog._on_apply_clicked()

        self.assertEqual(
            dialog._loaded_command["command_id"],
            "commands/json",
        )
        self.assertFalse(dialog._structured_dirty)
        self.assertFalse(dialog._json_dirty)
        dialog._tabs.setCurrentIndex(0)
        self.assertEqual(dialog._project_command_id_edit.text(), "commands/json")

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

    def test_run_project_advanced_section_expands_when_named_refs_are_set(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/system/open_menu",
                "entity_refs": {
                    "caller": "$self_id",
                },
            }
        )

        self.assertTrue(dialog._run_project_advanced_toggle.isChecked())
        self.assertFalse(dialog._run_project_advanced_widget.isHidden())
        self.assertEqual(
            dialog._run_project_advanced_toggle.text(),
            "Advanced (1 set)",
        )

    def test_run_entity_advanced_section_expands_when_fields_are_set(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_entity_command",
                "entity_id": "$self_id",
                "command_id": "interact",
                "source_entity_id": "$instigator_id",
            }
        )

        self.assertTrue(dialog._run_entity_advanced_toggle.isChecked())
        self.assertFalse(dialog._run_entity_advanced_widget.isHidden())
        self.assertEqual(
            dialog._run_entity_advanced_toggle.text(),
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

    def test_command_editor_builds_named_entity_refs_for_run_project_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/system/open_menu",
            }
        )
        dialog._run_project_advanced_toggle.setChecked(True)
        dialog._run_project_entity_refs_field.add_empty_row()
        row = dialog._run_project_entity_refs_field._rows[0]
        row.name_edit.setText("caller")
        row.value_edit.setText("$self_id")

        command = dialog.command()

        self.assertEqual(
            command["entity_refs"],
            {
                "caller": "$self_id",
            },
        )

    def test_run_project_command_renders_typed_project_inputs(self):
        def inputs_provider(command_id: str):
            if command_id != "commands/animate":
                return None
            return {
                "target_entity": {"type": "entity_id", "label": "Target"},
                "visual": {"type": "visual_id", "of": "target_entity"},
                "animation": {"type": "animation_id", "of": "visual"},
                "frame_count": {"type": "int", "default": 4},
                "wait": {"type": "bool", "default": True},
                "direction": {
                    "type": "enum",
                    "values": ["down", "up"],
                    "default": "up",
                },
            }

        dialog = CommandEditorDialog(project_command_inputs_provider=inputs_provider)
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/animate",
                "target_entity": "npc_1",
                "visual": "body",
                "animation": "talk",
            }
        )

        self.assertFalse(dialog._run_project_inputs_note.isHidden())
        self.assertEqual(
            set(dialog._run_project_input_fields),
            {
                "target_entity",
                "visual",
                "animation",
                "frame_count",
                "wait",
                "direction",
            },
        )

        command = dialog.command()

        self.assertEqual(command["target_entity"], "npc_1")
        self.assertEqual(command["visual"], "body")
        self.assertEqual(command["animation"], "talk")
        self.assertEqual(command["frame_count"], 4)
        self.assertIs(command["wait"], True)
        self.assertEqual(command["direction"], "up")

    def test_run_project_command_scoped_input_pickers_use_parent_inputs(self):
        def inputs_provider(command_id: str):
            if command_id != "commands/animate":
                return None
            return {
                "target_entity": {"type": "entity_id"},
                "visual": {"type": "visual_id", "of": "target_entity"},
                "animation": {"type": "animation_id", "of": "visual"},
            }

        seen: list[tuple[str, EntityReferencePickerRequest]] = []

        def visual_picker(current_value: str, request: EntityReferencePickerRequest):
            seen.append(("visual", request))
            self.assertEqual(current_value, "")
            self.assertEqual(request.parameter_values["entity_id"], "npc_1")
            return "body"

        def animation_picker(current_value: str, request: EntityReferencePickerRequest):
            seen.append(("animation", request))
            self.assertEqual(current_value, "")
            self.assertEqual(request.parameter_values["entity_id"], "npc_1")
            self.assertEqual(request.parameter_values["visual_id"], "body")
            return "talk"

        dialog = CommandEditorDialog(
            project_command_inputs_provider=inputs_provider,
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/animate",
                "target_entity": "npc_1",
            }
        )

        dialog._pick_run_project_visual_input("visual")
        dialog._pick_run_project_animation_input("animation")
        command = dialog.command()

        self.assertEqual([kind for kind, _request in seen], ["visual", "animation"])
        self.assertEqual(command["visual"], "body")
        self.assertEqual(command["animation"], "talk")

    def test_run_project_command_clears_old_known_inputs_when_command_id_changes(self):
        def inputs_provider(command_id: str):
            if command_id == "commands/old":
                return {"target_entity": {"type": "entity_id"}}
            if command_id == "commands/new":
                return {"direction": {"type": "string"}}
            return None

        dialog = CommandEditorDialog(project_command_inputs_provider=inputs_provider)
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/old",
                "target_entity": "npc_1",
            }
        )

        dialog._project_command_id_edit.setText("commands/new")
        dialog._run_project_input_fields["direction"]["edit"].setText("left")
        command = dialog.command()

        self.assertEqual(command["command_id"], "commands/new")
        self.assertEqual(command["direction"], "left")
        self.assertNotIn("target_entity", command)

    def test_command_editor_builds_run_entity_command_with_advanced_fields(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_entity_command"})

        dialog._run_entity_entity_id_edit.setText("$self_id")
        dialog._run_entity_command_id_edit.setText("interact")
        dialog._run_entity_advanced_toggle.setChecked(True)
        dialog._run_entity_source_entity_id_field.set_optional_value("$instigator_id")
        dialog._set_optional_choice_combo_value(
            dialog._run_entity_refs_mode_field,
            "merge",
        )
        dialog._run_entity_entity_refs_field.add_empty_row()
        row = dialog._run_entity_entity_refs_field._rows[0]
        row.name_edit.setText("target")
        row.value_edit.setText("door_1")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "run_entity_command",
                "entity_id": "$self_id",
                "command_id": "interact",
                "source_entity_id": "$instigator_id",
                "refs_mode": "merge",
                "entity_refs": {
                    "target": "door_1",
                },
            },
        )

    def test_run_sequence_advanced_section_expands_when_fields_are_set(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_sequence",
                "source_entity_id": "$instigator_id",
            }
        )

        self.assertTrue(dialog._run_sequence_advanced_toggle.isChecked())
        self.assertFalse(dialog._run_sequence_advanced_widget.isHidden())
        self.assertEqual(
            dialog._run_sequence_advanced_toggle.text(),
            "Advanced (1 set)",
        )

    def test_command_editor_builds_run_sequence_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_sequence"})

        with patch.object(
            dialog,
            "_open_nested_command_list_dialog",
            return_value=[
                {"type": "wait_frames", "frames": 5},
                {"type": "set_entity_var", "entity_id": "$self_id", "name": "ready"},
            ],
        ):
            dialog._on_edit_run_sequence_commands()

        dialog._run_sequence_advanced_toggle.setChecked(True)
        dialog._run_sequence_source_entity_id_field.set_optional_value("$instigator_id")
        dialog._set_optional_choice_combo_value(
            dialog._run_sequence_refs_mode_field,
            "merge",
        )
        dialog._run_sequence_entity_refs_field.add_empty_row()
        row = dialog._run_sequence_entity_refs_field._rows[0]
        row.name_edit.setText("door")
        row.value_edit.setText("door_1")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "run_sequence",
                "commands": [
                    {"type": "wait_frames", "frames": 5},
                    {
                        "type": "set_entity_var",
                        "entity_id": "$self_id",
                        "name": "ready",
                    },
                ],
                "source_entity_id": "$instigator_id",
                "refs_mode": "merge",
                "entity_refs": {
                    "door": "door_1",
                },
            },
        )
        self.assertEqual(
            dialog._run_sequence_commands_field.summary_label.text(),
            "2 commands: wait_frames...",
        )

    def test_command_editor_builds_spawn_flow_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "spawn_flow"})

        with patch.object(
            dialog,
            "_open_nested_command_list_dialog",
            return_value=[
                {"type": "play_audio", "path": "assets/project/sfx/click.wav"},
            ],
        ):
            dialog._on_edit_spawn_flow_commands()

        dialog._spawn_flow_advanced_toggle.setChecked(True)
        dialog._spawn_flow_source_entity_id_field.set_optional_value("$self_id")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "spawn_flow",
                "commands": [
                    {
                        "type": "play_audio",
                        "path": "assets/project/sfx/click.wav",
                    }
                ],
                "source_entity_id": "$self_id",
            },
        )

    def test_command_editor_builds_run_parallel_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_parallel"})

        with patch.object(
            dialog,
            "_open_nested_command_list_dialog",
            return_value=[
                {
                    "type": "run_sequence",
                    "id": "move_branch",
                    "commands": [{"type": "wait_frames", "frames": 3}],
                },
                {
                    "type": "play_audio",
                    "path": "assets/project/sfx/click.wav",
                },
            ],
        ):
            dialog._on_edit_run_parallel_commands()

        dialog._set_optional_choice_combo_value(
            dialog._run_parallel_completion_mode_field,
            "child",
        )
        dialog._sync_run_parallel_completion_visibility()
        dialog._run_parallel_child_id_combo.setEditText("move_branch")
        dialog._run_parallel_advanced_toggle.setChecked(True)
        dialog._run_parallel_source_entity_id_field.set_optional_value("$instigator_id")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "run_parallel",
                "commands": [
                    {
                        "type": "run_sequence",
                        "id": "move_branch",
                        "commands": [{"type": "wait_frames", "frames": 3}],
                    },
                    {
                        "type": "play_audio",
                        "path": "assets/project/sfx/click.wav",
                    },
                ],
                "completion": {
                    "mode": "child",
                    "child_id": "move_branch",
                },
                "source_entity_id": "$instigator_id",
            },
        )
        branch_ids = [
            dialog._run_parallel_child_id_combo.itemText(index)
            for index in range(dialog._run_parallel_child_id_combo.count())
        ]
        self.assertIn("move_branch", branch_ids)

    def test_command_editor_parallel_branch_editor_can_set_branch_id(self):
        dialog = CommandEditorDialog(command_spec_id_label="branch_id")
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "wait_frames", "frames": 2})

        dialog._command_spec_id_field.set_optional_value("branch_a")

        self.assertEqual(
            dialog.command(),
            {
                "type": "wait_frames",
                "frames": 2,
                "id": "branch_a",
            },
        )

    def test_command_editor_builds_run_commands_for_collection_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "run_commands_for_collection"})

        dialog._run_for_each_value_edit.setPlainText(
            '[{"entity_id": "door_1"}, {"entity_id": "door_2"}]'
        )
        dialog._run_for_each_item_param_field.set_optional_value("target")
        dialog._run_for_each_index_param_field.set_optional_value("position")
        with patch.object(
            dialog,
            "_open_nested_command_list_dialog",
            return_value=[
                {
                    "type": "set_entity_var",
                    "entity_id": "$target.entity_id",
                    "name": "activated",
                    "value": True,
                }
            ],
        ):
            dialog._on_edit_run_commands_for_collection_commands()

        dialog._run_for_each_advanced_toggle.setChecked(True)
        dialog._run_for_each_source_entity_id_field.set_optional_value("$instigator_id")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "run_commands_for_collection",
                "value": [
                    {"entity_id": "door_1"},
                    {"entity_id": "door_2"},
                ],
                "item_param": "target",
                "index_param": "position",
                "commands": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$target.entity_id",
                        "name": "activated",
                        "value": True,
                    }
                ],
                "source_entity_id": "$instigator_id",
            },
        )
        self.assertEqual(
            dialog._run_for_each_commands_field.summary_label.text(),
            "1 command: set_entity_var",
        )

    def test_run_commands_for_collection_advanced_section_expands_when_fields_are_set(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_commands_for_collection",
                "source_entity_id": "$instigator_id",
            }
        )

        self.assertTrue(dialog._run_for_each_advanced_toggle.isChecked())
        self.assertFalse(dialog._run_for_each_advanced_widget.isHidden())
        self.assertEqual(
            dialog._run_for_each_advanced_toggle.text(),
            "Advanced (1 set)",
        )

    def test_command_editor_builds_if_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "if"})

        dialog._if_left_edit.setPlainText('"$current_area.gate_open"')
        dialog._if_op_field.setCurrentIndex(dialog._if_op_field.findData("neq"))
        dialog._if_right_edit.setPlainText("false")
        with patch.object(
            dialog,
            "_open_nested_command_list_dialog",
            side_effect=[
                [
                    {
                        "type": "set_entity_field",
                        "entity_id": "gate",
                        "field_name": "present",
                        "value": False,
                    }
                ],
                [
                    {
                        "type": "play_audio",
                        "path": "assets/project/sfx/locked.wav",
                    }
                ],
            ],
        ):
            dialog._on_edit_if_then_commands()
            dialog._on_edit_if_else_commands()

        self.assertEqual(
            dialog.command(),
            {
                "type": "if",
                "left": "$current_area.gate_open",
                "op": "neq",
                "right": False,
                "then": [
                    {
                        "type": "set_entity_field",
                        "entity_id": "gate",
                        "field_name": "present",
                        "value": False,
                    }
                ],
                "else": [
                    {
                        "type": "play_audio",
                        "path": "assets/project/sfx/locked.wav",
                    }
                ],
            },
        )
        self.assertEqual(
            dialog._if_then_commands_field.summary_label.text(),
            "1 command: set_entity_field",
        )
        self.assertEqual(
            dialog._if_else_commands_field.summary_label.text(),
            "1 command: play_audio",
        )

    def test_command_editor_builds_change_area_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "change_area"})

        dialog._change_area_area_id_edit.setText("areas/cave")
        dialog._change_area_entry_id_field.set_optional_value("north_door")
        dialog._change_area_destination_entity_id_field.set_optional_value("$self_id")
        dialog._change_area_transfer_entity_id_field.set_optional_value("$instigator_id")
        dialog._change_area_transfer_entity_ids_field.set_optional_value(
            "$self_id, helper_1"
        )
        dialog._change_area_camera_follow_field.set_patch_state(
            "set",
            {
                "mode": "entity",
                "entity_id": "$instigator_id",
                "offset_x": 12.0,
            },
        )
        dialog._change_area_advanced_toggle.setChecked(True)
        dialog._change_area_allowed_instigator_kinds_field.set_optional_value(
            "player, familiar"
        )
        dialog._change_area_source_entity_id_field.set_optional_value("$self_id")
        dialog._change_area_entity_refs_field.add_empty_row()
        row = dialog._change_area_entity_refs_field._rows[0]
        row.name_edit.setText("caller")
        row.value_edit.setText("$self_id")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "change_area",
                "area_id": "areas/cave",
                "entry_id": "north_door",
                "destination_entity_id": "$self_id",
                "transfer_entity_id": "$instigator_id",
                "transfer_entity_ids": ["$self_id", "helper_1"],
                "camera_follow": {
                    "mode": "entity",
                    "entity_id": "$instigator_id",
                    "offset_x": 12.0,
                },
                "allowed_instigator_kinds": ["player", "familiar"],
                "source_entity_id": "$self_id",
                "entity_refs": {
                    "caller": "$self_id",
                },
            },
        )

    def test_command_editor_builds_new_game_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "new_game"})

        dialog._new_game_area_id_edit.setText("areas/start")
        dialog._new_game_entry_id_field.set_optional_value("spawn")
        dialog._new_game_destination_entity_id_field.set_optional_value("player_1")
        dialog._new_game_source_entity_id_field.set_optional_value("$self_id")
        dialog._new_game_camera_follow_field.set_patch_state(
            "set",
            {
                "mode": "input_target",
                "action": "move",
                "offset_y": -8.0,
            },
        )

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "new_game",
                "area_id": "areas/start",
                "entry_id": "spawn",
                "destination_entity_id": "player_1",
                "source_entity_id": "$self_id",
                "camera_follow": {
                    "mode": "input_target",
                    "action": "move",
                    "offset_y": -8.0,
                },
            },
        )

    def test_command_editor_can_clear_transition_camera_follow(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "change_area"})

        dialog._change_area_area_id_edit.setText("areas/cave")
        dialog._change_area_camera_follow_field.set_patch_state("clear")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "change_area",
                "area_id": "areas/cave",
                "camera_follow": None,
            },
        )

    def test_command_editor_builds_load_game_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "load_game"})

        dialog._load_game_save_path_field.set_optional_value("saves/slot_1.json")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "load_game",
                "save_path": "saves/slot_1.json",
            },
        )

    def test_command_editor_builds_save_game_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "save_game"})

        dialog._save_game_save_path_field.set_optional_value("saves/slot_2.json")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "save_game",
                "save_path": "saves/slot_2.json",
            },
        )

    def test_command_editor_builds_quit_game_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "quit_game"})

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "quit_game",
            },
        )

    def test_command_editor_builds_simulation_runtime_commands(self):
        pause_dialog = CommandEditorDialog()
        self.addCleanup(pause_dialog.close)
        pause_dialog.load_command({"type": "set_simulation_paused"})
        pause_dialog._set_simulation_paused_field.setCurrentIndex(2)
        self.assertEqual(
            pause_dialog.command(),
            {
                "type": "set_simulation_paused",
                "paused": False,
            },
        )

        toggle_dialog = CommandEditorDialog()
        self.addCleanup(toggle_dialog.close)
        toggle_dialog.load_command({"type": "toggle_simulation_paused"})
        self.assertEqual(
            toggle_dialog.command(),
            {
                "type": "toggle_simulation_paused",
            },
        )

        step_dialog = CommandEditorDialog()
        self.addCleanup(step_dialog.close)
        step_dialog.load_command({"type": "step_simulation_tick"})
        self.assertEqual(
            step_dialog.command(),
            {
                "type": "step_simulation_tick",
            },
        )

        scale_dialog = CommandEditorDialog()
        self.addCleanup(scale_dialog.close)
        scale_dialog.load_command({"type": "adjust_output_scale"})
        scale_dialog._adjust_output_scale_delta_spin.setValue(-1)
        self.assertEqual(
            scale_dialog.command(),
            {
                "type": "adjust_output_scale",
                "delta": -1,
            },
        )

    def test_command_editor_builds_step_in_direction_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "step_in_direction"})

        dialog._step_in_direction_entity_id_edit.setText("$self_id")
        dialog._step_in_direction_direction_field.setCurrentText("right")
        dialog._step_in_direction_push_strength_field.set_optional_value(2)
        dialog._step_in_direction_frames_needed_field.set_optional_value(6)
        dialog._step_in_direction_wait_field.setCurrentIndex(1)
        dialog._step_in_direction_persistent_field.setCurrentIndex(2)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "step_in_direction",
                "entity_id": "$self_id",
                "direction": "right",
                "push_strength": 2,
                "frames_needed": 6,
                "wait": True,
                "persistent": False,
            },
        )

    def test_command_editor_builds_entity_position_commands(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_entity_position"})
        dialog._set_position_entity_id_edit.setText("$self_id")
        dialog._set_position_space_field.setCurrentText("world_grid")
        dialog._set_position_x_spin.setValue(3)
        dialog._set_position_y_spin.setValue(-2)
        dialog._set_position_mode_field.setCurrentText("relative")
        dialog._set_position_persistent_field.setCurrentIndex(1)

        self.assertEqual(
            dialog.command(),
            {
                "type": "set_entity_position",
                "entity_id": "$self_id",
                "space": "world_grid",
                "x": 3.0,
                "y": -2.0,
                "mode": "relative",
                "persistent": True,
            },
        )

    def test_command_editor_builds_entity_move_push_and_wait_commands(self):
        move_dialog = CommandEditorDialog()
        self.addCleanup(move_dialog.close)
        move_dialog.load_command({"type": "move_entity_position"})
        move_dialog._move_position_entity_id_edit.setText("$self_id")
        move_dialog._move_position_space_field.setCurrentText("world_pixel")
        move_dialog._move_position_x_spin.setValue(10.0)
        move_dialog._move_position_y_spin.setValue(-6.0)
        move_dialog._move_position_mode_field.setCurrentText("relative")
        move_dialog._move_position_duration_field.set_optional_value(0.5)
        move_dialog._move_position_frames_needed_field.set_optional_value(12)
        move_dialog._move_position_speed_field.set_optional_value(96.0)
        move_dialog._move_position_wait_field.setCurrentIndex(2)
        move_dialog._move_position_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            move_dialog.command(),
            {
                "type": "move_entity_position",
                "entity_id": "$self_id",
                "space": "world_pixel",
                "x": 10.0,
                "y": -6.0,
                "mode": "relative",
                "duration": 0.5,
                "frames_needed": 12,
                "speed_px_per_second": 96.0,
                "wait": False,
                "persistent": True,
            },
        )

        push_dialog = CommandEditorDialog()
        self.addCleanup(push_dialog.close)
        push_dialog.load_command({"type": "push_facing"})
        push_dialog._push_facing_entity_id_edit.setText("$self_id")
        push_dialog._push_facing_direction_field.setCurrentText("left")
        push_dialog._push_facing_push_strength_field.set_optional_value(2)
        push_dialog._push_facing_duration_field.set_optional_value(0.25)
        push_dialog._push_facing_frames_needed_field.set_optional_value(4)
        push_dialog._push_facing_speed_field.set_optional_value(64.0)
        push_dialog._push_facing_wait_field.setCurrentIndex(1)
        push_dialog._push_facing_persistent_field.setCurrentIndex(2)
        self.assertEqual(
            push_dialog.command(),
            {
                "type": "push_facing",
                "entity_id": "$self_id",
                "direction": "left",
                "push_strength": 2,
                "duration": 0.25,
                "frames_needed": 4,
                "speed_px_per_second": 64.0,
                "wait": True,
                "persistent": False,
            },
        )

        wait_dialog = CommandEditorDialog()
        self.addCleanup(wait_dialog.close)
        wait_dialog.load_command({"type": "wait_for_move"})
        wait_dialog._wait_for_move_entity_id_edit.setText("$self_id")
        self.assertEqual(
            wait_dialog.command(),
            {
                "type": "wait_for_move",
                "entity_id": "$self_id",
            },
        )

    def test_command_editor_builds_camera_policy_commands(self):
        state_dialog = CommandEditorDialog()
        self.addCleanup(state_dialog.close)
        state_dialog.load_command({"type": "set_camera_policy"})
        state_dialog._set_camera_policy_follow_field.set_patch_state(
            "set",
            {
                "mode": "entity",
                "entity_id": "$self_id",
                "offset_x": 6.0,
            },
        )
        state_dialog._set_camera_policy_bounds_field.set_patch_state(
            "clear",
        )
        state_dialog._set_camera_policy_deadzone_field.set_patch_state(
            "set",
            {
                "x": 32,
                "y": 16,
                "width": 120,
                "height": 80,
                "space": "viewport_pixel",
            },
        )
        self.assertEqual(
            state_dialog.command(),
            {
                "type": "set_camera_policy",
                "follow": {
                    "mode": "entity",
                    "entity_id": "$self_id",
                    "offset_x": 6.0,
                },
                "bounds": None,
                "deadzone": {
                    "x": 32.0,
                    "y": 16.0,
                    "width": 120.0,
                    "height": 80.0,
                    "space": "viewport_pixel",
                },
            },
        )

        push_dialog = CommandEditorDialog()
        self.addCleanup(push_dialog.close)
        push_dialog.load_command({"type": "push_camera_state"})
        self.assertEqual(push_dialog.command(), {"type": "push_camera_state"})

        pop_dialog = CommandEditorDialog()
        self.addCleanup(pop_dialog.close)
        pop_dialog.load_command({"type": "pop_camera_state"})
        self.assertEqual(pop_dialog.command(), {"type": "pop_camera_state"})

        move_dialog = CommandEditorDialog()
        self.addCleanup(move_dialog.close)
        move_dialog.load_command({"type": "move_camera"})
        move_dialog._move_camera_x_spin.setValue(6.0)
        move_dialog._move_camera_y_spin.setValue(4.0)
        move_dialog._move_camera_space_field.setCurrentText("world_grid")
        move_dialog._move_camera_mode_field.setCurrentText("relative")
        move_dialog._move_camera_duration_field.set_optional_value(0.5)
        move_dialog._move_camera_frames_needed_field.set_optional_value(12)
        move_dialog._move_camera_speed_field.set_optional_value(96.0)
        self.assertEqual(
            move_dialog.command(),
            {
                "type": "move_camera",
                "x": 6.0,
                "y": 4.0,
                "space": "world_grid",
                "mode": "relative",
                "duration": 0.5,
                "frames_needed": 12,
                "speed_px_per_second": 96.0,
            },
        )

    def test_command_editor_builds_play_audio_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "play_audio"})

        dialog._play_audio_path_edit.setText("assets/project/sfx/open.wav")
        dialog._play_audio_volume_field.set_optional_value(0.35)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "play_audio",
                "path": "assets/project/sfx/open.wav",
                "volume": 0.35,
            },
        )

    def test_command_editor_builds_set_sound_volume_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_sound_volume"})

        dialog._set_sound_volume_spin.setValue(0.45)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "set_sound_volume",
                "volume": 0.45,
            },
        )

    def test_command_editor_builds_play_music_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "play_music"})

        dialog._play_music_path_edit.setText("assets/project/music/cave.ogg")
        dialog._play_music_loop_field.setCurrentIndex(2)
        dialog._play_music_volume_field.set_optional_value(0.6)
        dialog._play_music_restart_if_same_field.setCurrentIndex(1)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "play_music",
                "path": "assets/project/music/cave.ogg",
                "loop": False,
                "volume": 0.6,
                "restart_if_same": True,
            },
        )

    def test_command_editor_builds_stop_pause_resume_and_set_music_volume_commands(self):
        stop_dialog = CommandEditorDialog()
        self.addCleanup(stop_dialog.close)
        stop_dialog.load_command({"type": "stop_music"})
        stop_dialog._stop_music_fade_seconds_field.set_optional_value(1.25)
        self.assertEqual(
            stop_dialog.command(),
            {
                "type": "stop_music",
                "fade_seconds": 1.25,
            },
        )

        pause_dialog = CommandEditorDialog()
        self.addCleanup(pause_dialog.close)
        pause_dialog.load_command({"type": "pause_music"})
        self.assertEqual(
            pause_dialog.command(),
            {
                "type": "pause_music",
            },
        )

        resume_dialog = CommandEditorDialog()
        self.addCleanup(resume_dialog.close)
        resume_dialog.load_command({"type": "resume_music"})
        self.assertEqual(
            resume_dialog.command(),
            {
                "type": "resume_music",
            },
        )

        volume_dialog = CommandEditorDialog()
        self.addCleanup(volume_dialog.close)
        volume_dialog.load_command({"type": "set_music_volume"})
        volume_dialog._set_music_volume_spin.setValue(0.8)
        self.assertEqual(
            volume_dialog.command(),
            {
                "type": "set_music_volume",
                "volume": 0.8,
            },
        )

    def test_command_editor_builds_show_screen_image_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "show_screen_image"})

        dialog._show_screen_image_element_id_edit.setText("banner")
        dialog._show_screen_image_path_edit.setText("assets/project/ui/banner.png")
        dialog._show_screen_image_x_spin.setValue(24.0)
        dialog._show_screen_image_y_spin.setValue(16.0)
        dialog._show_screen_image_frame_width_field.set_optional_value(32)
        dialog._show_screen_image_frame_height_field.set_optional_value(32)
        dialog._show_screen_image_frame_field.set_optional_value(2)
        dialog._show_screen_image_layer_field.set_optional_value(4)
        dialog._show_screen_image_anchor_field.setCurrentText("center")
        dialog._show_screen_image_flip_x_field.setCurrentIndex(1)
        dialog._show_screen_image_tint_field.set_optional_value("200, 180, 160")
        dialog._show_screen_image_visible_field.setCurrentIndex(2)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "show_screen_image",
                "element_id": "banner",
                "path": "assets/project/ui/banner.png",
                "x": 24.0,
                "y": 16.0,
                "frame_width": 32,
                "frame_height": 32,
                "frame": 2,
                "layer": 4,
                "anchor": "center",
                "flip_x": True,
                "tint": [200, 180, 160],
                "visible": False,
            },
        )

    def test_command_editor_builds_show_and_set_screen_text_commands(self):
        show_dialog = CommandEditorDialog()
        self.addCleanup(show_dialog.close)
        show_dialog.load_command({"type": "show_screen_text"})

        show_dialog._show_screen_text_element_id_edit.setText("hint")
        show_dialog._show_screen_text_text_edit.setText("Press E")
        show_dialog._show_screen_text_x_spin.setValue(12.0)
        show_dialog._show_screen_text_y_spin.setValue(28.0)
        show_dialog._show_screen_text_layer_field.set_optional_value(3)
        show_dialog._show_screen_text_anchor_field.setCurrentText("top")
        show_dialog._show_screen_text_color_field.set_optional_value("255, 240, 64")
        show_dialog._show_screen_text_font_id_field.set_optional_value("ui_small")
        show_dialog._show_screen_text_max_width_field.set_optional_value(180)
        show_dialog._show_screen_text_visible_field.setCurrentIndex(1)

        self.assertEqual(
            show_dialog.command(),
            {
                "type": "show_screen_text",
                "element_id": "hint",
                "text": "Press E",
                "x": 12.0,
                "y": 28.0,
                "layer": 3,
                "anchor": "top",
                "color": [255, 240, 64],
                "font_id": "ui_small",
                "max_width": 180,
                "visible": True,
            },
        )

        set_dialog = CommandEditorDialog()
        self.addCleanup(set_dialog.close)
        set_dialog.load_command({"type": "set_screen_text"})
        set_dialog._set_screen_text_element_id_edit.setText("hint")
        set_dialog._set_screen_text_text_edit.setText("")

        self.assertEqual(
            set_dialog.command(),
            {
                "type": "set_screen_text",
                "element_id": "hint",
                "text": "",
            },
        )

    def test_command_editor_builds_screen_element_removal_and_animation_commands(self):
        remove_dialog = CommandEditorDialog()
        self.addCleanup(remove_dialog.close)
        remove_dialog.load_command({"type": "remove_screen_element"})
        remove_dialog._remove_screen_element_id_edit.setText("hint")
        self.assertEqual(
            remove_dialog.command(),
            {
                "type": "remove_screen_element",
                "element_id": "hint",
            },
        )

        clear_dialog = CommandEditorDialog()
        self.addCleanup(clear_dialog.close)
        clear_dialog.load_command({"type": "clear_screen_elements"})
        clear_dialog._clear_screen_elements_layer_field.set_optional_value(2)
        self.assertEqual(
            clear_dialog.command(),
            {
                "type": "clear_screen_elements",
                "layer": 2,
            },
        )

        animation_dialog = CommandEditorDialog()
        self.addCleanup(animation_dialog.close)
        animation_dialog.load_command({"type": "play_screen_animation"})
        animation_dialog._play_screen_animation_element_id_edit.setText("banner")
        animation_dialog._play_screen_animation_frame_sequence_edit.setText("0, 1, 2, 1")
        animation_dialog._play_screen_animation_ticks_per_frame_field.set_optional_value(3)
        animation_dialog._play_screen_animation_hold_last_frame_field.setCurrentIndex(2)
        animation_dialog._play_screen_animation_wait_field.setCurrentIndex(1)
        self.assertEqual(
            animation_dialog.command(),
            {
                "type": "play_screen_animation",
                "element_id": "banner",
                "frame_sequence": [0, 1, 2, 1],
                "ticks_per_frame": 3,
                "hold_last_frame": False,
                "wait": True,
            },
        )

        wait_dialog = CommandEditorDialog()
        self.addCleanup(wait_dialog.close)
        wait_dialog.load_command({"type": "wait_for_screen_animation"})
        wait_dialog._wait_for_screen_animation_element_id_edit.setText("banner")
        self.assertEqual(
            wait_dialog.command(),
            {
                "type": "wait_for_screen_animation",
                "element_id": "banner",
            },
        )

    def test_command_editor_builds_entity_animation_commands(self):
        play_dialog = CommandEditorDialog()
        self.addCleanup(play_dialog.close)
        play_dialog.load_command({"type": "play_animation"})
        play_dialog._play_animation_entity_id_edit.setText("npc_1")
        play_dialog._play_animation_visual_id_field.set_optional_value("portrait")
        play_dialog._play_animation_name_edit.setText("blink")
        play_dialog._play_animation_frame_count_field.set_optional_value(4)
        play_dialog._play_animation_duration_ticks_field.set_optional_value(12)
        play_dialog._play_animation_wait_field.setCurrentIndex(2)
        self.assertEqual(
            play_dialog.command(),
            {
                "type": "play_animation",
                "entity_id": "npc_1",
                "visual_id": "portrait",
                "animation": "blink",
                "frame_count": 4,
                "duration_ticks": 12,
                "wait": False,
            },
        )

        wait_dialog = CommandEditorDialog()
        self.addCleanup(wait_dialog.close)
        wait_dialog.load_command({"type": "wait_for_animation"})
        wait_dialog._wait_for_animation_entity_id_edit.setText("npc_1")
        wait_dialog._wait_for_animation_visual_id_field.set_optional_value("portrait")
        self.assertEqual(
            wait_dialog.command(),
            {
                "type": "wait_for_animation",
                "entity_id": "npc_1",
                "visual_id": "portrait",
            },
        )

        stop_dialog = CommandEditorDialog()
        self.addCleanup(stop_dialog.close)
        stop_dialog.load_command({"type": "stop_animation"})
        stop_dialog._stop_animation_entity_id_edit.setText("npc_1")
        stop_dialog._stop_animation_visual_id_field.set_optional_value("portrait")
        stop_dialog._stop_animation_reset_field.setCurrentIndex(1)
        self.assertEqual(
            stop_dialog.command(),
            {
                "type": "stop_animation",
                "entity_id": "npc_1",
                "visual_id": "portrait",
                "reset_to_default": True,
            },
        )

    def test_command_editor_picks_visual_and_animation_ids(self):
        requests: dict[str, EntityReferencePickerRequest] = {}

        def visual_picker(_current, request=None):
            requests["visual"] = request
            return "body"

        def animation_picker(_current, request=None):
            requests["animation"] = request
            return "wave"

        dialog = CommandEditorDialog(
            visual_picker=visual_picker,
            animation_picker=animation_picker,
        )
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "play_animation"})
        dialog._play_animation_entity_id_edit.setText("npc_1")

        dialog._play_animation_visual_id_field.extra_button.click()
        self.assertEqual(dialog._play_animation_visual_id_field.optional_value(), "body")
        self.assertEqual(requests["visual"].parameter_spec["type"], "visual_id")
        self.assertEqual(
            requests["visual"].parameter_values,
            {
                "entity_id": "npc_1",
                "visual_id": "",
            },
        )

        dialog._play_animation_name_pick.click()
        self.assertEqual(dialog._play_animation_name_edit.text(), "wave")
        self.assertEqual(requests["animation"].parameter_spec["type"], "animation_id")
        self.assertEqual(
            requests["animation"].parameter_values,
            {
                "entity_id": "npc_1",
                "visual_id": "body",
                "animation": "",
            },
        )

    def test_command_editor_builds_set_entity_var_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_entity_var"})

        dialog._set_var_entity_id_edit.setText("$self_id")
        dialog._set_var_name_edit.setText("mood")
        dialog._set_var_value_edit.setPlainText('"happy"')
        dialog._set_var_persistent_field.setCurrentIndex(1)
        dialog._set_var_value_mode_field.setCurrentText("raw")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "set_entity_var",
                "entity_id": "$self_id",
                "name": "mood",
                "value": "happy",
                "persistent": True,
                "value_mode": "raw",
            },
        )

    def test_command_editor_builds_current_area_variable_commands(self):
        set_dialog = CommandEditorDialog()
        self.addCleanup(set_dialog.close)
        set_dialog.load_command({"type": "set_current_area_var"})
        set_dialog._set_current_area_var_name_edit.setText("opened")
        set_dialog._set_current_area_var_value_edit.setPlainText("true")
        set_dialog._set_current_area_var_persistent_field.setCurrentIndex(1)
        set_dialog._set_optional_choice_combo_value(
            set_dialog._set_current_area_var_value_mode_field,
            "raw",
        )
        self.assertEqual(
            set_dialog.command(),
            {
                "type": "set_current_area_var",
                "name": "opened",
                "value": True,
                "persistent": True,
                "value_mode": "raw",
            },
        )

    def test_command_editor_builds_entity_var_collection_commands(self):
        append_dialog = CommandEditorDialog()
        self.addCleanup(append_dialog.close)
        append_dialog.load_command({"type": "append_entity_var"})
        append_dialog._append_entity_var_entity_id_edit.setText("$self_id")
        append_dialog._append_entity_var_name_edit.setText("history")
        append_dialog._append_entity_var_value_edit.setPlainText('{"step": 1}')
        append_dialog._append_entity_var_persistent_field.setCurrentIndex(1)
        append_dialog._set_optional_choice_combo_value(
            append_dialog._append_entity_var_value_mode_field,
            "raw",
        )
        self.assertEqual(
            append_dialog.command(),
            {
                "type": "append_entity_var",
                "entity_id": "$self_id",
                "name": "history",
                "value": {"step": 1},
                "persistent": True,
                "value_mode": "raw",
            },
        )

        pop_dialog = CommandEditorDialog()
        self.addCleanup(pop_dialog.close)
        pop_dialog.load_command({"type": "pop_entity_var"})
        pop_dialog._pop_entity_var_entity_id_edit.setText("controller")
        pop_dialog._pop_entity_var_name_edit.setText("dialogue_state_stack")
        pop_dialog._pop_entity_var_store_var_field.set_optional_value("restored_snapshot")
        pop_dialog._pop_entity_var_default_edit.setPlainText("{}")
        pop_dialog._pop_entity_var_persistent_field.setCurrentIndex(2)
        self.assertEqual(
            pop_dialog.command(),
            {
                "type": "pop_entity_var",
                "entity_id": "controller",
                "name": "dialogue_state_stack",
                "store_var": "restored_snapshot",
                "default": {},
                "persistent": False,
            },
        )

    def test_command_editor_builds_entity_field_commands(self):
        single_dialog = CommandEditorDialog()
        self.addCleanup(single_dialog.close)
        single_dialog.load_command({"type": "set_entity_field"})
        single_dialog._set_entity_field_entity_id_edit.setText("$self_id")
        single_dialog._set_entity_field_name_combo.setEditText("visuals.main.flip_x")
        single_dialog._set_entity_field_value_edit.setPlainText("true")
        single_dialog._set_entity_field_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            single_dialog.command(),
            {
                "type": "set_entity_field",
                "entity_id": "$self_id",
                "field_name": "visuals.main.flip_x",
                "value": True,
                "persistent": True,
            },
        )

        bulk_dialog = CommandEditorDialog()
        self.addCleanup(bulk_dialog.close)
        bulk_dialog.load_command({"type": "set_entity_fields"})
        bulk_dialog._set_entity_fields_entity_id_edit.setText("gate_1")
        bulk_dialog._set_entity_fields_payload_edit.setPlainText(
            '{\n  "fields": {"present": false},\n  "variables": {"opened": true}\n}'
        )
        bulk_dialog._set_entity_fields_persistent_field.setCurrentIndex(2)
        self.assertEqual(
            bulk_dialog.command(),
            {
                "type": "set_entity_fields",
                "entity_id": "gate_1",
                "set": {
                    "fields": {"present": False},
                    "variables": {"opened": True},
                },
                "persistent": False,
            },
        )

    def test_command_editor_builds_spawn_entity_commands(self):
        partial_dialog = CommandEditorDialog()
        self.addCleanup(partial_dialog.close)
        partial_dialog.load_command({"type": "spawn_entity"})
        partial_dialog._spawn_entity_id_edit.setText("crate_2")
        partial_dialog._spawn_entity_template_field.set_optional_value(
            "entity_templates/props/crate"
        )
        partial_dialog._spawn_entity_kind_field.set_optional_value("crate")
        partial_dialog._spawn_entity_x_spin.setValue(7)
        partial_dialog._spawn_entity_y_spin.setValue(9)
        partial_dialog._spawn_entity_parameters_edit.setPlainText('{"variant": "red"}')
        partial_dialog._spawn_entity_present_field.setCurrentIndex(2)
        partial_dialog._spawn_entity_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            partial_dialog.command(),
            {
                "type": "spawn_entity",
                "entity_id": "crate_2",
                "template": "entity_templates/props/crate",
                "kind": "crate",
                "x": 7,
                "y": 9,
                "parameters": {"variant": "red"},
                "present": False,
                "persistent": True,
            },
        )

        full_dialog = CommandEditorDialog()
        self.addCleanup(full_dialog.close)
        full_dialog.load_command({"type": "spawn_entity"})
        full_dialog._set_optional_choice_combo_value(
            full_dialog._spawn_entity_mode_combo,
            "full",
        )
        full_dialog._sync_spawn_entity_mode_visibility()
        full_dialog._spawn_entity_full_edit.setPlainText(
            '{\n  "id": "banner_1",\n  "x": 2,\n  "y": 3,\n  "kind": "banner"\n}'
        )
        full_dialog._spawn_entity_present_field.setCurrentIndex(1)
        self.assertEqual(
            full_dialog.command(),
            {
                "type": "spawn_entity",
                "entity": {
                    "id": "banner_1",
                    "x": 2,
                    "y": 3,
                    "kind": "banner",
                },
                "present": True,
            },
        )

    def test_command_editor_builds_cross_area_state_commands(self):
        area_var_dialog = CommandEditorDialog()
        self.addCleanup(area_var_dialog.close)
        area_var_dialog.load_command({"type": "set_area_var"})
        area_var_dialog._set_area_var_area_id_edit.setText("areas/cave")
        area_var_dialog._set_area_var_name_edit.setText("door_open")
        area_var_dialog._set_area_var_value_edit.setPlainText("true")
        self.assertEqual(
            area_var_dialog.command(),
            {
                "type": "set_area_var",
                "area_id": "areas/cave",
                "name": "door_open",
                "value": True,
            },
        )

        area_entity_var_dialog = CommandEditorDialog()
        self.addCleanup(area_entity_var_dialog.close)
        area_entity_var_dialog.load_command({"type": "set_area_entity_var"})
        area_entity_var_dialog._set_area_entity_var_area_id_edit.setText("areas/cave")
        area_entity_var_dialog._set_area_entity_var_entity_id_edit.setText("gate_1")
        area_entity_var_dialog._set_area_entity_var_name_edit.setText("opened")
        area_entity_var_dialog._set_area_entity_var_value_edit.setPlainText("false")
        self.assertEqual(
            area_entity_var_dialog.command(),
            {
                "type": "set_area_entity_var",
                "area_id": "areas/cave",
                "entity_id": "gate_1",
                "name": "opened",
                "value": False,
            },
        )

        area_entity_field_dialog = CommandEditorDialog()
        self.addCleanup(area_entity_field_dialog.close)
        area_entity_field_dialog.load_command({"type": "set_area_entity_field"})
        area_entity_field_dialog._set_area_entity_field_area_id_edit.setText("areas/cave")
        area_entity_field_dialog._set_area_entity_field_entity_id_edit.setText("gate_1")
        area_entity_field_dialog._set_area_entity_field_name_combo.setEditText("present")
        area_entity_field_dialog._set_area_entity_field_value_edit.setPlainText("false")
        self.assertEqual(
            area_entity_field_dialog.command(),
            {
                "type": "set_area_entity_field",
                "area_id": "areas/cave",
                "entity_id": "gate_1",
                "field_name": "present",
                "value": False,
            },
        )

    def test_command_editor_builds_reset_state_commands(self):
        transient_dialog = CommandEditorDialog()
        self.addCleanup(transient_dialog.close)
        transient_dialog.load_command({"type": "reset_transient_state"})
        transient_dialog._reset_transient_entity_id_edit.setText("$self_id")
        transient_dialog._reset_transient_entity_ids_field.set_optional_value("crate_1, crate_2")
        transient_dialog._reset_transient_include_tags_field.set_optional_value("puzzle, resettable")
        transient_dialog._reset_transient_exclude_tags_field.set_optional_value("keep")
        transient_dialog._set_optional_choice_combo_value(
            transient_dialog._reset_transient_apply_field,
            "on_reentry",
        )
        self.assertEqual(
            transient_dialog.command(),
            {
                "type": "reset_transient_state",
                "entity_id": "$self_id",
                "entity_ids": ["crate_1", "crate_2"],
                "include_tags": ["puzzle", "resettable"],
                "exclude_tags": ["keep"],
                "apply": "on_reentry",
            },
        )

        persistent_dialog = CommandEditorDialog()
        self.addCleanup(persistent_dialog.close)
        persistent_dialog.load_command({"type": "reset_persistent_state"})
        persistent_dialog._reset_persistent_include_tags_field.set_optional_value(
            "door, puzzle"
        )
        persistent_dialog._reset_persistent_exclude_tags_field.set_optional_value("keep")
        self.assertEqual(
            persistent_dialog.command(),
            {
                "type": "reset_persistent_state",
                "include_tags": ["door", "puzzle"],
                "exclude_tags": ["keep"],
            },
        )

    def test_command_editor_builds_entity_state_commands(self):
        destroy_dialog = CommandEditorDialog()
        self.addCleanup(destroy_dialog.close)
        destroy_dialog.load_command({"type": "destroy_entity"})
        destroy_dialog._destroy_entity_id_edit.setText("crate_1")
        destroy_dialog._destroy_entity_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            destroy_dialog.command(),
            {
                "type": "destroy_entity",
                "entity_id": "crate_1",
                "persistent": True,
            },
        )

    def test_command_editor_builds_inventory_mutation_commands(self):
        picked_items: list[str] = []

        def item_picker(current_value: str) -> str | None:
            picked_items.append(current_value)
            return "items/copper_key"

        add_dialog = CommandEditorDialog(item_picker=item_picker)
        self.addCleanup(add_dialog.close)
        add_dialog.load_command({"type": "add_inventory_item"})
        add_dialog._add_inventory_entity_id_edit.setText("$self_id")
        add_dialog._add_inventory_item_pick.click()
        add_dialog._add_inventory_quantity_field.set_optional_value(2)
        add_dialog._add_inventory_quantity_mode_field.setCurrentText("partial")
        add_dialog._add_inventory_result_var_field.set_optional_value("pickup_result")
        add_dialog._add_inventory_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            add_dialog.command(),
            {
                "type": "add_inventory_item",
                "entity_id": "$self_id",
                "item_id": "items/copper_key",
                "quantity": 2,
                "quantity_mode": "partial",
                "result_var_name": "pickup_result",
                "persistent": True,
            },
        )

        remove_dialog = CommandEditorDialog(item_picker=item_picker)
        self.addCleanup(remove_dialog.close)
        remove_dialog.load_command({"type": "remove_inventory_item"})
        remove_dialog._remove_inventory_entity_id_edit.setText("player_1")
        remove_dialog._remove_inventory_item_id_edit.setText("items/copper_key")
        remove_dialog._remove_inventory_quantity_field.set_optional_value(1)
        remove_dialog._remove_inventory_quantity_mode_field.setCurrentText("atomic")
        remove_dialog._remove_inventory_result_var_field.set_optional_value("remove_result")
        remove_dialog._remove_inventory_persistent_field.setCurrentIndex(2)
        self.assertEqual(
            remove_dialog.command(),
            {
                "type": "remove_inventory_item",
                "entity_id": "player_1",
                "item_id": "items/copper_key",
                "quantity": 1,
                "quantity_mode": "atomic",
                "result_var_name": "remove_result",
                "persistent": False,
            },
        )

        use_dialog = CommandEditorDialog(item_picker=item_picker)
        self.addCleanup(use_dialog.close)
        use_dialog.load_command({"type": "use_inventory_item"})
        use_dialog._use_inventory_entity_id_edit.setText("player_1")
        use_dialog._use_inventory_item_id_edit.setText("items/potion")
        use_dialog._use_inventory_quantity_field.set_optional_value(3)
        use_dialog._use_inventory_result_var_field.set_optional_value("use_result")
        use_dialog._use_inventory_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            use_dialog.command(),
            {
                "type": "use_inventory_item",
                "entity_id": "player_1",
                "item_id": "items/potion",
                "quantity": 3,
                "result_var_name": "use_result",
                "persistent": True,
            },
        )
        self.assertEqual(picked_items, [""])

    def test_command_editor_builds_inventory_session_commands(self):
        open_dialog = CommandEditorDialog()
        self.addCleanup(open_dialog.close)
        open_dialog.load_command({"type": "open_inventory_session"})
        open_dialog._open_inventory_entity_id_edit.setText("$self_id")
        open_dialog._open_inventory_ui_preset_field.set_optional_value("compact")
        open_dialog._open_inventory_wait_field.setCurrentIndex(2)
        self.assertEqual(
            open_dialog.command(),
            {
                "type": "open_inventory_session",
                "entity_id": "$self_id",
                "ui_preset": "compact",
                "wait": False,
            },
        )

        close_dialog = CommandEditorDialog()
        self.addCleanup(close_dialog.close)
        close_dialog.load_command({"type": "close_inventory_session"})
        self.assertEqual(
            close_dialog.command(),
            {
                "type": "close_inventory_session",
            },
        )

        stacks_dialog = CommandEditorDialog()
        self.addCleanup(stacks_dialog.close)
        stacks_dialog.load_command({"type": "set_inventory_max_stacks"})
        stacks_dialog._set_inventory_max_entity_id_edit.setText("player_1")
        stacks_dialog._set_inventory_max_stacks_spin.setValue(12)
        stacks_dialog._set_inventory_max_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            stacks_dialog.command(),
            {
                "type": "set_inventory_max_stacks",
                "entity_id": "player_1",
                "max_stacks": 12,
                "persistent": True,
            },
        )

    def test_command_editor_builds_entity_command_toggle_commands(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_command_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            return "interact"

        single_dialog = CommandEditorDialog(
            entity_command_picker=entity_command_picker,
            current_entity_id="sign_1",
            current_entity_command_names=["interact", "on_blocked"],
        )
        self.addCleanup(single_dialog.close)
        single_dialog.load_command({"type": "set_entity_command_enabled"})
        single_dialog._set_entity_command_entity_id_edit.setText("$self_id")
        single_dialog._set_entity_command_pick.click()
        single_dialog._set_entity_command_enabled_field.setCurrentIndex(2)
        single_dialog._set_entity_command_persistent_field.setCurrentIndex(1)
        self.assertEqual(
            single_dialog.command(),
            {
                "type": "set_entity_command_enabled",
                "entity_id": "$self_id",
                "command_id": "interact",
                "enabled": False,
                "persistent": True,
            },
        )
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="command_id",
                    current_value="",
                    parameter_spec={
                        "type": "entity_command_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "$self_id",
                        "command_id": "",
                    },
                    entity_command_names_override=("interact", "on_blocked"),
                )
            ],
        )

    def test_command_editor_builds_set_input_route_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_input_route"})

        dialog._set_input_route_action_edit.setText("menu")
        dialog._set_input_route_entity_id_edit.setText("$self_id")
        dialog._set_input_route_command_id_edit.setText("open_menu")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "set_input_route",
                "action": "menu",
                "entity_id": "$self_id",
                "command_id": "open_menu",
            },
        )

    def test_command_editor_builds_push_input_routes_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "push_input_routes"})

        dialog._push_input_routes_actions_field.set_optional_value("interact, menu")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "push_input_routes",
                "actions": ["interact", "menu"],
            },
        )

    def test_command_editor_builds_pop_input_routes_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "pop_input_routes"})

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "pop_input_routes",
            },
        )

    def test_command_editor_builds_wait_frames_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "wait_frames"})

        dialog._wait_frames_spin.setValue(12)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "wait_frames",
                "frames": 12,
            },
        )

    def test_command_editor_builds_wait_seconds_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "wait_seconds"})

        dialog._wait_seconds_spin.setValue(1.5)

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "wait_seconds",
                "seconds": 1.5,
            },
        )

    def test_command_editor_builds_close_dialogue_session_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "close_dialogue_session"})

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "close_dialogue_session",
            },
        )

    def test_command_editor_builds_interact_facing_command(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "interact_facing"})

        dialog._interact_entity_id_edit.setText("$self_id")
        dialog._interact_direction_field.setCurrentText("left")

        command = dialog.command()

        self.assertEqual(
            command,
            {
                "type": "interact_facing",
                "entity_id": "$self_id",
                "direction": "left",
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

    def test_command_editor_named_ref_picker_reuses_shared_callback_shape(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            self.assertEqual(current_value, "")
            return "lever_1"

        dialog = CommandEditorDialog(
            entity_picker=entity_picker,
            current_entity_id="sign_1",
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_project_command",
                "command_id": "commands/system/open_menu",
            }
        )
        dialog._run_project_advanced_toggle.setChecked(True)
        dialog._run_project_entity_refs_field.add_empty_row()
        row = dialog._run_project_entity_refs_field._rows[0]
        row.name_edit.setText("caller")

        row._pick_button.click()

        self.assertEqual(row.value_edit.text(), "lever_1")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="entity_refs.caller",
                    current_value="",
                    parameter_spec={"type": "entity_id"},
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values=None,
                )
            ],
        )

    def test_command_editor_area_picker_reuses_shared_callback_shape(self):
        requests: list[EntityReferencePickerRequest] = []

        def area_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            self.assertEqual(current_value, "")
            return "areas/cave"

        dialog = CommandEditorDialog(
            area_picker=area_picker,
            current_entity_id="sign_1",
            current_area_id="areas/start",
        )
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "change_area"})

        dialog._change_area_area_pick.click()

        self.assertEqual(dialog._change_area_area_id_edit.text(), "areas/cave")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="area_id",
                    current_value="",
                    parameter_spec={"type": "area_id"},
                    current_area_id="areas/start",
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values=None,
                )
            ],
        )

    def test_command_editor_asset_picker_browses_audio_path(self):
        picked_values: list[str] = []

        def asset_picker(current_value: str) -> str | None:
            picked_values.append(current_value)
            return "assets/project/sfx/open.wav"

        dialog = CommandEditorDialog(asset_picker=asset_picker)
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "play_audio"})

        dialog._play_audio_browse.click()

        self.assertEqual(
            dialog._play_audio_path_edit.text(),
            "assets/project/sfx/open.wav",
        )
        self.assertEqual(picked_values, [""])

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
                        "of": "entity_id",
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

    def test_command_editor_entity_dialogue_picker_carries_live_self_dialogue_names(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_dialogue_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            return "dialogue_2"

        dialog = CommandEditorDialog(
            entity_dialogue_picker=entity_dialogue_picker,
            current_entity_id="sign_1",
            current_entity_dialogue_names=["dialogue_1", "dialogue_2"],
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "set_entity_active_dialogue",
                "entity_id": "$self_id",
                "dialogue_id": "dialogue_1",
            }
        )

        dialog._set_active_dialogue_pick.click()

        self.assertEqual(dialog._set_active_dialogue_id_edit.text(), "dialogue_2")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="dialogue_id",
                    current_value="dialogue_1",
                    parameter_spec={
                        "type": "entity_dialogue_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "$self_id",
                        "dialogue_id": "dialogue_1",
                    },
                    entity_dialogue_names_override=("dialogue_1", "dialogue_2"),
                )
            ],
        )

    def test_command_editor_entity_command_picker_uses_target_entity_context(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_command_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            self.assertEqual(current_value, "interact")
            return "bumped_into"

        dialog = CommandEditorDialog(
            entity_command_picker=entity_command_picker,
            current_entity_id="sign_1",
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_entity_command",
                "entity_id": "npc_1",
                "command_id": "interact",
            }
        )

        dialog._run_entity_command_pick.click()

        self.assertEqual(dialog._run_entity_command_id_edit.text(), "bumped_into")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="command_id",
                    current_value="interact",
                    parameter_spec={
                        "type": "entity_command_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "npc_1",
                        "command_id": "interact",
                    },
                )
            ],
        )

    def test_command_editor_entity_command_picker_carries_live_self_command_names(self):
        requests: list[EntityReferencePickerRequest] = []

        def entity_command_picker(
            current_value: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            return "repeat"

        dialog = CommandEditorDialog(
            entity_command_picker=entity_command_picker,
            current_entity_id="sign_1",
            current_entity_command_names=["interact", "repeat"],
        )
        self.addCleanup(dialog.close)
        dialog.load_command(
            {
                "type": "run_entity_command",
                "entity_id": "$self_id",
                "command_id": "interact",
            }
        )

        dialog._run_entity_command_pick.click()

        self.assertEqual(dialog._run_entity_command_id_edit.text(), "repeat")
        self.assertEqual(
            requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="command_id",
                    current_value="interact",
                    parameter_spec={
                        "type": "entity_command_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "$self_id",
                        "command_id": "interact",
                    },
                    entity_command_names_override=("interact", "repeat"),
                )
            ],
        )

    def test_command_editor_can_insert_common_entity_reference_tokens(self):
        dialog = CommandEditorDialog()
        self.addCleanup(dialog.close)
        dialog.load_command({"type": "set_entity_active_dialogue"})

        dialog._apply_entity_reference_token_to_edit(
            dialog._set_active_entity_id_edit,
            "$self_id",
        )
        dialog._apply_entity_reference_token_to_optional_field(
            dialog._actor_id_field,
            "$instigator_id",
        )

        self.assertEqual(dialog._set_active_entity_id_edit.text(), "$self_id")
        self.assertEqual(dialog._actor_id_field.optional_value(), "$instigator_id")

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

"""Tests for the focused project command editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from area_editor.widgets.project_command_editor_widget import ProjectCommandEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestProjectCommandEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_focused_edits_build_typed_inputs_and_preserve_deferred_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "play_npc_animation.json"
            _write_json(
                command_path,
                {
                    "params": ["target_entity"],
                    "deferred_param_shapes": {"hook": "command_payload"},
                    "commands": [],
                },
            )

            widget = ProjectCommandEditorWidget(
                "commands/play_npc_animation",
                command_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            target_row = fields._rows[0]
            target_row._type_combo.setCurrentText("entity_id")

            visual_row = fields._add_input_row("visual", {"type": "visual_id"})
            visual_row._of_combo.setCurrentIndex(visual_row._of_combo.findData("target_entity"))
            visual_row._default_edit.setText("body")

            animation_row = fields._add_input_row("animation", {"type": "animation_id"})
            animation_row._of_combo.setCurrentIndex(animation_row._of_combo.findData("visual"))
            animation_row._default_edit.setText("idle")

            widget.save_to_file()

            saved = json.loads(command_path.read_text(encoding="utf-8"))
            self.assertNotIn("params", saved)
            self.assertEqual(
                saved["inputs"],
                {
                    "target_entity": {
                        "type": "entity_id",
                    },
                    "visual": {
                        "type": "visual_id",
                        "of": "target_entity",
                        "default": "body",
                    },
                    "animation": {
                        "type": "animation_id",
                        "of": "visual",
                        "default": "idle",
                    },
                },
            )
            self.assertEqual(saved["deferred_param_shapes"], {"hook": "command_payload"})
            self.assertEqual(saved["commands"], [])

    def test_deferred_param_shapes_are_collapsed_under_advanced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "advanced.json"
            _write_json(
                command_path,
                {
                    "inputs": {},
                    "deferred_param_shapes": {"hook": "command_payload"},
                    "commands": [],
                },
            )

            widget = ProjectCommandEditorWidget("commands/advanced", command_path)
            self.addCleanup(widget.close)
            fields = widget.fields_editor

            self.assertTrue(fields._advanced_widget.isHidden())
            self.assertEqual(fields._advanced_toggle.text(), "Advanced (1 set)")

            fields._advanced_toggle.setChecked(True)

            self.assertFalse(fields._advanced_widget.isHidden())
            self.assertEqual(
                fields._deferred_param_shapes_edit.toPlainText().strip(),
                '{\n  "hook": "command_payload"\n}',
            )

    def test_enum_values_field_is_editable_when_row_type_is_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "choose_direction.json"
            _write_json(
                command_path,
                {
                    "inputs": {
                        "direction": {
                            "type": "enum",
                            "values": ["up", "down"],
                        },
                    },
                    "commands": [],
                },
            )

            widget = ProjectCommandEditorWidget("commands/choose_direction", command_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            row = widget.fields_editor._rows[0]

            self.assertTrue(row._values_edit.isEnabled())
            self.assertFalse(row._values_edit.isReadOnly())

    def test_focused_save_strips_legacy_input_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "labeled.json"
            _write_json(
                command_path,
                {
                    "inputs": {
                        "direction": {
                            "type": "enum",
                            "label": "Direction",
                            "values": ["up", "down"],
                        },
                    },
                    "commands": [],
                },
            )

            widget = ProjectCommandEditorWidget("commands/labeled", command_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)
            widget.fields_editor._set_dirty(True)
            widget.save_to_file()

            saved = json.loads(command_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["inputs"],
                {
                    "direction": {
                        "type": "enum",
                        "values": ["up", "down"],
                    },
                },
            )

    def test_focused_save_preserves_explicit_null_input_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "optional_timing.json"
            _write_json(
                command_path,
                {
                    "inputs": {
                        "duration": {
                            "type": "float",
                            "default": None,
                        },
                        "persistent": {
                            "type": "bool",
                            "default": None,
                        },
                    },
                    "commands": [],
                },
            )

            widget = ProjectCommandEditorWidget("commands/optional_timing", command_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)
            widget.fields_editor._set_dirty(True)
            widget.save_to_file()

            saved = json.loads(command_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["inputs"]["duration"]["default"], None)
            self.assertEqual(saved["inputs"]["persistent"]["default"], None)

    def test_command_body_edits_through_command_list_dialog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "show_message.json"
            _write_json(
                command_path,
                {
                    "inputs": {},
                    "commands": [
                        {
                            "type": "wait_frames",
                            "frames": 1,
                        }
                    ],
                },
            )
            replacement_commands = [
                {
                    "type": "show_screen_text",
                    "element_id": "message",
                    "text": "Hello",
                    "x": 0,
                    "y": 0,
                }
            ]

            class FakeCommandListDialog:
                loaded_commands: object = None

                def __init__(self, *args, **kwargs) -> None:
                    self.window_title = ""

                def setWindowTitle(self, title: str) -> None:
                    self.window_title = title

                def load_commands(self, commands: object) -> None:
                    FakeCommandListDialog.loaded_commands = commands

                def exec(self) -> QDialog.DialogCode:
                    return QDialog.DialogCode.Accepted

                def commands(self) -> list[dict[str, object]]:
                    return replacement_commands

            widget = ProjectCommandEditorWidget("commands/show_message", command_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            with patch(
                "area_editor.widgets.project_command_editor_widget.CommandListDialog",
                FakeCommandListDialog,
            ):
                widget.fields_editor._on_edit_commands()
            widget.save_to_file()

            saved = json.loads(command_path.read_text(encoding="utf-8"))
            self.assertEqual(
                FakeCommandListDialog.loaded_commands,
                [
                    {
                        "type": "wait_frames",
                        "frames": 1,
                    }
                ],
            )
            self.assertEqual(saved["commands"], replacement_commands)

    def test_command_body_edit_preserves_unsupported_inputs_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command_path = Path(tmp) / "raw_inputs.json"
            _write_json(
                command_path,
                {
                    "inputs": ["not", "an", "object"],
                    "commands": [],
                },
            )
            replacement_commands = [{"type": "wait_frames", "frames": 2}]

            class FakeCommandListDialog:
                def __init__(self, *args, **kwargs) -> None:
                    pass

                def setWindowTitle(self, title: str) -> None:
                    pass

                def load_commands(self, commands: object) -> None:
                    pass

                def exec(self) -> QDialog.DialogCode:
                    return QDialog.DialogCode.Accepted

                def commands(self) -> list[dict[str, object]]:
                    return replacement_commands

            widget = ProjectCommandEditorWidget("commands/raw_inputs", command_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            with patch(
                "area_editor.widgets.project_command_editor_widget.CommandListDialog",
                FakeCommandListDialog,
            ):
                widget.fields_editor._on_edit_commands()
            widget.save_to_file()

            saved = json.loads(command_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["inputs"], ["not", "an", "object"])
            self.assertEqual(saved["commands"], replacement_commands)

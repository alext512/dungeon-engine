"""Tests for the focused entity-template editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTableWidgetItem
from PySide6.QtCore import Qt

from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget
from area_editor.widgets.entity_visuals_editor import VisualDefinitionDialog


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestEntityTemplateEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_legacy_input_map_is_hidden_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "input_map": {"interact": 1},
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertTrue(widget.fields_editor._input_map_warning.isHidden())
            self.assertTrue(widget.fields_editor._input_map_text.isReadOnly())

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["input_map"], {"interact": 1})

    def test_invalid_entity_commands_uses_warning_and_preserves_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "entity_commands": {
                        "interact": {
                            "commands": [{"type": "show_message", "text": "Hi"}],
                        },
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertFalse(widget.fields_editor._entity_commands_warning.isHidden())
            self.assertTrue(widget.fields_editor._entity_commands_text.isReadOnly())

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "commands": [{"type": "show_message", "text": "Hi"}],
                    },
                },
            )

    def test_invalid_inventory_uses_warning_and_preserves_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "inventory": {
                        "max_stacks": 1,
                        "stacks": [{"item_id": "items/copper_key", "quantity": 0}],
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertFalse(widget.fields_editor._inventory_warning.isHidden())
            self.assertTrue(widget.fields_editor._inventory_stacks_text.isReadOnly())

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["inventory"],
                {
                    "max_stacks": 1,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 0}],
                },
            )

    def test_invalid_color_uses_warning_and_preserves_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "color": [255, "warm", 160],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertFalse(widget.fields_editor._color_warning.isHidden())
            self.assertFalse(widget.fields_editor._color_check.isEnabled())

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["color"], [255, "warm", 160])

    def test_invalid_dialogues_uses_warning_and_preserves_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "dialogues": {
                        "broken": {
                            "dialogue_path": "dialogues/intro",
                            "dialogue_definition": {"segments": []},
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertFalse(widget.fields_editor._dialogues_warning.isHidden())
            self.assertFalse(widget.fields_editor._dialogues_edit_button.isEnabled())

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["dialogues"],
                {
                    "broken": {
                        "dialogue_path": "dialogues/intro",
                        "dialogue_definition": {"segments": []},
                    }
                },
            )

    def test_invalid_visuals_uses_warning_and_preserves_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": ["not an object"],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            self.assertFalse(widget.fields_editor._visuals_warning.isHidden())
            self.assertFalse(widget.fields_editor._visuals_editor._editing_enabled)

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["visuals"], ["not an object"])

    def test_structured_fields_can_update_visuals_without_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            visuals = widget.fields_editor._visuals_editor
            with patch.object(
                visuals,
                "_open_visual_dialog",
                return_value={
                    "id": "body",
                    "path": "assets/project/sprites/player.png",
                    "frame_width": "$frame_width",
                    "frame_height": 16,
                    "frames": [0, 1, 2],
                    "default_animation": "idle_down",
                    "default_animation_by_facing": {
                        "up": "idle_up",
                        "down": "idle_down",
                    },
                    "animation_fps": 8,
                    "animate_when_moving": True,
                    "flip_x": False,
                    "visible": True,
                    "tint": [255, 240, 200],
                    "offset_x": -1,
                    "offset_y": 2,
                    "draw_order": 3,
                    "animations": {
                        "idle_down": {"frames": [0]},
                        "walk_down": {
                            "frames": [0, 1, 2],
                            "preserve_phase": True,
                        },
                    },
                },
            ):
                visuals._add_visual_after(None)

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["visuals"],
                [
                    {
                        "id": "body",
                        "path": "assets/project/sprites/player.png",
                        "frame_width": "$frame_width",
                        "frame_height": 16,
                        "frames": [0, 1, 2],
                        "default_animation": "idle_down",
                        "default_animation_by_facing": {
                            "up": "idle_up",
                            "down": "idle_down",
                        },
                        "animation_fps": 8,
                        "animate_when_moving": True,
                        "flip_x": False,
                        "visible": True,
                        "tint": [255, 240, 200],
                        "offset_x": -1,
                        "offset_y": 2,
                        "draw_order": 3,
                        "animations": {
                            "idle_down": {"frames": [0]},
                            "walk_down": {
                                "frames": [0, 1, 2],
                                "preserve_phase": True,
                            },
                        },
                    }
                ],
            )

    def test_visual_definition_dialog_builds_common_visual_fields(self) -> None:
        dialog = VisualDefinitionDialog()
        self.addCleanup(dialog.close)
        dialog.load_visual({})

        dialog._id_edit.setText("body")
        dialog._path_edit.setText("assets/project/sprites/player.png")
        dialog._frame_width_edit.setText("$frame_width")
        dialog._frame_height_edit.setText("16")
        dialog._frames_edit.setText("0, 1, 2")
        dialog._default_animation_edit.setText("idle_down")
        dialog._facing_edits["down"].setText("idle_down")
        dialog._facing_edits["up"].setText("idle_up")
        dialog._animation_fps_edit.setText("8")
        dialog._animate_when_moving_check.setCheckState(Qt.CheckState.Checked)
        dialog._flip_x_check.setCheckState(Qt.CheckState.Unchecked)
        dialog._visible_check.setCheckState(Qt.CheckState.Checked)
        dialog._tint_edit.setText("255, 240, 200")
        dialog._offset_x_edit.setText("-1")
        dialog._offset_y_edit.setText("2")
        dialog._draw_order_edit.setText("3")
        dialog._visual["animations"] = {
            "idle_down": {"frames": [0]},
            "walk_down": {"frames": [0, 1, 2], "preserve_phase": True},
        }

        self.assertEqual(
            dialog.visual(),
            {
                "id": "body",
                "path": "assets/project/sprites/player.png",
                "frame_width": "$frame_width",
                "frame_height": 16,
                "frames": [0, 1, 2],
                "default_animation": "idle_down",
                "default_animation_by_facing": {
                    "up": "idle_up",
                    "down": "idle_down",
                },
                "animation_fps": 8,
                "animate_when_moving": True,
                "flip_x": False,
                "visible": True,
                "tint": [255, 240, 200],
                "offset_x": -1,
                "offset_y": 2,
                "draw_order": 3,
                "animations": {
                    "idle_down": {"frames": [0]},
                    "walk_down": {
                        "frames": [0, 1, 2],
                        "preserve_phase": True,
                    },
                },
            },
        )

    def test_visuals_list_uses_context_menu_and_drag_reorder_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [
                        {"id": "main", "path": "main.png"},
                        {"id": "shadow", "path": "shadow.png"},
                        {"id": "spark", "path": "spark.png"},
                    ],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            visuals = widget.fields_editor._visuals_editor
            self.assertEqual(
                visuals._list.contextMenuPolicy(),
                Qt.ContextMenuPolicy.CustomContextMenu,
            )
            self.assertTrue(visuals._list.dragEnabled())

            visuals._duplicate_visual_at(1)
            visuals._remove_visual_at(0)
            visuals._on_visual_order_changed([2, 0, 1])
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [visual["id"] for visual in saved["visuals"]],
                ["spark", "shadow", "shadow_copy"],
            )

    def test_structured_fields_can_update_named_dialogues_and_active_dialogue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "variables": {"seen": False},
                    "dialogues": {
                        "starting_dialogue": {
                            "dialogue_definition": {
                                "segments": [{"type": "text", "text": "Hello"}]
                            }
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            updated_dialogues = {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                },
                "repeat_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Back again?"}]
                    }
                },
            }

            with patch.object(
                widget.fields_editor,
                "_open_entity_dialogues_dialog",
                return_value=(updated_dialogues, "repeat_dialogue"),
            ):
                widget.fields_editor._dialogues_edit_button.click()

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["dialogues"], updated_dialogues)
            self.assertEqual(
                saved["variables"],
                {"seen": False, "active_dialogue": "repeat_dialogue"},
            )

    def test_named_dialogue_rename_updates_self_targeting_template_entity_command_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "variables": {"active_dialogue": "starting_dialogue"},
                    "dialogues": {
                        "starting_dialogue": {
                            "dialogue_definition": {
                                "segments": [{"type": "text", "text": "Hello"}]
                            }
                        }
                    },
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "open_entity_dialogue",
                                    "entity_id": "$self_id",
                                    "dialogue_id": "starting_dialogue",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            with patch.object(
                widget.fields_editor,
                "_open_entity_dialogues_dialog",
                return_value=(
                    {
                        "intro_dialogue": {
                            "dialogue_definition": {
                                "segments": [{"type": "text", "text": "Hello"}]
                            }
                        }
                    },
                    "intro_dialogue",
                    {"starting_dialogue": "intro_dialogue"},
                ),
            ):
                widget.fields_editor._dialogues_edit_button.click()

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["variables"]["active_dialogue"], "intro_dialogue")
            self.assertEqual(
                saved["entity_commands"]["interact"]["commands"][0]["dialogue_id"],
                "intro_dialogue",
            )

    def test_structured_fields_can_update_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "space": "screen",
                    "visuals": [],
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._scope_combo.setCurrentText("global")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["space"], "screen")
            self.assertEqual(saved["scope"], "global")
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )

    def test_structured_fields_can_update_common_template_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "kind": "old_console",
                    "visuals": [],
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            fields._kind_edit.setText("console")
            fields._space_combo.setCurrentText("screen")
            fields._scope_combo.setCurrentText("global")
            fields._tags_edit.setText("ui, terminal")
            fields._facing_combo.setCurrentText("left")
            fields._solid_check.setChecked(True)
            fields._pushable_check.setChecked(True)
            fields._weight_spin.setValue(4)
            fields._push_strength_spin.setValue(2)
            fields._collision_push_strength_spin.setValue(1)
            fields._interactable_check.setChecked(True)
            fields._interaction_priority_spin.setValue(7)
            fields._present_check.setChecked(False)
            fields._visible_check.setChecked(False)
            fields._entity_commands_enabled_check.setChecked(False)
            fields._color_check.setChecked(True)
            fields._color_red_spin.setValue(120)
            fields._color_green_spin.setValue(90)
            fields._color_blue_spin.setValue(40)
            fields._render_order_spin.setValue(12)
            fields._y_sort_check.setChecked(True)
            fields._sort_y_offset_spin.setValue(2.5)
            fields._stack_order_spin.setValue(3)
            fields._variables_text.setPlainText('{"used": false}')
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["kind"], "console")
            self.assertEqual(saved["space"], "screen")
            self.assertEqual(saved["scope"], "global")
            self.assertEqual(saved["tags"], ["ui", "terminal"])
            self.assertEqual(saved["facing"], "left")
            self.assertTrue(saved["solid"])
            self.assertTrue(saved["pushable"])
            self.assertEqual(saved["weight"], 4)
            self.assertEqual(saved["push_strength"], 2)
            self.assertEqual(saved["collision_push_strength"], 1)
            self.assertTrue(saved["interactable"])
            self.assertEqual(saved["interaction_priority"], 7)
            self.assertFalse(saved["present"])
            self.assertFalse(saved["visible"])
            self.assertFalse(saved["entity_commands_enabled"])
            self.assertEqual(saved["color"], [120, 90, 40])
            self.assertEqual(saved["render_order"], 12)
            self.assertTrue(saved["y_sort"])
            self.assertEqual(saved["sort_y_offset"], 2.5)
            self.assertEqual(saved["stack_order"], 3)
            self.assertEqual(saved["variables"], {"used": False})
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )

    def test_variables_table_updates_template_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "pickup.json"
            _write_json(
                template_path,
                {
                    "kind": "item_pickup",
                    "space": "world",
                    "variables": {"opened": False},
                    "visuals": [],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/item_pickup",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            fields._variables_table.set_variables({})
            fields._variables_table.add_variable(
                "item_id",
                "items/consumables/glimmer_berry",
            )
            fields._variables_table.add_variable("quantity", "1")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["variables"],
                {
                    "item_id": "items/consumables/glimmer_berry",
                    "quantity": 1,
                },
            )

    def test_space_switch_keeps_implicit_render_defaults_implicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "backdrop.json"
            _write_json(
                template_path,
                {
                    "kind": "backdrop",
                    "visuals": [],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/backdrop",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._space_combo.setCurrentText("screen")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["space"], "screen")
            self.assertNotIn("render_order", saved)
            self.assertNotIn("y_sort", saved)

    def test_structured_fields_preserve_existing_input_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "input_map": {
                        "interact": "interact",
                    },
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._kind_edit.setText("console_terminal")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["input_map"],
                {
                    "interact": "interact",
                },
            )
            self.assertEqual(saved["kind"], "console_terminal")
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )

    def test_input_map_table_is_not_written_by_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._kind_edit.setText("console")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertNotIn("input_map", saved)
            self.assertEqual(saved["kind"], "console")

    def test_structured_fields_can_update_entity_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "entity_commands": {
                        "interact": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/old",
                            }
                        ],
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._entity_commands_text.setPlainText(
                '{\n'
                '  "interact": [\n'
                '    {"type": "run_project_command", "command_id": "commands/system/open_gate"}\n'
                "  ],\n"
                '  "disabled_example": {\n'
                '    "enabled": false,\n'
                '    "commands": []\n'
                "  }\n"
                "}"
            )
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": [
                        {
                            "type": "run_project_command",
                            "command_id": "commands/system/open_gate",
                        }
                    ],
                    "disabled_example": {
                        "enabled": False,
                        "commands": [],
                    },
                },
            )

    def test_entity_command_controls_can_add_named_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)
            fields = widget.fields_editor

            with patch.object(
                fields,
                "_prompt_entity_command_name",
                return_value="interact",
            ), patch.object(
                fields,
                "_open_entity_command_list_dialog",
                return_value=[
                    {
                        "type": "run_project_command",
                        "command_id": "commands/system/open_gate",
                    }
                ],
            ):
                fields._on_add_entity_command_clicked()

            widget.save_to_file()
            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": [
                        {
                            "type": "run_project_command",
                            "command_id": "commands/system/open_gate",
                        }
                    ],
                },
            )

    def test_entity_command_name_prompt_suggests_standard_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            fields = widget.fields_editor
            captured: dict[str, object] = {}

            def fake_get_item(parent, title, label, items, current, editable):
                captured["label"] = label
                captured["items"] = list(items)
                captured["current"] = current
                captured["editable"] = editable
                return "on_occupant_enter", True

            with patch(
                "area_editor.widgets.entity_template_editor_widget.QInputDialog.getItem",
                fake_get_item,
            ):
                selected = fields._prompt_entity_command_name(
                    title="Add Entity Command",
                    existing_names={"interact"},
                )

            self.assertEqual(selected, "on_occupant_enter")
            self.assertIn("type a custom name", str(captured["label"]))
            self.assertNotIn("interact", captured["items"])
            self.assertIn("on_blocked", captured["items"])
            self.assertIn("on_occupant_enter", captured["items"])
            self.assertIn("on_occupant_leave", captured["items"])
            self.assertIn("custom_command", captured["items"])
            self.assertEqual(captured["current"], 0)
            self.assertTrue(captured["editable"])

    def test_structured_fields_can_update_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "visuals": [],
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._inventory_check.setChecked(True)
            widget.fields_editor._inventory_max_stacks_spin.setValue(2)
            widget.fields_editor._inventory_stacks_text.setPlainText(
                '[\n'
                '  {"item_id": "items/copper_key", "quantity": 1},\n'
                '  {"item_id": "items/light_orb", "quantity": 2}\n'
                ']'
            )
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["inventory"],
                {
                    "max_stacks": 2,
                    "stacks": [
                        {"item_id": "items/copper_key", "quantity": 1},
                        {"item_id": "items/light_orb", "quantity": 2},
                    ],
                },
            )
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )

    def test_inventory_stack_table_can_update_stacks_without_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            fields._inventory_check.setChecked(True)
            fields._inventory_max_stacks_spin.setValue(2)
            fields._on_add_inventory_stack_clicked()
            fields._inventory_stacks_table.setItem(
                0,
                0,
                QTableWidgetItem("items/copper_key"),
            )
            fields._inventory_stacks_table.setItem(0, 1, QTableWidgetItem("1"))
            fields._on_add_inventory_stack_clicked()
            fields._inventory_stacks_table.setItem(
                1,
                0,
                QTableWidgetItem("items/light_orb"),
            )
            fields._inventory_stacks_table.setItem(1, 1, QTableWidgetItem("2"))
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["inventory"],
                {
                    "max_stacks": 2,
                    "stacks": [
                        {"item_id": "items/copper_key", "quantity": 1},
                        {"item_id": "items/light_orb", "quantity": 2},
                    ],
                },
            )

    def test_persistence_table_can_update_variable_overrides_without_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "variables": {
                        "shake_timer": 0,
                        "times_pushed": 0,
                    },
                    "visuals": [],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            fields._entity_state_check.setChecked(True)

            self.assertEqual(fields._persistence_variables_table.rowCount(), 2)
            self.assertEqual(
                [
                    fields._persistence_variables_table.item(row, 0).text()
                    for row in range(fields._persistence_variables_table.rowCount())
                ],
                ["shake_timer", "times_pushed"],
            )

            shake_combo = fields._persistence_variables_table.cellWidget(0, 1)
            shake_combo.setCurrentIndex(shake_combo.findData(False))

            pushed_combo = fields._persistence_variables_table.cellWidget(1, 1)
            pushed_combo.setCurrentIndex(pushed_combo.findData(True))

            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["persistence"],
                {
                    "entity_state": True,
                    "variables": {
                        "shake_timer": False,
                        "times_pushed": True,
                    },
                },
            )

    def test_persistence_table_tracks_variables_from_basics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(template_path, {"visuals": []})

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            fields = widget.fields_editor
            fields._variables_text.setPlainText(
                '{\n  "opened": false,\n  "flash_timer": 0\n}'
            )

            self.assertEqual(fields._persistence_variables_table.rowCount(), 2)
            self.assertEqual(
                [
                    fields._persistence_variables_table.item(row, 0).text()
                    for row in range(fields._persistence_variables_table.rowCount())
                ],
                ["opened", "flash_timer"],
            )
            for row in range(fields._persistence_variables_table.rowCount()):
                combo = fields._persistence_variables_table.cellWidget(row, 1)
                self.assertEqual(
                    combo.currentData(),
                    None,
                )

            opened_combo = fields._persistence_variables_table.cellWidget(0, 1)
            opened_combo.setCurrentIndex(opened_combo.findData(True))
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["persistence"],
                {"entity_state": False, "variables": {"opened": True}},
            )

    def test_structured_fields_preserve_unmanaged_engine_owned_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "space": "screen",
                    "scope": "global",
                    "render_order": 7,
                    "y_sort": False,
                    "color": [255, 240, 200],
                    "inventory": {
                        "max_stacks": 3,
                        "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                    },
                    "input_map": {"confirm": "interact"},
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                    "visuals": [],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._visuals_text.setPlainText(
                '[{"id": "main", "path": "assets/project/ui/console.png"}]'
            )
            widget.fields_editor._entity_state_check.setChecked(True)
            widget.fields_editor._persistence_variables_text.setPlainText(
                '{"last_used": true}'
            )
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["space"], "screen")
            self.assertEqual(saved["scope"], "global")
            self.assertEqual(saved["render_order"], 7)
            self.assertFalse(saved["y_sort"])
            self.assertEqual(saved["color"], [255, 240, 200])
            self.assertEqual(
                saved["inventory"],
                {
                    "max_stacks": 3,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                },
            )
            self.assertEqual(saved["input_map"], {"confirm": "interact"})
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )
            self.assertEqual(
                saved["visuals"],
                [{"id": "main", "path": "assets/project/ui/console.png"}],
            )
            self.assertEqual(
                saved["persistence"],
                {
                    "entity_state": True,
                    "variables": {"last_used": True},
                },
            )

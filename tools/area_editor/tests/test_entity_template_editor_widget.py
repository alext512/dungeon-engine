"""Tests for the focused entity-template editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestEntityTemplateEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_invalid_input_map_uses_warning_and_preserves_original_value(self) -> None:
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

            self.assertFalse(widget.fields_editor._input_map_warning.isHidden())
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

    def test_structured_fields_can_update_input_map(self) -> None:
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

            widget.fields_editor._input_map_text.setPlainText(
                '{\n  "interact": "interact",\n  "menu": "open_menu"\n}'
            )
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["input_map"],
                {
                    "interact": "interact",
                    "menu": "open_menu",
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

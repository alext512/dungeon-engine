"""Tests for the structured entity-instance fields editor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument
from area_editor.widgets.entity_instance_json_panel import (
    EntityInstanceJsonPanel,
    EntityReferencePickerRequest,
)


class TestEntityInstanceFieldsEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = EntityInstanceJsonPanel()
        self.addCleanup(self.panel.close)
        self.panel.set_area_bounds(12, 9)
        self.catalog = TemplateCatalog()
        self.catalog._templates["entity_templates/area_door"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {
                            "type": "change_area",
                            "area_id": "$target_area",
                            "entry_id": "$target_entry",
                        }
                    ]
                }
            }
        }
        self.catalog._templates["entity_templates/display_sprite"] = {
            "space": "screen",
            "parameter_specs": {
                "sprite_path": {
                    "type": "asset_path",
                    "asset_kind": "image",
                },
                "frame_width": {
                    "type": "int",
                    "min": 1,
                },
                "frame_height": {
                    "type": "int",
                    "min": 1,
                },
                "frames": {
                    "type": "array",
                    "items": {
                        "type": "int",
                        "min": 0,
                    },
                },
                "animation_fps": {
                    "type": "number",
                    "min": 0,
                },
            },
            "visuals": [{"path": "$sprite_path"}],
        }
        self.catalog._templates["entity_templates/reference_panel"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {
                            "type": "run_project_command",
                            "command_id": "$command_id",
                            "dialogue_path": "$dialogue_path",
                            "item_id": "$item_id",
                            "area_id": "$target_area",
                            "entity_id": "$target_id",
                        }
                    ]
                }
            }
        }
        self.catalog._templates["entity_templates/dialogue_owner"] = {
            "variables": {
                "active_dialogue": "starting_dialogue",
            },
            "dialogues": {
                "starting_dialogue": {
                    "dialogue_definition": {
                        "segments": [{"type": "text", "text": "Hello"}]
                    }
                }
            },
        }
        self.catalog._templates["entity_templates/parameterized_dialogue_owner"] = {
            "parameters": {
                "dialogue_definition": {
                    "segments": [{"type": "text", "text": "Default parameterized hello"}]
                }
            },
            "variables": {
                "active_dialogue": "starting_dialogue",
            },
            "dialogues": {
                "starting_dialogue": {
                    "dialogue_definition": "$dialogue_definition",
                }
            },
        }
        self.catalog._templates["entity_templates/area_transition"] = {
            "parameters": {
                "target_area": "areas/start",
                "destination_entity_id": "spawn_marker",
            },
            "parameter_specs": {
                "target_area": {
                    "type": "area_id",
                },
                "destination_entity_id": {
                    "type": "entity_id",
                    "of": "target_area",
                    "scope": "area",
                    "space": "world",
                },
            },
            "entity_commands": {
                "on_occupant_enter": {
                    "enabled": True,
                    "commands": [
                        {
                            "type": "change_area",
                            "area_id": "$target_area",
                            "destination_entity_id": "$destination_entity_id",
                        }
                    ],
                }
            },
        }
        self.catalog._templates["entity_templates/button_target"] = {
            "parameters": {
                "target_entity_id": "",
                "target_press_command_id": "contribute_on",
            },
            "parameter_specs": {
                "target_entity_id": {
                    "type": "entity_id",
                    "scope": "area",
                    "space": "world",
                },
                "target_press_command_id": {
                    "type": "entity_command_id",
                    "of": "target_entity_id",
                },
            },
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {
                            "type": "run_entity_command",
                            "entity_id": "$target_entity_id",
                            "command_id": "$target_press_command_id",
                        }
                    ],
                }
            },
        }
        self.catalog._templates["entity_templates/spec_panel"] = {
            "parameters": {
                "arrival_marker": "",
                "panel_art": "",
                "commandish_string": "",
            },
            "parameter_specs": {
                "arrival_marker": {
                    "type": "entity_id",
                    "scope": "area",
                    "space": "world",
                },
                "panel_art": {
                    "type": "asset_path",
                    "asset_kind": "image",
                },
                "commandish_string": {
                    "type": "string",
                },
            },
        }
        self.catalog._templates["entity_templates/animation_panel"] = {
            "parameters": {
                "target_entity_id": "",
                "visual": "body",
                "animation": "idle",
            },
            "parameter_specs": {
                "target_entity_id": {
                    "type": "entity_id",
                    "scope": "area",
                    "space": "world",
                },
                "visual": {
                    "type": "visual_id",
                    "of": "target_entity_id",
                },
                "animation": {
                    "type": "animation_id",
                    "of": "visual",
                },
            },
        }
        self.catalog._templates["entity_templates/toggle_panel"] = {
            "parameters": {
                "toggleable": True,
            },
            "parameter_specs": {
                "toggleable": {
                    "type": "bool",
                },
            },
        }
        self.catalog._templates["entity_templates/dialogue_sign"] = {
            "parameters": {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Default sign text.",
                        }
                    ]
                }
            },
            "parameter_specs": {
                "dialogue_definition": {
                    "type": "dialogue_definition",
                    "required": True,
                }
            },
        }
        self.catalog._templates["entity_templates/sign"] = {
            "solid": True,
            "interactable": True,
            "interaction_priority": 10,
            "facing": "left",
        }
        self.panel.set_template_catalog(self.catalog)

    def test_build_entity_from_fields_parses_named_parameters(self):
        entity = EntityDocument(
            id="door_1",
            grid_x=3,
            grid_y=4,
            template="entity_templates/area_door",
            parameters={"target_area": "areas/a", "target_entry": "entry_a"},
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        parameters = self.panel._parameters_editor
        parameters._parameter_edits["target_area"].setText("001")
        parameters._parameter_edits["target_entry"].setText("[1, 2]")
        fields._id_edit.setText("door_2")
        fields._x_spin.setValue(6)

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated.id, "door_2")
        self.assertEqual(updated.x, 6)
        self.assertEqual(updated.parameters, {
            "target_area": "001",
            "target_entry": [1, 2],
        })
        self.assertEqual(updated._extra, entity._extra)

    def test_world_space_entity_keeps_pixel_offsets_none_until_enabled(self):
        entity = EntityDocument(
            id="actor",
            grid_x=1,
            grid_y=2,
            template="entity_templates/area_door",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertTrue(fields._pixel_x_row.isHidden())
        self.assertTrue(fields._pixel_y_row.isHidden())

        updated = self.panel.build_entity_from_fields()

        self.assertIsNone(updated.pixel_x)
        self.assertIsNone(updated.pixel_y)

    def test_effective_space_uses_template_space_for_screen_template_instances(self):
        entity = EntityDocument(
            id="title_backdrop",
            pixel_x=32,
            pixel_y=48,
            template="entity_templates/display_sprite",
            parameters={"sprite_path": "assets/project/ui/title/backdrop.png"},
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertEqual(fields._space_label.text(), "screen")
        self.assertTrue(fields._x_spin.isHidden())
        self.assertTrue(fields._y_spin.isHidden())
        self.assertFalse(fields._pixel_x_row.isHidden())
        self.assertFalse(fields._pixel_y_row.isHidden())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated.space, "screen")
        self.assertEqual(updated.pixel_x, 32)
        self.assertEqual(updated.pixel_y, 48)

    def test_non_dict_parameters_show_warning_and_preserve_original_value(self):
        entity = EntityDocument(
            id="odd",
            grid_x=0,
            grid_y=0,
            template="entity_templates/area_door",
            parameters=["not", "a", "dict"],
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertFalse(parameters._warning_label.isHidden())
        self.assertFalse(parameters._empty_label.isHidden())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated.parameters, ["not", "a", "dict"])

    def test_legacy_input_map_is_hidden_and_preserved(self):
        entity = EntityDocument(
            id="controller",
            grid_x=0,
            grid_y=0,
            template="entity_templates/reference_panel",
            _extra={
                "input_map": {"interact": 1},
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertTrue(fields._input_map_warning.isHidden())
        self.assertTrue(fields._input_map_text.isReadOnly())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["input_map"], {"interact": 1})

    def test_invalid_entity_commands_shows_warning_and_preserves_original_value(self):
        entity = EntityDocument(
            id="controller",
            grid_x=0,
            grid_y=0,
            template="entity_templates/reference_panel",
            _extra={
                "entity_commands": {
                    "interact": {
                        "commands": [{"type": "show_message", "text": "Hi"}],
                    },
                },
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertFalse(fields._entity_commands_warning.isHidden())
        self.assertTrue(fields._entity_commands_text.isReadOnly())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["entity_commands"],
            {
                "interact": {
                    "commands": [{"type": "show_message", "text": "Hi"}],
                },
            },
        )

    def test_invalid_inventory_shows_warning_and_preserves_original_value(self):
        entity = EntityDocument(
            id="carrier",
            grid_x=0,
            grid_y=0,
            template="entity_templates/reference_panel",
            _extra={
                "inventory": {
                    "max_stacks": 1,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 0}],
                },
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertFalse(fields._inventory_warning.isHidden())
        self.assertTrue(fields._inventory_stacks_text.isReadOnly())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["inventory"],
            {
                "max_stacks": 1,
                "stacks": [{"item_id": "items/copper_key", "quantity": 0}],
            },
        )

    def test_invalid_color_shows_warning_and_preserves_original_value(self):
        entity = EntityDocument(
            id="tinted",
            grid_x=0,
            grid_y=0,
            template="entity_templates/reference_panel",
            _extra={
                "color": [255, "warm", 160],
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertFalse(fields._color_warning.isHidden())
        self.assertFalse(fields._color_check.isEnabled())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["color"], [255, "warm", 160])

    def test_build_entity_from_fields_updates_common_engine_fields_and_variables(self):
        entity = EntityDocument(
            id="crate_1",
            grid_x=2,
            grid_y=3,
            template="entity_templates/area_door",
            _extra={
                "kind": "crate",
                "tags": ["wood", "pushable"],
                "facing": "left",
                "solid": True,
                "pushable": True,
                "weight": 3,
                "push_strength": 2,
                "collision_push_strength": 1,
                "interactable": True,
                "interaction_priority": 5,
                "present": True,
                "visible": True,
                "entity_commands_enabled": True,
                "variables": {"opened": False},
                "visuals": [{"id": "main", "path": "assets/project/sprites/crate.png"}],
                "custom_field": "keep-me",
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._kind_edit.setText("heavy_crate")
        fields._tags_edit.setText("metal, movable")
        fields._facing_combo.setCurrentText("up")
        fields._solid_check.setChecked(False)
        fields._pushable_check.setChecked(True)
        fields._weight_spin.setValue(7)
        fields._push_strength_spin.setValue(4)
        fields._collision_push_strength_spin.setValue(6)
        fields._interactable_check.setChecked(True)
        fields._interaction_priority_spin.setValue(9)
        fields._present_check.setChecked(False)
        fields._visible_check.setChecked(False)
        fields._entity_commands_enabled_check.setChecked(False)
        fields._color_check.setChecked(True)
        fields._color_red_spin.setValue(120)
        fields._color_green_spin.setValue(90)
        fields._color_blue_spin.setValue(40)
        fields._variables_text.setPlainText('{\n  "opened": true,\n  "uses": 3\n}')
        fields._visuals_text.setPlainText(
            '[\n'
            '  {\n'
            '    "id": "main",\n'
            '    "path": "assets/project/sprites/heavy_crate.png",\n'
            '    "frame_width": 16,\n'
            '    "frame_height": 16\n'
            '  }\n'
            ']'
        )

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["kind"], "heavy_crate")
        self.assertEqual(updated._extra["tags"], ["metal", "movable"])
        self.assertEqual(updated._extra["facing"], "up")
        self.assertFalse(updated._extra["solid"])
        self.assertTrue(updated._extra["pushable"])
        self.assertEqual(updated._extra["weight"], 7)
        self.assertEqual(updated._extra["push_strength"], 4)
        self.assertEqual(updated._extra["collision_push_strength"], 6)
        self.assertTrue(updated._extra["interactable"])
        self.assertEqual(updated._extra["interaction_priority"], 9)
        self.assertFalse(updated._extra["present"])
        self.assertFalse(updated._extra["visible"])
        self.assertFalse(updated._extra["entity_commands_enabled"])
        self.assertEqual(updated._extra["color"], [120, 90, 40])
        self.assertEqual(updated._extra["variables"], {"opened": True, "uses": 3})
        self.assertEqual(
            updated._extra["visuals"],
            [
                {
                    "id": "main",
                    "path": "assets/project/sprites/heavy_crate.png",
                    "frame_width": 16,
                    "frame_height": 16,
                }
            ],
        )
        self.assertEqual(updated._extra["custom_field"], "keep-me")

    def test_template_managed_field_defaults_drive_ui_without_forcing_overrides(self):
        entity = EntityDocument(
            id="sign_1",
            grid_x=4,
            grid_y=5,
            template="entity_templates/sign",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertEqual(fields._facing_combo.currentText(), "left")
        self.assertTrue(fields._solid_check.isChecked())
        self.assertTrue(fields._interactable_check.isChecked())
        self.assertEqual(fields._interaction_priority_spin.value(), 10)

        updated = self.panel.build_entity_from_fields()

        self.assertNotIn("facing", updated._extra)
        self.assertNotIn("solid", updated._extra)
        self.assertNotIn("interactable", updated._extra)
        self.assertNotIn("interaction_priority", updated._extra)

    def test_dialogue_definition_parameter_uses_popup_editor_and_builds_explicit_override(self):
        entity = EntityDocument(
            id="sign_dialogue",
            grid_x=3,
            grid_y=2,
            template="entity_templates/dialogue_sign",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor
        field = parameters._parameter_fields["dialogue_definition"]

        self.assertEqual(field.control_kind, "dialogue_definition")
        self.assertEqual(
            field.summary_label.text(),
            "1 segment, 1 text",
        )
        self.assertFalse(field.explicit_override_enabled)
        self.assertEqual(parameters.build_parameters_value(), None)

        updated_definition = {
            "segments": [
                {
                    "type": "choice",
                    "text": "Read more?",
                    "options": [
                        {
                            "option_id": "yes",
                            "text": "Yes",
                        }
                    ],
                }
            ]
        }

        with patch.object(
            parameters,
            "_open_dialogue_definition_dialog",
            return_value=updated_definition,
        ):
            assert field.action_button is not None
            field.action_button.click()

        built = parameters.build_parameters_value()

        self.assertEqual(
            built,
            {
                "dialogue_definition": updated_definition,
            },
        )
        self.assertTrue(field.explicit_override_enabled)
        self.assertEqual(field.status_label.text(), "authored override")

        parameters._on_dialogue_parameter_reset("dialogue_definition")

        self.assertEqual(parameters.build_parameters_value(), None)
        self.assertFalse(field.explicit_override_enabled)

    def test_build_entity_from_fields_updates_named_dialogues_and_active_dialogue(self):
        entity = EntityDocument(
            id="sign_dialogues",
            grid_x=2,
            grid_y=2,
            _extra={
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

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

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
            fields,
            "_open_entity_dialogues_dialog",
            return_value=(updated_dialogues, "repeat_dialogue"),
        ):
            fields._dialogues_edit_button.click()

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["dialogues"], updated_dialogues)
        self.assertEqual(
            updated._extra["variables"],
            {"seen": False, "active_dialogue": "repeat_dialogue"},
        )

    def test_template_owned_dialogues_show_in_summary_without_forcing_override(self):
        entity = EntityDocument(
            id="templated_dialogue_sign",
            grid_x=2,
            grid_y=2,
            template="entity_templates/dialogue_owner",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertEqual(
            fields._dialogues_summary.text(),
            "1 dialogue; active: starting_dialogue",
        )

        updated = self.panel.build_entity_from_fields()

        self.assertNotIn("dialogues", updated._extra)
        self.assertNotIn("variables", updated._extra)

    def test_parameterized_template_dialogues_show_in_summary_without_override(self):
        entity = EntityDocument(
            id="templated_parameter_dialogue_sign",
            grid_x=3,
            grid_y=2,
            template="entity_templates/parameterized_dialogue_owner",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        self.assertEqual(
            fields._dialogues_summary.text(),
            "1 dialogue; active: starting_dialogue",
        )

        updated = self.panel.build_entity_from_fields()

        self.assertNotIn("dialogues", updated._extra)
        self.assertNotIn("variables", updated._extra)

    def test_hidden_dialogue_bridge_parameter_override_is_preserved_when_unchanged(self):
        entity = EntityDocument(
            id="templated_parameter_dialogue_sign",
            grid_x=3,
            grid_y=2,
            template="entity_templates/parameterized_dialogue_owner",
            parameters={
                "dialogue_definition": {
                    "segments": [{"type": "text", "text": "Overridden hello"}]
                }
            },
        )

        self.panel.load_entity(entity)

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated.parameters,
            {
                "dialogue_definition": {
                    "segments": [{"type": "text", "text": "Overridden hello"}]
                }
            },
        )
        self.assertNotIn("dialogues", updated._extra)

    def test_parameters_tab_exposes_named_dialogues_shortcut_instead_of_bridge_parameter(self):
        entity = EntityDocument(
            id="templated_parameter_dialogue_sign",
            grid_x=3,
            grid_y=2,
            template="entity_templates/parameterized_dialogue_owner",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor
        fields = self.panel._fields_editor

        self.assertTrue(parameters._dialogues_shortcut_visible)
        self.assertNotIn("dialogue_definition", parameters._parameter_fields)
        self.assertEqual(
            parameters._dialogues_shortcut_summary.text(),
            "1 dialogue; active: starting_dialogue",
        )

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
            fields,
            "_open_entity_dialogues_dialog",
            return_value=(updated_dialogues, "starting_dialogue"),
        ):
            assert parameters._dialogues_shortcut_button is not None
            parameters._dialogues_shortcut_button.click()

        self.assertEqual(
            parameters._dialogues_shortcut_summary.text(),
            "2 dialogues; active: starting_dialogue",
        )

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["dialogues"], updated_dialogues)
        self.assertEqual(updated._extra["variables"], {"active_dialogue": "starting_dialogue"})
        self.assertIsNone(updated.parameters)

    def test_fields_dialogue_edit_syncs_parameters_shortcut_summary(self):
        entity = EntityDocument(
            id="templated_parameter_dialogue_sign",
            grid_x=3,
            grid_y=2,
            template="entity_templates/parameterized_dialogue_owner",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor
        fields = self.panel._fields_editor

        updated_dialogues = {
            "intro_dialogue": {
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
            fields,
            "_open_entity_dialogues_dialog",
            return_value=(updated_dialogues, "intro_dialogue"),
        ):
            fields._dialogues_edit_button.click()

        self.assertEqual(
            parameters._dialogues_shortcut_summary.text(),
            "2 dialogues; active: intro_dialogue",
        )

    def test_named_dialogue_rename_updates_self_targeting_entity_command_refs(self):
        entity = EntityDocument(
            id="speaker",
            grid_x=1,
            grid_y=1,
            _extra={
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
                                "type": "set_entity_active_dialogue",
                                "entity_id": "speaker",
                                "dialogue_id": "starting_dialogue",
                            }
                        ],
                    }
                },
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor

        with patch.object(
            fields,
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
            fields._dialogues_edit_button.click()

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["variables"]["active_dialogue"], "intro_dialogue")
        self.assertEqual(
            updated._extra["entity_commands"]["interact"]["commands"][0]["dialogue_id"],
            "intro_dialogue",
        )

    def test_build_entity_from_fields_updates_scope(self):
        entity = EntityDocument(
            id="tracker",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._scope_combo.setCurrentText("global")

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["scope"], "global")

    def test_build_entity_from_fields_preserves_existing_input_map(self):
        entity = EntityDocument(
            id="controller",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
            _extra={
                "input_map": {
                    "interact": "interact",
                }
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._kind_edit.setText("controller_panel")

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["input_map"],
            {
                "interact": "interact",
            },
        )
        self.assertEqual(updated._extra["kind"], "controller_panel")

    def test_build_entity_from_fields_updates_entity_commands(self):
        entity = EntityDocument(
            id="controller",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
            _extra={
                "entity_commands": {
                    "interact": [
                        {
                            "type": "run_project_command",
                            "command_id": "commands/system/old",
                        }
                    ],
                }
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._entity_commands_text.setPlainText(
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

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["entity_commands"],
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

    def test_entity_command_controls_can_add_named_command(self):
        entity = EntityDocument(
            id="controller",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
        )

        self.panel.load_entity(entity)
        self.panel.set_editing_enabled(True)
        fields = self.panel._fields_editor

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

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["entity_commands"],
            {
                "interact": [
                    {
                        "type": "run_project_command",
                        "command_id": "commands/system/open_gate",
                    }
                ],
            },
        )

    def test_build_entity_from_fields_updates_inventory(self):
        entity = EntityDocument(
            id="carrier",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._inventory_check.setChecked(True)
        fields._inventory_max_stacks_spin.setValue(2)
        fields._inventory_stacks_text.setPlainText(
            '[\n'
            '  {"item_id": "items/copper_key", "quantity": 1},\n'
            '  {"item_id": "items/light_orb", "quantity": 2}\n'
            ']'
        )

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["inventory"],
            {
                "max_stacks": 2,
                "stacks": [
                    {"item_id": "items/copper_key", "quantity": 1},
                    {"item_id": "items/light_orb", "quantity": 2},
                ],
            },
        )

    def test_build_entity_from_fields_preserves_inventory_extra_keys(self):
        entity = EntityDocument(
            id="carrier",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
            _extra={
                "inventory": {
                    "max_stacks": 1,
                    "stacks": [
                        {
                            "item_id": "items/copper_key",
                            "quantity": 1,
                            "note": "starter",
                        }
                    ],
                    "custom_inventory_key": "keep-me",
                },
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._inventory_max_stacks_spin.setValue(2)

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["inventory"]["custom_inventory_key"], "keep-me")
        self.assertEqual(
            updated._extra["inventory"]["stacks"],
            [
                {
                    "item_id": "items/copper_key",
                    "quantity": 1,
                    "note": "starter",
                }
            ],
        )

    def test_build_entity_from_fields_preserves_engine_owned_fields(self):
        entity = EntityDocument(
            id="terminal_1",
            grid_x=4,
            grid_y=5,
            template="entity_templates/reference_panel",
            _extra={
                "scope": "global",
                "color": [255, 220, 160],
                "inventory": {
                    "max_stacks": 2,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                },
                "input_map": {"interact": "use_terminal"},
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

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._kind_edit.setText("console")
        fields._variables_text.setPlainText('{"visited": true}')

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated._extra["scope"], "global")
        self.assertEqual(updated._extra["color"], [255, 220, 160])
        self.assertEqual(
            updated._extra["inventory"],
            {
                "max_stacks": 2,
                "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
            },
        )
        self.assertEqual(
            updated._extra["input_map"],
            {"interact": "use_terminal"},
        )
        self.assertEqual(
            updated._extra["entity_commands"],
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
        self.assertEqual(updated._extra["kind"], "console")
        self.assertEqual(updated._extra["variables"], {"visited": True})

    def test_build_entity_from_fields_rejects_non_array_visuals(self):
        entity = EntityDocument(
            id="crate_1",
            grid_x=2,
            grid_y=3,
            template="entity_templates/area_door",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._visuals_text.setPlainText('{"id": "main"}')

        with self.assertRaisesRegex(ValueError, "Visuals must be a JSON array."):
            self.panel.build_entity_from_fields()

    def test_build_entity_from_fields_updates_persistence_policy(self):
        entity = EntityDocument(
            id="crate_1",
            grid_x=2,
            grid_y=3,
            template="entity_templates/area_door",
            _extra={
                "persistence": {
                    "entity_state": True,
                    "variables": {"shake_timer": False},
                }
            },
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._persistence_entity_state_check.setChecked(False)
        fields._persistence_variables_text.setPlainText(
            '{\n  "times_pushed": true,\n  "shake_timer": false\n}'
        )

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated._extra["persistence"],
            {
                "entity_state": False,
                "variables": {
                    "times_pushed": True,
                    "shake_timer": False,
                },
            },
        )

    def test_parameter_reference_picker_buttons_fill_known_reference_fields(self):
        entity = EntityDocument(
            id="terminal_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/reference_panel",
        )
        self.panel.set_reference_picker_callbacks(
            area_picker=lambda current: "areas/vault",
            entity_picker=lambda current: "gate_controller",
            item_picker=lambda current: "items/copper_key",
            dialogue_picker=lambda current: "dialogues/system/notice",
            command_picker=lambda current: "commands/system/open_gate",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        for name in (
            "target_area",
            "target_id",
            "item_id",
            "dialogue_path",
            "command_id",
        ):
            self.assertIn(name, parameters._parameter_browse_buttons)

        parameters._parameter_browse_buttons["target_area"].click()
        parameters._parameter_browse_buttons["target_id"].click()
        parameters._parameter_browse_buttons["item_id"].click()
        parameters._parameter_browse_buttons["dialogue_path"].click()
        parameters._parameter_browse_buttons["command_id"].click()

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated.parameters,
            {
                "target_area": "areas/vault",
                "target_id": "gate_controller",
                "item_id": "items/copper_key",
                "dialogue_path": "dialogues/system/notice",
                "command_id": "commands/system/open_gate",
            },
        )

    def test_parameter_specs_drive_picker_buttons(self):
        entity = EntityDocument(
            id="panel_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/spec_panel",
        )
        self.panel.set_reference_picker_callbacks(
            entity_picker=lambda current: "arrival_marker_1",
            asset_picker=lambda current: "assets/project/ui/panel.png",
            command_picker=lambda current: "commands/system/should_not_apply",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertIn("arrival_marker", parameters._parameter_browse_buttons)
        self.assertIn("panel_art", parameters._parameter_browse_buttons)
        self.assertNotIn("commandish_string", parameters._parameter_browse_buttons)

        parameters._parameter_browse_buttons["arrival_marker"].click()
        parameters._parameter_browse_buttons["panel_art"].click()

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated.parameters,
            {
                "arrival_marker": "arrival_marker_1",
                "panel_art": "assets/project/ui/panel.png",
            },
        )

    def test_entity_parameter_picker_receives_request_context(self):
        entity = EntityDocument(
            id="button_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/button_target",
        )
        requests: list[EntityReferencePickerRequest] = []

        def pick_entity(
            current: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            self.assertEqual(current, "")
            requests.append(request)
            return "gate_1"

        self.panel.set_area_context("areas/demo")
        self.panel.set_reference_picker_callbacks(entity_picker=pick_entity)
        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        parameters._parameter_browse_buttons["target_entity_id"].click()

        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0],
            EntityReferencePickerRequest(
                parameter_name="target_entity_id",
                current_value="",
                parameter_spec={
                    "type": "entity_id",
                    "scope": "area",
                    "space": "world",
                },
                current_area_id="areas/demo",
                entity_id="button_1",
                entity_template_id="entity_templates/button_target",
                parameter_values={
                    "target_entity_id": "",
                    "target_press_command_id": "contribute_on",
                },
            ),
        )
        self.assertEqual(parameters._parameter_edits["target_entity_id"].text(), "gate_1")

    def test_parameter_specs_parse_typed_values(self):
        entity = EntityDocument(
            id="sprite_1",
            pixel_x=0,
            pixel_y=0,
            template="entity_templates/display_sprite",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor
        parameters._parameter_edits["sprite_path"].setText("assets/project/ui/sprite.png")
        parameters._parameter_edits["frame_width"].setText("32")
        parameters._parameter_edits["frame_height"].setText("16")
        parameters._parameter_edits["frames"].setText("[0, 1, 2]")
        parameters._parameter_edits["animation_fps"].setText("12.5")

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(
            updated.parameters,
            {
                "animation_fps": 12.5,
                "frame_height": 16,
                "frame_width": 32,
                "frames": [0, 1, 2],
                "sprite_path": "assets/project/ui/sprite.png",
            },
        )

    def test_bool_parameters_use_checkbox_and_can_reset_to_default(self):
        entity = EntityDocument(
            id="lever_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/toggle_panel",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor
        field = parameters._parameter_fields["toggleable"]
        self.assertEqual(field.control_kind, "bool")
        self.assertIsNotNone(field.checkbox)
        assert field.checkbox is not None

        self.assertTrue(field.checkbox.isChecked())
        self.assertFalse(field.explicit_override_enabled)

        field.checkbox.setChecked(False)
        updated = self.panel.build_entity_from_fields()
        self.assertEqual(updated.parameters, {"toggleable": False})

        parameters._on_bool_parameter_reset("toggleable")
        reset = self.panel.build_entity_from_fields()
        self.assertIsNone(reset.parameters)

    def test_build_entity_from_fields_rejects_invalid_persistence_variables(self):
        entity = EntityDocument(
            id="crate_1",
            grid_x=2,
            grid_y=3,
            template="entity_templates/area_door",
        )

        self.panel.load_entity(entity)
        fields = self.panel._fields_editor
        fields._persistence_variables_text.setPlainText('{"times_pushed": 1}')

        with self.assertRaisesRegex(
            ValueError,
            "Persistence variable 'times_pushed' must be true or false.",
        ):
            self.panel.build_entity_from_fields()

    def test_template_parameter_defaults_show_as_placeholders(self):
        entity = EntityDocument(
            id="to_start_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/area_transition",
        )

        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertIn("target_area", parameters._parameter_edits)
        self.assertIn("destination_entity_id", parameters._parameter_edits)
        self.assertEqual(
            parameters._parameter_edits["target_area"].placeholderText(),
            "areas/start",
        )
        self.assertEqual(
            parameters._parameter_edits["destination_entity_id"].placeholderText(),
            "spawn_marker",
        )

    def test_entity_parameter_with_of_area_uses_selected_area_context(self):
        entity = EntityDocument(
            id="to_cave_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/area_transition",
            parameters={
                "target_area": "areas/cave",
            },
        )
        requests: list[EntityReferencePickerRequest] = []

        def pick_entity(
            current: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            return "cave_exit"

        self.panel.set_reference_picker_callbacks(entity_picker=pick_entity)
        self.panel.set_area_context("areas/start")
        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertTrue(parameters._parameter_browse_buttons["destination_entity_id"].isEnabled())
        parameters._parameter_browse_buttons["destination_entity_id"].click()

        self.assertEqual(parameters._parameter_edits["destination_entity_id"].text(), "cave_exit")
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0],
            EntityReferencePickerRequest(
                parameter_name="destination_entity_id",
                current_value="",
                parameter_spec={
                    "type": "entity_id",
                    "of": "target_area",
                    "scope": "area",
                    "space": "world",
                },
                current_area_id="areas/start",
                entity_id="to_cave_1",
                entity_template_id="entity_templates/area_transition",
                parameter_values={
                    "target_area": "areas/cave",
                    "destination_entity_id": "spawn_marker",
                },
            ),
        )

    def test_entity_command_parameters_use_entity_command_picker(self):
        entity = EntityDocument(
            id="button_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/button_target",
        )

        requests: list[EntityReferencePickerRequest] = []

        def pick_command(
            current: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            requests.append(request)
            return "contribute_off"

        self.panel.set_reference_picker_callbacks(
            entity_picker=lambda current: "gate_1",
            entity_command_picker=pick_command,
        )
        self.panel.set_area_context("areas/demo")
        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertIn("target_entity_id", parameters._parameter_browse_buttons)
        self.assertIn("target_press_command_id", parameters._parameter_browse_buttons)
        self.assertFalse(parameters._parameter_browse_buttons["target_press_command_id"].isEnabled())

        parameters._parameter_edits["target_entity_id"].setText("gate_1")
        parameters._parameter_browse_buttons["target_press_command_id"].click()

        self.assertEqual(parameters._parameter_edits["target_press_command_id"].text(), "contribute_off")
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0],
            EntityReferencePickerRequest(
                parameter_name="target_press_command_id",
                current_value="",
                parameter_spec={
                    "type": "entity_command_id",
                    "of": "target_entity_id",
                },
                current_area_id="areas/demo",
                entity_id="button_1",
                entity_template_id="entity_templates/button_target",
                parameter_values={
                    "target_entity_id": "gate_1",
                    "target_press_command_id": "contribute_on",
                    "entity_id": "gate_1",
                },
            ),
        )

    def test_visual_and_animation_parameters_use_of_picker_context(self):
        entity = EntityDocument(
            id="animator_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/animation_panel",
        )

        visual_requests: list[EntityReferencePickerRequest] = []
        animation_requests: list[EntityReferencePickerRequest] = []

        def pick_visual(
            current: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            visual_requests.append(request)
            return "shadow"

        def pick_animation(
            current: str,
            request: EntityReferencePickerRequest,
        ) -> str | None:
            animation_requests.append(request)
            return "pulse"

        self.panel.set_reference_picker_callbacks(
            visual_picker=pick_visual,
            animation_picker=pick_animation,
        )
        self.panel.set_area_context("areas/demo")
        self.panel.load_entity(entity)
        parameters = self.panel._parameters_editor

        self.assertFalse(parameters._parameter_browse_buttons["visual"].isEnabled())
        self.assertFalse(parameters._parameter_browse_buttons["animation"].isEnabled())

        parameters._parameter_edits["target_entity_id"].setText("target_1")
        self.assertTrue(parameters._parameter_browse_buttons["visual"].isEnabled())
        self.assertTrue(parameters._parameter_browse_buttons["animation"].isEnabled())

        parameters._parameter_browse_buttons["visual"].click()
        parameters._parameter_browse_buttons["animation"].click()

        self.assertEqual(parameters._parameter_edits["visual"].text(), "shadow")
        self.assertEqual(parameters._parameter_edits["animation"].text(), "pulse")
        self.assertEqual(
            visual_requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="visual",
                    current_value="",
                    parameter_spec={
                        "type": "visual_id",
                        "of": "target_entity_id",
                    },
                    current_area_id="areas/demo",
                    entity_id="animator_1",
                    entity_template_id="entity_templates/animation_panel",
                    parameter_values={
                        "target_entity_id": "target_1",
                        "visual": "body",
                        "animation": "idle",
                        "entity_id": "target_1",
                    },
                )
            ],
        )
        self.assertEqual(
            animation_requests,
            [
                EntityReferencePickerRequest(
                    parameter_name="animation",
                    current_value="",
                    parameter_spec={
                        "type": "animation_id",
                        "of": "visual",
                    },
                    current_area_id="areas/demo",
                    entity_id="animator_1",
                    entity_template_id="entity_templates/animation_panel",
                    parameter_values={
                        "target_entity_id": "target_1",
                        "visual": "shadow",
                        "animation": "idle",
                        "entity_id": "target_1",
                        "visual_id": "shadow",
                    },
                )
            ],
        )

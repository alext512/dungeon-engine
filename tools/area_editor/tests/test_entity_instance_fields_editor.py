"""Tests for the structured entity-instance fields editor."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument
from area_editor.widgets.entity_instance_json_panel import EntityInstanceJsonPanel


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
            "visuals": [{"path": "$sprite_path"}],
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
        fields._parameter_edits["target_area"].setText("001")
        fields._parameter_edits["target_entry"].setText("[1, 2]")
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
        fields = self.panel._fields_editor

        self.assertFalse(fields._parameter_warning.isHidden())
        self.assertTrue(fields._parameters_widget.isHidden())

        updated = self.panel.build_entity_from_fields()

        self.assertEqual(updated.parameters, ["not", "a", "dict"])

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
        fields._variables_text.setPlainText('{\n  "opened": true,\n  "uses": 3\n}')

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
        self.assertEqual(updated._extra["variables"], {"opened": True, "uses": 3})
        self.assertEqual(updated._extra["custom_field"], "keep-me")

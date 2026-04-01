"""Tests for entity template visual lookup and parameter substitution."""

from __future__ import annotations

import unittest

from area_editor.catalogs.template_catalog import TemplateCatalog


class TestTemplateCatalog(unittest.TestCase):
    def test_parameterized_visual_substitutes_instance_values(self):
        catalog = TemplateCatalog()
        catalog._templates["entity_templates/display_sprite"] = {
            "visuals": [
                {
                    "path": "$sprite_path",
                    "frame_width": "$frame_width",
                    "frame_height": "$frame_height",
                    "frames": "$frames",
                    "offset_x": 3,
                }
            ]
        }

        visual = catalog.get_first_visual(
            "entity_templates/display_sprite",
            {
                "sprite_path": "assets/project/ui/title/backdrop.png",
                "frame_width": 256,
                "frame_height": 128,
                "frames": [0],
            },
        )

        self.assertIsNotNone(visual)
        assert visual is not None
        self.assertEqual(visual.path, "assets/project/ui/title/backdrop.png")
        self.assertEqual(visual.frame_width, 256)
        self.assertEqual(visual.frame_height, 128)
        self.assertEqual(visual.frames, [0])

    def test_unresolved_parameterized_visual_is_skipped(self):
        catalog = TemplateCatalog()
        catalog._templates["entity_templates/display_sprite"] = {
            "visuals": [
                {
                    "path": "$sprite_path",
                    "frame_width": "$frame_width",
                    "frame_height": "$frame_height",
                    "frames": "$frames",
                }
            ]
        }

        visual = catalog.get_first_visual("entity_templates/display_sprite")

        self.assertIsNone(visual)

    def test_get_template_parameter_names_discovers_expected_variables(self):
        catalog = TemplateCatalog()
        catalog._templates["entity_templates/sign"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {
                            "type": "run_entity_command",
                            "entity_id": "$ref_ids.dialogue_controller",
                            "command_id": "open",
                            "dialogue_path": "$dialogue_path",
                            "title": "$refs.speaker.title",
                            "entity_refs": {
                                "speaker": "$self_id",
                            },
                        }
                    ]
                }
            }
        }

        names = catalog.get_template_parameter_names("entity_templates/sign")

        self.assertEqual(names, ["dialogue_path"])

    def test_get_template_parameter_names_caches_results_until_clear(self):
        catalog = TemplateCatalog()
        catalog._templates["entity_templates/door"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {"type": "change_area", "area_id": "$target_area"}
                    ]
                }
            }
        }

        self.assertEqual(
            catalog.get_template_parameter_names("entity_templates/door"),
            ["target_area"],
        )

        catalog._templates["entity_templates/door"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {"type": "change_area", "entry_id": "$target_entry"}
                    ]
                }
            }
        }

        self.assertEqual(
            catalog.get_template_parameter_names("entity_templates/door"),
            ["target_area"],
        )
        catalog.clear()
        catalog._templates["entity_templates/door"] = {
            "entity_commands": {
                "interact": {
                    "enabled": True,
                    "commands": [
                        {"type": "change_area", "entry_id": "$target_entry"}
                    ]
                }
            }
        }
        self.assertEqual(
            catalog.get_template_parameter_names("entity_templates/door"),
            ["target_entry"],
        )

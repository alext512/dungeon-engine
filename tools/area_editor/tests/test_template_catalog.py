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

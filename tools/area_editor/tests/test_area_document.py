"""Tests for the area document model — loading, field access, round-trip."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from area_editor.documents.area_document import (
    AreaDocument,
    EntityDocument,
    TileLayerDocument,
    TilesetRef,
    load_area_document,
    save_area_document,
)

_TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "projects" / "test_project"
_VILLAGE_SQUARE = _TEST_PROJECT / "areas" / "village_square.json"
_TITLE_SCREEN = _TEST_PROJECT / "areas" / "title_screen.json"


@unittest.skipUnless(_VILLAGE_SQUARE.is_file(), "village_square.json not found")
class TestVillageSquareLoading(unittest.TestCase):
    def setUp(self):
        self.doc = load_area_document(_VILLAGE_SQUARE)

    def test_name(self):
        self.assertTrue(len(self.doc.name) > 0)

    def test_tile_size(self):
        self.assertGreater(self.doc.tile_size, 0)

    def test_has_tile_layers(self):
        self.assertGreater(len(self.doc.tile_layers), 0)

    def test_dimensions(self):
        self.assertGreater(self.doc.width, 0)
        self.assertGreater(self.doc.height, 0)

    def test_has_entities(self):
        self.assertGreater(len(self.doc.entities), 0)

    def test_has_tilesets(self):
        self.assertGreater(len(self.doc.tilesets), 0)

    def test_render_order_fields_preserved(self):
        overlay_layers = [l for l in self.doc.tile_layers if l.render_order == 20]
        self.assertTrue(overlay_layers, "Expected at least one overlay layer with render_order=20")


@unittest.skipUnless(_TITLE_SCREEN.is_file(), "title_screen.json not found")
class TestTitleScreenLoading(unittest.TestCase):
    def setUp(self):
        self.doc = load_area_document(_TITLE_SCREEN)

    def test_loads_without_error(self):
        self.assertIsInstance(self.doc, AreaDocument)

    def test_has_entities(self):
        """title_screen has screen-space entities even without tilesets."""
        self.assertGreater(len(self.doc.entities), 0)


class TestUnknownFieldPreservation(unittest.TestCase):
    """Unknown keys must survive a from_dict -> to_dict round-trip."""

    def test_area_extra_fields(self):
        raw = {"name": "test", "tile_size": 16, "unknown_thing": [1, 2, 3]}
        doc = AreaDocument.from_dict(raw)
        out = doc.to_dict()
        self.assertEqual(out["unknown_thing"], [1, 2, 3])

    def test_tileset_extra_fields(self):
        raw = {"firstgid": 1, "path": "a.png", "tile_width": 16, "tile_height": 16, "custom": True}
        ts = TilesetRef.from_dict(raw)
        out = ts.to_dict()
        self.assertTrue(out["custom"])

    def test_layer_extra_fields(self):
        raw = {"name": "bg", "render_order": 0, "y_sort": False, "stack_order": 0, "grid": [], "opacity": 0.5}
        layer = TileLayerDocument.from_dict(raw)
        out = layer.to_dict()
        self.assertAlmostEqual(out["opacity"], 0.5)

    def test_entity_extra_fields(self):
        raw = {
            "id": "e1",
            "grid_x": 0,
            "grid_y": 0,
            "render_order": 10,
            "kind": "lever",
            "visuals": [{"id": "main"}],
            "entity_commands": {"interact": {"enabled": True, "commands": []}},
        }
        ent = EntityDocument.from_dict(raw)
        out = ent.to_dict()
        self.assertEqual(out["kind"], "lever")
        self.assertEqual(out["visuals"], [{"id": "main"}])
        self.assertEqual(
            out["entity_commands"],
            {"interact": {"enabled": True, "commands": []}},
        )


class TestEntityPositioning(unittest.TestCase):
    def test_world_space_default(self):
        ent = EntityDocument.from_dict({"id": "a", "grid_x": 5, "grid_y": 3})
        self.assertFalse(ent.is_screen_space)

    def test_screen_space(self):
        ent = EntityDocument.from_dict({"id": "b", "space": "screen", "pixel_x": 100, "pixel_y": 50})
        self.assertTrue(ent.is_screen_space)
        self.assertEqual(ent.pixel_x, 100)
        self.assertEqual(ent.pixel_y, 50)


@unittest.skipUnless(_VILLAGE_SQUARE.is_file(), "village_square.json not found")
class TestRoundTrip(unittest.TestCase):
    """Loading and re-serialising should not lose any top-level keys."""

    def test_no_key_loss(self):
        raw = json.loads(_VILLAGE_SQUARE.read_text(encoding="utf-8"))
        doc = AreaDocument.from_dict(dict(raw))
        out = doc.to_dict()
        for key in raw:
            self.assertIn(key, out, f"Key '{key}' was lost during round-trip")


class TestSaveAreaDocument(unittest.TestCase):
    def test_save_and_reload_preserves_unknown_fields(self):
        raw = {
            "name": "save-test",
            "tile_size": 16,
            "tile_layers": [
                {
                    "name": "ground",
                    "render_order": 0,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[0]],
                }
            ],
            "unknown_root": {"kept": True},
        }
        doc = AreaDocument.from_dict(raw)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "area.json"
            save_area_document(path, doc)
            loaded = load_area_document(path)

        self.assertEqual(loaded._extra["unknown_root"], {"kept": True})


if __name__ == "__main__":
    unittest.main()

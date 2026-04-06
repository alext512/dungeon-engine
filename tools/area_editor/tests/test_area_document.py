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
from area_editor.json_format import format_json_for_editor
from fixture_project import FixtureProject, create_editor_fixture_project

_FIXTURE_TEMP: tempfile.TemporaryDirectory[str] | None = None
_FIXTURE: FixtureProject | None = None


def setUpModule() -> None:
    global _FIXTURE_TEMP, _FIXTURE
    _FIXTURE_TEMP = tempfile.TemporaryDirectory()
    _FIXTURE = create_editor_fixture_project(Path(_FIXTURE_TEMP.name))


def tearDownModule() -> None:
    global _FIXTURE_TEMP, _FIXTURE
    if _FIXTURE_TEMP is not None:
        _FIXTURE_TEMP.cleanup()
    _FIXTURE_TEMP = None
    _FIXTURE = None


class TestVillageSquareLoading(unittest.TestCase):
    def setUp(self):
        assert _FIXTURE is not None
        self.doc = load_area_document(_FIXTURE.village_square)

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


class TestTitleScreenLoading(unittest.TestCase):
    def setUp(self):
        assert _FIXTURE is not None
        self.doc = load_area_document(_FIXTURE.title_screen)

    def test_loads_without_error(self):
        self.assertIsInstance(self.doc, AreaDocument)

    def test_has_entities(self):
        """title_screen has screen-space entities even without tilesets."""
        self.assertGreater(len(self.doc.entities), 0)


class TestUnknownFieldPreservation(unittest.TestCase):
    """Unknown keys must survive a from_dict -> to_dict round-trip."""

    def test_area_name_field_is_rejected(self):
        raw = {"name": "legacy", "tile_size": 16}
        with self.assertRaises(ValueError) as raised:
            AreaDocument.from_dict(raw)
        self.assertIn("must not declare 'name'", str(raised.exception))

    def test_area_extra_fields(self):
        raw = {"tile_size": 16, "unknown_thing": [1, 2, 3]}
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


class TestRoundTrip(unittest.TestCase):
    """Loading and re-serialising should not lose any top-level keys."""

    def test_no_key_loss(self):
        assert _FIXTURE is not None
        raw = json.loads(_FIXTURE.village_square.read_text(encoding="utf-8"))
        doc = AreaDocument.from_dict(dict(raw))
        out = doc.to_dict()
        for key in raw:
            self.assertIn(key, out, f"Key '{key}' was lost during round-trip")


class TestSaveAreaDocument(unittest.TestCase):
    def test_save_and_reload_preserves_unknown_fields(self):
        raw = {
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

    def test_save_formats_known_matrix_fields_compactly(self):
        raw = {
            "tile_size": 16,
            "tile_layers": [
                {
                    "name": "ground",
                    "render_order": 0,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[0, 1, 2], [3, 4, 5]],
                }
            ],
            "cell_flags": [[None, {"solid": True}], [False, None]],
        }
        doc = AreaDocument.from_dict(raw)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "area.json"
            save_area_document(path, doc)
            saved = path.read_text(encoding="utf-8")

        self.assertIn('"grid": [\n        [0, 1, 2],\n        [3, 4, 5]\n      ]', saved)
        self.assertIn(
            '"cell_flags": [\n    [null, {"solid": true}],\n    [false, null]\n  ]',
            saved,
        )


class TestEditorJsonFormatting(unittest.TestCase):
    def test_known_matrix_fields_render_compact_rows(self):
        text = format_json_for_editor(
            {
                "tile_layers": [
                    {
                        "name": "ground",
                        "render_order": 0,
                        "y_sort": False,
                        "stack_order": 0,
                        "grid": [[1, 2], [3, 4]],
                    }
                ],
                "cell_flags": [[None, True], [False, {"solid": True}]],
            }
        )

        self.assertIn('"grid": [\n        [1, 2],\n        [3, 4]\n      ]', text)
        self.assertIn(
            '"cell_flags": [\n    [null, true],\n    [false, {"solid": true}]\n  ]',
            text,
        )


if __name__ == "__main__":
    unittest.main()

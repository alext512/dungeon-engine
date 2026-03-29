"""Tests for cell-flag editing helpers."""

from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument, TileLayerDocument
from area_editor.operations.cell_flags import cell_is_walkable, set_cell_walkable


def _make_area(*, cell_flags=None) -> AreaDocument:
    return AreaDocument(
        name="test",
        tile_size=16,
        tilesets=[],
        tile_layers=[
            TileLayerDocument(
                name="ground",
                draw_above_entities=False,
                grid=[[0, 0], [0, 0]],
            )
        ],
        cell_flags=cell_flags or [],
        entry_points={},
        entities=[],
        camera={},
        input_targets={},
        variables={},
        enter_commands=[],
    )


class TestCellFlagOperations(unittest.TestCase):
    def test_missing_grid_defaults_to_walkable(self):
        area = _make_area(cell_flags=[])
        self.assertTrue(cell_is_walkable(area, 0, 0))

    def test_setting_default_walkable_cell_to_walkable_is_noop(self):
        area = _make_area(cell_flags=[])
        changed = set_cell_walkable(area, 0, 0, True)
        self.assertFalse(changed)
        self.assertEqual(area.cell_flags, [])

    def test_setting_default_walkable_cell_to_blocked_materializes_grid(self):
        area = _make_area(cell_flags=[])
        changed = set_cell_walkable(area, 1, 0, False)
        self.assertTrue(changed)
        self.assertFalse(cell_is_walkable(area, 1, 0))
        self.assertTrue(cell_is_walkable(area, 0, 0))

    def test_dict_cell_preserves_unknown_keys(self):
        area = _make_area(
            cell_flags=[[{"walkable": False, "terrain": "water"}, True]]
        )
        changed = set_cell_walkable(area, 0, 0, True)
        self.assertTrue(changed)
        self.assertEqual(
            area.cell_flags[0][0],
            {"walkable": True, "terrain": "water"},
        )

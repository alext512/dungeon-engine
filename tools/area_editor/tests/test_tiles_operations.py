"""Tests for tile painting helper operations."""

from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument, TileLayerDocument
from area_editor.operations.tiles import eyedrop_tile, paint_tile


def _make_area() -> AreaDocument:
    return AreaDocument(
        tile_size=16,
        tilesets=[],
        tile_layers=[
            TileLayerDocument(
                name="ground",
                render_order=0,
                y_sort=False,
                sort_y_offset=0.0,
                stack_order=0,
                grid=[[0, 1], [2, 3]],
            )
        ],
        cell_flags=[],
        entry_points={},
        entities=[],
        camera={},
        input_routes={},
        variables={},
        enter_commands=[],
    )


class TestTileOperations(unittest.TestCase):
    def test_paint_tile_updates_grid(self):
        area = _make_area()
        changed = paint_tile(area, 0, 0, 0, 9)
        self.assertTrue(changed)
        self.assertEqual(area.tile_layers[0].grid[0][0], 9)

    def test_paint_tile_is_noop_when_gid_matches(self):
        area = _make_area()
        changed = paint_tile(area, 0, 1, 0, 1)
        self.assertFalse(changed)

    def test_eyedrop_tile_reads_gid(self):
        area = _make_area()
        self.assertEqual(eyedrop_tile(area, 0, 1, 1), 3)

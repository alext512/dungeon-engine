"""Tests for tileset-edit helper operations."""

from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument, TileLayerDocument, TilesetRef
from area_editor.operations.tilesets import (
    append_tileset,
    next_tileset_firstgid,
    tileset_frame_count,
    update_tileset_dimensions,
)


def _area_with_tilesets(*tilesets: TilesetRef) -> AreaDocument:
    return AreaDocument(
        tile_size=16,
        tilesets=list(tilesets),
        tile_layers=[
            TileLayerDocument(
                name="ground",
                render_order=0,
                y_sort=False,
                sort_y_offset=0.0,
                stack_order=0,
                grid=[[0]],
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


class TestTilesetOperations(unittest.TestCase):
    def test_tileset_frame_count_uses_whole_tiles_only(self):
        self.assertEqual(tileset_frame_count(34, 18, 16, 16), 2)

    def test_next_tileset_firstgid_respects_existing_ranges(self):
        area = _area_with_tilesets(
            TilesetRef(1, "assets/one.png", 16, 16),
            TilesetRef(20, "assets/two.png", 16, 16),
        )

        result = next_tileset_firstgid(area, [5, 4])

        self.assertEqual(result, 24)

    def test_append_tileset_uses_next_safe_firstgid(self):
        area = _area_with_tilesets(
            TilesetRef(1, "assets/one.png", 16, 16),
            TilesetRef(6, "assets/two.png", 16, 16),
        )

        appended = append_tileset(
            area,
            "assets/three.png",
            16,
            16,
            existing_tile_counts=[5, 12],
        )

        self.assertEqual(appended.firstgid, 18)
        self.assertEqual(area.tilesets[-1].path, "assets/three.png")

    def test_update_tileset_dimensions_reports_changes(self):
        area = _area_with_tilesets(TilesetRef(1, "assets/one.png", 16, 16))

        self.assertTrue(update_tileset_dimensions(area, 0, 32, 24))
        self.assertEqual(area.tilesets[0].tile_width, 32)
        self.assertEqual(area.tilesets[0].tile_height, 24)
        self.assertFalse(update_tileset_dimensions(area, 0, 32, 24))

"""Tests for entity placement and movement helper operations."""

from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument, EntityDocument, TileLayerDocument
from area_editor.operations.entities import move_entity_by_id, move_entity_pixels


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
                grid=[[0, 0], [0, 0]],
            )
        ],
        cell_flags=[[{}, {}], [{}, {}]],
        entry_points={},
        entities=[],
        camera={},
        input_routes={},
        variables={},
        enter_commands=[],
    )


class TestEntityOperations(unittest.TestCase):
    def test_move_entity_by_id_rejects_screen_space_entities(self):
        area = _make_area()
        area.entities.append(
            EntityDocument(
                id="hud",
                grid_x=0,
                grid_y=0,
                pixel_x=10,
                pixel_y=12,
                space="screen",
            )
        )

        changed = move_entity_by_id(area, "hud", 1, 0)

        self.assertFalse(changed)
        self.assertEqual(area.entities[0].pixel_x, 10)
        self.assertEqual(area.entities[0].pixel_y, 12)

    def test_move_entity_pixels_updates_pixel_coordinates_from_none(self):
        area = _make_area()
        area.entities.append(EntityDocument(id="overlay", grid_x=0, grid_y=0))

        changed = move_entity_pixels(area, "overlay", 5, -3)

        self.assertTrue(changed)
        self.assertEqual(area.entities[0].pixel_x, 5)
        self.assertEqual(area.entities[0].pixel_y, -3)

    def test_move_entity_pixels_is_noop_for_missing_entity(self):
        area = _make_area()

        changed = move_entity_pixels(area, "missing", 1, 1)

        self.assertFalse(changed)

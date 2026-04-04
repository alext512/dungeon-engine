from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument
from area_editor.operations.areas import (
    add_columns_left,
    add_columns_right,
    add_rows_above,
    add_rows_below,
    can_remove_left_columns,
    can_remove_top_rows,
    make_empty_area_document,
    remove_left_columns,
    remove_top_rows,
)


class TestAreaOperations(unittest.TestCase):
    def test_make_empty_area_document_creates_expected_defaults(self):
        area = make_empty_area_document(
            name="Demo",
            width=4,
            height=3,
            tile_size=16,
            include_default_ground_layer=True,
        )

        self.assertEqual(area.name, "Demo")
        self.assertEqual(area.tile_size, 16)
        self.assertEqual(area.width, 4)
        self.assertEqual(area.height, 3)
        self.assertEqual(len(area.tile_layers), 1)
        self.assertEqual(area.tile_layers[0].name, "ground")

    def test_add_rows_above_shifts_world_entities_but_not_screen_entities(self):
        area = self._make_area_with_entities()

        changed = add_rows_above(area, 2, screen_entity_ids={"screen_logo"})

        self.assertTrue(changed)
        self.assertEqual(area.height, 5)
        world = next(entity for entity in area.entities if entity.id == "crate")
        screen = next(entity for entity in area.entities if entity.id == "screen_logo")
        self.assertEqual(world.grid_y, 3)
        self.assertEqual(screen.pixel_y, 12)

    def test_add_columns_left_shifts_world_entities_but_not_screen_entities(self):
        area = self._make_area_with_entities()

        changed = add_columns_left(area, 3, screen_entity_ids={"screen_logo"})

        self.assertTrue(changed)
        self.assertEqual(area.width, 6)
        world = next(entity for entity in area.entities if entity.id == "crate")
        screen = next(entity for entity in area.entities if entity.id == "screen_logo")
        self.assertEqual(world.grid_x, 4)
        self.assertEqual(screen.pixel_x, 24)

    def test_add_rows_below_and_columns_right_keep_entity_positions(self):
        area = self._make_area_with_entities()

        self.assertTrue(add_rows_below(area, 1))
        self.assertTrue(add_columns_right(area, 2))

        world = next(entity for entity in area.entities if entity.id == "crate")
        self.assertEqual((world.grid_x, world.grid_y), (1, 1))

    def test_remove_top_rows_blocks_when_world_entity_would_fall_out(self):
        area = self._make_area_with_entities()

        self.assertFalse(can_remove_top_rows(area, 2, screen_entity_ids={"screen_logo"}))
        self.assertFalse(remove_top_rows(area, 2, screen_entity_ids={"screen_logo"}))

    def test_remove_left_columns_blocks_when_world_entity_would_fall_out(self):
        area = self._make_area_with_entities()

        self.assertFalse(can_remove_left_columns(area, 2, screen_entity_ids={"screen_logo"}))
        self.assertFalse(remove_left_columns(area, 2, screen_entity_ids={"screen_logo"}))

    def test_remove_top_rows_shifts_remaining_world_entities(self):
        area = self._make_area_with_entities()
        area.entities[0].grid_y = 2

        self.assertTrue(can_remove_top_rows(area, 1, screen_entity_ids={"screen_logo"}))
        self.assertTrue(remove_top_rows(area, 1, screen_entity_ids={"screen_logo"}))

        world = next(entity for entity in area.entities if entity.id == "crate")
        self.assertEqual(world.grid_y, 1)
        self.assertEqual(area.height, 2)

    def _make_area_with_entities(self) -> AreaDocument:
        area = AreaDocument.from_dict(
            {
                "name": "Demo",
                "tile_size": 16,
                "tilesets": [],
                "tile_layers": [
                    {
                        "name": "ground",
                        "render_order": 0,
                        "y_sort": False,
                        "stack_order": 0,
                        "grid": [
                            [0, 0, 0],
                            [0, 0, 0],
                            [0, 0, 0],
                        ],
                    }
                ],
                "entities": [
                    {
                        "id": "crate",
                        "grid_x": 1,
                        "grid_y": 1,
                    },
                    {
                        "id": "screen_logo",
                        "space": "screen",
                        "pixel_x": 24,
                        "pixel_y": 12,
                    },
                ],
                "variables": {},
            }
        )
        return area

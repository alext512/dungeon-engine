"""Tests for cell-flag editing helpers."""

from __future__ import annotations

import unittest

from area_editor.documents.area_document import AreaDocument, TileLayerDocument
from area_editor.operations.cell_flags import cell_is_blocked, set_cell_blocked


def _make_area(*, cell_flags=None) -> AreaDocument:
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
        cell_flags=cell_flags or [],
        entry_points={},
        entities=[],
        camera={},
        input_targets={},
        variables={},
        enter_commands=[],
    )


class TestCellFlagOperations(unittest.TestCase):
    def test_missing_grid_defaults_to_unblocked(self):
        area = _make_area(cell_flags=[])
        self.assertFalse(cell_is_blocked(area, 0, 0))

    def test_setting_default_unblocked_cell_to_unblocked_is_noop(self):
        area = _make_area(cell_flags=[])
        changed = set_cell_blocked(area, 0, 0, False)
        self.assertFalse(changed)
        self.assertEqual(area.cell_flags, [])

    def test_setting_default_unblocked_cell_to_blocked_materializes_grid(self):
        area = _make_area(cell_flags=[])
        changed = set_cell_blocked(area, 1, 0, True)
        self.assertTrue(changed)
        self.assertTrue(cell_is_blocked(area, 1, 0))
        self.assertFalse(cell_is_blocked(area, 0, 0))

    def test_dict_cell_preserves_unknown_keys(self):
        area = _make_area(cell_flags=[[{"blocked": True, "tags": ["water"]}, {}]])
        changed = set_cell_blocked(area, 0, 0, False)
        self.assertTrue(changed)
        self.assertEqual(
            area.cell_flags[0][0],
            {"blocked": False, "tags": ["water"]},
        )

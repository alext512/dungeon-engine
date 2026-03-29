"""Widget tests for the editable tile canvas."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument, EntityDocument, TileLayerDocument
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.widgets.tile_canvas import TileCanvas


def _make_area() -> AreaDocument:
    return AreaDocument(
        name="test",
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
        cell_flags=[[True, False], [True, True]],
        entry_points={},
        entities=[],
        camera={},
        input_targets={},
        variables={},
        enter_commands=[],
    )


class TestTileCanvasCellFlagEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_apply_cell_flag_brush_updates_document_and_emits_signal(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_cell_flags_edit_mode(True)

        edits: list[tuple[int, int, bool]] = []
        canvas.cell_flag_edited.connect(
            lambda col, row, walkable: edits.append((col, row, walkable))
        )

        changed = canvas.apply_cell_flag_brush(1, 0, True)

        self.assertTrue(changed)
        self.assertTrue(area.cell_flags[0][1])
        self.assertEqual(edits, [(1, 0, True)])
        self.assertEqual(len(canvas._cell_flag_group.childItems()), 0)

    def test_unified_render_order_interleaves_y_sorted_layer_and_entities(self):
        area = AreaDocument(
            name="render-order",
            tile_size=16,
            tilesets=[],
            tile_layers=[
                TileLayerDocument(
                    name="ground",
                    render_order=0,
                    y_sort=False,
                    sort_y_offset=0.0,
                    stack_order=0,
                    grid=[[0]],
                ),
                TileLayerDocument(
                    name="front",
                    render_order=10,
                    y_sort=True,
                    sort_y_offset=0.0,
                    stack_order=0,
                    grid=[[1]],
                ),
            ],
            cell_flags=[[True]],
            entry_points={},
            entities=[
                EntityDocument(
                    id="player",
                    x=0,
                    y=0,
                    render_order=10,
                    y_sort=True,
                    sort_y_offset=0.0,
                    stack_order=1,
                )
            ],
            camera={},
            input_targets={},
            variables={},
            enter_commands=[],
        )

        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)

        self.assertEqual(len(canvas._layer_items[0]), 1)
        self.assertEqual(len(canvas._layer_items[0][0].childItems()), 0)
        self.assertEqual(len(canvas._layer_items[1]), 1)
        self.assertEqual(len(canvas._entity_items), 1)
        self.assertLess(canvas._layer_items[1][0].zValue(), canvas._entity_items[0].zValue())

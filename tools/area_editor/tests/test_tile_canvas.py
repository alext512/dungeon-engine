"""Widget tests for the editable tile canvas."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument, TileLayerDocument
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
                draw_above_entities=False,
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
